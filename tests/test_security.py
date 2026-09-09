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
