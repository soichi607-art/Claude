# テストレポート（2026-09-10 更新・2 回目）

## 最新: 利用者の AMD 実機（2026-09-10）
実行環境: Windows 11 (10.0.26200), AMD Ryzen 5 220 w/ Radeon 740M, 16.4GB, Python 3.12.14（uv 管理、`start_windows.bat` が作成した `.venv`）, **FFmpeg 無し**。

結果: **30 passed, 7 failed（全 37 件）**。失敗 7 件はすべて FFmpeg / ffprobe 不在が原因（FFmpeg 導入後に再実行すること）:
- test_audio_and_video: test_stitch_audio_duration, test_render_mv_small, test_encoder_fallback_to_libx264（ffmpeg 実行）
- test_web_flow: test_project_flow（音源アップロードが ffprobe 失敗で 400）, test_render_outputs_and_package, test_ai_clip_import_and_swap（描画）, test_run_preflight_reports_ok（前提チェックが「ffmpeg が見つかりません」を返す＝正しい挙動）

今回追加したテスト（FFmpeg 不要、AMD 機で成功）:
- test_hardware_and_generation::test_hw_encoder_priority_and_args — h264_amf / h264_nvenc の候補化、採用順、`encoder_args`、未知名は libx264
- test_hardware_and_generation::test_dotenv_inline_comments_are_not_values — `.env` の行内コメント・引用符・`export` の扱い
- test_diagnostics_report に「## ハードウェアエンコーダー」の見出し確認を追加

補足: 修正前は同じ環境で 17 件失敗していた。差分 10 件は `.env` の行内コメント混入（LAN モード誤判定 → 全画面 503）によるもので、パーサー修正で回復。

## 前回: 開発コンテナ（2026-09-10）
実行環境: 開発コンテナ（Linux 6.18, Intel Xeon 4 vCPU, 16GB, Python 3.11.15, FFmpeg 6.1.1, GPU なし）。Intel 実機（Core 5 120U）では未実行。

## 実行コマンド
```
python -m pytest -v
```
描画テストは `SOA_RENDER_SCALE=0.125` `SOA_RENDER_FPS=10`（135×240 相当）で実行（tests/conftest.py で設定）。

## 結果: 35 passed, 0 failed（約 150 秒）

| ファイル | 内容 | 件数 |
|---|---|---|
| tests/test_acestep_client.py | 公式 API.md の全エンドポイントを模した偽サーバーで release_task→query_result→/v1/audio の往復、Bearer 認証失敗、未接続表示 | 3 |
| tests/test_audio_and_video.py | BPM/構成検出、25/65/90 の編集プラン合計とループ尾、acrossfade 後の尺、MV 描画（映像+音声+一時ファイル削除）、歌詞 ASS、色検証、カバー画像、HW エンコーダー失敗時の libx264 フォールバック | 8 |
| tests/test_hardware_and_generation.py | 診断レポート項目、PC 保護、実測のみからの ETA、Eco/Overnight キュー投入とキャンセル | 3 |
| tests/test_prompt_lyrics.py | 参考アーティスト名がプロンプトに入らないこと、中立化監査、NG ワード、英日対訳行数一致・決定性、seed による独自性 | 4 |
| tests/test_security.py | ファイル名無害化、パストラバーサル拒否、拡張子/マジックバイト/サイズ検証、キー秘匿、PATH に無い FFmpeg を tools 配下から検出 | 5 |
| tests/test_web_flow.py | 全画面 200、CSRF 拒否、セキュリティヘッダ、プロジェクト作成→手動アップロード→採用→8 本描画→post_package.zip→キャラクター確定→video_generation_pack.zip→AI 動画 ZIP 取り込み/解除→投稿準備→共有→投稿済み→成績入力→診断、操作ガイド/次にやること、run.py 前提チェック | 12 |

## 手動確認
- `python scripts/diagnose.py`: docs/HARDWARE_REPORT.md 生成。h264_qsv / h264_vaapi は本環境で失敗、libx264 成功 → 採用 libx264（実機では再診断）
- 実サーバー `python run.py` を起動し、Chromium（390×844, iPhone UA）で 12 画面をスクリーンショット確認。横スクロール幅 390px
- 40 秒サンプル音源で 8 本の動画を描画（約 90 秒 @ 縮小解像度）。ffprobe で尺・解像度・H.264/AAC を確認
- フレーム抽出でタイトル・歌詞テロップ（英語）・日本語テロップ・波形・グリッチ・ビートフラッシュを目視確認

## 未テスト
- 実 ACE-Step（XPU/CPU）での生成時間、Colab/Kaggle での Notebook 実行、iOS Safari 実機での Web Share、Intel QSV / AMD AMF / NVIDIA NVENC の実機エンコード、1080p フル解像度での描画時間、FFmpeg 導入後の AMD 機での全件テスト
