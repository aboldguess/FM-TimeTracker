"""Mini-README: Tests that configuration resolves the `.env` path deterministically.

These checks prevent bootstrap credential regressions caused by starting the app
from a directory other than the repository root.
"""

from pathlib import Path

from app.config import ENV_FILE_PATH, PROJECT_ROOT, Settings


def test_env_file_path_is_absolute_and_repo_relative() -> None:
    """Ensure settings look for `.env` in the repository root, not cwd."""
    assert ENV_FILE_PATH.is_absolute()
    assert ENV_FILE_PATH == PROJECT_ROOT / ".env"
    assert Settings.model_config["env_file"] == ENV_FILE_PATH


def test_project_root_matches_package_parent() -> None:
    """Guard rail: keep project root aligned with `app/` parent folder."""
    assert PROJECT_ROOT == Path(__file__).resolve().parents[1]
