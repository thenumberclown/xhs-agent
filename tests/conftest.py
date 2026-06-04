"""Pytest fixtures shared across all tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test.db")


@pytest.fixture
def sample_cases():
    """Load sample reference cases from fixtures."""
    import json
    fixtures_dir = Path(__file__).parent / "fixtures"
    case_file = fixtures_dir / "cases.json"
    if case_file.exists():
        return json.loads(case_file.read_text())
    return []
