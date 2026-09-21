"""Generate a Colab/Kaggle-compatible .ipynb for the free-GPU video workflow.

The notebook is executed manually by the user. It contains explicit checks:
GPU present → license confirmation cell → 3-5 s test → 6-10 scenes → ZIP.
Model/version specifics that this project could not verify online are left
as clearly marked 「未確認」 fields to be filled from the official pages.
"""
from __future__ import annotations

import json
from pathlib import Path


def _md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text}


def _code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text}


def build_notebook(out: Path, title: str = "SoA EDM Studio – Free GPU Video Notebook") -> Path:
    cells = [
        _md(f"# {title}\n\n"
            "このノートブックは **手動で** 実行してください（自動化・常設化・複数アカウント利用は禁止）。\n\n"
            "1. `video_generation_pack.zip` をアップロード\n2. GPU 確認\n3. ライセンス確認（確認日・URLを記録）\n4. モデル取得\n5. 3〜5秒テスト生成\n6. 6〜10シーン生成\n7. ZIP ダウンロード → SoA EDM Studio に取り込み\n\n"
            "> 無料GPUの割当・時間・提供継続は保証されません。割当がない場合は中止し、FFmpegモーショングラフィックス版で完成させてください。"),
        _code("# 1. ZIP アップロード（Colab の場合）。Kaggle の場合は Data > Upload から追加し、パスを変更してください。\n"
              "import os, zipfile, json\n"
              "try:\n    from google.colab import files  # type: ignore\n    up = files.upload()\n    zip_name = next(iter(up))\nexcept Exception:\n    zip_name = 'video_generation_pack.zip'  # Kaggle: /kaggle/input/... に合わせて変更\n"
              "os.makedirs('pack', exist_ok=True)\n"
              "with zipfile.ZipFile(zip_name) as z:\n    z.extractall('pack')\n"
              "scenes = json.load(open('pack/scenes.json', encoding='utf-8'))\n"
              "print(len(scenes), 'scenes'); print(os.listdir('pack/character'))"),
        _code("# 2. GPU 確認（割当がなければここで中止）\n"
              "import subprocess\n"
              "r = subprocess.run(['nvidia-smi'], capture_output=True, text=True)\n"
              "print(r.stdout or r.stderr)\n"
              "assert r.returncode == 0, 'GPU が割り当てられていません。中止して FFmpeg 版で完成させてください。'"),
        _md("## 3. ライセンス確認（必須・未確認のまま進まない）\n\n"
            "使用するモデルの **公式ページ** でライセンスと商用利用条件を確認し、下のセルに記入してください。\n\n"
            "- Wan2.1（候補）: https://github.com/Wan-Video/Wan2.1 — リポジトリの LICENSE.txt は Apache-2.0（2026-09-09 確認）。モデル重み（Hugging Face `Wan-AI/Wan2.1-*`）のライセンス表記は **未確認** → 使用時に確認して記録\n"
            "- Google Colab の利用規約・制限: https://research.google.com/colaboratory/faq.html （**未確認**: 使用時に確認）\n"
            "- Kaggle Notebooks の GPU 制限: https://www.kaggle.com/docs/notebooks （**未確認**: 使用時に確認）"),
        _code("LICENSE_CONFIRMED = False  # 公式ページで確認したら True にする\n"
              "LICENSE_NOTE = {\n    'model': '未確認',\n    'model_url': '未確認',\n    'license': '未確認',\n    'commercial_use': '未確認',\n    'checked_on': '未確認 (YYYY-MM-DD)',\n    'service_terms_url': '未確認',\n}\n"
              "assert LICENSE_CONFIRMED, 'ライセンスと商用利用条件を確認してから進めてください'\n"
              "json.dump(LICENSE_NOTE, open('pack/license_check.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)"),
        _md("## 4. モデル取得\n\n"
            "Wan2.1 公式 README（2026-09-09 確認）の記載:\n"
            "- `T2V-1.3B` は「requires only 8.19 GB VRAM」\n"
            "- I2V は 14B（480P / 720P）のみ → 無料GPU（例: T4 16GB）では **動作未確認**。まず T2V-1.3B でテストし、キャラクター基準画像の一致は I2V が使えないと限定的です。\n\n"
            "以下は公式 README のコマンド形式です。実行前に README の最新版を確認してください。"),
        _code("# 公式 README (https://github.com/Wan-Video/Wan2.1) の手順に従う。バージョン変更に注意。\n"
              "!git clone https://github.com/Wan-Video/Wan2.1.git\n"
              "%cd Wan2.1\n"
              "!pip install -q -r requirements.txt\n"
              "!pip install -q 'huggingface_hub[cli]'\n"
              "!huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B --local-dir ./Wan2.1-T2V-1.3B\n"
              "%cd .."),
        _code("# 5. 3〜5秒テスト生成（1本）。失敗したらここで中止。\n"
              "import subprocess, time\n"
              "test = scenes[0]\n"
              "t0 = time.time()\n"
              "cmd = ['python', 'Wan2.1/generate.py', '--task', 't2v-1.3B', '--size', '832*480', '--ckpt_dir', 'Wan2.1/Wan2.1-T2V-1.3B',\n"
              "       '--offload_model', 'True', '--t5_cpu', '--prompt', test['prompt'].replace('\\n', ' ')]\n"
              "print(' '.join(cmd[:8]), '...')\n"
              "r = subprocess.run(cmd, capture_output=True, text=True)\n"
              "print(r.stdout[-2000:], r.stderr[-2000:])\n"
              "print('elapsed', round(time.time()-t0), 's')\n"
              "assert r.returncode == 0, 'テスト生成に失敗。設定を見直すか中止してください。'"),
        _md("> `generate.py` の出力ファイル名・フレーム数オプション（3〜5秒相当）は使用時点の README で確認してください（本ノートブック作成時点では **未確認**）。"),
        _code("# 6. 6〜10 シーン生成（テスト成功後のみ）\n"
              "import glob, shutil, os\n"
              "os.makedirs('pack/results', exist_ok=True)\n"
              "for sc in scenes[:10]:\n"
              "    cmd = ['python', 'Wan2.1/generate.py', '--task', 't2v-1.3B', '--size', '832*480', '--ckpt_dir', 'Wan2.1/Wan2.1-T2V-1.3B',\n"
              "           '--offload_model', 'True', '--t5_cpu', '--prompt', sc['prompt'].replace('\\n', ' ')]\n"
              "    r = subprocess.run(cmd, capture_output=True, text=True)\n"
              "    outs = sorted(glob.glob('*.mp4') + glob.glob('Wan2.1/*.mp4'), key=os.path.getmtime)\n"
              "    if r.returncode == 0 and outs:\n"
              "        shutil.move(outs[-1], f\"pack/results/{sc['scene']}.mp4\")\n"
              "        print('ok', sc['scene'])\n"
              "    else:\n"
              "        print('failed', sc['scene'], r.stderr[-500:])"),
        _code("# 7. ZIP ダウンロード\n"
              "shutil.make_archive('ai_clips', 'zip', 'pack/results')\n"
              "shutil.copy('pack/license_check.json', 'license_check.json')\n"
              "try:\n    from google.colab import files  # type: ignore\n    files.download('ai_clips.zip')\nexcept Exception:\n    print('ai_clips.zip を Output からダウンロードしてください')"),
        _md("## 8. SoA EDM Studio に取り込み\n\nMV編集画面 →「AI動画ZIP取り込み」で `ai_clips.zip` をアップロード → MVを再生成。"),
    ]
    nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
