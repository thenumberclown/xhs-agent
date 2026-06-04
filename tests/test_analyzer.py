"""Tests for the Analyzer Agent."""

import pytest
from src.agents.analyzer import AnalyzeAgent
from src.storage.models import WriteStrategy


class TestAnalyzeAgent:
    """Tests for analyze agent (requires Ollama)."""

    @pytest.fixture
    def agent(self):
        return AnalyzeAgent()

    def test_choose_strategy_basic(self, agent):
        """Strategy selection should return a valid WriteStrategy."""
        strategy = agent.choose_strategy(
            product_name="测试护肤品",
            product_desc="一款主打补水的面膜，适合干性皮肤",
            target_audience="25-35岁女性",
        )
        assert isinstance(strategy, WriteStrategy)
        assert strategy.content_type is not None
        assert strategy.headline_formula
        assert strategy.tone

    def test_choose_strategy_with_cases(self, agent):
        """Strategy with reference cases."""
        strategy = agent.choose_strategy(
            product_name="家居收纳盒",
            product_desc="多尺寸组合收纳盒，可叠放",
            target_audience="租房年轻人",
            success_cases="案例1：3个收纳神器让10平米出租屋变大2倍...点赞5000",
        )
        assert strategy.content_type is not None


class TestAnalyzeAgentUnit:
    """Unit tests without Ollama dependency."""

    def test_summarize_empty(self):
        """Summarizing empty analyses should return defaults."""
        agent = AnalyzeAgent(None)  # Will fail if it tries to call LLM
        # We're testing the data processing, not the LLM call
        result = AnalyzeAgent(None).summarize_patterns([])
        assert result is not None
        assert result.headline_formulas_used == []
