#!/usr/bin/env python3
"""史灯(アカウントB)連載小説の成果を分析し、次話への改善指示を生成する。

note-autopilot の `feedback` は PV・スキを取得して DB に記録するが、
「連載小説として次に何を直すか」までは出さない。このスクリプトがそれを担当する。

  analyze  … data_b/note_autopilot.db を読み、話ごとの指標と改善指示を
             data_b/series_insights.json と output_b/reports/ に書き出す。
  schema   … DB のテーブルとカラムを表示する(列名が違って分析できないときの調査用)。

改善指示は LLM を使わず、決定的なルールで生成する。
理由: 追加費用がかからず、同じ数字からは必ず同じ指示が出る(再現性がある)ため。

DB のカラム名は実装によって異なるため、名前の候補から自動で探す。
見つからない場合は落ちずに、何が見つからなかったかを報告する。

標準ライブラリのみで動作する。
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data_b", "note_autopilot.db")
SERIES_PATH = os.path.join(ROOT, "series", "shitou_series.json")
INSIGHTS_PATH = os.path.join(ROOT, "data_b", "series_insights.json")
REPORT_DIR = os.path.join(ROOT, "output_b", "reports")

# 実装ごとの表記ゆれを吸収するためのカラム名候補(小文字で比較する)
COL_PV = ("pv", "views", "view_count", "page_views", "pv_count", "read_count")
COL_LIKES = ("likes", "like_count", "suki", "sukis", "like", "liked_count")
COL_TITLE = ("title", "article_title", "name", "headline")
COL_DATE = ("published_at", "posted_at", "publish_date", "created_at", "updated_at")
COL_COMMENTS = ("comments", "comment_count")

KANJI = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
         "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def pick(columns, candidates):
    """候補名のうち、実在するカラム名を返す(大文字小文字を無視)。"""
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    # 部分一致も許す(例: total_pv)
    for cand in candidates:
        for lc, orig in lower.items():
            if cand in lc:
                return orig
    return None


def table_columns(con):
    out = {}
    for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        cols = [r[1] for r in con.execute("PRAGMA table_info('{0}')".format(name))]
        out[name] = cols
    return out


def episode_from_title(title):
    """タイトルから話数を取り出す。第1話 / 第１話 / 第一話 に対応する。"""
    if not title:
        return None
    t = str(title)
    m = re.search(r"第\s*([0-9０-９]+)\s*話", t)
    if m:
        digits = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        return int(digits)
    m = re.search(r"第\s*([一二三四五六七八九十]+)\s*話", t)
    if m:
        s = m.group(1)
        if s == "十":
            return 10
        if s.startswith("十"):
            return 10 + KANJI.get(s[1:], 0)
        if s.endswith("十"):
            return KANJI.get(s[0], 0) * 10
        if len(s) == 1:
            return KANJI.get(s)
    return None


def find_source(con):
    """タイトルとPVを同時に取れる表を探す。無ければ2つの表の結合を試みる。"""
    tables = table_columns(con)
    if not tables:
        return None, "DB にテーブルがありません。"

    # 1) 単一テーブルで完結する場合
    for name, cols in tables.items():
        t, p = pick(cols, COL_TITLE), pick(cols, COL_PV)
        if t and p:
            return {
                "kind": "single", "table": name, "title": t, "pv": p,
                "likes": pick(cols, COL_LIKES), "date": pick(cols, COL_DATE),
                "comments": pick(cols, COL_COMMENTS),
            }, None

    # 2) 記事テーブルと統計テーブルを共通カラムで結合する場合
    art = [(n, c) for n, c in tables.items() if pick(c, COL_TITLE)]
    sta = [(n, c) for n, c in tables.items() if pick(c, COL_PV)]
    for an, ac in art:
        for sn, sc in sta:
            if an == sn:
                continue
            shared = [c for c in ac if c in sc and c.lower() not in ("id",)]
            shared += [c for c in ac if c in sc and c.lower() == "id" and not shared]
            if shared:
                return {
                    "kind": "join", "table": an, "stats_table": sn, "on": shared[0],
                    "title": pick(ac, COL_TITLE), "pv": pick(sc, COL_PV),
                    "likes": pick(sc, COL_LIKES) or pick(ac, COL_LIKES),
                    "date": pick(ac, COL_DATE) or pick(sc, COL_DATE),
                    "comments": pick(sc, COL_COMMENTS) or pick(ac, COL_COMMENTS),
                }, None

    detail = "; ".join("{0}({1})".format(n, ",".join(c)) for n, c in tables.items())
    return None, ("タイトル列とPV列を同時に特定できませんでした。検出したテーブル: " + detail)


def fetch_rows(con, src):
    def q(col, alias, table=None):
        if not col:
            return "NULL AS {0}".format(alias)
        prefix = (table + ".") if table else ""
        return '{0}"{1}" AS {2}'.format(prefix, col, alias)

    if src["kind"] == "single":
        sql = 'SELECT {0}, {1}, {2}, {3}, {4} FROM "{5}"'.format(
            q(src["title"], "title"), q(src["pv"], "pv"), q(src["likes"], "likes"),
            q(src["date"], "dt"), q(src["comments"], "comments"), src["table"])
    else:
        a, s, on = src["table"], src["stats_table"], src["on"]
        sql = ('SELECT {0}, {1}, {2}, {3}, {4} FROM "{5}" a '
               'JOIN "{6}" s ON a."{7}" = s."{7}"').format(
            q(src["title"], "title", "a"), q(src["pv"], "pv", "s"),
            q(src["likes"], "likes", "s"), q(src["date"], "dt", "a"),
            q(src["comments"], "comments", "s"), a, s, on)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql)]


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build_metrics(rows):
    """話数ごとに集計する。同じ話が複数行ある場合は最大値を採る(計測の累積を想定)。"""
    per = {}
    for r in rows:
        ep = episode_from_title(r.get("title"))
        if ep is None:
            continue
        cur = per.setdefault(ep, {"ep": ep, "title": r.get("title"), "pv": 0.0,
                                  "likes": 0.0, "comments": 0.0, "dt": r.get("dt")})
        cur["pv"] = max(cur["pv"], to_num(r.get("pv")))
        cur["likes"] = max(cur["likes"], to_num(r.get("likes")))
        cur["comments"] = max(cur["comments"], to_num(r.get("comments")))
    out = []
    for ep in sorted(per):
        m = per[ep]
        m["like_rate"] = round(m["likes"] / m["pv"] * 100, 2) if m["pv"] else 0.0
        out.append(m)
    first_pv = out[0]["pv"] if out and out[0]["pv"] else 0.0
    prev_pv = None
    for m in out:
        m["retention_vs_ep1"] = round(m["pv"] / first_pv * 100, 1) if first_pv else None
        m["pv_change_vs_prev"] = (round((m["pv"] - prev_pv) / prev_pv * 100, 1)
                                  if prev_pv else None)
        prev_pv = m["pv"] if m["pv"] else prev_pv
    return out


def median(values):
    vs = sorted(values)
    if not vs:
        return 0.0
    n = len(vs)
    return vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2


def build_directives(metrics):
    """数字から、次話の執筆に渡す改善指示を組み立てる。"""
    if not metrics:
        return ["まだ計測データがない。第1話は作品設定どおりに書き、"
                "冒頭3文で異変を提示することだけを最優先にする。"]
    if len(metrics) == 1:
        m = metrics[0]
        return ["計測対象がまだ1話のみ(第{0}話 PV{1:.0f} / スキ{2:.0f} / スキ率{3}%)。"
                "傾向の判断はできないため、作品設定どおりに書く。".format(
                    m["ep"], m["pv"], m["likes"], m["like_rate"])]

    d = []
    latest = metrics[-1]
    rates = [m["like_rate"] for m in metrics if m["pv"]]
    med_rate = median(rates)

    chg = latest.get("pv_change_vs_prev")
    if chg is not None:
        if chg <= -20:
            d.append("直近の第{0}話は前話比 PV {1}% と落ちている。"
                     "次話は【タイトル】を最優先で直す。何が起きるのかが具体的に分かる語を入れ、"
                     "抽象語(真実・決断・運命など)を使わない。".format(latest["ep"], chg))
        elif chg >= 20:
            d.append("直近の第{0}話は前話比 PV +{1}% と伸びている。"
                     "この話のタイトルの作り方(具体物＋動きのある述語)を次話でも踏襲する。"
                     .format(latest["ep"], chg))

    if latest["pv"] and latest["like_rate"] < med_rate:
        d.append("第{0}話のスキ率 {1}% は連載の中央値 {2}% を下回る。"
                 "読まれてはいるが刺さっていない。次話は本文中盤の情景描写(光・音・匂い・気温)を"
                 "1場面ぶん厚くし、会話で状況を説明する量を減らす。".format(
                     latest["ep"], latest["like_rate"], round(med_rate, 2)))
    elif latest["pv"] and latest["like_rate"] > med_rate:
        d.append("第{0}話のスキ率 {1}% は中央値 {2}% を上回る。"
                 "この話の描写の密度と場面転換の速さを次話でも保つ。".format(
                     latest["ep"], latest["like_rate"], round(med_rate, 2)))

    ret = latest.get("retention_vs_ep1")
    if ret is not None and ret < 60:
        d.append("第1話に対する第{0}話の PV は {1}% まで落ちている。"
                 "連載の途中離脱が起きている。次話は冒頭に、前話を読んでいない人でも"
                 "状況が分かる1〜2文を自然に入れ(あらすじの羅列にしない)、"
                 "導入文には必ず『この話だけでも読める』手がかりを書く。".format(latest["ep"], ret))

    best = max(metrics, key=lambda m: m["pv"])
    if best["ep"] != latest["ep"]:
        d.append("これまでで最も読まれたのは第{0}話「{1}」(PV {2:.0f})。"
                 "この話のタイトルの語彙と、扱った対立の種類を次話の参考にする。".format(
                     best["ep"], best["title"], best["pv"]))

    if not d:
        d.append("指標に大きな変化がない。作品設定どおりに書き、"
                 "各話の『新事実・対立・選択・引き』を確実に入れることを優先する。")
    return d


def cmd_schema():
    if not os.path.exists(DB_PATH):
        print("DB が見つかりません: {0}".format(DB_PATH))
        return 1
    con = sqlite3.connect(DB_PATH)
    try:
        for name, cols in sorted(table_columns(con).items()):
            print("{0}: {1}".format(name, ", ".join(cols)))
    finally:
        con.close()
    return 0


def write_insights(payload):
    os.makedirs(os.path.dirname(INSIGHTS_PATH), exist_ok=True)
    with open(INSIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_report(payload):
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = os.path.join(REPORT_DIR, "analysis_{0}.md".format(stamp))
    lines = ["# 史灯 連載分析レポート", "",
             "生成: {0}".format(payload["generated_at"]), ""]
    if payload["metrics"]:
        lines += ["| 話 | タイトル | PV | スキ | スキ率 | 前話比PV | 第1話比PV |",
                  "|---|---|---|---|---|---|---|"]
        for m in payload["metrics"]:
            lines.append("| 第{0}話 | {1} | {2:.0f} | {3:.0f} | {4}% | {5} | {6} |".format(
                m["ep"], m["title"], m["pv"], m["likes"], m["like_rate"],
                "—" if m["pv_change_vs_prev"] is None else "{0}%".format(m["pv_change_vs_prev"]),
                "—" if m["retention_vs_ep1"] is None else "{0}%".format(m["retention_vs_ep1"])))
    else:
        lines.append("計測できた話がありません。")
    lines += ["", "## 次話への改善指示", ""]
    lines += ["- {0}".format(x) for x in payload["directives"]]
    if payload.get("warnings"):
        lines += ["", "## 注意", ""] + ["- {0}".format(w) for w in payload["warnings"]]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def cmd_analyze():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    warnings = []

    if not os.path.exists(DB_PATH):
        payload = {"generated_at": now, "metrics": [],
                   "directives": build_directives([]),
                   "warnings": ["DB が見つかりません: {0}。まだ1話も公開していない場合は正常です。"
                                .format(DB_PATH)]}
        write_insights(payload)
        print(write_report(payload))
        return 0

    con = sqlite3.connect(DB_PATH)
    try:
        src, err = find_source(con)
        if src is None:
            payload = {"generated_at": now, "metrics": [],
                       "directives": build_directives([]),
                       "warnings": [err,
                                    "`python scripts/shitou_analyze.py schema` の出力を共有すれば"
                                    "カラム対応を修正できます。"]}
            write_insights(payload)
            print(write_report(payload))
            sys.stderr.write("[shitou-analyze] {0}\n".format(err))
            return 0
        rows = fetch_rows(con, src)
    except sqlite3.Error as e:
        payload = {"generated_at": now, "metrics": [],
                   "directives": build_directives([]),
                   "warnings": ["DB 読み取りに失敗: {0}".format(e)]}
        write_insights(payload)
        print(write_report(payload))
        sys.stderr.write("[shitou-analyze] DB 読み取りに失敗: {0}\n".format(e))
        return 0
    finally:
        con.close()

    metrics = build_metrics(rows)
    if not metrics:
        warnings.append("タイトルから話数(第N話)を取り出せた記事がありません。"
                        "タイトルの付け方が変わっていないか確認してください。")
    if all(m["pv"] == 0 for m in metrics) and metrics:
        warnings.append("PV がすべて0です。feedback がまだ実行されていない可能性があります。")

    payload = {"generated_at": now, "source": src, "metrics": metrics,
               "directives": build_directives(metrics), "warnings": warnings}
    write_insights(payload)
    report = write_report(payload)
    print("[shitou-analyze] {0}話ぶんを分析しました。".format(len(metrics)))
    print("  改善指示: {0}".format(INSIGHTS_PATH))
    print("  レポート: {0}".format(report))
    for d in payload["directives"]:
        print("  - {0}".format(d))
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "analyze"
    if cmd == "analyze":
        return cmd_analyze()
    if cmd == "schema":
        return cmd_schema()
    sys.stderr.write(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
