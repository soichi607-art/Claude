#!/usr/bin/env python3
"""note アカウントの公開プロフィールと記事一覧を、ログインせずに読み取って記録する。

目的: 「この note ID は誰のアカウントか」を、推測ではなく取得結果で確認すること。
      (例: 共有された `soa_komeyoshi` を SoA に使うか、史灯(B)に使うかの判断材料)

  python scripts/note_profile_check.py soa_komeyoshi
  python scripts/note_profile_check.py soa_komeyoshi tsukaeru_prompt --pages 2

安全のための制約:
- 読み取り(GET)のみ。Cookie・.env・トークンは一切読まない、送らない。
- リクエストの間隔は最低 3 秒あける。note を連打しない。
- 401 / 403 / 429 を受けたら、その場で全処理を止める(終了コード 2)。リトライしない。
  これは本体の緊急停止と同じ考え方。STOP ファイルには触れない(作りも消しもしない)。

取得結果は、取得日時(UTC)・取得元 URL と一緒に Markdown と JSON で保存する。
API の生レスポンスも保存するので、項目名が変わっても後から確認できる。
note の API は非公式で、項目名は変わる前提。見つからない項目は「取得できず」と書き、
推測で埋めない。

標準ライブラリのみで動作する。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "output_b", "account_checks")
DEFAULT_BASE = "https://note.com"
MIN_INTERVAL_SEC = 3.0
STOP_STATUSES = (401, 403, 429)
ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")
MISSING = "取得できず"

# 2026-09-11 時点の登録済みアカウント(出典: docs/note-autopilot-resume-2026-09-11.md §2)
KNOWN_IDS = {
    "ai_uresuji": "アカウントA",
    "tsukaeru_prompt": "アカウントB(史灯へ切り替え予定)",
    "soa_agri": "アカウントSoA(仮ID)",
}

# 非公式 API のため、項目名の候補を複数持つ
KEY_NAME = ("nickname", "name", "displayName")
KEY_URLNAME = ("urlname", "urlName")
KEY_PROFILE = ("profile", "description", "bio")
KEY_FOLLOWERS = ("followerCount", "follower_count", "followersCount")
KEY_NOTES = ("noteCount", "note_count")
KEY_TITLE = ("name", "title")
KEY_PUBLISHED = ("publishAt", "publish_at", "publishedAt", "createdAt")
KEY_NOTE_KEY = ("key",)


class StopRequested(Exception):
    """401/403/429 を受けた。これ以上 note にアクセスしてはいけない。"""

    def __init__(self, status, url):
        super().__init__(f"HTTP {status}: {url}")
        self.status = status
        self.url = url


class Fetcher:
    def __init__(self, base_url, interval=MIN_INTERVAL_SEC, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.interval = max(interval, MIN_INTERVAL_SEC) if base_url == DEFAULT_BASE else interval
        self.timeout = timeout
        self._last = 0.0

    def get_json(self, path):
        url = self.base_url + path
        wait = self._last + self.interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "note-autopilot-profile-check/1.0 (read-only)",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                body = res.read().decode("utf-8")
                return res.status, url, json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code in STOP_STATUSES:
                raise StopRequested(e.code, url)
            return e.code, url, None
        finally:
            self._last = time.monotonic()


def pick(obj, keys):
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj and obj[k] not in (None, ""):
            return obj[k]
    return None


def parse_creator(payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    return {
        "name": pick(data, KEY_NAME),
        "urlname": pick(data, KEY_URLNAME),
        "profile": pick(data, KEY_PROFILE),
        "followers": pick(data, KEY_FOLLOWERS),
        "note_count": pick(data, KEY_NOTES),
    }


def parse_contents(payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data.get("contents") if isinstance(data, dict) else None
    articles = []
    for it in items or []:
        articles.append({
            "title": pick(it, KEY_TITLE),
            "published_at": pick(it, KEY_PUBLISHED),
            "key": pick(it, KEY_NOTE_KEY),
        })
    is_last = data.get("isLastPage") if isinstance(data, dict) else None
    return articles, is_last


def check(fetcher, note_id, pages):
    result = {
        "note_id": note_id,
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "known_as": KNOWN_IDS.get(note_id),
        "sources": [],
        "raw": {},
    }
    status, url, payload = fetcher.get_json(f"/api/v2/creators/{note_id}")
    result["sources"].append({"url": url, "status": status})
    result["raw"]["creator"] = payload
    if status != 200 or payload is None:
        result["exists"] = False if status == 404 else None
        return result
    result["exists"] = True
    result["profile"] = parse_creator(payload)

    articles = []
    for page in range(1, pages + 1):
        status, url, payload = fetcher.get_json(
            f"/api/v2/creators/{note_id}/contents?kind=note&page={page}")
        result["sources"].append({"url": url, "status": status})
        result["raw"][f"contents_page{page}"] = payload
        if status != 200 or payload is None:
            break
        got, is_last = parse_contents(payload)
        articles.extend(got)
        if is_last is True or not got:
            break
    result["articles"] = articles
    return result


def show(value):
    if value is None:
        return MISSING
    return str(value).replace("\n", " ").replace("|", "\\|")


def to_markdown(results, stopped=None):
    lines = ["# note アカウント確認結果", ""]
    if stopped:
        lines += [f"**note から HTTP {stopped.status} を受けたため途中で全停止しました"
                  f"({stopped.url})。以降の ID は確認していません。**", ""]
    for r in results:
        lines += [f"## `{r['note_id']}`", ""]
        lines.append(f"- 取得日時(UTC): {r['fetched_at_utc']}")
        lines.append(f"- 登録済みアカウントとの対応: {r['known_as'] or '登録済みの ID ではない'}")
        for s in r["sources"]:
            lines.append(f"- 取得元: {s['url']}(HTTP {s['status']})")
        if r.get("exists") is False:
            lines += ["", "**この ID のアカウントは見つかりませんでした(HTTP 404)。**", ""]
            continue
        if not r.get("exists"):
            lines += ["", "**取得に失敗しました。内容は確認できていません。**", ""]
            continue
        p = r["profile"]
        lines += [
            "",
            "| 項目 | 取得結果 |",
            "|---|---|",
            f"| 表示名 | {show(p['name'])} |",
            f"| ID | {show(p['urlname'])} |",
            f"| 自己紹介 | {show(p['profile'])} |",
            f"| フォロワー数 | {show(p['followers'])} |",
            f"| 記事数(API の値) | {show(p['note_count'])} |",
            "",
            f"### 記事一覧(取得できた {len(r['articles'])} 件)",
            "",
        ]
        if r["articles"]:
            lines += ["| 公開日時 | タイトル |", "|---|---|"]
            for a in r["articles"]:
                lines.append(f"| {show(a['published_at'])} | {show(a['title'])} |")
        else:
            lines.append("記事は取得できませんでした(0 件、または取得失敗)。")
        lines.append("")
    lines.append("項目が「取得できず」の場合は推測で埋めず、同じフォルダの JSON の `raw` を確認してください。")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("note_ids", nargs="+", help="確認する note ID(例: soa_komeyoshi)")
    ap.add_argument("--pages", type=int, default=1, help="記事一覧を何ページ読むか(既定 1、最大 5)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="保存先フォルダ")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help=argparse.SUPPRESS)
    ap.add_argument("--interval", type=float, default=MIN_INTERVAL_SEC, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    for nid in args.note_ids:
        if not ID_PATTERN.match(nid):
            print(f"note ID の形式が不正です: {nid!r}", file=sys.stderr)
            return 1
    pages = min(max(args.pages, 1), 5)

    fetcher = Fetcher(args.base_url, interval=args.interval)
    results, code, stopped = [], 0, None
    try:
        for nid in args.note_ids:
            results.append(check(fetcher, nid, pages))
    except StopRequested as e:
        stopped = e
        print(f"note から HTTP {e.status} を受けたため、全処理を停止しました: {e.url}", file=sys.stderr)
        print("リトライはしません。時間をおいてから手動で再実行してください。", file=sys.stderr)
        code = 2
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"note に接続できませんでした: {e}", file=sys.stderr)
        code = 3

    if results:
        os.makedirs(args.out, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = os.path.join(args.out, f"note-account-check-{stamp}")
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump({"stopped": {"status": stopped.status, "url": stopped.url} if stopped else None,
                       "results": results}, f, ensure_ascii=False, indent=2)
        md = to_markdown(results, stopped)
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write(md)
        print(md)
        print(f"保存しました: {base}.md / .json")
    return code


if __name__ == "__main__":
    sys.exit(main())
