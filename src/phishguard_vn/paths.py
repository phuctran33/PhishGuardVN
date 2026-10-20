"""Local-first project paths with optional overrides for other runtimes."""
from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Use an override or locate this source checkout's project marker."""
    override = os.environ.get("PHISHGUARD_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / "pyproject.toml").is_file():
            raise FileNotFoundError(f"PHISHGUARD_ROOT has no pyproject.toml: {root}")
        return root
    for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for candidate in (start, *start.parents):
            if (candidate / "pyproject.toml").is_file() and (
                candidate / "src" / "phishguard_vn"
            ).is_dir():
                return candidate
    raise FileNotFoundError("Set PHISHGUARD_ROOT to the cloned project directory.")


def get_data_dir() -> Path:
    """Original input folder; override for a dataset stored outside the checkout."""
    override = os.environ.get("PHISHGUARD_DATA_DIR")
    return Path(override).expanduser().resolve() if override else get_project_root() / "data"


def get_config_path() -> Path:
    return get_project_root() / "configs" / "baseline.toml"
