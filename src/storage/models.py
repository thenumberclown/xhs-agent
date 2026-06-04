"""Data models for the XHS Agent system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────


class Platform(str, Enum):
    XIAOHONGSHU = "xiaohongshu"
    DOUYIN = "douyin"


class TaskStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    PUBLISHED = "published"
    TRACKED = "tracked"
    ARCHIVED = "archived"


class ContentType(str, Enum):
    """10 types of viral content patterns from research."""
    ULTRA_VALUE = "ultra_value"            # 极致性价比型
    REVIEW = "review"                      # 测评/避雷型
    BEFORE_AFTER = "before_after"          # 效果展示型
    PAIN_POINT = "pain_point"              # 场景痛点解决型
    LIFESTYLE = "lifestyle"                # 场景化种草型
    EMOTIONAL = "emotional"                # 情感价值型
    KNOWLEDGE = "knowledge"                # 知识干货型
    DATA_BAIT = "data_bait"                # 数据引诱型
    SELF_EXPOSURE = "self_exposure"        # 自我暴露型
    REVERSE_HOOK = "reverse_hook"          # 正话反说型


# ─── Core Models ──────────────────────────────────────────────


class CopyTask(BaseModel):
    """A single copywriting task."""
    id: Optional[int] = None
    product_name: str
    product_desc: str
    platform: Platform = Platform.XIAOHONGSHU
    content_type: Optional[ContentType] = None
    target_audience: str = ""
    keywords: list[str] = Field(default_factory=list)
    style_notes: str = ""                 # Extra instructions
    status: TaskStatus = TaskStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.now)


class GeneratedCopy(BaseModel):
    """A generated piece of copy."""
    id: Optional[int] = None
    task_id: int
    version: int = 1                     # For A/B testing
    title: str
    body: str
    hashtags: list[str] = Field(default_factory=list)
    cover_suggestion: str = ""
    publish_time_hint: str = ""          # e.g., "weekday 19:00-20:00"
    quality_score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)


class CopyPerformance(BaseModel):
    """Post-publish performance metrics."""
    id: Optional[int] = None
    copy_id: int
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0
    ces_score: float = 0.0              # 小红书 CES = likes*1 + collects*1 + comments*4 + shares*4 + follows*8
    recorded_at: datetime = Field(default_factory=datetime.now)
    notes: str = ""


class ReferenceCase(BaseModel):
    """A collected reference case from the internet."""
    id: Optional[int] = None
    platform: Platform = Platform.XIAOHONGSHU
    url: str = ""
    title: str
    body: str = ""
    author_name: str = ""
    hashtags: list[str] = Field(default_factory=list)
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: int = 0
    content_type: Optional[ContentType] = None
    headline_formula: str = ""           # Which of 7 headline formulas
    structure_pattern: str = ""          # e.g., "5-paragraph", "story+method"
    quality_label: str = ""              # "success" | "failure" | "neutral"
    embedding_id: Optional[str] = None   # Chroma embedding ID
    collected_at: datetime = Field(default_factory=datetime.now)


class AnalysisResult(BaseModel):
    """Result of analyzing reference cases."""
    headline_formulas_used: list[str] = Field(default_factory=list)
    structure_pattern: str = ""
    emoji_density: str = ""              # "low" | "medium" | "high"
    avg_title_length: int = 0
    top_keywords: list[str] = Field(default_factory=list)
    recommended_type: ContentType = ContentType.PAIN_POINT
    target_audience: str = ""
    style_notes: str = ""
    insights: list[str] = Field(default_factory=list)


class WriteStrategy(BaseModel):
    """Strategy output from the strategy selection step."""
    content_type: ContentType
    headline_formula: str                # Which of 7 formulas to use
    structure: str                       # e.g., "5-paragraph", "story+method"
    angle: str                           # The specific angle/perspective
    tone: str                            # e.g., "friendly", "professional", "emotional"
    target_emotion: str                  # e.g., "curiosity", "FOMO", "relief"


class HeadlineCandidate(BaseModel):
    """A candidate headline with score."""
    title: str
    formula: str
    score: int = 0                       # 1-10


class ReviewReport(BaseModel):
    """Quality review result."""
    passed: bool
    overall_score: int                   # 1-100
    compliance_issues: list[str] = Field(default_factory=list)
    quality_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    similarity_warning: str = ""         # Warn if too similar to existing copy
