"""The one-key-every-pattern loader: a single repo-root .env is found from a
nested pattern folder, the nearest .env wins, the real environment wins over any
file, and an unreplaced placeholder is skipped (not silently used)."""

import os

from dotenv_loader import load_dotenv


def _make_repo(tmp_path):
    """A fake repo: a root marked by pyproject.toml, with a nested pattern dir."""
    (tmp_path / "pyproject.toml").write_text("[tool.x]\n", encoding="utf-8")
    pattern_dir = tmp_path / "patterns" / "pattern-01" / "run"
    pattern_dir.mkdir(parents=True)
    return pattern_dir


def _clear(*keys):
    for key in keys:
        os.environ.pop(key, None)


def test_one_root_env_is_found_from_a_nested_pattern_folder(tmp_path):
    pattern_dir = _make_repo(tmp_path)
    (tmp_path / ".env").write_text("DOTENV_TEST_KEY=from-root\n", encoding="utf-8")
    _clear("DOTENV_TEST_KEY")
    try:
        loaded = load_dotenv(pattern_dir)
        assert os.environ["DOTENV_TEST_KEY"] == "from-root"
        assert loaded == [tmp_path / ".env"]
    finally:
        _clear("DOTENV_TEST_KEY")


def test_the_nearest_env_wins_over_the_root(tmp_path):
    pattern_dir = _make_repo(tmp_path)
    (tmp_path / ".env").write_text("DOTENV_TEST_KEY=from-root\n", encoding="utf-8")
    (pattern_dir / ".env").write_text("DOTENV_TEST_KEY=from-pattern\n", encoding="utf-8")
    _clear("DOTENV_TEST_KEY")
    try:
        load_dotenv(pattern_dir)
        assert os.environ["DOTENV_TEST_KEY"] == "from-pattern"
    finally:
        _clear("DOTENV_TEST_KEY")


def test_a_value_already_in_the_environment_wins_over_any_file(tmp_path):
    pattern_dir = _make_repo(tmp_path)
    (tmp_path / ".env").write_text("DOTENV_TEST_KEY=from-root\n", encoding="utf-8")
    os.environ["DOTENV_TEST_KEY"] = "from-shell"
    try:
        load_dotenv(pattern_dir)
        assert os.environ["DOTENV_TEST_KEY"] == "from-shell"
    finally:
        _clear("DOTENV_TEST_KEY")


def test_the_search_stops_at_the_repo_root(tmp_path):
    """A .env above the repo root (no pyproject/.git there) is not picked up."""
    pattern_dir = _make_repo(tmp_path)
    (tmp_path.parent / ".env").write_text("DOTENV_TEST_KEY=from-outside\n", encoding="utf-8")
    _clear("DOTENV_TEST_KEY")
    try:
        loaded = load_dotenv(pattern_dir)
        assert "DOTENV_TEST_KEY" not in os.environ
        assert loaded == []
    finally:
        _clear("DOTENV_TEST_KEY")
        (tmp_path.parent / ".env").unlink(missing_ok=True)


def test_an_unreplaced_placeholder_is_skipped(tmp_path):
    pattern_dir = _make_repo(tmp_path)
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=sk-or-v1-REPLACE-WITH-YOUR-KEY\n", encoding="utf-8"
    )
    _clear("OPENROUTER_API_KEY")
    try:
        load_dotenv(pattern_dir)
        # The placeholder must not reach the environment as if it were a key.
        assert "OPENROUTER_API_KEY" not in os.environ
    finally:
        _clear("OPENROUTER_API_KEY")
