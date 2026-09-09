"""SQLModel tables. All optional metrics use None to mean 「未取得」 (distinct from 0)."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Optional

from sqlmodel import Field, SQLModel


def now() -> dt.datetime:
    return dt.datetime.now()


class JSONMixin:
    """Helpers for text columns holding JSON."""

    @staticmethod
    def loads(text: str | None, default: Any = None) -> Any:
        if not text:
            return default if default is not None else {}
        try:
            return json.loads(text)
        except ValueError:
            return default if default is not None else {}

    @staticmethod
    def dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False)


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""


class Character(JSONMixin, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "AERA"
    profile: str = ""
    theme_color: str = "#37E5FF"
    theme_color_2: str = "#B8C2CC"
    prompt: str = ""
    negative_prompt: str = ""
    sheet_prompt: str = ""
    seed: Optional[int] = None
    approved: bool = False
    approved_at: Optional[dt.datetime] = None
    approved_by: str = ""
    is_active: bool = True
    created_at: dt.datetime = Field(default_factory=now)


class CharacterImage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    character_id: int = Field(foreign_key="character.id", index=True)
    kind: str  # base / front / profile_left / profile_right / three_quarter / full_front / full_back / expressions / transparent
    path: str
    note: str = ""
    created_at: dt.datetime = Field(default_factory=now)


class Project(JSONMixin, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = ""
    status: str = "draft"  # draft / generating / compare / selected / mv / ready / posted
    mode: str = "eco"  # eco / standard / overnight
    inputs_json: str = "{}"
    story_json: str = "{}"  # per-project uniqueness: theme, narrative, palette, camera, wardrobe...
    neutral_prompt: str = ""
    lyrics_en: str = ""
    lyrics_ja: str = ""
    selected_candidate_id: Optional[int] = None
    character_id: Optional[int] = Field(default=None, foreign_key="character.id")
    created_at: dt.datetime = Field(default_factory=now)
    updated_at: dt.datetime = Field(default_factory=now)

    @property
    def inputs(self) -> dict:
        return self.loads(self.inputs_json)

    @property
    def story(self) -> dict:
        return self.loads(self.story_json)


class Candidate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    label: str  # A / B / C
    focus: str  # catchy / drop / vocal
    prompt: str = ""
    lyrics: str = ""
    target_duration_s: int = 30
    status: str = "pending"  # pending / queued / running / done / failed / uploaded / cancelled
    audio_path: str = ""
    full_audio_path: str = ""  # 2-3 min version after adoption
    seed: Optional[int] = None
    bpm: Optional[int] = None
    key_scale: str = ""
    generation_seconds: Optional[float] = None
    acestep_task_id: str = ""
    error: str = ""
    is_selected: bool = False
    source: str = ""  # acestep / upload
    created_at: dt.datetime = Field(default_factory=now)


class GenerationJob(JSONMixin, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, index=True)
    candidate_id: Optional[int] = None
    kind: str  # acestep_test10 / acestep_test30 / candidate / full / mv / shorts / pack
    status: str = "queued"  # queued / running / done / failed / cancelled / paused
    params_json: str = "{}"
    note: str = ""
    error: str = ""
    created_at: dt.datetime = Field(default_factory=now)
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None
    elapsed_s: Optional[float] = None
    eta_s: Optional[float] = None  # from measured benchmarks only
    progress: int = 0  # 0-100 where measurable, else 0


class ReferenceAudio(JSONMixin, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    filename: str
    path: str
    rights_confirmed: bool = False
    analysis_json: str = "{}"
    analyzed_at: Optional[dt.datetime] = None
    created_at: dt.datetime = Field(default_factory=now)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, index=True)
    kind: str  # prompt_neutralization / approval / delete / share / import
    before: str = ""
    after: str = ""
    actor: str = ""
    created_at: dt.datetime = Field(default_factory=now)


class SceneClip(JSONMixin, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    scene: str  # hook / intro / verse / buildup / drop1 / break / final_drop / outro
    order: int = 0
    prompt: str = ""
    negative_prompt: str = ""
    seed: Optional[int] = None
    camera: str = ""
    lighting: str = ""
    action: str = ""
    environment: str = ""
    mood: str = ""
    source: str = "motion"  # motion (FFmpeg) / ai (imported)
    video_path: str = ""
    duration_s: Optional[float] = None
    created_at: dt.datetime = Field(default_factory=now)


class RenderOutput(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str  # youtube_short_25s.mp4 etc.
    kind: str  # video / image / text / zip
    path: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    encoder: str = ""
    created_at: dt.datetime = Field(default_factory=now)


class PostRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    platform: str  # youtube / tiktok
    output_name: str
    title: str = ""
    caption: str = ""
    hashtags: str = ""
    ai_disclosure: bool = False
    commercial_disclosure: bool = False
    precheck_json: str = "{}"
    approved_by_rep: bool = False
    status: str = "draft"  # draft / ready / shared / posted
    posted_at: Optional[dt.datetime] = None
    url: str = ""
    created_at: dt.datetime = Field(default_factory=now)


class Metric(SQLModel, table=True):
    """None = 未取得, 0 = 実際に0."""

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="postrecord.id", index=True)
    recorded_at: dt.datetime = Field(default_factory=now)
    views: Optional[int] = None
    avg_watch_s: Optional[float] = None
    completion_rate: Optional[float] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    follows_gained: Optional[int] = None
    source: str = "manual"  # manual only; official APIs not wired (see KNOWN_LIMITATIONS)
    note: str = ""


class Benchmark(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str  # acestep_10s / acestep_30s / acestep_full / mv_render / shorts_render
    device: str = ""
    duration_s: Optional[float] = None  # audio seconds requested
    elapsed_s: Optional[float] = None
    success: bool = False
    note: str = ""
    created_at: dt.datetime = Field(default_factory=now)
