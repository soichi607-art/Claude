from pathlib import Path

import pytest
from fastapi import HTTPException

from app import security


def test_safe_filename_strips_paths_and_unicode():
    assert security.safe_filename("../../etc/passwd") == "passwd"
    assert security.safe_filename("C:\\Users\\x\\song ファイル.wav") == "song_.wav"
    assert security.safe_filename("") == "file"


def test_ensure_inside_rejects_traversal(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    assert security.ensure_inside(base, base / "a.txt") == (base / "a.txt").resolve()
    with pytest.raises(HTTPException):
        security.ensure_inside(base, base / ".." / "evil.txt")


def test_validate_upload_checks_magic_and_ext():
    wav_head = b"RIFF\x00\x00\x00\x00WAVEfmt "
    assert security.validate_upload("song.wav", wav_head, 1000, "audio") == "song.wav"
    with pytest.raises(HTTPException):
        security.validate_upload("song.exe", wav_head, 1000, "audio")
    with pytest.raises(HTTPException):
        security.validate_upload("song.wav", b"MZ\x90\x00" + b"\x00" * 12, 1000, "audio")
    with pytest.raises(HTTPException):
        security.validate_upload("song.wav", wav_head, 0, "audio")
    with pytest.raises(HTTPException):
        security.validate_upload("song.wav", wav_head, 10**12, "audio")
    assert security.validate_upload("img.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, 10, "image") == "img.png"
    assert security.validate_upload("clips.zip", b"PK\x03\x04" + b"\x00" * 12, 10, "zip") == "clips.zip"


def test_redact_hides_keys():
    out = security.redact("Authorization: Bearer abcdefghijklmnop1234")
    assert "abcdefghijklmnop1234" not in out


def test_ffmpeg_found_in_tools_folder_without_bin(tmp_path, monkeypatch):
    """A portable FFmpeg dropped anywhere under tools/ is found even when PATH has none."""
    from app.services import ffmpeg as ff

    fake_root = tmp_path / "ffmpeg-8.0-essentials_build" / "somewhere" / "deep"
    fake_root.mkdir(parents=True)
    (fake_root / "ffmpeg").write_text("#!/bin/sh\n")
    monkeypatch.setattr(ff.settings, "ffmpeg_bin", "definitely-not-on-path-ffmpeg")
    monkeypatch.setattr(ff.shutil, "which", lambda *_a, **_k: None)  # simulate: nothing on PATH
    monkeypatch.setattr(ff, "_candidate_roots", lambda: [])
    ff._FOUND.clear()
    assert ff.find_binary("ffmpeg", extra_roots=[tmp_path]) == str(fake_root / "ffmpeg")
    ff._FOUND.clear()
    assert ff.find_binary("ffmpeg") is None
    ff._FOUND.clear()
