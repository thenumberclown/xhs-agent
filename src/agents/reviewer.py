"""Review Agent - quality assurance for generated copy."""

from __future__ import annotations

import logging
from typing import Optional

from ..prompts.review import REVIEW_SYSTEM, REVIEW_USER
from ..storage.models import ReviewReport
from ..storage.vector_store import get_vector_store, VectorStore
from ..utils.ollama_client import get_client, OllamaClient

logger = logging.getLogger(__name__)


class ReviewAgent:
    """Reviews generated copy for quality and compliance."""

    # Common banned/promotional words on Xiaohongshu
    BANNED_PATTERNS = [
        "第一", "最强", "最好", "全网", "绝对", "100%",
        "永久", "根治", "治愈", "神效", "立竿见影",
        "免费领取", "加微信", "私信我", "点击链接",
    ]

    def __init__(
        self,
        client: OllamaClient | None = None,
        vector_store: VectorStore | None = None,
        _connect: bool = True,
    ) -> None:
        self.client = client if client is not None else (get_client() if _connect else None)
        self.vs = vector_store if vector_store is not None else (get_vector_store() if _connect else None)

    def review(
        self,
        title: str,
        body: str,
        hashtags: list[str] | None = None,
    ) -> ReviewReport:
        """Review a generated copy using AI + rule-based checks."""

        # 1. Rule-based compliance check
        compliance_issues = self._check_compliance(title, body)

        # 2. Similarity check
        similar_count = self._check_similarity(title, body)
        similarity_warning = ""
        if similar_count > 0:
            similarity_warning = f"发现 {similar_count} 篇相似度较高的历史文案，建议人工确认是否重复"

        # 3. AI-powered quality review
        ai_review = self._ai_review(title, body, hashtags or [], similar_count)

        # 4. Merge results
        all_issues = compliance_issues + ai_review.get("issues", [])
        suggestions = ai_review.get("suggestions", [])

        # Decide pass/fail
        errors = [i for i in all_issues if i.get("severity") == "error"]
        passed = len(errors) == 0 and ai_review.get("overall_score", 0) >= 60

        return ReviewReport(
            passed=passed,
            overall_score=ai_review.get("overall_score", 70),
            compliance_issues=[i["description"] for i in compliance_issues],
            quality_issues=[
                i["description"]
                for i in all_issues
                if i.get("severity") != "error"
            ],
            suggestions=suggestions,
            similarity_warning=similarity_warning,
        )

    def _check_compliance(self, title: str, body: str) -> list[dict]:
        """Rule-based check for banned words and patterns."""
        issues = []
        full_text = title + " " + body

        for pattern in self.BANNED_PATTERNS:
            if pattern in full_text:
                issues.append({
                    "severity": "error",
                    "category": "compliance",
                    "description": f"包含违规词汇: '{pattern}'",
                })

        # Check title length
        if len(title) > 30:
            issues.append({
                "severity": "warning",
                "category": "style",
                "description": f"标题过长 ({len(title)}字)，建议控制在20字以内",
            })

        # Check body length
        if len(body) < 100:
            issues.append({
                "severity": "warning",
                "category": "quality",
                "description": "正文过短，建议至少150字以提升搜索权重",
            })

        return issues

    def _check_similarity(self, title: str, body: str) -> int:
        """Check against vector store for similar existing copies."""
        try:
            similar = self.vs.search_similar_copies(
                query=f"{title}\n{body[:200]}",
                n_results=5,
            )
            # Count close matches (cosine distance < 0.3)
            close = [s for s in similar if s.get("distance", 1.0) < 0.3]
            return len(close)
        except Exception as e:
            logger.warning("Similarity check failed: %s", e)
            return 0

    def _ai_review(
        self,
        title: str,
        body: str,
        hashtags: list[str],
        similar_count: int,
    ) -> dict:
        """Use the AI model to review the copy."""
        messages = [
            {"role": "system", "content": REVIEW_SYSTEM},
            {
                "role": "user",
                "content": REVIEW_USER.format(
                    title=title,
                    body=body,
                    hashtags=", ".join(hashtags),
                    similar_count=similar_count,
                ),
            },
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.2)
            logger.info("AI review: passed=%s, score=%d",
                         result.get("passed"), result.get("overall_score", 0))
            return result
        except Exception as e:
            logger.error("AI review failed: %s", e)
            return {
                "passed": True,
                "overall_score": 70,
                "issues": [],
                "suggestions": [],
            }
