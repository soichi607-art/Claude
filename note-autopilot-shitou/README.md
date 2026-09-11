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

加えて、**話数と前話との整合を保持する仕組みが本体に無い**ため、
`scripts/shitou_state.py` がその状態管理を担当します。

---

## 2. ファイル一覧と配置先

`C:\Users\User\Documents\note-autopilot\` 直下に、同じ構造のままコピーします。

| ファイル | 配置先 | 種別 |
|---|---|---|
| `config.b.yaml` | `config.b.yaml` | **既存を上書き**(先に退避すること) |
| `prompts_b/_templates/*.tmpl` | `prompts_b/_templates/` | 新規。**編集するのはこちら** |
| `prompts_b/*.txt` | `prompts_b/` | 新規。`sync` が自動生成するため直接編集しない |
| `series/shitou_series.json` | `series/` | 新規。作品設定(人物・全話プロット・伏線・史実と創作の区別) |
| `scripts/shitou_state.py` | `scripts/` | 新規。話数管理とプロンプト生成 |
| `scripts/daily-b.ps1` | `scripts/` | 新規。B 専用の日次パイプライン |
| `scripts/register-task-b.ps1` | `scripts/` | 新規。定期実行の登録 |
| `data_b/series_state.json` | `data_b/` | 新規。進行状態(第1話から開始の初期値) |

> **重要**: 変更前に `config.b.yaml` を `config.b.yaml.bak` として必ず退避してください。
> 旧「プロンプト置き場」設定に戻す必要が出た場合の唯一の復旧手段です。

---

## 3. 導入手順

```powershell
cd C:\Users\User\Documents\note-autopilot

# 0) 退避
Copy-Item config.b.yaml config.b.yaml.bak

# 1) このディレクトリの中身を上記の配置先へコピー

# 2) 動作確認(実通信なし)
uv run python scripts\shitou_state.py status
uv run python scripts\shitou_state.py sync
Get-Content prompts_b\article_gen.txt | Select-Object -First 40

# 3) 生成だけを試す(公開しない)
#    先に config.b.yaml の publisher.publish_mode を "draft" に変更しておく
uv run python -m note_autopilot --config config.b.yaml collect
uv run python -m note_autopilot --config config.b.yaml analyze
uv run python -m note_autopilot --config config.b.yaml generate

# 4) 下書きの中身を目視確認
Get-ChildItem output_b\drafts -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 5

# 5) note の下書きに入ることを確認
uv run python -m note_autopilot --config config.b.yaml publish

# 6) 問題なければ publish_mode を "full" に戻し、定期実行を登録
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

## 4. 日々の動き

火・木・土 17:00 に `daily-b.ps1` が次の順で動きます。

```
shitou_state.py sync   … 次に書く話の仕様・前話の要約・作品設定をプロンプトへ差し込む
  ↓
collect → analyze → generate → publish
  ↓
publish が成功(終了コード0)したときだけ shitou_state.py advance で話数を +1
  ↓
feedback
```

**公開に失敗した日は話数が進みません。**次回の実行で同じ話を書き直します。
品質ゲートで保留された場合(終了コード5)も同様で、記事は `output_b/hold/` に残ります。

全10話が終わると `sync` が終了コード20を返し、`daily-b.ps1` は何もせずに終了します。

### 手動での操作

```powershell
uv run python scripts\shitou_state.py status      # 今どこまで進んだか
uv run python scripts\shitou_state.py set 4       # 第4話からやり直す(4話以降の記録は消える)
uv run python scripts\shitou_state.py advance     # 手動で1話進める
```

### 次の連載を始めるとき

1. `series/shitou_series.json` を新しい作品の設定に差し替える
2. `uv run python scripts\shitou_state.py set 1`

`prompts_b/_templates/` は作品に依存しない書き方にしてあるため、差し替え不要です。

---

## 5. 設計上の判断(意図的にこうしている箇所)

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

---

## 6. 未検証事項(実機で必ず確認すること)

**この一式は、この作業環境から note-autopilot 本体のコードを実行できないため、
実機での動作確認ができていません。**確認すべき点を、壊れやすい順に挙げます。

1. **`min_headings: 0` が許容されるか。**下限値のバリデーションが `>=1` になっている場合は
   設定読み込みで落ちます。落ちたら `1` にし、本文の先頭に `<h2>副題</h2>` を置くよう
   `prompts_b/_templates/article_gen.tmpl` を1行変えてください
2. **`theme_select` の `format` が `howto|checklist` の列挙で検証されているか。**
   されていれば `"howto"` 固定で問題ありません
3. **`avoid_recent_keywords: 0` が「無効」として扱われるか。**
   0 が無効化ではなく別の意味を持つ実装なら、2話目以降がテーマ選定で落ちます
4. **`max_similarity: 0.92` でも連載2話目以降が通るか。**
   落ちるようなら 0.97 まで上げる(1.0 にすると重複検出が完全に無効になるため避ける)
5. **本文の HTML に見出しタグが無くても publish が通るか**
6. `shitou_state.py advance` が拾う「直近の下書き」の形式
   (形式が不明でも落ちないよう防御的に実装してありますが、冒頭抜粋が空になる可能性があります)

エラーが出たら、**終了コードと標準エラー出力をそのまま共有してください。**該当箇所を直します。

---

## 7. 運用上の注意

- **全文無料公開で開始します**(`paid_enabled: false`)。有料化は連載が軌道に乗ってから
- A(`ai_uresuji`)とキーワードが重複しないようにしてあります
  (`tests/test_multi_account.py` が重複を検出します)
- 投稿時刻は A の月水金日 17:00、SoA の火金 18:30 と重ならない火・木・土 17:00 です
- **AI 自動運用であることの開示について**: 既存の A / SoA は本文中に明記する設計ですが、
  小説本文に毎話それを入れると読み味を壊すため、この一式では**本文には入れていません**。
  代わりに **note のプロフィール欄に明記してください。**開示自体をやめる判断は
  既存設計(`docs/account-profiles.md` 大原則2)からの方針転換になるため、行っていません
- **完全自動公開では、人が本文を読む前に公開されます。**品質ゲートは物語の整合を
  完全には判定できません。最低でも第1話・第2話は `publish_mode: "draft"` で
  目視確認することを強く推奨します
