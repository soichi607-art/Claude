#!/usr/bin/env python3
"""史灯(アカウントB)連載小説の進行状態を管理し、プロンプトを毎回生成する。

note-autopilot 本体は「1回の実行で1記事」を前提にしており、連載の話数や
前話との整合を保持する仕組みを持たない。このスクリプトがその不足分を埋める。

  sync     … series/shitou_series.json と data_b/series_state.json から
             prompts_b/{theme_select,article_gen,quality_gate,x_promo}.txt を生成する。
             generate の前に必ず実行する。
  advance  … 1話ぶん進める。publish が成功したときだけ実行する。
  status   … 現在の状態を表示する。
  set N    … 話数を手動で N に合わせる(やり直し・巻き戻し用)。
  mark-prepared … 現在の話の記事生成が完了したことを記録する。
  is-prepared   … 現在の話の記事が生成済みなら終了コード0、未生成なら1を返す。
                  (生成と公開を別の時刻に分けても二重生成しないようにするため)

終了コード:
  0  … 正常
  20 … 全話完了(これ以上書く話がない)。呼び出し側は以降の処理を止めること
  1  … 設定ファイルの不備など

標準ライブラリのみで動作する(PyYAML 等に依存しない)。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES_PATH = os.path.join(ROOT, "series", "shitou_series.json")
STATE_PATH = os.path.join(ROOT, "data_b", "series_state.json")
INSIGHTS_PATH = os.path.join(ROOT, "data_b", "series_insights.json")
TPL_DIR = os.path.join(ROOT, "prompts_b", "_templates")
OUT_DIR = os.path.join(ROOT, "prompts_b")
DRAFTS_DIR = os.path.join(ROOT, "output_b", "drafts")

TEMPLATES = {
    "theme_select.tmpl": "theme_select.txt",
    "article_gen.tmpl": "article_gen.txt",
    "quality_gate.tmpl": "quality_gate.txt",
    "x_promo.tmpl": "x_promo.txt",
}


def load_series():
    with open(SERIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state(series):
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"series_title": series["series_title"], "next_episode": 1, "published": []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def find_episode(series, ep):
    for e in series["episodes"]:
        if e["ep"] == ep:
            return e
    return None


def render_foreshadow(series, ids):
    if not ids:
        return "なし"
    table = {f["id"]: f for f in series["foreshadowing"]}
    lines = []
    for i in ids:
        f = table.get(i)
        if f:
            lines.append("  - {0}: {1}(仕込み第{2}話 / 回収第{3}話)".format(
                f["id"], f["item"], f["plant_ep"], f["payoff_ep"]))
        else:
            lines.append("  - {0}: (作品設定に定義なし)".format(i))
    return "\n".join(lines)


def render_episode_spec(series, ep):
    e = find_episode(series, ep)
    if e is None:
        return None
    return "\n".join([
        "第{0}話".format(e["ep"]),
        "- タイトルの方向: {0}".format(e["title_hint"]),
        "- 副題の方向: {0}".format(e["subtitle_hint"]),
        "- 舞台: {0}".format(e["stage"]),
        "- 新事実: {0}".format(e["new_fact"]),
        "- 対立: {0}".format(e["conflict"]),
        "- 選択: {0}".format(e["choice"]),
        "- 次話への引き: {0}".format(e["hook"]),
        "- この話で仕込む伏線:",
        render_foreshadow(series, e["plant"]),
        "- この話で回収する伏線:",
        render_foreshadow(series, e["payoff"]),
    ])


def render_prev_summaries(series, state):
    published = state.get("published", [])
    if not published:
        return "まだ1話も公開していない。第1話として、読者が前提知識なしで読み始められるように書くこと。"
    lines = []
    for rec in published:
        e = find_episode(series, rec["ep"])
        outline = ""
        if e:
            outline = "新事実={0} / 選択={1} / 引き={2}".format(
                e["new_fact"], e["choice"], e["hook"])
        lines.append("- 第{0}話「{1}」: {2}".format(
            rec["ep"], rec.get("title") or (e["title_hint"] if e else ""), outline))
        head = rec.get("head")
        if head:
            lines.append("  (本文冒頭) {0}".format(head))
    return "\n".join(lines)


def render_improvement():
    """shitou_analyze.py が書いた改善指示を読む。無ければ空扱いにする。"""
    if not os.path.exists(INSIGHTS_PATH):
        return ("まだ分析データがない(scripts/shitou_analyze.py が未実行、または公開実績なし)。"
                "作品設定どおりに書くこと。")
    try:
        with open(INSIGHTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return "分析データを読めなかった。作品設定どおりに書くこと。"

    lines = []
    directives = data.get("directives") or []
    if directives:
        lines.append("(分析日時: {0})".format(data.get("generated_at", "不明")))
        lines += ["- {0}".format(d) for d in directives]
    metrics = data.get("metrics") or []
    if metrics:
        lines.append("")
        lines.append("公開済みの実測値:")
        for m in metrics:
            lines.append("- 第{0}話: PV {1:.0f} / スキ {2:.0f} / スキ率 {3}%".format(
                m["ep"], m["pv"], m["likes"], m["like_rate"]))
    if not lines:
        return "分析の結果、特筆すべき改善点はない。作品設定どおりに書くこと。"
    return "\n".join(lines)


def render_bible(series):
    s = series["setting"]
    lines = [
        "作品タイトル: {0}(全{1}話)".format(series["series_title"], series["total_episodes"]),
        "ログライン: {0}".format(series["logline"]),
        "テーマ: {0}".format(series["theme"]),
        "想定読者: {0}".format(series["target_reader"]),
        "",
        "【舞台設定】",
        "- 会社: {0}".format(s["company"]),
        "- 製品: {0}".format(s["product"]),
        "- 場所: {0}".format(s["place"]),
        "- 事故: {0}".format(s["incident"]),
        "- 年代の書き方: {0}".format(s["era"]),
        "",
        "【登場人物】",
    ]
    for c in series["characters"]:
        lines.append("- {0} / {1}歳 / {2}".format(c["name"], c["age"], c["role"]))
        lines.append("  {0}".format(c["detail"]))
    lines += ["", "【伏線一覧】"]
    for f in series["foreshadowing"]:
        lines.append("- {0}: {1}(仕込み第{2}話 → 回収第{3}話)".format(
            f["id"], f["item"], f["plant_ep"], f["payoff_ep"]))
    ff = series["fact_and_fiction"]
    lines += ["", "【史実と創作の区別】", "着想源(史実):"]
    lines += ["- {0}".format(x) for x in ff["inspiration"]]
    lines += ["創作(すべて架空):"]
    lines += ["- {0}".format(x) for x in ff["fiction"]]
    lines += ["禁止事項:"]
    lines += ["- {0}".format(x) for x in ff["prohibitions"]]
    lines += ["", "【文体】"]
    lines += ["- {0}".format(x) for x in series["style"]]
    return "\n".join(lines)


def cmd_sync():
    series = load_series()
    state = load_state(series)
    ep = state["next_episode"]

    if ep > series["total_episodes"]:
        sys.stderr.write(
            "[shitou] 全{0}話を公開済みです。次の連載を始めるには "
            "series/shitou_series.json を差し替え、`shitou_state.py set 1` を実行してください。\n"
            .format(series["total_episodes"]))
        return 20

    spec = render_episode_spec(series, ep)
    if spec is None:
        sys.stderr.write("[shitou] 第{0}話が series/shitou_series.json に定義されていません。\n".format(ep))
        return 1

    values = {
        "@@SERIES_TITLE@@": series["series_title"],
        "@@TOTAL_EP@@": str(series["total_episodes"]),
        "@@NEXT_EP@@": str(ep),
        "@@EPISODE_SPEC@@": spec,
        "@@PREV_SUMMARIES@@": render_prev_summaries(series, state),
        "@@SERIES_BIBLE@@": render_bible(series),
        "@@IMPROVEMENT@@": render_improvement(),
    }

    for tpl, out in TEMPLATES.items():
        with open(os.path.join(TPL_DIR, tpl), encoding="utf-8") as f:
            text = f.read()
        for k, v in values.items():
            text = text.replace(k, v)
        header = ("# 自動生成ファイル — 直接編集しないこと。\n"
                  "# 生成元: prompts_b/_templates/{0}\n"
                  "# 生成コマンド: python scripts/shitou_state.py sync\n"
                  "# 対象: 第{1}話\n").format(tpl, ep)
        with open(os.path.join(OUT_DIR, out), "w", encoding="utf-8") as f:
            f.write(header + text)

    print("[shitou] 第{0}話用にプロンプト4件を生成しました。".format(ep))
    return 0


def newest_draft_head(limit=160):
    """直近の下書きの冒頭を取り出す。形式が不明でも落ちないように防御的に実装する。"""
    try:
        if not os.path.isdir(DRAFTS_DIR):
            return None
        paths = []
        for dirpath, _dirnames, filenames in os.walk(DRAFTS_DIR):
            for name in filenames:
                p = os.path.join(dirpath, name)
                try:
                    paths.append((os.path.getmtime(p), p))
                except OSError:
                    continue
        if not paths:
            return None
        paths.sort()
        newest = paths[-1][1]
        with open(newest, encoding="utf-8", errors="replace") as f:
            text = f.read(4000)
        import re
        text = re.sub(r"<[^>]+>", "", text)
        text = " ".join(text.split())
        return text[:limit] if text else None
    except Exception:
        return None


def cmd_advance():
    series = load_series()
    state = load_state(series)
    ep = state["next_episode"]

    if ep > series["total_episodes"]:
        sys.stderr.write("[shitou] 既に全話完了しています。進めません。\n")
        return 20

    e = find_episode(series, ep)
    state.setdefault("published", []).append({
        "ep": ep,
        "title": e["title_hint"] if e else "",
        "head": newest_draft_head(),
    })
    state["next_episode"] = ep + 1
    state.pop("prepared_ep", None)
    save_state(state)
    print("[shitou] 第{0}話を公開済みとして記録し、次を第{1}話にしました。".format(ep, ep + 1))
    if state["next_episode"] > series["total_episodes"]:
        print("[shitou] これで全{0}話が完了です。".format(series["total_episodes"]))
    return 0


def cmd_status():
    series = load_series()
    state = load_state(series)
    print("作品: {0}(全{1}話)".format(series["series_title"], series["total_episodes"]))
    print("次に書く話: 第{0}話".format(state["next_episode"]))
    print("公開済み: {0}話".format(len(state.get("published", []))))
    for rec in state.get("published", []):
        print("  - 第{0}話 {1}".format(rec["ep"], rec.get("title", "")))
    return 0


def cmd_set(arg):
    series = load_series()
    state = load_state(series)
    try:
        n = int(arg)
    except (TypeError, ValueError):
        sys.stderr.write("[shitou] set には整数を渡してください。\n")
        return 1
    if n < 1:
        sys.stderr.write("[shitou] 話数は1以上にしてください。\n")
        return 1
    state["next_episode"] = n
    state.pop("prepared_ep", None)
    state["published"] = [r for r in state.get("published", []) if r["ep"] < n]
    save_state(state)
    print("[shitou] 次に書く話を第{0}話にしました。".format(n))
    return 0


def cmd_mark_prepared():
    series = load_series()
    state = load_state(series)
    state["prepared_ep"] = state["next_episode"]
    save_state(state)
    print("[shitou] 第{0}話の記事を生成済みとして記録しました。".format(state["next_episode"]))
    return 0


def cmd_is_prepared():
    series = load_series()
    state = load_state(series)
    if state.get("prepared_ep") == state["next_episode"]:
        print("[shitou] 第{0}話は生成済みです。".format(state["next_episode"]))
        return 0
    print("[shitou] 第{0}話はまだ生成されていません。".format(state["next_episode"]))
    return 1


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "sync":
        return cmd_sync()
    if cmd == "advance":
        return cmd_advance()
    if cmd == "status":
        return cmd_status()
    if cmd == "set":
        return cmd_set(argv[2] if len(argv) > 2 else None)
    if cmd == "mark-prepared":
        return cmd_mark_prepared()
    if cmd == "is-prepared":
        return cmd_is_prepared()
    sys.stderr.write("[shitou] 不明なコマンド: {0}\n".format(cmd))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
