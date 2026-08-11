"""Structured logging setup.

``print()`` is a standards violation the validator checks for, so the framework
has to make logging the path of least resistance.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO", *, json_format: bool = False) -> None:
    """Configure root logging once, at process start."""
    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        fmt = (
            '{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}'
        )
    else:
        fmt = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S%z"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
