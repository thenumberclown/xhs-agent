"""Research Agent - collects reference copywriting cases.

Phase 1: Web search (via Claude Code's built-in WebSearch/WebFetch)
Phase 2: Manual import (CLI)
Phase 3: Browser extension integration
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..storage.database import Database
from ..storage.models import ReferenceCase, Platform

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Finds and collects reference copywriting examples."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.settings = get_settings()

    def search_xiaohongshu(self, query: str, max_results: int = 10) -> list[dict]:
        """Search for Xiaohongshu references.

        Note: This method expects the raw search results to be passed in
        from the caller (e.g., Claude Code's WebSearch). In a standalone
        deployment, this would use the Ollama model + web search.
        """
        # The actual search is done externally (WebSearch tool).
        # This method receives parsed results and stores them.
        logger.info("Search XHS for: %s (max %d results)", query, max_results)
        return []

    def import_case(
        self,
        title: str,
        body: str = "",
        *,
        platform: str = "xiaohongshu",
        url: str = "",
        author_name: str = "",
        hashtags: list[str] | None = None,
        likes: int = 0,
        collects: int = 0,
        comments: int = 0,
        shares: int = 0,
        quality_label: str = "neutral",
    ) -> int:
        """Import a single reference case into the database."""
        ref_data = {
            "platform": platform,
            "url": url,
            "title": title,
            "body": body,
            "author_name": author_name,
            "hashtags": hashtags or [],
            "likes": likes,
            "collects": collects,
            "comments": comments,
            "shares": shares,
            "quality_label": quality_label,
        }
        ref_id = self.db.save_reference(ref_data)

        # Also save to disk as backup
        self._save_to_disk(ref_id, ref_data)

        logger.info("Imported reference case #%d: %s", ref_id, title[:50])
        return ref_id

    def import_from_json(self, filepath: Path) -> list[int]:
        """Batch import cases from a JSON file."""
        data = json.loads(filepath.read_text())
        if isinstance(data, dict):
            data = [data]
        ids = []
        for item in data:
            ref_id = self.import_case(
                title=item["title"],
                body=item.get("body", ""),
                platform=item.get("platform", "xiaohongshu"),
                url=item.get("url", ""),
                author_name=item.get("author_name", ""),
                hashtags=item.get("hashtags", []),
                likes=item.get("likes", 0),
                collects=item.get("collects", 0),
                comments=item.get("comments", 0),
                shares=item.get("shares", 0),
                quality_label=item.get("quality_label", "neutral"),
            )
            ids.append(ref_id)
        logger.info("Imported %d cases from %s", len(ids), filepath)
        return ids

    def _save_to_disk(self, ref_id: int, data: dict) -> None:
        """Backup to JSON file."""
        cases_dir = self.settings.cases_dir
        filepath = cases_dir / f"case_{ref_id:06d}.json"
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_success_cases(
        self, platform: str = "xiaohongshu", limit: int = 5
    ) -> list[dict]:
        """Get top successful reference cases."""
        return self.db.list_references(
            platform=platform,
            quality_label="success",
            limit=limit,
        )

    def get_all_cases(
        self, platform: str = "xiaohongshu", limit: int = 50
    ) -> list[dict]:
        """Get all reference cases."""
        return self.db.list_references(platform=platform, limit=limit)

    def format_for_prompt(self, cases: list[dict], max_cases: int = 3) -> str:
        """Format reference cases for inclusion in a prompt."""
        if not cases:
            return "（暂无参考案例）"

        lines = []
        for i, case in enumerate(cases[:max_cases]):
            hashtags_str = ", ".join(case.get("hashtags", [])[:5])
            lines.append(
                f"案例{i + 1}：{case['title']}\n"
                f"正文：{case['body'][:300]}...\n"
                f"数据：点赞{case['likes']} 收藏{case['collects']}\n"
                f"标签：{hashtags_str}"
            )
        return "\n\n".join(lines)
