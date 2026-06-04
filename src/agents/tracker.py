"""Tracker Agent - monitors post performance and manages learning loop."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..storage.database import Database
from ..storage.vector_store import get_vector_store, VectorStore
from ..storage.models import CopyPerformance

logger = logging.getLogger(__name__)


class TrackerAgent:
    """Tracks post-publish performance and feeds data back for learning."""

    def __init__(
        self,
        db: Database | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.db = db or Database()
        self.vs = vector_store or get_vector_store()
        self.settings = get_settings()

    def record_performance(
        self,
        copy_id: int,
        likes: int = 0,
        collects: int = 0,
        comments: int = 0,
        shares: int = 0,
        views: int = 0,
        notes: str = "",
    ) -> int:
        """Record post-publish performance metrics."""
        perf_data = {
            "copy_id": copy_id,
            "likes": likes,
            "collects": collects,
            "comments": comments,
            "shares": shares,
            "views": views,
            "notes": notes,
        }
        perf_id = self.db.save_performance(perf_data)
        logger.info("Recorded performance for copy #%d: likes=%d, ces=%.1f",
                     copy_id, likes, perf_data.get("ces_score", 0))
        return perf_id

    def get_copy_performance(self, copy_id: int) -> dict | None:
        """Get the latest performance record for a copy."""
        copy = self.db.get_copy(copy_id)
        if not copy:
            return None
        perfs = self._get_performances_for_copy(copy_id)
        return perfs[-1] if perfs else None

    def evaluate_copy(self, copy_id: int) -> str:
        """Evaluate a copy's performance: 'success', 'failure', or 'pending'."""
        perf = self.get_copy_performance(copy_id)
        if not perf:
            return "pending"

        ces = perf.get("ces_score", 0)
        # Thresholds based on research data
        if ces >= 100:
            return "success"
        elif ces < 10 and perf.get("views", 0) > 200:
            return "failure"
        else:
            return "neutral"

    def index_successful_copy(self, copy_id: int) -> None:
        """Index a successful copy into the vector store for future retrieval."""
        copy = self.db.get_copy(copy_id)
        if not copy:
            return

        text = f"{copy['title']}\n{copy['body']}"
        meta = {
            "copy_id": str(copy_id),
            "task_id": str(copy.get("task_id", "")),
            "version": str(copy.get("version", 1)),
            "quality_label": self.evaluate_copy(copy_id),
        }

        try:
            self.vs.add_copy(
                doc_id=f"copy_{copy_id}",
                text=text,
                metadata=meta,
            )
            logger.info("Indexed copy #%d into vector store", copy_id)
        except Exception as e:
            logger.error("Failed to index copy #%d: %s", copy_id, e)

    def promote_to_reference(self, copy_id: int) -> Optional[int]:
        """Promote a highly successful copy to a reference case."""
        copy = self.db.get_copy(copy_id)
        if not copy:
            return None

        evaluation = self.evaluate_copy(copy_id)
        if evaluation != "success":
            logger.info("Copy #%d not successful enough to promote", copy_id)
            return None

        # Get the task for context
        task = self.db.get_task(copy["task_id"])

        ref_data = {
            "platform": task.get("platform", "xiaohongshu") if task else "xiaohongshu",
            "url": "",
            "title": copy["title"],
            "body": copy["body"],
            "hashtags": copy.get("hashtags", []),
            "likes": 0,  # Will be updated by performance data
            "collects": 0,
            "comments": 0,
            "shares": 0,
            "quality_label": "success",
            "content_type": task.get("content_type") if task else None,
        }

        # Update with actual metrics
        perf = self.get_copy_performance(copy_id)
        if perf:
            ref_data.update({
                "likes": perf.get("likes", 0),
                "collects": perf.get("collects", 0),
                "comments": perf.get("comments", 0),
                "shares": perf.get("shares", 0),
            })

        ref_id = self.db.save_reference(ref_data)

        # Also index the reference
        text = f"{copy['title']}\n{copy['body']}"
        try:
            self.vs.add_case(
                doc_id=f"promoted_{ref_id}",
                text=text,
                metadata={"quality_label": "success", "source": "self"},
            )
        except Exception as e:
            logger.warning("Failed to index promoted case: %s", e)

        # Update task status
        if task:
            self.db.update_task_status(copy["task_id"], "archived")

        logger.info("Promoted copy #%d to reference #%d", copy_id, ref_id)
        return ref_id

    def get_learning_stats(self, platform: str = "xiaohongshu") -> dict:
        """Get learning statistics for the given platform."""
        copies = self.db.list_copies()
        total = len(copies)
        if total == 0:
            return {"total": 0, "success_rate": 0, "avg_ces": 0, "trend": "no_data"}

        successes = 0
        total_ces = 0.0
        perf_count = 0

        for c in copies:
            perf = self.get_copy_performance(c["id"])
            if perf:
                perf_count += 1
                total_ces += perf.get("ces_score", 0)
                if perf.get("ces_score", 0) >= 100:
                    successes += 1

        success_rate = (successes / total * 100) if total > 0 else 0
        avg_ces = total_ces / perf_count if perf_count > 0 else 0

        # Simple trend: compare recent vs older
        recent = [c for c in copies if c.get("created_at") and
                  datetime.fromisoformat(c["created_at"]) > datetime.now() - timedelta(days=7)]
        recent_rate = 0
        if recent:
            recent_success = sum(
                1 for c in recent
                if (self.get_copy_performance(c["id"]) or {}).get("ces_score", 0) >= 100
            )
            recent_rate = recent_success / len(recent) * 100

        trend = "stable"
        if recent_rate > success_rate + 5:
            trend = "improving"
        elif recent_rate < success_rate - 5:
            trend = "declining"

        return {
            "total": total,
            "success_rate": round(success_rate, 1),
            "avg_ces": round(avg_ces, 1),
            "trend": trend,
            "recent_rate": round(recent_rate, 1),
        }

    def _get_performances_for_copy(self, copy_id: int) -> list[dict]:
        """Internal: get all performance records for a copy."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from ..storage.database import PerformanceRecord

        engine = create_engine(self.db.engine.url)
        with Session(engine) as s:
            recs = (
                s.query(PerformanceRecord)
                .filter(PerformanceRecord.copy_id == copy_id)
                .order_by(PerformanceRecord.recorded_at.asc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "copy_id": r.copy_id,
                    "likes": r.likes,
                    "collects": r.collects,
                    "comments": r.comments,
                    "shares": r.shares,
                    "views": r.views,
                    "ces_score": r.ces_score,
                    "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                    "notes": r.notes,
                }
                for r in recs
            ]
