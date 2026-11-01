"""Orchestrator: menjalankan semua maintenance task secara berurutan.

Mengikuti prinsip "real changes only": task hanya mengubah file ketika
ada masalah nyata yang ditemukan.  Bila tidak ada perubahan, tidak ada
commit (note.md bagian 5B: tidak ada empty commit, tidak ada commit
berulang tanpa perubahan).
"""

from __future__ import annotations

import logging
from typing import Callable, List

from .config import Config
from .git_ops import (
    GitError,
    commit,
    diff_stats,
    ensure_clean_state,
    fetch,
    push,
    stage,
    sync_branch,
)
from .logging_utils import StatusReport, write_step_summary
from .maintenance import (
    TaskResult,
    check_links_task,
    dependency_check_task,
    ensure_gitignore_task,
    stale_branch_report_task,
    format_check_task,
)

logger = logging.getLogger("bot.orchestrator")

# Jenis commit message sesuai note.md (conventional commits)
COMMIT_TYPES = {
    "dead-link-check": "fix",
    "gitignore-hygiene": "chore",
    "stale-branch-report": "docs",
    "format-check": "style",
    "dependency-check": "test",
}


def build_commit_message(results: List[TaskResult]) -> str:
    """Bangun commit message konvensional dari task yang menghasilkan ubahan."""
    primary = "chore"
    changed = [r for r in results if r.status == "changed"]
    if changed:
        types = {COMMIT_TYPES.get(r.name, "chore") for r in changed}
        primary = sorted(types)[0]
    scopes = ", ".join(sorted({r.name for r in changed})) or "maintenance"
    summary = "automated maintenance"
    lines = [f"{primary}({scopes}): {summary}"]
    for res in results:
        lines.append(f"- {res.name}: {res.detail}")
    return "\n".join(lines)


def run_maintenance(cfg: Config) -> StatusReport:
    """Pipeline harian: fetch -> tasks -> stage -> commit -> push.

    Mengembalikan StatusReport untuk monitoring.  Setiap kegagalan
    ditanam dalam report dan, bila fatal, di-raise agar workflow gagal.
    """
    report = StatusReport()
    report.repository = cfg.repository
    report.branch = cfg.branch

    logger.info("Memulai maintenance untuk %s branch %s", cfg.repository, cfg.branch)
    fetch(cwd=cfg.workspace, timeout=cfg.timeout)
    ensure_clean_state(cfg.workspace, cfg.branch)
    sync_branch(cwd=cfg.workspace, branch=cfg.branch)

    tasks: List[Callable[[], TaskResult]] = []
    if cfg.run_link_check:
        tasks.append(lambda: check_links_task(cfg.workspace, cfg.timeout))
    if cfg.run_stale_branch_report:
        tasks.append(
            lambda: stale_branch_report_task(
                cfg.workspace, cfg.token, cfg.repository, cfg.timeout
            )
        )
    if cfg.run_format_check:
        tasks.append(lambda: format_check_task(cfg.workspace))
    if cfg.run_dependency_check:
        tasks.append(lambda: dependency_check_task(cfg.workspace, cfg.timeout))
    tasks.append(lambda: ensure_gitignore_task(cfg.workspace))

    results: List[TaskResult] = []
    for task in tasks:
        try:
            res = task()
        except Exception as exc:  # noqa: BLE001 - task gagal, run lanjut
            logger.exception("Task error: %s", exc)
            res = TaskResult(name=task.__name__, status="error", detail=str(exc))
            report.add_error(f"{task.__name__}: {exc}")
        results.append(res)
        report.add_task(res.name, res.status, res.detail)
        logger.info("Task %s -> %s: %s", res.name, res.status, res.detail)

    # Kumpulkan file yang berubah dari semua task
    files_to_stage: List[str] = []
    for res in results:
        files_to_stage.extend(res.changed_files)

    # Pastikan file yang diubah oleh task walker adalah path relatif yang
    # valid (format_check mengembalikan relative path, report file absolut
    # sudah ditulis langsung ke root).
    stage_set = sorted(set(files_to_stage))

    if not stage_set:
        logger.info("Tidak ada task yang menghasilkan perubahan. Tidak ada commit.")
        report.success = True
        write_step_summary(report)
        return report

    if len(stage_set) > cfg.max_changes:
        logger.warning(
            "Perubahan melebihi batas (%d > %d); membatalkan commit demi keamanan.",
            len(stage_set),
            cfg.max_changes,
        )
        report.add_error(
            f"Perubahan melebihi batas maksimal ({len(stage_set)} > {cfg.max_changes})"
        )
        report.success = False
        write_step_summary(report)
        return report

    stage(cwd=cfg.workspace, paths=stage_set)

    # Validasi ulang: pastikan benar-benar ada perubahan staged
    files_changed, insertions, deletions, kept = diff_stats(
        cwd=cfg.workspace, exclude=cfg.exclude_files
    )
    if files_changed == 0:
        logger.info("Tidak ada perubahan nyata setelah exclude. Tidak ada commit.")
        report.success = True
        write_step_summary(report)
        return report

    if cfg.dry_run:
        logger.info("DRY RUN: perubahan distage tapi tidak di-commit/push.")
        report.success = True
        report.files_changed = files_changed
        report.insertions = insertions
        report.deletions = deletions
        write_step_summary(report)
        return report

    message = build_commit_message(results)
    sha = commit(cwd=cfg.workspace, message=message)
    if sha:
        report.commit_sha = sha
        report.commit_message = message.splitlines()[0]
        report.files_changed = files_changed
        report.insertions = insertions
        report.deletions = deletions
        try:
            push(
                cwd=cfg.workspace,
                branch=cfg.branch,
                max_retries=cfg.push_max_retries,
            )
            report.success = True
        except GitError as exc:
            logger.error("Push gagal: %s", exc)
            report.add_error(f"Push gagal: {exc}")
            report.success = False
    else:
        report.success = True
        report.files_changed = 0
    write_step_summary(report)
    return report
