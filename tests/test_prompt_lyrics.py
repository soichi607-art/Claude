from app.services import copywriter, lyrics, prompt_builder


INPUTS = {"theme": "Neon Rain", "free_text": "like Some Famous DJ", "genre_modern": "uk_garage", "genre_2010s": "future_bass", "brightness": 80,
          "intensity": 70, "emotion": 40, "festival": 90, "futuristic": 60, "catchiness": 95, "vocal_type": "duet", "vocal_pitch": "high",
          "vocal_tone": "powerful", "ng_words": "gun, blood", "ref_artists": "Some Famous DJ, Other Star", "ref_songs": "Big Hit"}


def test_reference_names_never_reach_prompt():
    neutral, audit = prompt_builder.neutralize_references(INPUTS, {"bpm": 130.2, "key": "A Minor", "timbre": ["bright"], "sections": [{"high": True}], "energy": [0.7, 0.8]})
    assert "Some Famous DJ" not in neutral and "Big Hit" not in neutral
    assert "130 bpm" in neutral and "A Minor" in neutral
    assert audit["after"]["names_removed"] is True
    caption = prompt_builder.build_caption(INPUTS, "drop", neutral)
    assert "Some Famous DJ" not in caption and "Other Star" not in caption
    assert "uk garage" in caption and "future bass" in caption and "duet" in caption and "massive festival" in caption
    assert "massive, satisfying drop" in caption


def test_neutralize_without_analysis_is_empty():
    neutral, audit = prompt_builder.neutralize_references(INPUTS, None)
    assert neutral == ""
    assert audit["after"]["names_removed"] is True


def test_ng_words_detected_and_lyrics_bilingual():
    assert prompt_builder.contains_ng("a gun in the rain", "gun, blood") == ["gun"]
    en, ja = lyrics.generate(INPUTS, 42, 150, "catchy")
    en_lines = [l for l in en.splitlines() if l.strip()]
    ja_lines = [l for l in ja.splitlines() if l.strip()]
    assert len(en_lines) == len(ja_lines)
    assert "[chorus]" in en and "Neon Rain" in en
    assert not any(w in en.lower() for w in ("gun", "blood"))
    en2, _ = lyrics.generate(INPUTS, 42, 150, "catchy")
    assert en2 == en  # deterministic
    en3, _ = lyrics.generate(INPUTS, 43, 150, "catchy")
    assert en3 != en


def test_copy_and_story_vary_by_seed():
    s1, s2 = copywriter.build_story(INPUTS, 1), copywriter.build_story(INPUTS, 2)
    assert s1 != s2
    c = copywriter.build_copy("Neon Rain", INPUTS, "AERA", 5, s1)
    assert "AERA" in c["youtube_title"] and "#EDM" in c["hashtags"]
    assert "Some Famous DJ" not in c["youtube_description"]
    assert "AI" in c["youtube_description"]
    assert prompt_builder.default_bpm({"genre_modern": "dnb"}) == 173
    assert prompt_builder.default_bpm({"bpm": "140"}) == 140
