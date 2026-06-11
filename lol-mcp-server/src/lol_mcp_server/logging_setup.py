"""Logging configuration.

CRUCIAL FOR STDIO TRANSPORT: every log record MUST go to stderr. The MCP stdio
transport uses stdout exclusively for JSON-RPC frames. Any stray byte on stdout
(a stray print, a logging StreamHandler defaulting to stdout) corrupts the
protocol stream and the client disconnects. We therefore pin the handler to
``sys.stderr`` and never call bare ``print()`` anywhere in this package.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logging to emit to stderr only. Idempotent."""
    global _CONFIGURED
    logger = logging.getLogger("lol_mcp_server")
    if _CONFIGURED:
        return logger

    handler = logging.StreamHandler(stream=sys.stderr)  # <-- stderr, never stdout
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # don't double-log through the root handler

    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the package namespace."""
    return logging.getLogger(f"lol_mcp_server.{name}")
