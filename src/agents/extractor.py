"""Chapter Detail Extractor — extracts structured info from novel chapters.

This is the "template-driven" approach: read a chapter → extract key details →
plug them into proven copy templates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ..utils.ollama_client import get_client, OllamaClient

logger = logging.getLogger(__name__)

# ─── Extraction Prompt ───────────────────────────────────────

EXTRACT_SYSTEM = """你是小红书爆款推文专家。请从小说章节中提取可用于宣发文案的关键信息。

请严格按照 JSON 格式输出。

重要原则：
1. one_liner 必须是能直接用作标题的钩子句（15-25字），要包含冲突/反差/悬念
2. hook_elements 是"如果只让你用一句话安利这本书，你会说什么"——必须是具体的、有画面感的
3. anomalies 要选最独特、最有记忆点的细节——读者看完会记住的那种
4. quotable_lines 要是原文中真正精彩、可直接引用的句子

输出字段：
{
  "title": "章节标题",
  "one_liner": "一句话钩子（15-25字，含冲突/悬念/反差，可直接作标题用）",
  "core_scenes": ["场景1", "场景2"],
  "anomalies": [
    {"what": "异常名称（简短）", "location": "位置", "detail": "具体描述（含原文细节）"}
  ],
  "character_moments": [
    {"character": "角色名", "moment": "高光时刻/名场面"}
  ],
  "quotable_lines": ["金句1", "金句2"],
  "emotional_arc": "情感走向",
  "hook_elements": ["卖点1（具体且有画面感）", "卖点2"],
  "tone_keywords": ["调性词1", "调性词2"],
  "word_count": 0
}"""

EXTRACT_USER = """请分析以下小说章节，提取宣发关键信息：

章节标题：{title}

正文：
{body}

请提取可用于小红书/抖音/知乎宣发的关键元素。"""


class ChapterExtractor:
    """Extracts structured metadata from a novel chapter for copy generation."""

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or get_client()

    def extract(self, title: str, body: str) -> dict:
        """Extract key details from a chapter.

        Args:
            title: Chapter title
            body: Full chapter text

        Returns:
            Structured extraction result
        """
        # Truncate if too long (keep first 2500 chars + last 800 for ending)
        if len(body) > 4000:
            body = body[:2500] + "\n\n...\n\n" + body[-800:]

        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": EXTRACT_USER.format(title=title, body=body)},
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.3, max_tokens=2048)
            result["word_count"] = len(body)
            logger.info("Extracted details from chapter: %s", title)
            return result
        except Exception as e:
            logger.error("Extraction failed for %s: %s", title, e)
            return {
                "title": title,
                "one_liner": "",
                "core_scenes": [],
                "anomalies": [],
                "character_moments": [],
                "quotable_lines": [],
                "emotional_arc": "",
                "hook_elements": [],
                "tone_keywords": [],
                "word_count": len(body),
            }

    def extract_file(self, filepath: Path) -> dict:
        """Extract from a chapter file."""
        content = filepath.read_text(encoding="utf-8")
        # Parse title from first line or filename
        title = filepath.stem
        for line in content.split("\n")[:3]:
            if line.startswith("# "):
                title = line.replace("# ", "").strip()
                break
        return self.extract(title, content)
