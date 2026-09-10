"""Rule-based bilingual lyric generation (EN with faithful JA meaning).

No LLM is used. Each English line is paired with its Japanese meaning so
``lyrics_ja.txt`` is an accurate translation of what the vocal sings, not a
machine guess. Lines are selected deterministically from a project seed so the
same project always regenerates the same lyrics, and different projects differ.
"""
from __future__ import annotations

import random
import re
from typing import Any

from .prompt_builder import contains_ng

# (english, japanese)
BANK: dict[str, list[tuple[str, str]]] = {
    "verse": [
        ("City lights are fading into blue", "街の灯りが青に溶けていく"),
        ("I hear the night calling out your name", "夜が君の名前を呼んでいる"),
        ("Every heartbeat is a countdown to the sky", "鼓動のひとつひとつが空へのカウントダウン"),
        ("Silver shadows dancing on the floor", "銀色の影がフロアで踊る"),
        ("We were made of static and starlight", "僕らはノイズと星の光でできていた"),
        ("Running through the echoes of the rain", "雨のこだまの中を駆け抜けて"),
        ("Neon rivers running through my veins", "ネオンの川が血管を流れる"),
        ("Hold the moment, let the silence break", "この瞬間を掴んで、沈黙を壊そう"),
        ("Glass horizons open up tonight", "ガラスの地平線が今夜開いていく"),
        ("I can feel the gravity let go", "重力が手を離すのを感じる"),
        ("Every wire in the sky is humming low", "空を走るすべての線が低く唸る"),
        ("Footsteps written on a screen of light", "光のスクリーンに刻まれた足音"),
    ],
    "pre": [
        ("Closer, closer, feel the rising tide", "もっと近くへ、満ちてくる潮を感じて"),
        ("Higher, higher, we won't hide", "もっと高く、もう隠れない"),
        ("Count it down, one more breath before we fly", "カウントダウン、飛び立つ前にもう一度息をして"),
        ("Hands up now, the ground is far behind", "手を上げて、地面はもう遥か後ろ"),
        ("Louder, louder, till the walls give way", "もっと大きく、壁が崩れるまで"),
        ("Brighter, brighter, chase the break of day", "もっと明るく、夜明けを追いかけて"),
    ],
    "chorus": [
        ("We are the light in the dark, we are alive", "僕らは闇の中の光、生きている"),
        ("Take me to the edge of the sky tonight", "今夜、空の果てまで連れて行って"),
        ("Burn like a signal, never fade away", "信号のように燃えて、決して消えない"),
        ("Run with me now, we are electric", "今すぐ一緒に走ろう、僕らはエレクトリック"),
        ("Rise up, rise up, through the falling rain", "立ち上がれ、降りしきる雨を抜けて"),
        ("Feel it, feel it, we are infinite", "感じて、感じて、僕らは無限だ"),
        ("Louder than the silence, we ignite", "沈黙より大きく、僕らは火をつける"),
        ("Don't let go, the night is ours tonight", "離さないで、今夜この夜は僕らのもの"),
    ],
    "bridge": [
        ("When the bass falls quiet, I still hear you", "ベースが静まっても、まだ君が聞こえる"),
        ("One more time before the morning comes", "朝が来る前にもう一度だけ"),
        ("Every ending is a door we open wide", "すべての終わりは大きく開く扉"),
        ("Breathe in the static, let it carry us", "ノイズを吸い込んで、運ばれていこう"),
    ],
    "outro": [
        ("We are the light, we are alive", "僕らは光、生きている"),
        ("Never fade, never fade", "消えない、消えない"),
        ("The night is ours", "この夜は僕らのもの"),
        ("Carry me home on the sound", "音に乗せて家まで連れて帰って"),
    ],
}

THEME_HOOKS: list[tuple[str, str]] = [
    ("{theme}, {theme}, echo in my mind", "{theme}、{theme}、心に響く"),
    ("This is our {theme} tonight", "これが今夜の僕らの{theme}"),
    ("{theme} in the neon light", "ネオンの光の中の{theme}"),
]

STRUCTURES = {
    30: ["[intro]", "[chorus]"],
    60: ["[intro]", "[verse]", "[pre-chorus]", "[chorus]"],
    120: ["[intro]", "[verse]", "[pre-chorus]", "[chorus]", "[verse]", "[chorus]", "[outro]"],
    180: ["[intro]", "[verse]", "[pre-chorus]", "[chorus]", "[verse]", "[pre-chorus]", "[chorus]", "[bridge]", "[chorus]", "[outro]"],
}

_ASCII_THEME = re.compile(r"^[A-Za-z0-9 '\-]{2,24}$")


def _structure(duration_s: int) -> list[str]:
    for limit in sorted(STRUCTURES):
        if duration_s <= limit:
            return STRUCTURES[limit]
    return STRUCTURES[180]


def generate(inputs: dict[str, Any], seed: int, duration_s: int = 30, focus: str = "catchy") -> tuple[str, str]:
    """Return (lyrics_en, lyrics_ja) with matching section tags."""
    rng = random.Random(seed)
    ng = inputs.get("ng_words", "")
    theme_raw = (inputs.get("theme") or "").strip()
    theme_en = theme_raw if _ASCII_THEME.match(theme_raw) else ""

    def pick(kind: str, n: int) -> list[tuple[str, str]]:
        pool = [p for p in BANK[kind] if not contains_ng(p[0], ng)]
        rng.shuffle(pool)
        return pool[:n] if pool else [("(lyric omitted by NG filter)", "（NGワードにより省略）")]

    chorus_lines = pick("chorus", 4)
    if theme_en:
        hook = rng.choice(THEME_HOOKS)
        chorus_lines[0] = (hook[0].format(theme=theme_en), hook[1].format(theme=theme_en))
    if focus == "vocal":
        chorus_lines = chorus_lines[:3]
    en, ja = [], []
    for tag in _structure(duration_s):
        en.append(tag)
        ja.append(tag)
        if tag == "[intro]":
            lines = pick("verse", 1) if duration_s > 30 else []
        elif tag == "[verse]":
            lines = pick("verse", 4)
        elif tag == "[pre-chorus]":
            lines = pick("pre", 2)
        elif tag == "[chorus]":
            lines = chorus_lines
        elif tag == "[bridge]":
            lines = pick("bridge", 2)
        else:
            lines = pick("outro", 2)
        for e, j in lines:
            en.append(e)
            ja.append(j)
        en.append("")
        ja.append("")
    return "\n".join(en).strip() + "\n", "\n".join(ja).strip() + "\n"
