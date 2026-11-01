"""Maintenance tasks: real changes only, tidak ada perubahan artifisial.

Setiap task mengembalikan daftar file yang berubah karena alasan nyata:
dead link ditemukan, dependency usang tercatat, atau format file tidak
rapi.  Jika tidak ada masalah, task tidak mengubah apa-apa — itulah yang
mencegah commit palsu / spam (aturan note.md bagian 5B).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("bot.maintenance")

LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
REF_RE = re.compile(r"^\[[^\]]+\]:\s*(https?://\S+)", re.MULTILINE)
USER_AGENT = "github-daily-automation-bot/1.0 (link-checker)"
MAX_LINKS_TO_CHECK = 40
STALE_BRANCH_DAYS = 30
FORMAT_EXTENSIONS = (".py", ".md", ".yml", ".yaml", ".txt")


@dataclass
class TaskResult:
    """Hasil satu maintenance task."""

    name: str
    status: str = "no-change"  # changed | no-change | error
    detail: str = ""
    changed_files: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changed_files)


def find_text_files(root: str, extensions: tuple) -> List[str]:
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".git", "node_modules", ".venv", "__pycache__"}
        ]
        for fname in filenames:
            if fname.endswith(extensions):
                found.append(os.path.join(dirpath, fname))
    return sorted(found)


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="strict") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Skip %s: %r", path, exc)
        return None


def write_text(path: str, content: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True
    except OSError as exc:
        logger.warning("Gagal menulis %s: %r", path, exc)
        return False
def _report_unchanged(report_path: str, new_body: str) -> bool:
    if not os.path.exists(report_path):
        return False
    existing = read_text(report_path)
    return existing == new_body


def _api_get_json(url: str, token: str, timeout: int):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def check_url(url: str, timeout: int) -> Optional[int]:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            url, method=method, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code == 405:
                continue
            return exc.code
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
    return None


def extract_links(content: str) -> List[str]:
    seen: Dict[str, None] = {}
    for url in LINK_RE.findall(content) + REF_RE.findall(content):
        seen.setdefault(url, None)
    return list(seen)


def check_links_task(root: str, timeout: int) -> TaskResult:
    result = TaskResult(name="dead-link-check")
    checked = 0
    broken: Dict[str, List[str]] = {}

    for path in find_text_files(root, (".md",)):
        if checked >= MAX_LINKS_TO_CHECK:
            break
        content = read_text(path)
        if content is None:
            continue
        for url in extract_links(content):
            if checked >= MAX_LINKS_TO_CHECK:
                break
            checked += 1
            status = check_url(url, timeout)
            if status is None or status >= 400:
                broken.setdefault(url, []).append(path)

    if not broken:
        result.detail = f"{checked} link dicek, semua sehat."
        return result

    lines = [
        "# Dead Link Report",
        "",
        f"- **Checked**: {checked} links",
        f"- **Broken**: {len(broken)} links",
        "",
        "| URL | Status | Found in |",
        "|---|---|---|",
    ]
    for url, paths in broken.items():
        rel = ", ".join(os.path.relpath(p, root) for p in sorted(set(paths)))
        lines.append(f"| {url} | broken | {rel} |")
    lines.append("")
    report_path = os.path.join(root, "DEAD_LINKS.md")
    if write_text(report_path, "\n".join(lines)):
        result.status = "changed"
        result.changed_files = ["DEAD_LINKS.md"]
        result.detail = f"{len(broken)} dead link ditemukan dari {checked}."
    else:
        result.status = "error"
        result.detail = "Gagal menulis DEAD_LINKS.md."
    return result
_GITIGNORE_SUGGEST = [
    "__pycache__/",
    "*.py[cod]",
    ".venv/",
    "venv/",
    "node_modules/",
    ".env",
    ".DS_Store",
    "Thumbs.db",
    "*.log",
]


def ensure_gitignore_task(root: str) -> TaskResult:
    result = TaskResult(name="gitignore-hygiene")
    path = os.path.join(root, ".gitignore")
    existing_raw = read_text(path)
    if existing_raw is None and os.path.exists(path):
        result.status = "error"
        result.detail = "Gagal membaca .gitignore."
        return result
    existing = existing_raw or ""
    missing = [e for e in _GITIGNORE_SUGGEST if e not in existing]
    if not missing:
        result.detail = ".gitignore sudah lengkap."
        return result
    new_content = existing
    if existing and not existing.endswith("\n"):
        new_content += "\n"
    if not existing:
        new_content = "# Entries added by GitHub Daily Automation Bot\n"
    new_content += "\n".join(missing) + "\n"
    if write_text(path, new_content):
        result.status = "changed"
        result.changed_files = [".gitignore"]
        result.detail = f"Menambah {len(missing)} entry: {', '.join(missing)}"
    else:
        result.status = "error"
        result.detail = "Gagal menulis .gitignore."
    return result
def stale_branch_report_task(
    root: str, token: str, repository: str, timeout: int
) -> TaskResult:
    result = TaskResult(name="stale-branch-report")
    if not token or not repository:
        result.status = "error"
        result.detail = "Token atau repository tidak tersedia."
        return result
    branches = _api_get_json(
        f"https://api.github.com/repos/{repository}/branches", token, timeout
    )
    if branches is None:
        result.status = "error"
        result.detail = "GitHub API branches gagal."
        return result
    threshold = datetime.now(timezone.utc) - timedelta(days=STALE_BRANCH_DAYS)
    stale: List[str] = []
    for branch in branches:
        name = branch.get("name", "")
        commit_url = (branch.get("commit") or {}).get("url", "")
        if not commit_url:
            continue
        data = _api_get_json(commit_url, token, timeout)
        if data is None:
            continue
        date_str = ((data.get("commit") or {}).get("committer") or {}).get(
            "date", ""
        )
        if not date_str:
            continue
        commit_date = _parse_github_date(date_str)
        if commit_date is None:
            continue
        if commit_date < threshold:
            stale.append(name)
    new_body = _render_stale_report(stale)
    report_path = os.path.join(root, "MAINTENANCE_REPORT.md")
    if _report_unchanged(report_path, new_body):
        result.detail = f"{len(stale)} branch stale (tidak berubah)."
        return result
    if write_text(report_path, new_body):
        result.status = "changed"
        result.changed_files = ["MAINTENANCE_REPORT.md"]
        result.detail = f"{len(stale)} branch stale tercatat."
    else:
        result.status = "error"
        result.detail = "Gagal menulis MAINTENANCE_REPORT.md."
    return result


def _parse_github_date(date_str: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _render_stale_report(stale: List[str]) -> str:
    lines = [
        "# Stale Branch Report",
        "",
        "Branch tanpa commit >30 hari (diperiksa secara harian):",
        "",
    ]
    if stale:
        lines += [f"- `{name}`" for name in sorted(stale)]
    else:
        lines.append("- Tidak ada branch stale.")
    lines += ["", "---", "_Generated by GitHub Daily Automation Bot._", ""]
    return "\n".join(lines)
def format_check_task(root: str) -> TaskResult:
    result = TaskResult(name="format-check")
    changed: List[str] = []
    checked = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".git", "node_modules", ".venv", "__pycache__"}
        ]
        for fname in filenames:
            if not fname.endswith(FORMAT_EXTENSIONS):
                continue
            path = os.path.join(dirpath, fname)
            content = read_text(path)
            if content is None:
                continue
            checked += 1
            new_content = content
            if content and not content.endswith("\n"):
                new_content += "\n"
            new_content = re.sub(r"[ \t]+\n", "\n", new_content)
            if new_content == content:
                continue
            if write_text(path, new_content):
                changed.append(os.path.relpath(path, root))
    if changed:
        result.status = "changed"
        result.changed_files = changed
        result.detail = f"{len(changed)} file dirapikan ({checked} dicek)."
    else:
        result.detail = f"{checked} file sudah rapi."
    return result
def dependency_check_task(root: str, timeout: int) -> TaskResult:
    result = TaskResult(name="dependency-check")
    if not os.path.exists(os.path.join(root, "requirements.txt")):
        result.detail = "Tidak ada requirements.txt; skip."
        return result
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "list",
                "--outdated",
                "--format=json",
                "--disable-pip-version-check",
            ],
            capture_output=True,
            text=True,
            timeout=timeout * 3,
            cwd=root,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        result.status = "error"
        result.detail = f"pip list gagal: {exc}"
        return result
    outdated: List[str] = []
    if proc.returncode == 0:
        data = _parse_json(proc.stdout)
        outdated = _format_outdated(data)
    new_body = _render_dependency_report(outdated)
    report_path = os.path.join(root, "DEPENDENCY_REPORT.md")
    if _report_unchanged(report_path, new_body):
        result.detail = f"{len(outdated)} dependency usang (tidak berubah)."
        return result
    if write_text(report_path, new_body):
        result.status = "changed"
        result.changed_files = ["DEPENDENCY_REPORT.md"]
        result.detail = f"{len(outdated)} dependency usang tercatat."
    else:
        result.status = "error"
        result.detail = "Gagal menulis DEPENDENCY_REPORT.md."
    return result


def _parse_json(stdout: str) -> list:
    if not stdout.strip():
        return []
    try:
        return json.loads(stdout)
    except ValueError:
        return []


def _format_outdated(data: list) -> List[str]:
    outdated: List[str] = []
    for item in data:
        name = item.get("name", "?")
        current = item.get("version", "?")
        latest = item.get("latest_version", "?")
        outdated.append(f"{name}=={current} -> {latest}")
    return outdated


def _render_dependency_report(outdated: List[str]) -> str:
    lines = [
        "# Outdated Dependency Report",
        "",
        "Dependency Python dengan versi lebih baru tersedia:",
        "",
    ]
    if outdated:
        lines += [f"- `{item}`" for item in outdated]
    else:
        lines.append("- Semua dependency sudah versi terbaru.")
    lines += ["", "---", "_Generated by GitHub Daily Automation Bot._", ""]
    return "\n".join(lines)
