"""Tests for the Reviewer Agent (unit tests without LLM)."""

import pytest
from src.agents.reviewer import ReviewAgent


class TestReviewAgentUnit:
    """Unit tests that don't require Ollama."""

    @pytest.fixture
    def agent(self):
        return ReviewAgent(None, None, _connect=False)

    def test_check_compliance_clean(self, agent):
        """Clean copy should pass compliance check."""
        issues = agent._check_compliance(
            title="10个实用的收纳技巧，第3个太赞了",
            body="收纳真的是一门学问。今天分享10个我亲测有效的收纳方法，每一个都是踩过无数坑之后总结出来的。从厨房到卧室，从衣柜到书桌，这些技巧都能让你的空间利用率翻倍。希望能帮到大家。你们有什么收纳技巧吗？欢迎在评论区分享出来一起交流。",
        )
        assert len(issues) == 0

    def test_check_compliance_banned_word(self, agent):
        """Copy with banned words should be flagged."""
        issues = agent._check_compliance(
            title="全网最好的护肤品推荐",
            body="这是第一好用的产品，绝对有效果，100%推荐！",
        )
        assert len(issues) >= 3  # 全网, 第一, 绝对, 100%

    def test_check_compliance_long_title(self, agent):
        """Overly long title should get a warning."""
        issues = agent._check_compliance(
            title="这是一条超级超级超级超级超级超级超级超级长的标题用来测试字数限制",
            body="正常的正文内容" * 10,
        )
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(warnings) >= 1

    def test_check_compliance_short_body(self, agent):
        """Very short body should get a warning."""
        issues = agent._check_compliance(
            title="正常标题",
            body="太短了",
        )
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(warnings) >= 1
