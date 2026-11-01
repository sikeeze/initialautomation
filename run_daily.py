#!/usr/bin/env python3
"""Entry point harian: konfigurasi -> maintenance -> laporan status.

Dipanggil oleh GitHub Actions (run_daily.yml) atau dijalankan manual.
"""

from __future__ import annotations

import sys

from src.config import Config
from src.logging_utils import setup_logging
from src.orchestrator import run_maintenance


def main() -> int:
    try:
        cfg = Config.from_env()
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    log = setup_logging(cfg.log_level)
    log.info("GitHub Daily Automation Bot aktif (dry_run=%s)", cfg.dry_run)
    report = run_maintenance(cfg)
    log.info(
        "Selesai: success=%s commit=%s files_changed=%d",
        report.success,
        (report.commit_sha or "-")[:8],
        report.files_changed,
    )
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
