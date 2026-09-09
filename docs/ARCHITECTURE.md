# アーキテクチャ

```
run.py ─ uvicorn ─ app/main.py (FastAPI, lifespan: DB初期化 / 既定キャラ / ワーカー起動)
  ├─ middleware: Basic認証(LAN時のみ) / セキュリティヘッダ / CSP
  ├─ routers/: dashboard, projects, generation(jobs), characters, mv, shorts, publish, analytics, settings_page
  ├─ web.py: Jinja2 テンプレート, CSRF(double-submit cookie, itsdangerous署名), flash
  ├─ security.py: アップロード検証(拡張子+マジックバイト+サイズ), パストラバーサル防止, ログ秘匿
  ├─ models.py (SQLModel/SQLite): AppSetting, Character, CharacterImage, Project, Candidate, GenerationJob,
  │                               ReferenceAudio, AuditLog, SceneClip, RenderOutput, PostRecord, Metric, Benchmark
  └─ services/
       hardware.py        診断 (OS/CPU/メモリ/GPU/XPU/FFmpeg/QSV/エンコーダー実動作)
       safety.py          PC保護 (空きメモリ/空き容量/バッテリー/温度)
       generation.py      単一ワーカー キュー, cancel/pause/resume, 実測ベンチマーク→ETA, Eco/Standard/Overnight
       acestep_client.py  公式 API.md 準拠 REST クライアント
       prompt_builder.py  ジャンル語彙, スライダー→語句, 参考情報の中立化(監査ログ), NGワード
       audio_analysis.py  librosa: BPM/キー/エネルギー/ビート/構成推定
       lyrics.py          英日対訳フレーズバンクによる決定的歌詞生成
       copywriter.py      物語/背景/衣装/色/カメラの曲別割当, タイトル/投稿文/ハッシュタグ, 申告チェックリスト
       ffmpeg.py          shell=False ラッパー, probe, エンコーダー引数 (QSV→libx264), パスエスケープ
       fonts.py           フォント自動検出 (未設定は「未設定」表示)
       mv_builder.py      セクション単位の描画→concat→音声反応レイヤー/歌詞ASS/テロップ/色調統一
       shorts_builder.py  25/65/90 の編集プラン→acrossfade 音声再編集→再描画
       covers.py          Pillow カバー/サムネイル/プレースホルダー
       packaging.py       テキスト出力, video_generation_pack.zip, post_package.zip
       notebook.py        Colab/Kaggle 用 .ipynb 生成
       video_import.py    AI動画 ZIP の検証取り込み
app/static: app.css / app.js(ポーリング・確認・コピー) / share.js(Web Share) / sw.js / manifest
```

## データフロー
入力 → Project.inputs_json → (参考音源解析) → 中立化 → Candidate.prompt/lyrics（A/B/C）→ GenerationJob → ACE-Step API → 音源 → 採用 → 解析キャッシュ → MV/ショート描画 → RenderOutput → 投稿パッケージ → PostRecord → Metric

## 同時実行とPC保護
- ジョブは1件ずつ（スレッド1本）。開始前に safety.check()。FFmpeg には `-threads`（既定: 論理コアの半分）。
- Overnight は案ごとに `not_before` を付けて休止時間を挟む連鎖。
- 一時ファイルは描画後に削除、1時間超の tmp も掃除。

## セキュリティ
- 既定 127.0.0.1。LAN 公開時は Basic 認証必須（未設定なら起動拒否）。
- CSRF: 署名付き Cookie と form の一致検証。CSP: self のみ。
- FFmpeg: 引数はリスト、ユーザー文字列はファイル経由（textfile / ASS）、色は16進検証。
- 出力ファイルは DB 登録済みのものだけをプロジェクト配下パス検証付きで配信。
