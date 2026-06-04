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
    """Extracts structured metadata from a novel chapter for copy generation.

    For long chapters, splits into chunks to avoid LLM timeout on limited hardware.
    """

    CHUNK_SIZE = 1800       # chars per chunk — keeps LLM input within GPU-friendly range
    CHUNK_OVERLAP = 200     # overlap between chunks to preserve context

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or get_client()

    def extract(self, title: str, body: str) -> dict:
        """Extract key details from a chapter.

        Chapters <= CHUNK_SIZE are processed directly.
        Longer chapters are split into overlapping chunks, each extracted separately,
        then merged.
        """
        word_count = len(body)

        if word_count <= self.CHUNK_SIZE:
            return self._extract_single(title, body, word_count)

        # Chunked extraction for long chapters
        chunks = self._smart_chunk(body)
        logger.info("Chapter '%s' split into %d chunks (%d chars total)",
                     title, len(chunks), word_count)

        all_anomalies: list[dict] = []
        all_moments: list[str] = []
        all_quotes: list[str] = []
        all_scenes: list[str] = []
        all_hooks: list[str] = []
        all_tones: list[str] = []
        one_liner = ""
        emotional_arc = ""

        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} [片段{i+1}/{len(chunks)}]"
            result = self._extract_single(chunk_title, chunk, len(chunk))

            # Collect structured data
            all_anomalies.extend(result.get("anomalies", []))
            all_scenes.extend(result.get("core_scenes", []))
            all_hooks.extend(result.get("hook_elements", []))
            all_tones.extend(result.get("tone_keywords", []))

            for m in result.get("character_moments", []):
                if isinstance(m, dict):
                    all_moments.append(m.get("moment", str(m)))
                elif isinstance(m, str) and m:
                    all_moments.append(m)

            for q in result.get("quotable_lines", []):
                if q and q not in all_quotes:
                    all_quotes.append(q)

            # Use one_liner from first chunk (sets the scene)
            if i == 0 and result.get("one_liner"):
                one_liner = result["one_liner"]

            # Use emotional_arc from last chunk (has the ending)
            if i == len(chunks) - 1 and result.get("emotional_arc"):
                emotional_arc = result["emotional_arc"]

        # Deduplicate anomalies by what field
        seen_what = set()
        unique_anomalies = []
        for a in all_anomalies:
            what = a.get("what", str(a)) if isinstance(a, dict) else str(a)
            if what not in seen_what:
                seen_what.add(what)
                unique_anomalies.append(a if isinstance(a, dict) else {"what": what})

        # Deduplicate and limit
        unique_scenes = list(dict.fromkeys(all_scenes))[:3]
        unique_hooks = list(dict.fromkeys(all_hooks))[:5]
        unique_tones = list(dict.fromkeys(all_tones))[:5]

        merged = {
            "title": title,
            "one_liner": one_liner or (unique_hooks[0] if unique_hooks else ""),
            "core_scenes": unique_scenes,
            "anomalies": unique_anomalies[:5],
            "character_moments": all_moments[:5],
            "quotable_lines": all_quotes[:5],
            "emotional_arc": emotional_arc,
            "hook_elements": unique_hooks,
            "tone_keywords": unique_tones,
            "word_count": word_count,
        }

        logger.info("Merged extraction: %d anomalies, %d moments, %d quotes",
                     len(merged["anomalies"]), len(merged["character_moments"]),
                     len(merged["quotable_lines"]))
        return merged

    def _extract_single(self, title: str, body: str, word_count: int) -> dict:
        """Run a single LLM extraction on a (possibly chunked) body."""
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": EXTRACT_USER.format(title=title, body=body)},
        ]

        try:
            result = self.client.chat_json(messages, temperature=0.3, max_tokens=1536)
            result["word_count"] = word_count
            logger.info("Extracted from: %s", title)
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
                "word_count": word_count,
            }

    def _smart_chunk(self, text: str) -> list[str]:
        """Split text into chunks at natural paragraph boundaries."""
        paragraphs = text.split("\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > self.CHUNK_SIZE and current:
                chunks.append(current.strip())
                # Keep overlap: last ~200 chars of previous chunk
                overlap = current[-self.CHUNK_OVERLAP:] if len(current) > self.CHUNK_OVERLAP else current
                current = overlap + "\n" + para
            else:
                current = current + "\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())
        return chunks

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
