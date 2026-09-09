# ハードウェア診断レポート

- 生成日時: 2026-09-09T15:56:16+00:00
- 注意: このレポートは **このスクリプトを実行したマシン** の実測値です。別のPCで使う場合は `python scripts/diagnose.py` を再実行してください。

## OS
- System: Linux 6.18.44-fc-v24
- Version: #1 SMP PREEMPT_DYNAMIC @0
- Arch: x86_64

## CPU
- 名称: Intel(R) Xeon(R) Processor @ 2.10GHz
- 論理コア: 4 / 物理コア: 4

## メモリ
- 合計: 16.9 GB / 利用可能: 16.1 GB

## ストレージ
- パス: /home/user/Claude/data/tmp
- 合計: 270.6 GB / 空き: 31.2 GB

## GPU
- 検出元: none
- デバイス: 未確認
- VRAM: 未確認

## Intel XPU (torch.xpu)
- torch インストール: なし
- torch.xpu.is_available(): 未確認
- デバイス名: 未確認
- 備考: torch未インストール（ACE-Stepのvenv内で再診断してください）

## ツールチェーン
- Python: 3.11.15 (/usr/local/bin/python3)
- Node.js: v22.22.2
- Git: git version 2.43.0
- FFmpeg: ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers
- ffprobe: ffprobe version 6.1.1-3ubuntu5 Copyright (c) 2007-2023 the FFmpeg developers

## Intel Quick Sync Video
- エンコーダー有り (h264_qsv)。実動作は要テスト

## 動画エンコーダー（ffmpeg -encoders）
- libx264: あり
- h264_qsv: あり
- h264_vaapi: あり
- h264_videotoolbox: なし
- h264_nvenc: あり
- h264_amf: なし
- aac: あり
- libx265: あり
- hevc_qsv: あり

## エンコーダー実動作テスト（1秒のテスト映像を実際にエンコード）
- h264_qsv: 失敗 — [h264_qsv @ 0x5626adf505c0] Error creating a MFX session: -9.
[vost#0:0/h264_qsv @ 0x5626adf501c0] Error while opening encoder - maybe incorrect parameters such
- h264_vaapi: 失敗 — [AVHWDeviceContext @ 0x55aa4504bf40] No VA display found for device /dev/dri/renderD128.
Device creation failed: -22.
Failed to set value '/dev/dri/renderD128' 
- libx264: 成功 — OK
- **採用エンコーダー: libx264**

## ACE-Step 1.5
- ディレクトリ: 未設定 (存在: False)
- venv: 未確認
- API URL: 未設定
- /health: 未確認

## 電源・温度
- バッテリー: {'present': False}
- 温度センサー: {'available': False}

## 判定
- Intel XPU: 未確認（ACE-Step の venv で `python scripts/diagnose.py` を再実行）
- 動画エンコード: libx264 を使用
