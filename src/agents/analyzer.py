"""Analyze Agent - breaks down reference cases and extracts patterns."""

from __future__ import annotations

import logging
from typing import Optional

from ..prompts.analyze import (
    ANALYZE_SYSTEM,
    ANALYZE_USER,
    STRATEGY_SYSTEM,
    STRATEGY_USER,
)
from ..storage.models import AnalysisResult, WriteStrategy, ContentType
from ..utils.ollama_client import get_client, OllamaClient

logger = logging.getLogger(__name__)


class AnalyzeAgent:
    """Analyzes copywriting examples and formulates strategies."""

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or get_client()

    def analyze_case(self, case: dict) -> dict:
        """Analyze a single reference case.

        Returns structured analysis (dict matching ANALYZE_SYSTEM output schema).
        """
        messages = [
            {"role": "system", "content": ANALYZE_SYSTEM},
            {
                "role": "user",
                "content": ANALYZE_USER.format(
                    title=case.get("title", ""),
                    body=case.get("body", ""),
                    hashtags=", ".join(case.get("hashtags", [])),
                    likes=case.get("likes", 0),
                    collects=case.get("collects", 0),
                    comments=case.get("comments", 0),
                ),
            },
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.3)
            logger.info(
                "Analyzed case: quality=%s, headline=%s",
                result.get("estimated_quality", "?"),
                result.get("headline_formula", "?"),
            )
            return result
        except Exception as e:
            logger.error("Failed to analyze case: %s", e)
            return {
                "headline_formula": "未知",
                "headline_score": 5,
                "structure_pattern": "未知",
                "content_type": "knowledge",
                "emoji_density": "medium",
                "estimated_quality": "neutral",
                "extract_keywords": [],
                "one_line_summary": "分析失败",
            }

    def analyze_batch(self, cases: list[dict]) -> list[dict]:
        """Analyze multiple cases sequentially."""
        results = []
        for case in cases:
            result = self.analyze_case(case)
            result["_source_title"] = case.get("title", "")
            results.append(result)
        return results

    def summarize_patterns(self, analyses: list[dict]) -> AnalysisResult:
        """Aggregate multiple case analyses into a summary."""
        if not analyses:
            return AnalysisResult()

        # Count patterns
        formulas: dict[str, int] = {}
        structures: dict[str, int] = {}
        emojis: dict[str, int] = {}
        all_keywords: list[str] = []

        for a in analyses:
            f = a.get("headline_formula", "")
            if f:
                formulas[f] = formulas.get(f, 0) + 1
            s = a.get("structure_pattern", "")
            if s:
                structures[s] = structures.get(s, 0) + 1
            e = a.get("emoji_density", "")
            if e:
                emojis[e] = emojis.get(e, 0) + 1
            all_keywords.extend(a.get("extract_keywords", []))

        # Get top patterns
        top_formula = max(formulas, key=formulas.get) if formulas else "数字清单"
        top_structure = max(structures, key=structures.get) if structures else "五段式"
        top_emoji = max(emojis, key=emojis.get) if emojis else "medium"

        # Count keyword frequency
        kw_freq: dict[str, int] = {}
        for kw in all_keywords:
            kw_freq[kw] = kw_freq.get(kw, 0) + 1
        top_keywords = sorted(kw_freq, key=kw_freq.get, reverse=True)[:10]

        # Collect insights
        insights = []
        for a in analyses:
            s = a.get("one_line_summary", "")
            if s:
                insights.append(s)

        return AnalysisResult(
            headline_formulas_used=list(formulas.keys()),
            structure_pattern=top_structure,
            emoji_density=top_emoji,
            avg_title_length=0,
            top_keywords=top_keywords,
            recommended_type=ContentType.PAIN_POINT,
            target_audience="",
            style_notes="",
            insights=insights,
        )

    def choose_strategy(
        self,
        product_name: str,
        product_desc: str,
        *,
        target_audience: str = "",
        style_notes: str = "",
        success_cases: str = "",
    ) -> WriteStrategy:
        """Choose the best content strategy for a product."""
        messages = [
            {"role": "system", "content": STRATEGY_SYSTEM},
            {
                "role": "user",
                "content": STRATEGY_USER.format(
                    product_name=product_name,
                    product_desc=product_desc,
                    target_audience=target_audience or "通用",
                    style_notes=style_notes or "无",
                    success_cases=success_cases or "无",
                ),
            },
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.5)
            strategy = WriteStrategy(
                content_type=ContentType(result.get("content_type", "pain_point")),
                headline_formula=result.get("headline_formula", "数字清单"),
                structure=result.get("structure", "五段式"),
                angle=result.get("angle", ""),
                tone=result.get("tone", "亲切口语"),
                target_emotion=result.get("target_emotion", "好奇"),
            )
            logger.info("Strategy chosen: type=%s, formula=%s",
                         strategy.content_type.value, strategy.headline_formula)
            return strategy
        except Exception as e:
            logger.error("Strategy selection failed: %s", e)
            return WriteStrategy(
                content_type=ContentType.PAIN_POINT,
                headline_formula="数字清单",
                structure="五段式",
                angle=f"{product_name}的实用推荐",
                tone="亲切口语",
                target_emotion="好奇",
            )
