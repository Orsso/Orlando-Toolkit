from __future__ import annotations

"""Logging bootstrap for Orlando Toolkit.

This module loads the YAML configuration located at
``orlando_toolkit/config/logging.yaml`` and applies it globally.  Any handler
``filename`` paths that are relative are rewritten so the log files reside
under the directory specified by the ``ORLANDO_LOG_DIR`` environment variable
(default: ``logs``).

The YAML file defines, among others, a dedicated ``structure`` logger with its
own file handler, ensuring that verbose diagnostics from the Structure tab are
captured in a separate ``structure.log`` file and do not clutter the main
application log.
"""

from pathlib import Path
import importlib.resources as _res
import logging
import logging.config
import os
import yaml

__all__ = ["setup_logging"]

_CFG_PKG = "orlando_toolkit.config"
_CFG_FILE = "logging.yaml"


def _load_yaml_config() -> dict:
    """Return the configuration dictionary embedded in the YAML file."""
    raw_yaml = _res.read_text(_CFG_PKG, _CFG_FILE)
    return yaml.safe_load(raw_yaml)  # type: ignore[arg-type]


def _rewrite_log_paths(cfg: dict) -> None:
    """Ensure handler filenames are absolute and land under $ORLANDO_LOG_DIR."""
    log_dir = Path(os.environ.get("ORLANDO_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    for handler in cfg.get("handlers", {}).values():
        filename = handler.get("filename")
        if filename and not Path(filename).is_absolute():
            handler["filename"] = str(log_dir / Path(filename).name)


def setup_logging() -> None:
    """Install the YAML logging configuration globally.

    Import and call this once near the start of your application's entry point
    (e.g. in ``run.py``) before any other modules emit log records.
    """
    cfg = _load_yaml_config()
    _rewrite_log_paths(cfg)
    logging.config.dictConfig(cfg)
    logging.getLogger(__name__).info("===== Logging initialised (YAML) =====")
