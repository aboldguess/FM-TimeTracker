"""Mini-README: Tests for project-task form helper parsing behavior."""

import pytest
from fastapi import HTTPException

from app.main import parse_task_names


def test_parse_task_names_trims_blanks_and_deduplicates() -> None:
    raw = "\nDesign\n design \nBuild\n\n"
    assert parse_task_names(raw) == ["Design", "Build"]


def test_parse_task_names_rejects_overlong_names() -> None:
    overlong = "x" * 121
    with pytest.raises(HTTPException) as exc_info:
        parse_task_names(overlong)
    assert exc_info.value.status_code == 400
