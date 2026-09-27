import asyncio
import logging

import pytest
from sci_etl_core.llm.relevance_async import AsyncRelevanceFilter
from sci_etl_core.models import RawRecord

from udg_catalogue import logs
from udg_catalogue.logs import CORE_LOGGER_NAME, LOGGER_NAME, configure_run_logging
from udg_catalogue.progress import LoggingRelevanceFilter

RECORD = RawRecord(record_id="2601.00001v1", title="Dragonfly 44", abstract="Short abstract.")


class AcceptingRelevanceFilter(AsyncRelevanceFilter):
    async def is_relevant(self, record):
        return True


@pytest.fixture(autouse=True)
def restored_loggers(monkeypatch):
    monkeypatch.setattr(logs, "_installed", {})
    yield
    for name in (LOGGER_NAME, CORE_LOGGER_NAME):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def core_line_while_checking_a_paper(message):
    async def check_then_log():
        await LoggingRelevanceFilter(AcceptingRelevanceFilter(), lambda _message: None).is_relevant(RECORD)
        logging.getLogger(f"{CORE_LOGGER_NAME}.pipeline").warning(message)

    asyncio.run(check_then_log())


def test_run_log_holds_catalogue_and_core_lines_with_the_paper_id(tmp_path, capsys):
    log_file = tmp_path / "logs" / "run.log"

    logger = configure_run_logging(log_file)
    logger.info("Run started")
    logging.getLogger(CORE_LOGGER_NAME).info("Outside any paper")
    core_line_while_checking_a_paper("Retrying the download")

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert logger.name == LOGGER_NAME
    assert [line.split(" - ", 1)[1] for line in lines] == [
        "Run started",
        "Outside any paper",
        "[2601.00001v1] Retrying the download",
    ]
    assert "[WARNING] [sci_etl_core.pipeline]" in lines[2]
    assert capsys.readouterr().out.splitlines()[-1].endswith("[2601.00001v1] Retrying the download")
    assert not logging.getLogger(CORE_LOGGER_NAME).propagate


def test_core_arguments_are_merged_before_the_paper_id_is_added(tmp_path):
    log_file = tmp_path / "run.log"
    configure_run_logging(log_file)

    async def check_then_log():
        await LoggingRelevanceFilter(AcceptingRelevanceFilter(), lambda _message: None).is_relevant(RECORD)
        logging.getLogger(CORE_LOGGER_NAME).info("Fetched %d bytes", 42)

    asyncio.run(check_then_log())

    assert log_file.read_text(encoding="utf-8").rstrip().endswith("[2601.00001v1] Fetched 42 bytes")


def test_repeating_the_same_configuration_adds_no_handlers(tmp_path):
    log_file = tmp_path / "run.log"

    first = configure_run_logging(log_file)
    handlers = list(first.handlers)
    second = configure_run_logging(log_file)

    assert second is first
    assert second.handlers == handlers
    assert len(handlers) == 2


def test_a_new_log_file_replaces_the_handlers_installed_before(tmp_path):
    old_file = tmp_path / "old.log"
    new_file = tmp_path / "new.log"
    old_handlers = list(configure_run_logging(old_file).handlers)

    logger = configure_run_logging(new_file, logging.WARNING)
    logger.info("Hidden")
    logger.warning("Shown")

    assert not any(handler in logger.handlers for handler in old_handlers)
    assert not any(handler in logging.getLogger(CORE_LOGGER_NAME).handlers for handler in old_handlers)
    assert old_handlers[0].stream is None
    assert old_file.read_text(encoding="utf-8") == ""
    assert new_file.read_text(encoding="utf-8").rstrip().endswith("Shown")
    assert logging.getLogger(CORE_LOGGER_NAME).level == logging.WARNING
