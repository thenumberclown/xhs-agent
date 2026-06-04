"""Write Agent - generates copywriting content in multiple steps.

Step 1: Choose strategy
Step 2: Generate headlines
Step 3: Pick best headline + expand to full body
"""

from __future__ import annotations

import logging
from typing import Optional

from ..prompts.write import (
    HEADLINE_SYSTEM,
    HEADLINE_USER,
    BODY_SYSTEM,
    BODY_USER,
)
from ..storage.models import (
    WriteStrategy,
    HeadlineCandidate,
    GeneratedCopy,
    Platform,
)
from ..utils.ollama_client import get_client, OllamaClient

logger = logging.getLogger(__name__)


class WriteAgent:
    """Generates copywriting content via multi-step prompting."""

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or get_client()

    def generate_headlines(
        self,
        product_name: str,
        product_desc: str,
        strategy: WriteStrategy,
        count: int = 3,
    ) -> list[HeadlineCandidate]:
        """Generate multiple headline candidates."""
        messages = [
            {"role": "system", "content": HEADLINE_SYSTEM},
            {
                "role": "user",
                "content": HEADLINE_USER.format(
                    product_name=product_name,
                    product_desc=product_desc,
                    content_type=strategy.content_type.value,
                    headline_formula=strategy.headline_formula,
                    target_audience=strategy.angle,
                    tone=strategy.tone,
                    count=count,
                ),
            },
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.8)
            candidates = []
            for c in result.get("candidates", []):
                candidates.append(HeadlineCandidate(
                    title=c.get("title", ""),
                    formula=c.get("formula", strategy.headline_formula),
                    score=c.get("score", 5),
                ))
            if not candidates:
                # Fallback
                candidates.append(HeadlineCandidate(
                    title=f"{product_name}真的太绝了！谁用谁知道",
                    formula=strategy.headline_formula,
                    score=5,
                ))
            logger.info("Generated %d headlines", len(candidates))
            return candidates
        except Exception as e:
            logger.error("Headline generation failed: %s", e)
            return [
                HeadlineCandidate(
                    title=f"2026年必入的{product_name}，第3个效果惊人",
                    formula="数字清单",
                    score=6,
                )
            ]

    def expand_body(
        self,
        product_name: str,
        product_desc: str,
        title: str,
        strategy: WriteStrategy,
        examples: str = "",
    ) -> dict:
        """Expand a headline into a full body copy."""
        messages = [
            {"role": "system", "content": BODY_SYSTEM},
            {
                "role": "user",
                "content": BODY_USER.format(
                    product_name=product_name,
                    product_desc=product_desc,
                    title=title,
                    content_type=strategy.content_type.value,
                    angle=strategy.angle,
                    tone=strategy.tone,
                    examples=examples or "无",
                ),
            },
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.7, max_tokens=4096)
            logger.info("Body generated: %d chars", len(result.get("body", "")))
            return result
        except Exception as e:
            logger.error("Body generation failed: %s", e)
            return {
                "body": f"最近发现了一个好物——{product_name}！\n\n{product_desc}\n\n真的推荐大家试试！",
                "hashtags": ["好物推荐", "种草"],
                "cover_suggestion": "产品实拍图 + 文字标题",
                "publish_time": "工作日 19:00-20:00",
            }

    def generate(
        self,
        product_name: str,
        product_desc: str,
        strategy: WriteStrategy,
        best_headline: HeadlineCandidate,
        examples: str = "",
    ) -> GeneratedCopy:
        """Full generation pipeline: strategy → headline → body."""
        body_result = self.expand_body(
            product_name=product_name,
            product_desc=product_desc,
            title=best_headline.title,
            strategy=strategy,
            examples=examples,
        )

        return GeneratedCopy(
            task_id=0,  # Will be set by caller
            version=1,
            title=best_headline.title,
            body=body_result.get("body", ""),
            hashtags=body_result.get("hashtags", []),
            cover_suggestion=body_result.get("cover_suggestion", ""),
            publish_time_hint=body_result.get("publish_time", ""),
        )

    def generate_multi(
        self,
        product_name: str,
        product_desc: str,
        strategy: WriteStrategy,
        headlines: list[HeadlineCandidate],
        examples: str = "",
        max_versions: int = 3,
    ) -> list[GeneratedCopy]:
        """Generate multiple versions (A/B testing)."""
        copies = []
        top_headlines = sorted(headlines, key=lambda h: h.score, reverse=True)[:max_versions]

        for i, headline in enumerate(top_headlines):
            copy = self.generate(
                product_name=product_name,
                product_desc=product_desc,
                strategy=strategy,
                best_headline=headline,
                examples=examples,
            )
            copy.version = i + 1
            copies.append(copy)
            logger.info("Generated version %d with headline: %s", copy.version, headline.title)

        return copies
