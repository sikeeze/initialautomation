"""Unit tests: config validation, change detection, git failure, credentials."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config  # noqa: E402
from src.git_ops import (  # noqa: E402
    GitError,
    changed_files,
    diff_stats,
    has_changes,
    run_git,
)
from src.logging_utils import redact_secrets  # noqa: E402
from src.maintenance import (  # noqa: E402
    TaskResult,
    ensure_gitignore_task,
    extract_links,
    format_check_task,
)
from src.orchestrator import build_commit_message  # noqa: E402


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "sikeeze/initialautomation")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(ROOT))
    with pytest.raises(ValueError):
        Config.from_env()


def test_config_rejects_bad_repository(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "a" * 30)
    monkeypatch.setenv("GITHUB_REPOSITORY", "invalid-no-slash")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(ROOT))
    with pytest.raises(ValueError):
        Config.from_env()


def test_config_accepts_valid(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "a" * 30)
    monkeypatch.setenv("GITHUB_REPOSITORY", "sikeeze/initialautomation")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(ROOT))
    cfg = Config.from_env()
    assert cfg.repository == "sikeeze/initialautomation"
    assert cfg.max_changes >= 1


# ---------------------------------------------------------------------------
# Credential redaction (no secret leaks in logs)
# ---------------------------------------------------------------------------


def test_redact_secrets_all_token_kinds():
    text = "token ghp_AAAAAAAAAAAAAAAAAAAA and gho_BBBBBBBBBBBBBBBBBBBB"
    out = redact_secrets(text)
    assert "ghp_" not in out and "gho_" not in out
    assert "REDACTED" in out


# ---------------------------------------------------------------------------
# Git helpers against a real temp repo
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    run_git(["init", "-b", "main"], cwd=str(tmp_path))
    run_git(["config", "user.name", "test"], cwd=str(tmp_path))
    run_git(["config", "user.email", "t@t"], cwd=str(tmp_path))
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(["add", "."], cwd=str(tmp_path))
    run_git(["commit", "-m", "init"], cwd=str(tmp_path))
    return tmp_path


def test_no_changes_detected(tmp_path):
    repo = _make_repo(tmp_path)
    assert has_changes(str(repo)) is False
    assert changed_files(str(repo)) == []
    stats = diff_stats(str(repo))
    assert stats[0] == 0


def test_change_detection(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "README.md").write_text("hello world\n", encoding="utf-8")
    assert has_changes(str(repo)) is True
    files, ins, dele, kept = diff_stats(str(repo))
    assert files == 1
    assert ins >= 1


def test_run_git_failure_raises():
    # bad revision: pasti gagal di mana saja, tanpa bergantung pada
    # status repo direktori test
    with pytest.raises(GitError):
        run_git(["log", "--oneline", "branch-yang-tidak-ada"], cwd=str(ROOT))


def test_diff_stats_exclude(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "MAINTENANCE_REPORT.md").write_text("report\n", encoding="utf-8")
    files, ins, dele, kept = diff_stats(
        str(repo), exclude=("MAINTENANCE_REPORT.md",)
    )
    assert files == 0
    assert kept == []


# ---------------------------------------------------------------------------
# Maintenance tasks
# ---------------------------------------------------------------------------


def test_format_check_no_change_on_clean_file(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    res = format_check_task(str(tmp_path))
    assert res.status == "no-change"
    assert res.changed_files == []


def test_format_check_fixes_missing_newline(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("x = 1", encoding="utf-8")
    res = format_check_task(str(tmp_path))
    assert res.status == "changed"
    assert res.changed_files == [str(p.name)]
    assert p.read_text(encoding="utf-8").endswith("\n")


def test_gitignore_added_once(tmp_path):
    res = ensure_gitignore_task(str(tmp_path))
    assert res.status == "changed"
    res2 = ensure_gitignore_task(str(tmp_path))
    assert res2.status == "no-change"


def test_extract_links():
    md = "[a](https://example.com) and [b](http://x.org)\n[c]: https://y.io\n"
    links = extract_links(md)
    assert "https://example.com" in links
    assert "https://y.io" in links


def test_commit_message_conventional():
    results = [
        TaskResult(name="dead-link-check", status="changed", detail="1 broken"),
        TaskResult(name="format-check", status="no-change", detail="ok"),
    ]
    msg = build_commit_message(results)
    assert msg.startswith("fix(") or msg.startswith("chore(")
    assert "automated maintenance" in msg
    assert "dead-link-check" in msg


def test_commit_message_no_change_default():
    results = [TaskResult(name="format-check", status="no-change", detail="ok")]
    msg = build_commit_message(results)
    assert msg.startswith("chore(maintenance): automated maintenance")


def test_heartbeat_creates_entry_once(tmp_path):
    from src.maintenance import heartbeat_task

    results = [TaskResult(name="format-check", status="no-change", detail="ok")]
    res1 = heartbeat_task(str(tmp_path), results)
    assert res1.status == "changed"
    assert res1.changed_files == ["ACTIVITY.md"]
    res2 = heartbeat_task(str(tmp_path), results)
    assert res2.status == "no-change"
    assert res2.changed_files == []


def test_heartbeat_content_documented(tmp_path):
    from src.maintenance import heartbeat_task

    results = [TaskResult(name="dead-link-check", status="no-change", detail="ok")]
    heartbeat_task(str(tmp_path), results)
    body = (tmp_path / "ACTIVITY.md").read_text(encoding="utf-8")
    assert "Activity Log" in body
    assert "WIB" in body
    assert "dead-link-check=no-change" in body
