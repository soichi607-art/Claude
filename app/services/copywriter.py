"""Template-based titles, descriptions, captions, hashtags — varied per project seed."""
from __future__ import annotations

import random
from typing import Any

from .prompt_builder import EDM_2010S, MODERN_GENRES

TITLE_PATTERNS = [
    "{artist} - {theme} (Official AI Music Video)",
    "{artist} | {theme} [{genre}]",
    "{theme} — {artist} ({genre} / AI Vocal EDM)",
    "{artist} “{theme}” Official Visualizer",
]
SHORT_TITLE_PATTERNS = [
    "{theme} 🔊 {artist} #{genre_tag}",
    "{artist} – {theme} (Drop)",
    "{theme} | {artist}",
]
STORY_SEEDS = [
    ("光の都市からの脱出", "escape from a city of light", "midnight metropolis of glass towers", "cyan / violet", "slow orbit → push-in"),
    ("海底の観測所", "a signal from an undersea observatory", "abyssal research station with bioluminescent glow", "teal / deep blue", "dolly forward → tilt up"),
    ("砂漠のアンテナ", "a lone antenna in a desert dawn", "endless dunes under a pale dawn sky with a giant antenna", "amber / cyan", "crane up → wide"),
    ("軌道上の温室", "a greenhouse in orbit", "orbital greenhouse with Earth rising behind glass", "green / silver", "lateral track → orbit"),
    ("雨の駅", "a last train in the rain", "rain-soaked futuristic train platform", "magenta / cyan", "handheld drift → static"),
    ("氷の大聖堂", "a cathedral of ice", "cathedral carved from ice lit from within", "ice blue / white", "slow tilt down → orbit"),
    ("信号塔の夜", "the night the towers spoke", "field of glowing signal towers", "violet / amber", "push-in → whip pan"),
    ("鏡の回廊", "corridor of mirrors", "infinite mirrored corridor with drifting light", "silver / cyan", "dolly back → spin"),
]
WARDROBE_VARIANTS = [
    "black performance jacket with subtle cyan light lines",
    "silver layered top with a black high-collar coat",
    "matte black jumpsuit with thin silver seams and cyan accents",
    "black and silver asymmetrical cape over the signature outfit",
]


def genre_label(inputs: dict[str, Any]) -> str:
    g = MODERN_GENRES.get(inputs.get("genre_modern", ""), {}).get("label") or EDM_2010S.get(inputs.get("genre_2010s", ""), {}).get("label")
    return g or "EDM"


def build_story(inputs: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    ja, en, env, palette, camera = rng.choice(STORY_SEEDS)
    return {
        "concept_ja": ja,
        "concept_en": en,
        "environment": env,
        "palette": palette,
        "camera_arc": camera,
        "wardrobe": rng.choice(WARDROBE_VARIANTS),
        "intro_style": rng.choice(["silhouette reveal", "close-up eye light", "wide establishing shot", "detail of ear device"]),
        "ending_style": rng.choice(["walk away into light", "freeze on confident look", "lights power down", "camera rises to sky"]),
        "shot_order": rng.sample(["wide", "medium", "close", "detail", "profile", "full-body"], 6),
        "lyric_style": rng.choice(["center pulse", "lower-third typewriter", "split glitch", "kinetic zoom"]),
        "accent_hex": rng.choice(["#37E5FF", "#8A5CFF", "#FFB347", "#4DFFC3"]),
    }


def build_copy(project_title: str, inputs: dict[str, Any], artist: str, seed: int, story: dict[str, Any]) -> dict[str, str]:
    rng = random.Random(seed + 7)
    genre = genre_label(inputs)
    genre_tag = genre.split("/")[0].strip().replace(" ", "").replace("&", "n")
    theme = project_title or (inputs.get("theme") or "Untitled")
    title = rng.choice(TITLE_PATTERNS).format(artist=artist, theme=theme, genre=genre)
    short_title = rng.choice(SHORT_TITLE_PATTERNS).format(artist=artist, theme=theme, genre_tag=genre_tag)
    base_tags = ["#EDM", f"#{genre_tag}", f"#{artist.replace(' ', '')}", "#AIMusic", "#AIArtist", "#Shorts", "#NewMusic", "#ElectronicMusic", "#VirtualArtist"]
    extra = rng.sample(["#FestivalMusic", "#DanceMusic", "#MusicVideo", "#Drop", "#BassMusic", "#AIVocal", "#ClubMusic", "#NightDrive"], 3)
    hashtags = " ".join(base_tags + extra)
    description = (
        f"{artist} - {theme}\n"
        f"Genre: {genre}\n\n"
        f"{story.get('concept_ja', '')} をテーマにした {artist} のオリジナル楽曲です。\n"
        f"An original {genre} track by the virtual artist {artist}. Concept: {story.get('concept_en', '')}.\n\n"
        "この楽曲・映像はAIツールを用いて制作されたオリジナル作品です（既存楽曲・実在人物の模倣ではありません）。\n"
        "Music, vocals and visuals were created with AI tools. Fully original — no real person or existing song is imitated.\n\n"
        f"{hashtags}"
    )
    caption = f"{short_title}\n{story.get('concept_ja', '')}\nAI制作のオリジナル曲です🎧\n{hashtags}"
    return {
        "youtube_title": title[:100],
        "short_title": short_title[:100],
        "youtube_description": description[:5000],
        "tiktok_caption": caption[:2200],
        "hashtags": hashtags,
    }


def disclosure_checklist(post_platforms: tuple[str, ...] = ("youtube", "tiktok")) -> str:
    return "\n".join([
        "公開前チェックリスト（代表者が確認）",
        "[ ] AI生成コンテンツであることをプラットフォームの申告機能で申告した（YouTube: 「改変または合成されたコンテンツ」の開示 / TikTok: 「AI生成コンテンツ」ラベル）",
        "[ ] 商用コンテンツ（宣伝・ブランド）の該当有無を確認し、該当する場合は申告した",
        "[ ] 実在人物の声・顔・既存曲・歌詞を模倣していない",
        "[ ] 参考アーティスト名・曲名がタイトル/説明/タグに含まれていない",
        "[ ] 歌詞にNGワードが含まれていない",
        "[ ] サムネイル・映像にロゴ・第三者の著作物が含まれていない",
        "[ ] 収益化は保証されない（各プラットフォームの最新規約を確認）",
        "[ ] 各プラットフォームの申告UIの名称・位置は変更される可能性があるため、投稿時点の公式ヘルプを確認した",
    ]) + "\n"
