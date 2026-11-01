"""Git operations: fetch, deteksi perubahan, commit, dan push aman.

Aturan dari note.md yang dipatuhi di modul ini:
- fetch sebelum maintenance
- selalu di branch default, tidak pernah force push
- tidak ada empty commit, tidak ubah histori yang sudah ada
- retry exponential backoff untuk kegagalan push
- push dianggap gagal aman (safe failure) bila konflik tidak teratasi
"""

from __future__ import annotations

import logging
import random
import subprocess
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger("bot.git")


class GitError(RuntimeError):
    """Error fatal git yang tidak bisa dimitigasi otomatis."""


class GitPushFailedError(GitError):
    """Push gagal setelah seluruh upaya retry."""


def run_git(
    args: Sequence[str],
    cwd: str,
    timeout: int = 60,
    check: bool = True,
    redact: bool = True,
) -> subprocess.CompletedProcess:
    """Jalankan perintah git dengan timeout dan sensor token di output.

    redact=True mencegah credential/token tercetak ke log saat git
    mencetak URL remote.
    """
    cmd = ["git", *args]
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = proc.stdout.strip()
    err = proc.stderr.strip()
    if redact and out:
        logger.debug("git %s -> %s", " ".join(args), out)
    if proc.returncode != 0 and check:
        safe_err = redact_secrets(err or out)
        raise GitError(f"git {' '.join(args)} failed: {safe_err}")
    return proc


def redact_secrets(text: str) -> str:
    """Sensor pola token GitHub dari teks (dipakai untuk pesan error)."""
    import re

    patterns = [
        r"ghp_[A-Za-z0-9]{20,}",
        r"gho_[A-Za-z0-9]{20,}",
        r"ghs_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "***REDACTED***", text)
    return text


def current_branch(cwd: str) -> str:
    proc = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    return proc.stdout.strip()


def has_remote_updates(cwd: str, branch: str) -> bool:
    """Cek apakah remote mempunyai commit yang belum kita punya."""
    proc = run_git(
        ["rev-list", "--count", f"HEAD..origin/{branch}"],
        cwd=cwd,
        check=False,
    )
    if proc.returncode != 0:
        return False
    try:
        return int(proc.stdout.strip() or "0") > 0
    except ValueError:
        return False


def fetch(cwd: str, timeout: int = 120) -> None:
    """Fetch remote tanpa mengubah working tree."""
    logger.info("git fetch origin")
    run_git(["fetch", "--tags", "--prune", "origin"], cwd=cwd, timeout=timeout)


def ensure_clean_state(cwd: str, branch: str) -> bool:
    """Pastikan working tree bersih dan staging tidak ada sampah.

    Mengembalikan True bila repo dalam kondisi siap maintenance.
    """
    proc = run_git(["status", "--porcelain"], cwd=cwd)
    if proc.stdout.strip():
        logger.warning(
            "Working tree tidak bersih saat mulai; perubahan lokal "
            "yang tidak terkait maintenance akan dilewati."
        )
        return False
    return True


def sync_branch(cwd: str, branch: str) -> None:
    """Sinkronkan branch dengan origin tanpa rebase destruktif.

    Hanya melakukan fast-forward; bila tidak possible, anggap konflik
    dan gagal aman daripada force push atau mengubah histori.
    """
    local = run_git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()
    remote = run_git(
        ["rev-parse", f"origin/{branch}"], cwd=cwd, check=False
    )
    if remote.returncode != 0:
        raise GitError(f"Remote branch origin/{branch} tidak ditemukan")
    remote_sha = remote.stdout.strip()
    if local == remote_sha:
        logger.info("Branch sudah sinkron dengan origin/%s", branch)
        return
    # Cek apakah fast-forward memungkinkan
    base = run_git(
        ["merge-base", "--is-ancestor", local, remote_sha],
        cwd=cwd,
        check=False,
    )
    if base.returncode == 0:
        logger.info("Fast-forward ke origin/%s", branch)
        run_git(["merge", "--ff-only", f"origin/{branch}"], cwd=cwd)
    else:
        raise GitError(
            "Branch lokal menyimpang dari origin (diverged). "
            "Tidak melakukan force push; perbaikan manual diperlukan."
        )


def has_changes(cwd: str) -> bool:
    """True bila ada perubahan terhadu HEAD (staged atau unstaged)."""
    proc = run_git(["status", "--porcelain"], cwd=cwd)
    return bool(proc.stdout.strip())


def diff_stats(
    cwd: str, exclude: Sequence[str] = ()
) -> Tuple[int, int, int, List[str]]:
    """Hitung jumlah file, insertions, deletions vs HEAD.

    File pada ``exclude`` tidak dihitung dan tidak distage.
    """
    files = changed_files(cwd)
    kept = [f for f in files if f not in exclude]
    inserted = 0
    deleted = 0
    if kept:
        proc = run_git(
            ["diff", "--numstat", "HEAD", "--", *kept],
            cwd=cwd,
            check=False,
        )
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                add_s, del_s = parts[0], parts[1]
                if add_s != "-":
                    inserted += int(add_s)
                if del_s != "-":
                    deleted += int(del_s)
    return len(kept), inserted, deleted, kept


def changed_files(cwd: str) -> List[str]:
    """Daftar file berubah vs HEAD (nama relatif)."""
    proc = run_git(["status", "--porcelain"], cwd=cwd)
    files: List[str] = []
    for line in proc.stdout.splitlines():
        if len(line) >= 3:
            files.append(line[3:])
    return files


def stage(cwd: str, paths: Sequence[str]) -> None:
    """Stage hanya file hasil maintenance; tidak pernah ``git add -A``."""
    if not paths:
        return
    run_git(["add", "--", *paths], cwd=cwd)


def commit(cwd: str, message: str) -> Optional[str]:
    """Commit perubahan ter-stage.  Mengembalikan SHA atau None.

    Tidak menggunakan --allow-empty, jadi bila tidak ada perubahan
    ter-stage, commit tidak dibuat (aturan note.md).
    """
    staged = run_git(["diff", "--cached", "--name-only"], cwd=cwd)
    if not staged.stdout.strip():
        logger.info("Tidak ada perubahan ter-stage; skip commit.")
        return None
    run_git(["commit", "-m", message], cwd=cwd)
    sha = run_git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()
    logger.info("Commit %s: %s", sha[:8], message)
    return sha


def push(
    cwd: str,
    branch: str,
    max_retries: int = 4,
    base_delay: float = 2.0,
) -> None:
    """Push ke origin dengan retry exponential backoff.

    Hanya push branch ini, tidak pernah --force atau --force-with-lease.
    Bila remote bergerak selama push, kita tarik ulang dan coba lagi.
    """
    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Push attempt %d/%d", attempt, max_retries)
            run_git(["push", "origin", branch], cwd=cwd, timeout=180)
            logger.info("Push berhasil.")
            return
        except GitError as exc:
            last_error = str(exc)
            logger.warning("Push gagal (attempt %d): %s", attempt, exc)
            if attempt == max_retries:
                break
            # Tarik ulang untuk menyelesaikan non-fast-forward
            fetch(cwd=cwd)
            try:
                sync_branch(cwd=cwd, branch=branch)
            except GitError as sync_exc:
                logger.warning("Sinkronisasi gagal: %s", sync_exc)
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            logger.info("Backoff %.1fs sebelum retry.", delay)
            import time

            time.sleep(delay)
    raise GitPushFailedError(
        f"Push gagal setelah {max_retries} upaya: {last_error}"
    )


def default_branch_from_remote(cwd: str) -> str:
    """Tebak branch default via git remote show origin."""
    proc = run_git(
        ["remote", "show", "origin"], cwd=cwd, timeout=60, check=False
    )
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("HEAD branch:"):
            return stripped.split(":", 1)[1].strip()
    return "main"
