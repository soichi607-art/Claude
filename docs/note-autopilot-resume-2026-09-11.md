# note 自動運用 再開メモ(2026-09-11 時点)

このドキュメントは 2026-09-11 の調査結果です。**推測は含めず、確認できた出典のみ**を記載し、
確認できなかったことは「未確認」と明記しています。

出典は Google ドライブ上のバックアップ `マイドライブ/note-autopilot/`
(バックアップ日時: 2026-08-27、ファイル更新日は各項に記載)です。

---

## 1. 結論(先に読むところ)

- **このクラウドセッションからは自動運用を再開できません。** 実体は利用者の Windows PC
  (`C:\Users\User\Documents\note-autopilot`)にあり、Windows タスクスケジューラで動いています
  (出典: `README.md` §4、更新 2026-07-28)。このセッションはクラウドコンテナで、
  対象 PC に到達できません(2026-09-11 14:25〜14:29 に各ローカルセッションが
  `computer_unreachable` を記録、同 15:5x 時点で到達可能な同一マシン上のセッションなし)。
- **再開作業は PC 上で実行する必要があります。** 手順は §4 にまとめました。
- **最大の再開ブロッカーは note の Cookie 失効**である可能性が高いです(§4-2)。
- **「史灯(歴史小説家)」への切り替えは、設定変更だけでは完了しません。**
  既存の品質ゲートとプロンプトが「事実性」「捏造禁止」を前提に作られており、
  小説(創作)と正面から衝突します。詳細は §5。

---

## 2. 現在のアカウント構成(バックアップから確認)

| | アカウントA | アカウントB | アカウントSoA |
|---|---|---|---|
| クリエイター名 | AIが毎週数える note売れ筋 | AIが試したプロンプト置き場 | 株式会社SoA｜農業×AIの実践記録 |
| note ID | `ai_uresuji` | `tsukaeru_prompt` | `soa_agri`(案) |
| config | `config.yaml` | `config.b.yaml` | `config.soa.yaml` |
| データ/出力 | `data/` `output/` `backup/` | `data_b/` `output_b/` `backup_b/` | `*_soa` |
| .env のキー接尾辞 | なし | `_B` | `_SOA` |
| 投稿 | 月・水・金・日 17:00 | 火・木・土 17:00 | 火・金 18:30 |
| 公開モード | `full` | `full` | `draft` |
| 有料公開 | `paid_enabled: false`(全文無料) | 同左 | 収益化しない |

出典: `docs/account-profiles.md`(2026-07-28 改訂)、`docs/account-soa.md`(2026-08-13 作成)、
`config.yaml`(更新 2026-08-06)、`config.b.yaml`(更新 2026-08-06)。

> 注: `README.md` §2.4 は A を「月・水・金」と書いていますが、より新しい
> `docs/account-profiles.md` は「月・水・金・日(週4)」です。`config.yaml` の
> `target_monthly_articles: 17` は週4本の想定と整合します。**週4が現行**と判断しました。

---

## 3. 停止の経緯について(未確認)

- 2026-08-19 付で「Note の自動運用停止」という作業セッションが存在することは確認できました。
- ただし**そのセッションの中身は参照できず、「何をどう止めたのか」(タスクスケジューラを
  無効化したのか、STOP ファイルを置いたのか、Cookie を抜いたのか)は確認できていません。**
- したがって再開時は、§4-1 で**現状を実機で確認してから**進めてください。

---

## 4. 再開手順(利用者の Windows PC で実行)

前提: PowerShell、作業ディレクトリは `C:\Users\User\Documents\note-autopilot`。

### 4-1. 現状確認(まずこれ)

```powershell
cd C:\Users\User\Documents\note-autopilot

# 緊急停止フラグが残っていないか(アカウントごとに別ファイル)
Get-ChildItem data\STOP, data_b\STOP, data_soa\STOP -ErrorAction SilentlyContinue

# 定期実行タスクが生きているか(登録名と状態を確認)
Get-ScheduledTask -TaskName 'note-autopilot-*' | Select-Object TaskName, State
```

- `STOP` ファイルがある場合 = 401/403/429 を検知して全停止した状態です。
  **原因を確認してから手動削除**してください(自動解除は実装されていません。
  出典: `README.md` 絶対ルール表・§7)。
- `data_b\X_STOP` がある場合は放置で構いません(翌日 JST に自動解除。出典: 同 §7)。

### 4-2. note の Cookie を取り直す(最重要)

最終更新から 3 週間以上経っており、**Cookie は失効している前提**で進めてください。
`_note_session_v5` と `note_gql_auth_token` の**両方**が必要です
(片方だけだと `not_login` になる。出典: `README.md` §1 注記・§10 の 2026-07-26 実検証)。

**アカウントごとに別のブラウザ(または別 Chrome プロファイル)を必ず使うこと。**
同じブラウザで別アカウントにログインし直すと、**先のアカウントの Cookie が即失効します**
(A・B で実際に発生済み。出典: `README.md` §2.4、`docs/account-soa.md` 手順1)。

```powershell
# 1) 該当プロファイルの Chrome で note.com にログイン(右上が自分のアイコン)
# 2) F12 → Network タブ → Doc フィルタ → F5
# 3) 一覧の一番上の行を右クリック → Copy → Copy as cURL (bash)
# 4) 下記を実行(A はオプションなし)
powershell -ExecutionPolicy Bypass -File scripts\set-cookie.ps1
powershell -ExecutionPolicy Bypass -File scripts\set-cookie.ps1 -Account B
powershell -ExecutionPolicy Bypass -File scripts\set-cookie.ps1 -Account SOA
```

### 4-3. 疎通確認(投稿する前に必ず)

```powershell
uv run python -m note_autopilot healthcheck --live
uv run python -m note_autopilot --config config.b.yaml healthcheck --live
uv run python -m note_autopilot --config config.soa.yaml healthcheck --live
```

読み取り系 4 エンドポイントのスキーマ検証のみで、書き込みは行いません(出典: `README.md` §4)。
`stats/pv` が `not_login` なら Cookie 失効 → 4-2 をやり直し。
異常時の終了コードは 10。

> **note 側の仕様変更リスク**: 前回の実検証は 2026-07 です。約 2 か月経過しているため、
> healthcheck が通らない可能性があります。その場合は `README.md` §10 の
> 「残 TODO」と各 client の TODO を突合する作業が必要です(このセッションでは実機確認不可)。

### 4-4. Gemini API キーの確認

記事生成は既定で Gemini 無料枠を使います(`llm.backend: gemini` / `gemini-flash-latest`。
出典: `config.yaml`)。キーが失効・未設定なら:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\set-gemini-key.ps1
```

### 4-5. 段階的に戻す(いきなり full にしない)

1. `collect` → `analyze` → `generate` を手動で 1 サイクル回し、品質ゲートの結果を確認
2. 問題なければ `publisher.publish_mode` を `draft` にして `publish` を実行し、
   note の下書き一覧に入ることを実アカウントで確認
3. そこまで通ってから `full` に戻す

(出典: `README.md` §3 の運用開始手順、実アカウント検証チェックリスト)

### 4-6. 定期実行を再登録する

```powershell
# 管理者 PowerShell
powershell -ExecutionPolicy Bypass -File scripts\register-tasks.ps1
powershell -ExecutionPolicy Bypass -File scripts\register-task-soa.ps1
Get-ScheduledTask -TaskName 'note-autopilot-*' | Select-Object TaskName, State
```

> 17:00 実行の理由: Gemini 無料枠の日次上限が太平洋時間 0 時 = **JST 16:00 にリセット**
> されるため、リセット直後に回して 1 日分の枠を使い切る設計です(出典: `README.md` §4)。

---

## 5. 「史灯(歴史小説家)」運用に切り替えるうえでの論点

**どちらのアカウントを史灯にするのかが未確定です。** A(`ai_uresuji`)と B(`tsukaeru_prompt`)
のどちらかを確認してから設定を起こします。

そのうえで、**現行の実装をそのまま使うと史灯の記事は公開されない**見込みです。理由:

| 現行の仕組み | 史灯(小説)との衝突 |
|---|---|
| 品質ゲート 4 軸 × 25 点(事実性 / 価値 / 独自性 / 安全性)、**80 点未満は公開しない** | 創作は「事実性」「価値(読後に読者が何かできるようになるか)」の採点基準に乗らない |
| 絶対ルール「実績・経歴の捏造禁止」(`prompts/article_gen.txt` C-2 + C-3 採点基準) | 歴史小説は創作。史実と創作の線引きルールを別途定義しないと機械的に弾かれる |
| `article_writer.READER_PROBLEM_CONSTRAINT`(読者の困りごと → AI での解決 → 今日試せる一歩の順で書く、コードで強制) | 小説の構成と両立しない |
| `AI_DISCLOSURE_CONSTRAINT`(全記事に AI が自動で書いている旨を明記、コードで強制) | 小説本文に毎回入れるのは読み味を壊す。**ただし開示自体はやめるべきでない**(§6) |
| `min_headings: 3`(見出し 3 つ以上) | 小説本文に見出しは通常 3 つも立たない |
| `max_similarity: 0.5`(直近 30 記事との TF-IDF 類似度上限) | **連載小説は前話と語彙が似るため機械的に弾かれる可能性が高い** |
| `collector` / `analyzer` が「生成AI・副業・プロンプト」等のキーワードで市場を計測しテーマを選定 | 歴史小説にはこの選定ロジックがそのまま使えない |

→ 史灯用には **専用 config + 専用プロンプト群(prompts_shitou/)+ 品質ゲートの別基準**を
起こすのが現実的です。既存 A/B/SoA と同様、DB・出力先・STOP ファイル・バックアップ先を
分離すれば既存アカウントには影響しません(出典: `docs/account-soa.md` の分離設計)。

**史灯のプロンプトを受領後に、上記一式を作成します。**

---

## 6. 運用上の注意(既存ルールとして明記されているもの)

- note の禁止事項に「当社が判断するスパム投稿」が含まれるため、**同じ記事・同じデータを
  複数アカウントに流さない**。キーワードの重複も避ける
  (`tests/test_multi_account.py` が重複を検出。出典: `README.md` §2.4)。
  史灯は他 3 アカウントとジャンルが完全に異なるため、この点では有利です。
- 投稿曜日・時刻を既存 3 アカウントとずらす(同日同時刻の投稿は機械的な運用に見えるため。
  出典: 同上)。現行の埋まり具合: 月水金日 17:00(A)/ 火木土 17:00(B)/ 火金 18:30(SoA)。
- **AI 自動運用であることの開示は続けるべき**です。プロフィール欄など本文外で明示する形に
  変えるのは可能ですが、開示自体を落とす判断は既存設計(`docs/account-profiles.md` 大原則2)
  からの明確な方針転換になるため、利用者の明示的な指示が必要です。
- note への投稿は非公式 API を利用しており、仕様変更で壊れる前提の実装です
  (出典: `README.md` 冒頭注意書き)。

---

## 7. このセッションで確認できなかったこと

- 2026-08-19 に**実際に何を止めたのか**
- 現在 PC 上で `STOP` ファイルやタスクスケジューラがどうなっているか
- note 側の非公式 API が 2026-09 時点でも 2026-07 の実検証どおり動くか
- 史灯に切り替えたのが A / B のどちらか
- note アカウントの現在のプロフィール実物(このセッションから note にはログインできません)
