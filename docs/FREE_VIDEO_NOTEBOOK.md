# 無料GPU Notebook による AI 動画生成（手動実行）

確認日: 2026-09-09

## 方針
- 実機（Core 5 120U / 16GB）には重い動画モデルを導入しません。
- 無料 GPU（Google Colab / Kaggle）を **ユーザーが手動で** 実行します。GPU 割当・時間・無料提供の継続は保証されません。
- 制限回避、複数アカウント、自動常設サーバー化は禁止です。
- AI 動画がなくても FFmpeg モーショングラフィックス版で作品を完成できます（B ルート）。

## 候補モデル: Wan2.1
- 出典: https://github.com/Wan-Video/Wan2.1（確認日 2026-09-09）
- リポジトリ LICENSE.txt: Apache License 2.0
- README 記載: 「T2V-1.3B ... requires only 8.19 GB VRAM」。I2V は 14B（480P/720P）のみ。
- **未確認**: Hugging Face 上のモデル重みのライセンス表記、無料 GPU（T4 等）での I2V-14B の動作可否、`generate.py` の出力ファイル名・フレーム数指定。使用時に公式 README で確認して Notebook 内 `LICENSE_NOTE` に記録してください。
- 注意: I2V が使えない場合、キャラクター基準画像との同一性は T2V プロンプトだけでは限定的です。

## サービス規約（未確認・使用時に確認）
- Google Colab FAQ: https://research.google.com/colaboratory/faq.html
- Kaggle Notebooks: https://www.kaggle.com/docs/notebooks

## 手順
1. MV編集画面で「video_generation_pack.zip を出力」（代表者がキャラクター基準画像を確定済みであること）
2. 「Notebook をダウンロード (.ipynb)」
3. Colab / Kaggle に Notebook をアップロードし、上から順に手動実行
   1. ZIP アップロード
   2. GPU 確認（割当なしなら中止）
   3. ライセンス確認セルに記入（`LICENSE_CONFIRMED = True` にしないと先へ進めません）
   4. モデル取得
   5. 3〜5秒テスト生成 1 本
   6. 成功後 6〜10 シーン生成（hook / intro / verse / buildup / drop1 / break / final_drop / outro）
   7. `ai_clips.zip` をダウンロード
4. MV編集画面「AI動画ZIP取り込み」→ フルMV / ショートを再描画

## パックの内容
character/（基準画像ほか）、song_info.json、scenes.json、prompts/*.txt（[CHARACTER]/[ACTION]/[ENVIRONMENT]/[CAMERA]/[LIGHTING]/[MOOD]/[TECHNICAL]）、negative_prompt.txt、README_GENERATION_STEPS.md、results/（格納先）、audio/（採用音源）

## 取り込み時のルール
- ファイル名にシーン名を含める（例 `drop1.mp4`）。拡張子 mp4/mov/webm/mkv、1ファイル 500MB 以下、40 ファイル以下。
- ffprobe で動画ストリームを検証し、通らないものはスキップして理由を表示します。
- 取り込んだシーンは「AI動画を外す」でモーショングラフィックスに戻せます。
