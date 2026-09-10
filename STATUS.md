# STATUS — SoA EDM Studio（2026-09-10 更新）

凡例: ✅ 完成・テスト済 / 🟡 実装済だが実機・外部サービスで未検証 / ⛔ 未実装（意図的）

## 完了条件との対応
| 条件 | 状態 | 備考 |
|---|---|---|
| ローカルで起動できる | ✅ | `start_windows.bat` / `./start.sh` でセットアップ込みの起動、`python run.py --open`。`--check` で前提チェック。TestClient と実サーバーで全画面 200 |
| iPhone で操作できる | 🟡 | Chromium 390px エミュレーション（iPhone UA）で 12 画面を確認、横スクロールなし。実機 iPhone Safari は未検証 |
| 楽曲3案を管理できる | ✅ | A/B/C のプロンプト・歌詞・seed・音源・採用をテスト |
| ACE-Step 利用可否を正しく表示できる | ✅ | 公式 `/health` `/v1/models` `/v1/stats` を表示。未接続時は「未接続」。偽サーバーで API.md 準拠の往復をテスト |
| AI 動画なしでも MV を完成できる | ✅ | モーショングラフィックス版（9:16 / 16:9）をテストで描画 |
| AI 動画を取り込んで差し替えられる | ✅ | ZIP 取り込み→シーン差し替え→解除をテスト（実 AI 動画は未使用） |
| 25・65・90・Full 版を出力できる | ✅ | 6 本のショート＋フル 2 本。編集プランの合計秒数・ループ尾をテスト |
| 投稿素材を 2〜3 操作でアプリへ渡せる | 🟡 | Web Share API（files）フロー＋フォールバックを実装。iOS 実機・LAN http での動作は未確認 |
| 有料サービスを呼ばない | ✅ | 外部通信は ACE-Step（localhost）のみ。CSP `connect-src 'self'` |
| テストが通る | ✅ | 35 件パス（docs/TEST_REPORT.md） |
| STATUS.md | ✅ | 本書 |

## Phase 別
| Phase | 状態 | 備考 |
|---|---|---|
| 1 環境診断 | ✅ | `docs/HARDWARE_REPORT.md` は実機で起動スクリプトが生成（git 管理外）。GPU/XPU/QSV は実機で確認 |
| 2 PLAN.md | ✅ | 出典・確認日付き |
| 3 Web UI と DB | ✅ | CSRF・CSP・Basic 認証（LAN）・アップロード検証・パス検証 |
| 4 プロジェクト管理 | ✅ | 中立化＋監査ログ、NG ワード、参考音源解析（権限確認必須） |
| 5 キャラクター管理 | ✅ | プロンプト/ネガ/シート/seed、9 種画像、代表者確定フロー。画像生成自体は外部 Notebook（ADR-004） |
| 6 FFmpeg MV | ✅ | セクション描画、ビート同期フラッシュ、rgbashift グリッチ、life/cellauto パーティクル、波形・スペクトラム、ASS 歌詞、Ken Burns、色調統一、QSV→libx264 |
| 7 25/65/90/Full | ✅ | 音声編集プラン＋acrossfade、版ごとの導入/結末テロップ、TikTok セーフゾーン |
| 8 投稿パッケージ・Web Share | 🟡 | 上記 |
| 9 ACE-Step 10 秒テスト | 🟡 | 実装済。実 ACE-Step サーバーは本環境に無く未実測 |
| 10 30 秒テスト | 🟡 | 同上（10 秒成功後のみ有効） |
| 11 Eco | 🟡 | キュー投入・採用 1 案のフル化をテスト。実生成は未実測 |
| 12 Overnight | 🟡 | 連鎖＋休止時間をテスト。夜間実運用は未実測 |
| 13 無料 GPU Notebook | 🟡 | .ipynb 生成。Colab/Kaggle での実行・Wan2.1 の実動作は未確認 |
| 14 AI 動画 ZIP 取り込み | ✅ | |
| 15 分析画面 | ✅ | 手動入力。未取得（空欄）と 0 を区別 |
| 16 テスト・ドキュメント | ✅ | アプリ内「ガイド」タブ、ダッシュボード「次にやること」、docs/USER_GUIDE_JA.md |
| 17 操作性の仕上げ（2026-09-10） | ✅ | ワンクリック起動スクリプト、前提チェック、HW エンコーダー失敗時の libx264 自動フォールバック、新規 venv からの再現インストール検証 |
| 18 環境の緩和（2026-09-10） | ✅ | Python 3.11〜3.14 対応（PyPI の Windows ビルド有無を確認）、FFmpeg の自動検出（PATH / tools フォルダ / winget / ダウンロード フォルダ）、start_windows.bat の winget 自動導入提案 |

## 未実装（意図的）
- 自動投稿、公式 API による成績取得、実機での画像/動画生成モデル常駐（docs/KNOWN_LIMITATIONS.md）

## 実機で最初に行うこと
1. `python scripts/diagnose.py` で docs/HARDWARE_REPORT.md を更新（Intel XPU / QSV の可否を確認）
2. docs/ACESTEP_SETUP.md に従い ACE-Step API を起動し、設定画面で 10 秒→30 秒テスト
3. モデル重み・Notebook サービスのライセンスを確認して記録欄を埋める
