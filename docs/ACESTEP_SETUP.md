# ACE-Step 1.5 セットアップ（SoA EDM Studio 用）

確認日: 2026-09-09 / 出典: https://github.com/ace-step/ACE-Step-1.5 （commit ca1e85f, 2026-08-29）の README.md, docs/en/INSTALL.md, docs/en/API.md, README-XPU.md

本アプリは ACE-Step を **別プロセスの REST API サーバー** として利用します（ADR-002）。使用エンドポイントは公式 API.md 記載の `/health`, `/v1/models`, `/v1/stats`, `/release_task`, `/query_result`, `/v1/audio` のみです。

## 1. 前提（公式記載）

| 項目 | 公式記載 |
|---|---|
| Python | 3.11–3.12（XPU は 3.11 推奨） |
| デバイス | 「CUDA GPU recommended (also supports MPS / ROCm / Intel XPU / CPU)」 |
| CPU | 「ACE-Step can run on CPU for inference only, but performance will be significantly slower.」DiT-only（`ACESTEP_INIT_LLM=false`）推奨 |
| Intel GPU | Windows の Ultra 9 285H 内蔵GPUでテスト済み。「Intel discrete GPUs are expected to work but not yet tested」。nanovllm 非対応 |
| VRAM ≤6GB の推奨 | 「2B turbo」+「INT8 quantization + full CPU offload」、LM 無効 |
| ライセンス | コード: MIT。**モデル重み（Hugging Face ACE-Step/*）のライセンス表記は本セッションで未確認** → 導入時に各モデルカードで確認し、下の記録欄に記入 |

> Core 5 120U（内蔵GPU、共有メモリ16GB）での動作は **未確認** です。10秒→30秒テストの実測で判断してください。

## 2. Windows + Intel 内蔵GPU（XPU）で試す

公式 README-XPU.md の手順:

```bat
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
setup_xpu.bat            REM venv_xpu を作成し PyTorch XPU + 依存をインストール（5〜10GB）
start_api_server_xpu.bat REM REST API を 127.0.0.1:8001 で起動
```

XPU 検出確認（公式）:
```bat
call venv_xpu\Scripts\activate
python -c "import torch; print(torch.xpu.is_available())"
```
`False` なら Intel GPU ドライバー更新、または公式 Troubleshooting の再インストール手順へ。

## 3. CPU のみで試す

```bash
uv sync
# .env に以下（公式 INSTALL.md「CPU-Only Mode」）
ACESTEP_INIT_LLM=false
ACESTEP_DEVICE=cpu
uv run acestep-api        # 127.0.0.1:8001
```
CPU 実行は「significantly slower」（公式）。実測が長すぎる場合は手動アップロード運用へ。

## 4. SoA EDM Studio 側の設定

`.env`:
```
ACESTEP_DIR=C:\ACE-Step-1.5
ACESTEP_API_URL=http://127.0.0.1:8001
ACESTEP_API_KEY=            # サーバー側で ACESTEP_API_KEY を設定した場合のみ同じ値
```

設定画面 → 「10秒テストを実行」→ 成功後「30秒テストを実行」。両方成功して初めて3案生成が有効化されます。完了予定時刻は実測値の中央値からのみ算出します（推測はしません）。

## 5. 本アプリが送る主なパラメータ（API.md 準拠）

`prompt`, `lyrics`, `audio_duration`(10–600), `bpm`, `key_scale`, `inference_steps`(turbo 既定 8), `use_random_seed=false` + `seed`, `audio_format=wav`, `thinking`(既定 false), `vocal_language=en`, `use_cot_caption=false`, `use_cot_language=false`, `batch_size=1`

## 6. 手動アップロード（ACE-Step が使えない場合）

プロジェクト画面 → 各案の「手動アップロード」。権利確認済みのオリジナル音源のみ。MV・ショート・投稿パッケージは ACE-Step なしで完成できます。

## 7. ライセンス確認記録（導入時に記入）

| モデル | URL | ライセンス | 商用利用 | 確認日 |
|---|---|---|---|---|
| acestep-v15-turbo | https://huggingface.co/ACE-Step/acestep-v15-turbo | 未確認 | 未確認 | 未確認 |
| acestep-5Hz-lm-0.6B | https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B | 未確認 | 未確認 | 未確認 |
