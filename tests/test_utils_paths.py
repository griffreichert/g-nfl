"""Tests for g_nfl.utils.paths (#51): PROJECT_DIR must resolve from
__file__, not cwd."""

import importlib

from g_nfl.utils import paths


def test_project_dir_independent_of_cwd(tmp_path, monkeypatch):
    original = paths.PROJECT_DIR
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(paths)
    assert reloaded.PROJECT_DIR == original
    assert (reloaded.PROJECT_DIR / "pyproject.toml").exists()
