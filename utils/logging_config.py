"""
Central logging setup (utils/logging_config.py).

Streamlit re-runs the script top-to-bottom on every interaction, so logging is
configured once (idempotently) under a single "vector_sentinel" parent logger,
and modules fetch a child logger via get_logger(__name__).

Handlers that swallow an exception on purpose — token refresh that may fail
harmlessly, optional writes with a fallback, best-effort parsing — should log
here (usually at DEBUG, or WARNING/ERROR when a real feature failed) instead of
silently discarding the error, so failures are diagnosable from server logs.

Verbosity is controlled by the LOG_LEVEL environment variable (default INFO).
This module intentionally imports nothing from the app (only stdlib) to stay
free of circular-import risk.
"""

import logging
import os

_PARENT = "vector_sentinel"
_configured = False


def _configure_once():
    global _configured
    if _configured:
        return
    parent = logging.getLogger(_PARENT)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    parent.setLevel(getattr(logging, level_name, logging.INFO))
    # Guard against duplicate handlers accumulating across Streamlit reruns.
    if not parent.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        parent.addHandler(handler)
    parent.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Returns a child logger under the shared parent, configuring it once."""
    _configure_once()
    return logging.getLogger(f"{_PARENT}.{name}")
