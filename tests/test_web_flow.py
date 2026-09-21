import io
import zipfile
from pathlib import Path

from app.services import packaging, shorts_builder


PROJECT = {"title": "Neon Rain", "theme": "Neon Rain", "genre_modern": "uk_garage", "genre_2010s": "future_bass", "brightness": 70, "intensity": 60,
           "emotion": 50, "festival": 60, "futuristic": 70, "catchiness": 80, "vocal_type": "female", "vocal_pitch": "mid", "vocal_tone": "bright",
           "duration_target": 150, "mode": "eco", "ref_artists": "Some Famous DJ"}


def test_pages_render(client):
    for url in ["/", "/projects/new", "/jobs", "/jobs/partial", "/characters", "/analytics", "/settings", "/manifest.webmanifest", "/sw.js", "/healthz"]:
        r = client.get(url)
        assert r.status_code == 200, url
    assert client.get("/projects/999").status_code == 404


def test_csrf_required(client):
    assert client.post("/projects/new", data=PROJECT).status_code == 403
    assert client.post("/projects/new", data={**PROJECT, "csrf_token": "bad"}).status_code == 403


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Frame-Options"] == "DENY" and "Content-Security-Policy" in r.headers


def test_project_flow(client, csrf, test_audio_40: Path):
    r = client.post("/projects/new", data={**PROJECT, "csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects/1"
    page = client.get("/projects/1").text
    assert "Some Famous DJ" not in page.split("参考情報")[0]  # never in prompts section
    assert "案 A" in page and "案 C" in page
    # generation blocked until 10s/30s tests pass
    r = client.post("/projects/1/generate", data={"csrf_token": csrf, "mode": "eco"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects/1"
    # upload requires the originality confirmation
    with open(test_audio_40, "rb") as f:
        r = client.post("/projects/1/candidates/1/upload", data={"csrf_token": csrf}, files={"audio": ("song.wav", f, "audio/wav")})
    assert r.status_code == 400
    with open(test_audio_40, "rb") as f:
        r = client.post("/projects/1/candidates/1/upload", data={"csrf_token": csrf, "original": "on"}, files={"audio": ("song.wav", f, "audio/wav")}, follow_redirects=False)
    assert r.status_code == 303
    # wrong content
    r = client.post("/projects/1/candidates/2/upload", data={"csrf_token": csrf, "original": "on"}, files={"audio": ("song.wav", io.BytesIO(b"MZ" + b"\x00" * 100), "audio/wav")})
    assert r.status_code == 400
    r = client.post("/projects/1/select/1", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects/1/mv"
    assert client.post("/projects/1/select/2", data={"csrf_token": csrf}).status_code == 400
    assert "drop1" in client.get("/projects/1/mv").text
    assert client.get("/projects/1/shorts").status_code == 200
    assert client.get("/projects/1/audio/1").status_code == 200


def test_render_outputs_and_package(client, csrf):
    outs = shorts_builder.render_all(1)
    assert len(outs) == 8
    r = client.post("/projects/1/publish/package", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303
    r = client.get("/projects/1/files/post_package.zip")
    assert r.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    expected = set(packaging.expected_outputs()) - {"video_generation_pack.zip", "post_package.zip"}
    assert expected <= names
    for name in ("youtube_short_25s.mp4", "tiktok_reward_65s.mp4", "full_mv_16x9.mp4"):
        assert client.get(f"/projects/1/files/{name}").status_code == 200
    assert client.get("/projects/1/files/../../.env").status_code in (400, 404, 422)
    assert client.get("/projects/1/files/nope.mp4").status_code == 404
    # video pack requires approved character
    r = client.post("/projects/1/mv/pack", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/projects/1/mv/notebook").status_code == 200


def test_character_approval_and_pack(client, csrf, tmp_path):
    from app.services import covers

    img = covers.placeholder_character(tmp_path / "base.png", 256, 256)
    with open(img, "rb") as f:
        r = client.post("/characters/1/image", data={"csrf_token": csrf, "kind": "base", "original": "on"}, files={"image": ("base.png", f, "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/characters/1/image/base").status_code == 200
    assert client.post("/characters/1/approve", data={"csrf_token": csrf, "approver": ""}).status_code == 400
    r = client.post("/characters/1/approve", data={"csrf_token": csrf, "approver": "代表", "confirm": "on"}, follow_redirects=False)
    assert r.status_code == 303
    assert "確定済み" in client.get("/characters").text
    r = client.post("/projects/1/mv/pack", data={"csrf_token": csrf}, follow_redirects=False)
    r = client.get("/projects/1/files/video_generation_pack.zip")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "scenes.json" in names and "character/base.png" in names and "negative_prompt.txt" in names and "README_GENERATION_STEPS.md" in names
    assert any(n.startswith("prompts/") for n in names)
    txt = z.read("prompts/04_drop1.txt").decode()
    for tag in ("[CHARACTER]", "[ACTION]", "[ENVIRONMENT]", "[CAMERA]", "[LIGHTING]", "[MOOD]", "[TECHNICAL]"):
        assert tag in txt


def test_ai_clip_import_and_swap(client, csrf, test_audio):
    out_dir = Path(client.get("/projects/1/files/full_mv_9x16.mp4").headers.get("content-disposition", "") and "")  # noqa
    from app.config import settings

    clip = settings.projects_dir / "1" / "output" / "youtube_short_25s.mp4"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(clip, "results/drop1.mp4")
        z.writestr("results/notes.txt", "x")
        z.writestr("results/unknown.mp4", b"not a video")
    buf.seek(0)
    r = client.post("/projects/1/mv/import", data={"csrf_token": csrf, "license_ok": "on"}, files={"zip": ("ai_clips.zip", buf, "application/zip")}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/projects/1/mv").text
    assert "AI動画" in page
    from app.db import session_scope
    from app.models import SceneClip
    from sqlmodel import select

    with session_scope() as s:
        rows = {r.scene: r for r in s.exec(select(SceneClip).where(SceneClip.project_id == 1)).all()}
    assert rows["drop1"].source == "ai" and Path(rows["drop1"].video_path).exists()
    r = client.post("/projects/1/mv/scene/drop1/clear", data={"csrf_token": csrf, "confirm": "yes"}, follow_redirects=False)
    assert r.status_code == 303
    with session_scope() as s:
        row = s.exec(select(SceneClip).where(SceneClip.project_id == 1, SceneClip.scene == "drop1")).first()
    assert row.source == "motion"


def test_publish_share_and_analytics(client, csrf):
    data = {"csrf_token": csrf, "platform": "tiktok", "output_name": "tiktok_hook_25s.mp4", "title": "T", "caption": "C", "hashtags": "#a"}
    assert client.post("/projects/1/publish/post", data=data).status_code == 400  # checklist incomplete
    data.update({k: "on" for k in ("chk_ai", "chk_commercial", "chk_no_imitation", "chk_no_refnames", "chk_ng", "chk_no_logo", "chk_no_guarantee", "chk_rep")})
    r = client.post("/projects/1/publish/post", data=data, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects/1/share/1"
    page = client.get("/projects/1/share/1").text
    assert "share-btn" in page and "share-fallback" in page and "投稿済み" in page
    r = client.post("/projects/1/share/1/mark", data={"csrf_token": csrf, "status": "posted", "url": "https://example.com/v"}, follow_redirects=False)
    assert r.status_code == 303
    r = client.post("/analytics/1/metric", data={"csrf_token": csrf, "views": "120", "likes": "", "completion_rate": "45.5"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/analytics").text
    assert "120" in page and "未取得" in page and "45.5%" in page
    assert client.post("/analytics/1/metric", data={"csrf_token": csrf, "views": "abc"}).status_code == 400


def test_settings_diagnose_and_acestep_unreachable(client, csrf):
    page = client.get("/settings").text
    assert "未接続" in page
    r = client.post("/settings/acestep/test", data={"csrf_token": csrf, "secs": "10"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings"  # cannot start: unreachable
    r = client.post("/settings/diagnose", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert "採用:" in client.get("/settings").text


def test_delete_requires_confirmation(client, csrf):
    assert client.post("/projects/1/delete", data={"csrf_token": csrf}).status_code == 400


def test_help_and_dashboard_checklist(client):
    page = client.get("/help").text
    assert "全体の流れ" in page and "start_windows.bat" in page
    home = client.get("/").text
    assert "次にやること" in home and "チェックリスト" in home


def test_run_preflight_reports_ok():
    import run

    problems = run.preflight()
    assert problems == [] or all("LAN公開" in p for p in problems)
