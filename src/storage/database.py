"""SQLite database layer using SQLAlchemy ORM."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import get_settings


class Base(DeclarativeBase):
    pass


# ─── ORM Models ───────────────────────────────────────────────


class TaskRecord(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(200), nullable=False)
    product_desc = Column(Text, nullable=False)
    platform = Column(String(20), nullable=False, default="xiaohongshu")
    content_type = Column(String(50), nullable=True)
    target_audience = Column(String(200), default="")
    keywords = Column(Text, default="[]")       # JSON array
    style_notes = Column(Text, default="")
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, default=datetime.now)


class CopyRecord(Base):
    __tablename__ = "copies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    version = Column(Integer, default=1)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    hashtags = Column(Text, default="[]")        # JSON array
    cover_suggestion = Column(Text, default="")
    publish_time_hint = Column(String(100), default="")
    quality_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class PerformanceRecord(Base):
    __tablename__ = "performances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    copy_id = Column(Integer, ForeignKey("copies.id"), nullable=False)
    likes = Column(Integer, default=0)
    collects = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    views = Column(Integer, default=0)
    ces_score = Column(Float, default=0.0)
    recorded_at = Column(DateTime, default=datetime.now)
    notes = Column(Text, default="")


class ReferenceRecord(Base):
    __tablename__ = "references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False, default="xiaohongshu")
    url = Column(Text, default="")
    title = Column(String(500), nullable=False)
    body = Column(Text, default="")
    author_name = Column(String(200), default="")
    hashtags = Column(Text, default="[]")
    likes = Column(Integer, default=0)
    collects = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    content_type = Column(String(50), nullable=True)
    headline_formula = Column(String(100), default="")
    structure_pattern = Column(String(100), default="")
    quality_label = Column(String(20), default="neutral")
    embedding_id = Column(String(100), nullable=True)
    collected_at = Column(DateTime, default=datetime.now)


# ─── Database Manager ─────────────────────────────────────────


class Database:
    def __init__(self, db_path: str | None = None) -> None:
        path = db_path or get_settings().xhs_agent_db_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"
        self.engine = create_engine(url, echo=False)
        self.Session = sessionmaker(bind=self.engine)

    def init(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.Session()

    # ─── Task CRUD ───────────────────────────────

    def create_task(self, task: dict) -> int:
        with self.session() as s:
            record = TaskRecord(
                product_name=task["product_name"],
                product_desc=task["product_desc"],
                platform=task.get("platform", "xiaohongshu"),
                content_type=task.get("content_type"),
                target_audience=task.get("target_audience", ""),
                keywords=json.dumps(task.get("keywords", [])),
                style_notes=task.get("style_notes", ""),
                status=task.get("status", "draft"),
            )
            s.add(record)
            s.commit()
            return record.id

    def get_task(self, task_id: int) -> dict | None:
        with self.session() as s:
            rec = s.get(TaskRecord, task_id)
            if rec is None:
                return None
            return _task_to_dict(rec)

    def update_task_status(self, task_id: int, status: str) -> None:
        with self.session() as s:
            rec = s.get(TaskRecord, task_id)
            if rec:
                rec.status = status
                s.commit()

    def list_tasks(self, platform: str | None = None, limit: int = 50) -> list[dict]:
        with self.session() as s:
            q = s.query(TaskRecord)
            if platform:
                q = q.filter(TaskRecord.platform == platform)
            q = q.order_by(TaskRecord.created_at.desc()).limit(limit)
            return [_task_to_dict(r) for r in q.all()]

    # ─── Copy CRUD ──────────────────────────────

    def save_copy(self, copy_data: dict) -> int:
        with self.session() as s:
            rec = CopyRecord(
                task_id=copy_data["task_id"],
                version=copy_data.get("version", 1),
                title=copy_data["title"],
                body=copy_data["body"],
                hashtags=json.dumps(copy_data.get("hashtags", [])),
                cover_suggestion=copy_data.get("cover_suggestion", ""),
                publish_time_hint=copy_data.get("publish_time_hint", ""),
                quality_score=copy_data.get("quality_score"),
            )
            s.add(rec)
            s.commit()
            return rec.id

    def get_copy(self, copy_id: int) -> dict | None:
        with self.session() as s:
            rec = s.get(CopyRecord, copy_id)
            if rec is None:
                return None
            return _copy_to_dict(rec)

    def list_copies(self, task_id: int | None = None, limit: int = 20) -> list[dict]:
        with self.session() as s:
            q = s.query(CopyRecord)
            if task_id is not None:
                q = q.filter(CopyRecord.task_id == task_id)
            q = q.order_by(CopyRecord.created_at.desc()).limit(limit)
            return [_copy_to_dict(r) for r in q.all()]

    def get_best_copies(self, platform: str = "xiaohongshu", limit: int = 10) -> list[dict]:
        """Get top performing copies for few-shot learning."""
        with self.session() as s:
            results = (
                s.query(CopyRecord, PerformanceRecord.ces_score)
                .join(PerformanceRecord, CopyRecord.id == PerformanceRecord.copy_id)
                .join(TaskRecord, CopyRecord.task_id == TaskRecord.id)
                .filter(TaskRecord.platform == platform)
                .order_by(PerformanceRecord.ces_score.desc())
                .limit(limit)
                .all()
            )
            copies = []
            for copy_rec, ces in results:
                d = _copy_to_dict(copy_rec)
                d["ces_score"] = ces
                copies.append(d)
            return copies

    # ─── Performance CRUD ───────────────────────

    def save_performance(self, perf: dict) -> int:
        with self.session() as s:
            views = perf.get("views", 0)
            likes = perf.get("likes", 0)
            collects = perf.get("collects", 0)
            comments = perf.get("comments", 0)
            shares = perf.get("shares", 0)
            ces = likes + collects + comments * 4 + shares * 4

            rec = PerformanceRecord(
                copy_id=perf["copy_id"],
                likes=likes,
                collects=collects,
                comments=comments,
                shares=shares,
                views=views,
                ces_score=round(ces, 2),
                notes=perf.get("notes", ""),
            )
            s.add(rec)
            s.commit()
            return rec.id

    # ─── Reference CRUD ─────────────────────────

    def save_reference(self, ref: dict) -> int:
        with self.session() as s:
            rec = ReferenceRecord(
                platform=ref.get("platform", "xiaohongshu"),
                url=ref.get("url", ""),
                title=ref["title"],
                body=ref.get("body", ""),
                author_name=ref.get("author_name", ""),
                hashtags=json.dumps(ref.get("hashtags", [])),
                likes=ref.get("likes", 0),
                collects=ref.get("collects", 0),
                comments=ref.get("comments", 0),
                shares=ref.get("shares", 0),
                content_type=ref.get("content_type"),
                headline_formula=ref.get("headline_formula", ""),
                structure_pattern=ref.get("structure_pattern", ""),
                quality_label=ref.get("quality_label", "neutral"),
                embedding_id=ref.get("embedding_id"),
            )
            s.add(rec)
            s.commit()
            return rec.id

    def list_references(
        self,
        platform: str = "xiaohongshu",
        quality_label: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        with self.session() as s:
            q = s.query(ReferenceRecord).filter(ReferenceRecord.platform == platform)
            if quality_label:
                q = q.filter(ReferenceRecord.quality_label == quality_label)
            q = q.order_by(ReferenceRecord.collected_at.desc()).limit(limit)
            return [_ref_to_dict(r) for r in q.all()]

    def count_references(self, platform: str = "xiaohongshu") -> int:
        with self.session() as s:
            return s.query(ReferenceRecord).filter(ReferenceRecord.platform == platform).count()


# ─── Serialization helpers ────────────────────────────────────


def _task_to_dict(r: TaskRecord) -> dict:
    return {
        "id": r.id,
        "product_name": r.product_name,
        "product_desc": r.product_desc,
        "platform": r.platform,
        "content_type": r.content_type,
        "target_audience": r.target_audience,
        "keywords": json.loads(r.keywords) if r.keywords else [],
        "style_notes": r.style_notes,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _copy_to_dict(r: CopyRecord) -> dict:
    return {
        "id": r.id,
        "task_id": r.task_id,
        "version": r.version,
        "title": r.title,
        "body": r.body,
        "hashtags": json.loads(r.hashtags) if r.hashtags else [],
        "cover_suggestion": r.cover_suggestion,
        "publish_time_hint": r.publish_time_hint,
        "quality_score": r.quality_score,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _ref_to_dict(r: ReferenceRecord) -> dict:
    return {
        "id": r.id,
        "platform": r.platform,
        "url": r.url,
        "title": r.title,
        "body": r.body,
        "author_name": r.author_name,
        "hashtags": json.loads(r.hashtags) if r.hashtags else [],
        "likes": r.likes,
        "collects": r.collects,
        "comments": r.comments,
        "shares": r.shares,
        "content_type": r.content_type,
        "headline_formula": r.headline_formula,
        "structure_pattern": r.structure_pattern,
        "quality_label": r.quality_label,
        "embedding_id": r.embedding_id,
        "collected_at": r.collected_at.isoformat() if r.collected_at else None,
    }
