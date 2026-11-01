"""Configuration for GitHub Daily Automation Bot.

All values resolve from environment variables with safe defaults so the
bot never fails because of a missing optional setting.  No secrets are
hardcoded; the workflow injects them via GitHub Secrets.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

# Zona waktu acuan scheduler (Asia/Jakarta UTC+7).  GitHub Actions cron
# menggunakan UTC, jadi 00:00 WIB == 17:00 UTC hari sebelumnya.
DEFAULT_SCHEDULE_UTC = "0 17 * * *"

# Batas keamanan
MAX_CHANGES_PER_COMMIT = 200
COMMIT_SCOPE_FALLBACK = "automated maintenance"
REQUEST_TIMEOUT_SECONDS = 20
PUSH_MAX_RETRIES = 4


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    """Resolved configuration for one maintenance run."""

    repository: str
    branch: str
    token: str
    workspace: str
    schedule_utc: str = DEFAULT_SCHEDULE_UTC
    dry_run: bool = False
    max_changes: int = MAX_CHANGES_PER_COMMIT
    timeout: int = REQUEST_TIMEOUT_SECONDS
    push_max_retries: int = PUSH_MAX_RETRIES
    log_level: str = "INFO"
    # Maintenance switches
    run_link_check: bool = True
    run_stale_branch_report: bool = True
    run_format_check: bool = True
    run_dependency_check: bool = True
    exclude_files: tuple = ("MAINTENANCE_REPORT.md",)

    def validate(self) -> None:
        """Raise ``ValueError`` bila konfigurasi tidak layak dijalankan."""
        missing: List[str] = []
        if not self.repository or "/" not in self.repository:
            missing.append("GITHUB_REPOSITORY (format 'owner/name')")
        if not self.token:
            missing.append("GITHUB_TOKEN")
        if not self.workspace or not os.path.isdir(self.workspace):
            missing.append("WORKSPACE (direktori checkout repo)")
        if self.max_changes < 1:
            missing.append("MAX_CHANGES_PER_COMMIT (harus >= 1)")
        if self.timeout < 1:
            missing.append("REQUEST_TIMEOUT_SECONDS (harus >= 1)")
        if missing:
            raise ValueError(
                "Konfigurasi tidak valid: " + "; ".join(missing)
            )

    @staticmethod
    def from_env() -> "Config":
        """Build config dari environment (GitHub Actions atau lokal)."""
        repo = os.getenv("GITHUB_REPOSITORY", "")
        workspace = os.getenv("GITHUB_WORKSPACE") or os.getenv(
            "WORKSPACE", os.getcwd()
        )
        cfg = Config(
            repository=repo,
            token=os.getenv("GITHUB_TOKEN", ""),
            branch=os.getenv("INPUT_BRANCH", "main"),
            workspace=workspace,
            schedule_utc=os.getenv("SCHEDULE_UTC", DEFAULT_SCHEDULE_UTC),
            dry_run=_env_bool("INPUT_DRY_RUN") or _env_bool("DRY_RUN"),
            max_changes=int(
                os.getenv("INPUT_MAX_CHANGES", str(MAX_CHANGES_PER_COMMIT))
            ),
            timeout=int(
                os.getenv("INPUT_TIMEOUT", str(REQUEST_TIMEOUT_SECONDS))
            ),
            push_max_retries=int(
                os.getenv("PUSH_MAX_RETRIES", str(PUSH_MAX_RETRIES))
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            run_link_check=_env_bool("INPUT_RUN_LINK_CHECK", True),
            run_stale_branch_report=_env_bool(
                "INPUT_RUN_STALE_BRANCH_REPORT", True
            ),
            run_format_check=_env_bool("INPUT_RUN_FORMAT_CHECK", True),
            run_dependency_check=_env_bool(
                "INPUT_RUN_DEPENDENCY_CHECK", True
            ),
            exclude_files=tuple(_env_list("INPUT_EXCLUDE_FILES", "MAINTENANCE_REPORT.md")),
        )
        cfg.validate()
        return cfg
