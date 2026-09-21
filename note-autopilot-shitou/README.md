# 史灯(アカウントB)自動運用一式

note アカウントB を「AIが試したプロンプト置き場」から **「史灯」= 企業・社会派の連載小説**
へ切り替え、既存の note-autopilot でそのまま自動運用するためのファイル一式です。

**作品: 『耐火二時間』全10話**(題材: 検査データ改ざんと、内部告発者への長期報復人事)

---

## 1. これは何を解決しているか

note-autopilot は「トレンドを収集 → テーマを選定 → 1記事を生成 → 公開」という
**1回1記事・話数の概念なし**の設計です。連載小説をそのまま流すと次の3点で必ず止まります。

| 止まる箇所 | 原因 | この一式での対処 |
|---|---|---|
| テーマ選定 | 毎話 keyword が同じになり `avoid_recent_keywords: 5` で弾かれる | `config.b.yaml` で `0` に変更 |
| 品質ゲート(機械) | `min_headings: 3` / `max_similarity: 0.5` を連載小説は満たせない | `0` / `0.92` に変更、`min_chars` は 2800 へ引き上げ |
| 品質ゲート(LLM) | 「事実性」「実用価値」で採点され、創作は不合格になる | 4軸の**キー名は変えず**、各軸の評価内容を小説用に再定義 |

加えて次の2つを追加しています。

- **話数と前話との整合の保持**(本体に無い) → `scripts/shitou_state.py`
- **連載としての分析と、次話への改善指示**(本体の feedback は数値記録まで) → `scripts/shitou_analyze.py`

---

## 2. 公開を失敗させないための設計

**先に正直に書きます。「必ず公開」は保証できません。**
note の Cookie 失効(401 / `not_login`)や 429 を検知したときの全停止は、
アカウント凍結を避けるための安全装置です(`core/guardian.py`。解除APIは無く手動削除のみ)。
これを外すのは危険なので外していません。

また、**note の予約投稿は使わない方針**です(月額500円の note プレミアムが必要なため)。
予約投稿を使えば公開日に PC も Cookie も不要になりますが、その選択はしていません。

外さずに、**失敗率を下げ、失敗しても取り返す**構成にしています。

| 対策 | 何を防ぐか |
|---|---|
| **毎日 08:00 の疎通確認** | Cookie 失効を投稿日の前に見つける。週1回では失効したまま投稿日を迎える |
| **公開の「前日」09:00 に記事を生成** | 生成の失敗と公開の失敗を切り離す。**丸一日以上の猶予**ができる |
| **Gemini 無料枠切れ時の自動フォールバック** | 枠切れ(終了コード4)のとき `config.b.fallback.yaml`(Anthropic API)で1回だけやり直す |
| **各ステップの自動リトライ** | 一時的な失敗。待機は 60秒 → 180秒 → 420秒と伸ばし、note を連打しない |
| **17:00 の公開前に再度の疎通確認** | Cookie が死んでいるのに投稿を試みて 401 で全停止するのを防ぐ |
| **19:30 と 21:30 の再試行** | 17:00 に失敗しても、その日のうちに公開する |
| **失敗しても話数を進めない** | 次の投稿日にも同じ話が再試行される。話が飛ばない |
| **タスクの `StartWhenAvailable`** | PC が落ちていて実行できなかったタスクを、起動後に取り返す |
| **タスクの `WakeToRun`** | スリープ中の PC を起こして実行する(電源接続と BIOS 設定が前提) |
| **失敗時は必ず通知** | `NOTIFY_WEBHOOK_URL` へ送信。加えて**デスクトップに警告ファイルを置く** |

**リトライしないもの**: 終了コード2(緊急停止)。これはリトライしてはいけない失敗です。

### Gemini 無料枠切れのフォールバックについて

`.env` に `ANTHROPIC_API_KEY` **がある場合だけ**動きます。無ければフォールバックせず、
その日の生成をあきらめます(勝手に従量課金を発生させないため)。
使われた場合は「課金が発生しています」と通知されます。不要なら
`config.b.fallback.yaml` を削除してください。

### デスクトップの警告ファイル

`NOTIFY_WEBHOOK_URL` を設定していないと、失敗に気づく手段がログしかありません。
Cookie 失効は**人が直さないと絶対に復旧しない**ため、
デスクトップに `【note・史灯】要対応.txt` を作って対処手順を書き込みます。
翌朝の疎通確認が通れば自動で消えます。

### それでも残る穴(予約投稿を使わない以上、消せません)

| 残るリスク | なぜ消せないか | できること |
|---|---|---|
| **Cookie 失効** | ブラウザでのログインが必要。ID/パスワードでの自動ログインは2段階認証で止まり、規約上もグレー | 08:00 の通知とデスクトップ警告で**同じ日のうちに気づく** |
| **PC が起動していない** | 実行環境が PC のため | `StartWhenAvailable` と `WakeToRun` で軽減。持ち出し中は不可 |
| **note の仕様変更** | 非公式APIを使っているため | 毎日の疎通確認で早く気づく |

この3つを消す唯一の方法は、**全話を先に作って note の予約投稿に載せる**ことです
(note プレミアム 月額500円が必要)。採用しない方針のため、実装していません。

## 3. 分析と改善

`scripts/shitou_analyze.py` が、公開済みの話の実測値から**次話への改善指示**を作ります。
**LLM を使わず決定的なルールで判定**します(追加費用なし・同じ数字からは必ず同じ指示)。

見ている指標:

| 指標 | 意味 |
|---|---|
| PV / スキ / スキ率 | 話ごとの実測値 |
| 前話比 PV | タイトルと引きが効いたか |
| 第1話比 PV | 連載の離脱率。ここが落ちると読者が付いてきていない |

出す改善指示の例:

- 前話比 PV が -20% 以下 → 「次話はタイトルを最優先で直す。抽象語を使わない」
- スキ率が連載の中央値未満 → 「本文中盤の情景描写を1場面ぶん厚くする」
- 第1話比 PV が 60% 未満 → 「冒頭に、前話未読でも状況が分かる1〜2文を入れる」
- 最も読まれた話を特定 → 「その話のタイトルの語彙と対立の種類を参考にする」

この指示は2箇所に流れます。

1. `prompts_b/article_gen.txt` の「改善指示」欄 → **次話の執筆時に最優先で反映される**
2. `prompts_b/quality_gate.txt` → **指示が反映されていない原稿は value を減点される**

出力先:

- `data_b/series_insights.json` — プロンプトへ差し込む元データ
- `output_b/reports/analysis_YYYYMMDD.md` — 人が読むレポート(表付き)

DB のカラム名は実装によって異なるため、名前の候補から自動で探します。
**特定できない場合も落ちず**、何が見つからなかったかを報告します。その場合は:

```powershell
uv run python scripts\shitou_analyze.py schema
```

の出力を共有してください。カラム対応を修正します。

---

## 4. ファイル一覧と配置先

`C:\Users\User\Documents\note-autopilot\` 直下に、同じ構造のままコピーします。

| ファイル | 種別 |
|---|---|
| `config.b.yaml` | **既存を上書き**(先に退避すること) |
| `config.b.fallback.yaml` | 新規。Gemini 無料枠切れ時のみ使う(`llm.backend: api`) |
| `prompts_b/_templates/*.tmpl` | 新規。**編集するのはこちら** |
| `prompts_b/*.txt` | 新規。`sync` が自動生成するため直接編集しない |
| `series/shitou_series.json` | 新規。作品設定(人物・全話プロット・伏線・史実と創作の区別) |
| `scripts/shitou_state.py` | 新規。話数管理とプロンプト生成 |
| `scripts/shitou_analyze.py` | 新規。分析と改善指示の生成 |
| `scripts/_shitou-lib.ps1` | 新規。共通関数(リトライ・通知・ログ) |
| `scripts/healthcheck-b.ps1` | 新規。毎日 08:00 |
| `scripts/prepare-b.ps1` | 新規。火木土 09:00 |
| `scripts/daily-b.ps1` | 新規。火木土 17:00 |
| `scripts/catchup-b.ps1` | 新規。火木土 19:30 / 21:30 |
| `scripts/analyze-b.ps1` | 新規。毎週月曜 07:00 |
| `scripts/register-task-b.ps1` | 新規。上記6タスクの登録 |
| `data_b/series_state.json` | 新規。進行状態(第1話から開始の初期値) |

> **重要**: 変更前に `config.b.yaml` を `config.b.yaml.bak` として必ず退避してください。
> 旧「プロンプト置き場」設定に戻す必要が出た場合の唯一の復旧手段です。

---

## 5. 導入手順

```powershell
cd C:\Users\User\Documents\note-autopilot

# 0) 退避
Copy-Item config.b.yaml config.b.yaml.bak

# 1) このディレクトリの中身を上記の配置先へコピー

# 2) 動作確認(実通信なし)
uv run python scripts\shitou_state.py status
uv run python scripts\shitou_state.py sync
uv run python scripts\shitou_analyze.py analyze
Get-Content prompts_b\article_gen.txt | Select-Object -First 40

# 3) 生成だけを試す(公開しない)
#    先に config.b.yaml の publisher.publish_mode を "draft" に変更しておく
powershell -ExecutionPolicy Bypass -File scripts\prepare-b.ps1

# 4) 下書きの中身を目視確認
Get-ChildItem output_b\drafts -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 5

# 5) note の下書きに入ることを確認
powershell -ExecutionPolicy Bypass -File scripts\daily-b.ps1

# 6) 問題なければ publish_mode を "full" に戻し、定期実行を登録(管理者 PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\register-task-b.ps1
```

### note 側で必要な作業(人の手が必要)

1. B のプロフィール(クリエイター名・自己紹介・アイコン・ヘッダー)を史灯に変更
2. **B の note ID を変更した場合**、`config.b.yaml` の `promoter.article_url_template` を
   実際のIDに合わせて更新する(現在は `tsukaeru_prompt` のまま)
3. Cookie を取り直す(`_note_session_v5` と `note_gql_auth_token` の両方):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\set-cookie.ps1 -Account B
   ```
   ※ **B 専用のブラウザ/Chromeプロファイルで行うこと。**
   同じブラウザで別アカウントにログインすると、先のアカウントの Cookie が即失効します。

---

## 6. 一週間の動き

| 曜日・時刻 | タスク | 内容 |
|---|---|---|
| 毎日 08:00 | `healthcheck-b` | 疎通確認。失敗なら通知(Cookie 失効の早期発見) |
| 月水金 09:00 | `prepare-b` | sync → collect → analyze → generate。**翌日ぶんの記事**を用意 |
| 火木土 17:00 | `daily-b` | 疎通確認 → (未生成なら生成) → publish → 話数+1 → feedback → 分析 |
| | | 未公開の記事は常に1本だけ(公開してから次を作る) |
| 火木土 19:30 | `catchup-b` | 未公開なら publish を再試行 |
| 火木土 21:30 | `catchup2-b` | 同上(2回目) |
| 月曜 07:00 | `analyze-b` | feedback → 分析。改善指示を更新 |

ログは `logs/shitou-YYYYMM.log` に残ります。

### 手動での操作

```powershell
uv run python scripts\shitou_state.py status      # 今どこまで進んだか
uv run python scripts\shitou_state.py set 4       # 第4話からやり直す(4話以降の記録は消える)
uv run python scripts\shitou_analyze.py analyze   # 分析だけ実行
uv run python scripts\shitou_analyze.py schema    # DB のテーブルとカラムを表示
```

### 次の連載を始めるとき

1. `series/shitou_series.json` を新しい作品の設定に差し替える
2. `uv run python scripts\shitou_state.py set 1`

`prompts_b/_templates/` は作品に依存しない書き方にしてあるため、差し替え不要です。

---

## 7. 設計上の判断(意図的にこうしている箇所)

| 箇所 | 値 | 理由 |
|---|---|---|
| `theme_select` の `format` | 常に `"howto"` | 既存コードの検証を通すための固定値。小説の型としては使わない |
| `theme_select` の `price_jpy` | 常に `500` | 全文無料公開のため実際には使われないが、スキーマを満たすための固定値 |
| `theme_select` の `keyword` | トレンド候補から1つ選ぶ | 候補と紐づかない値を返すと後続処理で外れる可能性があるため |
| 品質ゲートの4軸キー名 | `fact`/`value`/`unique`/`safety` を維持 | キー名を変えるとコード側の JSON 検証で落ちるため。**中身だけ**を小説用に再定義 |
| `generator.research_enabled` | `false` | 毎話の本文に時事ネタが混入するのを防ぐ。史実調査は作品設定側で完結させる |
| `collector.collector_live` | `true` のまま | パイプラインの形を壊さないため。収集はするが題材選定には使わない |
| `analyzer.theme_count` | `1` | 1回の実行で書くのは次の1話だけ |
| `publisher.default_hashtags` | 5個固定 | 読者が第1話に遡れるよう、毎話同じシリーズタグを付ける |
| 分析に LLM を使わない | 決定的ルール | 追加費用がかからず、同じ数字からは必ず同じ指示が出る(再現性) |
| 終了コード2 をリトライしない | — | 401/403/429 の緊急停止。連打はアカウント凍結のリスクを上げる |

---

## 8. 未検証事項(実機で必ず確認すること)

**この一式は、作業環境から note-autopilot 本体を実行できないため、
本体との結合が確認できていません。**壊れやすい順に挙げます。

1. **`min_headings: 0` が許容されるか。**下限値の検証が `>=1` なら設定読み込みで落ちます。
   落ちたら `1` にし、本文の先頭に `<h2>副題</h2>` を置くよう
   `prompts_b/_templates/article_gen.tmpl` を1行変えてください
2. **`theme_select` の `format` が `howto|checklist` の列挙で検証されているか。**
   されていれば `"howto"` 固定で問題ありません
3. **`avoid_recent_keywords: 0` が「無効」として扱われるか。**
   0 が無効化でなければ、2話目以降がテーマ選定で落ちます
4. **`max_similarity: 0.92` で連載2話目以降が通るか。**
   落ちるようなら 0.97 まで上げる(1.0 は重複検出が完全に無効になるため避ける)
5. **各サブコマンドの終了コードが README の記載どおりか。**
   リトライの判定(3/4/5/6/8)がこれに依存しています
6. **`shitou_analyze.py` が DB のカラムを特定できるか。**
   できない場合は `schema` の出力を共有してください(落ちずに報告します)
7. `publish` が「未公開の合格記事のみ」を対象にすること。
   これが前提のため、もし公開済みの記事を再投稿する実装なら
   `catchup-b.ps1` は使わないでください(二重投稿になります)

エラーが出たら、**終了コードと標準エラー出力、`logs/shitou-*.log`** を共有してください。

---

## 9. 運用上の注意

- **全文無料公開で開始します**(`paid_enabled: false`)。有料化は連載が軌道に乗ってから
- A(`ai_uresuji`)とキーワードが重複しないようにしてあります
- 投稿時刻は A の月水金日 17:00、SoA の火金 18:30 と重ならない火・木・土 17:00 です
- **AI 自動運用であることの開示について**: 小説本文に毎話入れると読み味を壊すため、
  この一式では本文には入れていません。代わりに **note のプロフィール欄に明記してください。**
  開示自体をやめる判断は既存設計(`docs/account-profiles.md` 大原則2)からの
  方針転換になるため、行っていません
- **完全自動公開では、人が本文を読む前に公開されます。**品質ゲートは物語の整合を
  完全には判定できません。最低でも第1話・第2話は `publish_mode: "draft"` で
  目視確認することを強く推奨します
