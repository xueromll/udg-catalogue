"""The catalogue's log file and console output, shared with sci-etl-core's own log lines."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from udg_catalogue.progress import paper_message

LOGGER_NAME = "UDGPipeline"
CORE_LOGGER_NAME = "sci_etl_core"
_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_installed: dict[str, tuple[Path, int, tuple[logging.Handler, ...]]] = {}


class PaperContextFilter(logging.Filter):
    """Prefix a sci-etl-core line with the arXiv id of the paper it concerns, when one is being processed."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(CORE_LOGGER_NAME) and not getattr(record, "paper_prefixed", False):
            record.msg = paper_message(record.getMessage())
            record.args = ()
            record.paper_prefixed = True
        return True


def configure_run_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Return the catalogue logger, writing to ``log_file`` and to stdout.

    sci-etl-core logs under the ``sci_etl_core`` logger, whose lines go to the
    same handlers, so a failed paper, a retry, or a rejected galaxy reaches the
    log with its reason. A repeated call with the same file and level changes
    nothing; a different file or level replaces the handlers installed before.
    The log file's folder is created when missing.
    """
    target = Path(log_file).resolve()
    current = _installed.get(LOGGER_NAME)
    if current is not None and current[:2] == (target, level):
        return logging.getLogger(LOGGER_NAME)
    loggers = [logging.getLogger(name) for name in (LOGGER_NAME, CORE_LOGGER_NAME)]
    if current is not None:
        for logger in loggers:
            for handler in current[2]:
                logger.removeHandler(handler)
        for handler in current[2]:
            handler.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT, _DATE_FORMAT)
    handlers: tuple[logging.Handler, ...] = (
        logging.FileHandler(target, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    )
    for handler in handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        handler.addFilter(PaperContextFilter())
    for logger in loggers:
        logger.setLevel(level)
        logger.propagate = False
        for handler in handlers:
            logger.addHandler(handler)
    _installed[LOGGER_NAME] = (target, level, handlers)
    return loggers[0]
