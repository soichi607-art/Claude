"""Text outputs, video_generation_pack.zip and post_package.zip."""
from __future__ import annotations

import datetime as dt
import json
import zipfile
from pathlib import Path
from typing import Any

from sqlmodel import select

from ..config import settings
from ..db import session_scope
from ..models import Character, CharacterImage, Project, RenderOutput, SceneClip
from . import copywriter, covers, mv_builder

SCENE_LABELS = {"hook": "Hook", "intro": "Intro", "verse": "Verse", "buildup": "Build-up", "drop1": "Drop 1", "break": "Break", "final_drop": "Final Drop", "outro": "Outro"}
TECHNICAL = "cinematic music video, coherent motion, consistent identity, realistic anatomy, clean frames, no text, no watermark"
VIDEO_NEGATIVE = ("identity change, different person, different face, different hairstyle, different costume, child, celebrity, face morphing, "
                  "facial distortion, body deformation, extra limbs, duplicated body, broken hands, unstable eyes, flickering face, melting objects, "
                  "random people, sudden scene change, camera jitter, text, subtitles, logo, watermark, low quality")
CHARACTER_BLOCK = ("AERA, the exact same original virtual EDM artist from the reference image, androgynous adult, short asymmetrical hair fading from "
                   "metallic silver to pale cyan, luminous soft-cyan eyes, small triangular light pattern beside the left eye, translucent futuristic ear device")

SCENE_ACTIONS = {
    "hook": ("looks straight into the camera and lifts one hand as light ignites", "push-in", "hard cyan key light with violet rim", "electric anticipation"),
    "intro": ("stands still, breathing slowly, eyes closed then opening", "slow orbit", "dim cool ambient light with a single cyan glow", "calm, expectant"),
    "verse": ("walks slowly forward, glancing sideways", "lateral tracking", "soft blue fill, warm edge light", "reflective"),
    "buildup": ("raises both arms gradually as lights brighten", "slow crane up", "rising intensity, cyan strobes fading in", "tension"),
    "drop1": ("performs energetically, head moving with the beat", "fast orbit", "intense cyan and violet strobes, volumetric beams", "explosive, euphoric"),
    "break": ("turns away, silhouette against soft light", "dolly back", "low-key silhouette lighting, pale cyan haze", "intimate, quiet"),
    "final_drop": ("spins and throws a hand toward the sky", "whip pan into orbit", "maximum brightness, amber accents on cyan", "triumphant"),
    "outro": ("walks away into distance, looking back once", "static wide", "lights dimming to a single cyan point", "resolved, hopeful"),
}


def scene_prompts(project: Project, character_name: str, story: dict[str, Any]) -> list[dict[str, Any]]:
    env = story.get("environment", "vast futuristic environment")
    wardrobe = story.get("wardrobe", "elegant black and silver performance outfit with subtle cyan light lines")
    palette = story.get("palette", "cyan / violet")
    base_seed = mv_builder.hexcolor(story.get("accent_hex", "")) and (project.id or 1) * 1009
    out = []
    for i, scene in enumerate(mv_builder.SCENES):
        action, camera, lighting, mood = SCENE_ACTIONS[scene]
        prompt = "\n".join([
            f"[CHARACTER] {CHARACTER_BLOCK.replace('AERA', character_name)}, wearing {wardrobe}",
            f"[ACTION] {action}",
            f"[ENVIRONMENT] {env}",
            f"[CAMERA] {camera}",
            f"[LIGHTING] {lighting}; palette {palette}",
            f"[MOOD] {mood}",
            f"[TECHNICAL] {TECHNICAL}",
        ])
        out.append({"scene": scene, "label": SCENE_LABELS[scene], "order": i, "prompt": prompt, "negative_prompt": VIDEO_NEGATIVE,
                    "seed": base_seed + i * 7, "camera": camera, "lighting": lighting, "action": action, "environment": env, "mood": mood,
                    "target_seconds": 5})
    return out


def sync_scene_rows(project_id: int, prompts: list[dict[str, Any]]) -> None:
    with session_scope() as s:
        existing = {r.scene: r for r in s.exec(select(SceneClip).where(SceneClip.project_id == project_id)).all()}
        for p in prompts:
            row = existing.get(p["scene"]) or SceneClip(project_id=project_id, scene=p["scene"])
            row.order = p["order"]
            row.prompt = p["prompt"]
            row.negative_prompt = p["negative_prompt"]
            row.seed = p["seed"]
            row.camera = p["camera"]
            row.lighting = p["lighting"]
            row.action = p["action"]
            row.environment = p["environment"]
            row.mood = p["mood"]
            s.add(row)
        s.commit()


def write_text_outputs(project_id: int) -> dict[str, Path]:
    with session_scope() as s:
        p = s.get(Project, project_id)
        if not p:
            raise ValueError("project not found")
        ch = s.get(Character, p.character_id) if p.character_id else s.exec(select(Character).where(Character.is_active == True)).first()  # noqa: E712
        artist = ch.name if ch else "AERA"
        story = p.story
        inputs = p.inputs
        title = p.title or inputs.get("theme") or "Untitled"
        seed = (p.id or 1) * 131
        copy = copywriter.build_copy(title, inputs, artist, seed, story)
        lyrics_en, lyrics_ja = p.lyrics_en, p.lyrics_ja
    out_dir = mv_builder.project_dir(project_id) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "lyrics_en.txt": lyrics_en,
        "lyrics_ja.txt": lyrics_ja,
        "youtube_title.txt": copy["youtube_title"],
        "youtube_description.txt": copy["youtube_description"],
        "tiktok_caption.txt": copy["tiktok_caption"],
        "hashtags.txt": copy["hashtags"],
        "disclosure_checklist.txt": copywriter.disclosure_checklist(),
    }
    paths = {}
    for name, text in files.items():
        path = out_dir / name
        path.write_text(text or "", encoding="utf-8")
        paths[name] = path
        mv_builder.register_output(project_id, name, path, "text")
    return paths


def write_covers(project_id: int) -> dict[str, Path]:
    with session_scope() as s:
        p = s.get(Project, project_id)
        ch, img = mv_builder.character_assets(s, p)
        artist = ch.name if ch else "AERA"
        accent = p.story.get("accent_hex") or (ch.theme_color if ch else "#37E5FF")
        title = p.title or p.inputs.get("theme") or "Untitled"
        subtitle = p.story.get("concept_ja", "")
    out_dir = mv_builder.project_dir(project_id) / "output"
    res = covers.make_all_covers(out_dir, title, artist, accent, img if (ch and ch.approved) else None, (project_id or 1) * 3, subtitle)
    for name, path in res.items():
        mv_builder.register_output(project_id, name, path, "image")
    return res


def build_video_generation_pack(project_id: int) -> Path:
    with session_scope() as s:
        p = s.get(Project, project_id)
        if not p:
            raise ValueError("project not found")
        ch, img = mv_builder.character_assets(s, p)
        if not ch or not ch.approved:
            raise ValueError("代表者がキャラクター基準画像を承認するまで video_generation_pack は出力できません。")
        images = s.exec(select(CharacterImage).where(CharacterImage.character_id == ch.id)).all()
        story = p.story
        prompts = scene_prompts(p, ch.name, story)
        audio = mv_builder.selected_audio(p, s)
        info = {
            "project_id": p.id, "title": p.title, "artist": ch.name, "mode": p.mode, "inputs": p.inputs, "story": story,
            "lyrics_en": p.lyrics_en, "character_prompt": ch.prompt, "character_negative": ch.negative_prompt, "character_seed": ch.seed,
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
    sync_scene_rows(project_id, prompts)
    out_dir = mv_builder.project_dir(project_id) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / "video_generation_pack.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for im in images:
            if Path(im.path).exists():
                z.write(im.path, f"character/{im.kind}{Path(im.path).suffix.lower()}")
        z.writestr("song_info.json", json.dumps(info, ensure_ascii=False, indent=2))
        z.writestr("scenes.json", json.dumps(prompts, ensure_ascii=False, indent=2))
        for pr in prompts:
            z.writestr(f"prompts/{pr['order']:02d}_{pr['scene']}.txt", pr["prompt"] + "\n\nNEGATIVE:\n" + pr["negative_prompt"] + f"\n\nSEED: {pr['seed']}\nTARGET_SECONDS: {pr['target_seconds']}\n")
        z.writestr("negative_prompt.txt", VIDEO_NEGATIVE)
        z.writestr("README_GENERATION_STEPS.md", GENERATION_STEPS_MD)
        z.writestr("results/README.txt", "生成した動画をこのフォルダに scene名.mp4 (例: drop1.mp4) で保存し、フォルダごとZIPして SoA EDM Studio に取り込んでください。\n")
        if audio and audio.exists():
            z.write(audio, f"audio/{audio.name}")
    mv_builder.register_output(project_id, "video_generation_pack.zip", zpath, "zip")
    return zpath


GENERATION_STEPS_MD = """# 生成手順（無料GPU Notebook）

1. Google Colab または Kaggle Notebook を **手動で** 開き、docs/FREE_VIDEO_NOTEBOOK.md の手順に従う
2. この ZIP をアップロード
3. GPU の割当を確認（割当がない場合は中止し、FFmpeg モーショングラフィックス版で完成させる）
4. モデルを取得（使用時点のライセンス・商用利用条件を必ず確認し、確認日と URL を記録）
5. 3〜5 秒のテスト生成を 1 本行う
6. 成功したら scenes.json の順に 6〜10 シーンを生成（各 3〜5 秒）
7. results/ に scene名.mp4 で保存し、ZIP でダウンロード
8. SoA EDM Studio の「MV編集」→「AI動画ZIP取り込み」でアップロード

禁止: 制限回避、複数アカウント、常設サーバー化、他者の顔・声・楽曲の模倣。
"""


def build_post_package(project_id: int) -> Path:
    out_dir = mv_builder.project_dir(project_id) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_text_outputs(project_id)
    write_covers(project_id)
    with session_scope() as s:
        rows = s.exec(select(RenderOutput).where(RenderOutput.project_id == project_id)).all()
    zpath = out_dir / "post_package.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            if r.name.endswith(".zip"):
                continue
            if Path(r.path).exists():
                z.write(r.path, r.name)
        z.writestr("README.txt", "SoA EDM Studio 投稿パッケージ\n動画・サムネイル・タイトル・投稿文・ハッシュタグ・申告チェックリストが含まれます。\n投稿は代表者が iPhone で最終確認して公開してください。\n")
    mv_builder.register_output(project_id, "post_package.zip", zpath, "zip")
    return zpath


def expected_outputs() -> list[str]:
    return [
        "youtube_short_25s.mp4", "youtube_short_65s.mp4", "youtube_short_90s.mp4",
        "tiktok_hook_25s.mp4", "tiktok_reward_65s.mp4", "tiktok_story_90s.mp4",
        "full_mv_9x16.mp4", "full_mv_16x9.mp4",
        "cover_1x1.png", "cover_9x16.png", "thumbnail_16x9.png",
        "lyrics_en.txt", "lyrics_ja.txt", "youtube_title.txt", "youtube_description.txt", "tiktok_caption.txt", "hashtags.txt",
        "disclosure_checklist.txt", "video_generation_pack.zip", "post_package.zip",
    ]
