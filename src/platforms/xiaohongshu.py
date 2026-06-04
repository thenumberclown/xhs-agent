"""Xiaohongshu platform adapter - format rules, templates, and constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from ..storage.models import ContentType


@dataclass
class XiaohongshuPlatform:
    """Platform-specific configuration for Xiaohongshu."""

    name: str = "小红书"
    slug: str = "xiaohongshu"

    # Title constraints
    max_title_length: int = 20
    recommended_title_length: int = 18

    # Body constraints
    max_body_length: int = 1000
    recommended_body_length: int = 400

    # Hashtag constraints
    max_hashtags: int = 10
    recommended_hashtags: int = 5

    # Image constraints
    image_ratio: str = "3:4"
    recommended_colors: int = 3

    # Optimal publish times (Beijing time)
    publish_windows: ClassVar[list[str]] = [
        "07:00-09:00 (早高峰通勤)",
        "12:00-13:30 (午休时间)",
        "18:00-20:00 (下班后)",
        "22:00-23:30 (睡前时间)",
    ]

    # CES scoring formula
    ces_formula: str = "likes + collects + comments*4 + shares*4 + follows*8"

    # Content type → platform-specific advice
    type_advice: ClassVar[dict[str, str]] = {
        "ultra_value": "突出价格对比，用数字说话，封面放价格标签",
        "review": "横向对比3-5款产品，用表格形式呈现对比结果",
        "before_after": "封面用左右对比图，效果要真实可信",
        "pain_point": "标题直接点名痛点，正文先引起共鸣再给解决方案",
        "lifestyle": "强调场景氛围感，用暖色调图片，文字少而精",
        "emotional": "用故事开头，制造情感共鸣，结尾升华价值观",
        "knowledge": "标题含「干货」「攻略」关键词，正文分点清晰",
        "data_bait": "标题含「xx天」「xx个」量化承诺，正文给具体数据",
        "self_exposure": "标题含「我」「真实」等词，正文要有脆弱感",
        "reverse_hook": "标题制造反差，开头用「没想到」「居然」等词",
    }

    # Headline formula → template
    headline_templates: ClassVar[dict[str, str]] = {
        "数字清单": "{数字}{形容词}{品类}推荐，第{N}个{效果词}",
        "对比反差": "{低状态}和{高状态}的区别，就在{数字}个{关键词}",
        "避坑指南": "千万别买这{数字}样{品类}，我后悔死了",
        "揭秘内幕": "做了{数字}年{身份}，说点行业内幕",
        "情绪共鸣": "{年龄}岁，我终于不再{负面情绪}了",
        "教程步骤": "{数字}步搞定{目标}，{身份}也能学会",
        "资源合集": "整理了{数字}个{形容词}{品类}，建议收藏",
    }

    def format_hashtags(self, keywords: list[str], extra: list[str] | None = None) -> list[str]:
        """Format and deduplicate hashtags."""
        all_tags = list(dict.fromkeys(keywords + (extra or [])))  # preserve order, dedup
        return [f"#{t}" if not t.startswith("#") else t for t in all_tags[:self.max_hashtags]]

    def get_publish_window(self, index: int = 0) -> str:
        """Get a publish time window recommendation."""
        return self.publish_windows[index % len(self.publish_windows)]

    def get_type_advice(self, content_type: ContentType | str) -> str:
        """Get platform-specific advice for a content type."""
        key = content_type.value if isinstance(content_type, ContentType) else content_type
        return self.type_advice.get(key, "根据产品特点选择最合适的内容形式")

    def score_ces(self, likes: int = 0, collects: int = 0, comments: int = 0,
                  shares: int = 0, follows: int = 0) -> float:
        """Calculate Xiaohongshu CES engagement score."""
        return likes + collects + comments * 4 + shares * 4 + follows * 8

    def format_output(self, title: str, body: str, hashtags: list[str],
                      cover_hint: str = "", publish_time: str = "") -> str:
        """Format a complete post for display."""
        tag_str = " ".join(hashtags)
        lines = [
            "=" * 50,
            f"📝 标题：{title}",
            "",
            body,
            "",
            f"🏷️  标签：{tag_str}",
        ]
        if cover_hint:
            lines.append(f"🖼️  封面：{cover_hint}")
        if publish_time:
            lines.append(f"⏰ 发布时机：{publish_time}")
        lines.append("=" * 50)
        return "\n".join(lines)


# Singleton
_platform: XiaohongshuPlatform | None = None


def get_xhs() -> XiaohongshuPlatform:
    global _platform
    if _platform is None:
        _platform = XiaohongshuPlatform()
    return _platform
