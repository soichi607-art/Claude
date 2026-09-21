# クイックスタート（日本語）

## 0. 最短（推奨）
Windows は `start_windows.bat` をダブルクリック。Python（3.11〜3.14）が無ければスクリプトが winget での自動インストールを提案し（uv が入っていれば uv の Python を自動利用）、FFmpeg が無ければ同様に winget での自動インストールを提案します（または zip を `tools` フォルダへ）。macOS/Linux は Python を入れた上で `./start.sh`。初回セットアップと起動を自動で行い、ブラウザが開きます。画面の使い方は `docs/USER_GUIDE_JA.md` とアプリ内「ガイド」タブ。

## 1. 準備（PC・手動の場合）
1. Python 3.11〜3.14、FFmpeg（PATH、または zip を `tools` フォルダに展開、または winget `Gyan.FFmpeg`）、Git をインストール
2. このリポジトリを取得し、依存をインストール
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows  /  source .venv/bin/activate (macOS/Linux)
   pip install -r requirements.txt
   copy .env.example .env         # 必要に応じて編集
   ```
3. 環境診断
   ```bash
   python scripts/diagnose.py     # docs/HARDWARE_REPORT.md を生成
   ```
4. 起動
   ```bash
   python run.py                  # http://127.0.0.1:8000
   ```

## 2. iPhone から使う
1. `.env` に `SOA_HOST=0.0.0.0`、`SOA_AUTH_USER`、`SOA_AUTH_PASSWORD` を設定して再起動（LAN 公開時は認証必須）
2. 同じ Wi-Fi の iPhone Safari で `http://<PCのIP>:8000` を開く → 共有 → 「ホーム画面に追加」で PWA として使えます
3. 注意: Web Share API でのファイル共有は HTTPS（Secure Context）が必要な場合があり、`http://` の LAN では動かないことがあります（未確認）。その場合は共有画面のフォールバック手順（動画保存 → 投稿文コピー → アプリで手動投稿）を使ってください。

## 3. 制作の流れ
1. **新規プロジェクト**: テーマ・ジャンル・スライダー・ボーカルを入力 → 3案（A キャッチー / B ドロップ / C ボーカル）のプロンプトと英日対訳歌詞が自動生成
2. **楽曲生成**: 設定画面で ACE-Step の 10秒 → 30秒テストを成功させると3案生成が有効化。ACE-Step が使えない場合は各案に音源を手動アップロード
3. **3案比較**: 聴き比べて1案を採用（Eco/Standard は採用案だけをフル生成）
4. **MV編集**: フルMV（9:16 / 16:9）をモーショングラフィックスで描画。AI 動画は無料 GPU Notebook で生成して ZIP 取り込み（任意）
5. **ショート編集**: 25 / 65 / 90 秒（YouTube / TikTok）＋フル版を一括描画
6. **投稿準備**: テキスト・カバー・post_package.zip を出力 → 公開前チェック → 共有画面（投稿文コピー → 共有シート → アプリで公開 → 「投稿済み」記録）
7. **分析**: 再生数などを手動入力（空欄＝未取得、0＝実際に0）

## 4. 代表者の承認ポイント
- キャラクター基準画像の確定（AI 動画パック出力の前提）
- 公開前チェック 8 項目と最終公開ボタン（iPhone のアプリ側）
