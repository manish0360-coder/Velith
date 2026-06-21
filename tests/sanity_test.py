"""M0 sanity test.

The single load-bearing test of M0 (§8). Its job is to prove the pipe is
connected — that pytest runs (inside the container, per the acceptance
command), that configuration loads and validates, and that structured logging
emits. It asserts nothing about agents, models, datasets, or verification:
none of those exist yet.
"""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import ValidationError

from velith.core.config import Settings, get_settings
from velith.core.logging import JsonFormatter, configure_logging, get_logger


def test_pytest_executes() -> None:
    """Proves pytest itself runs to completion in this environment."""
    assert True


def test_settings_load_and_validate(settings: Settings) -> None:
    """Settings load from the environment and validate (M0 §2.4)."""
    assert settings.app_name == "velith"
    assert settings.environment in {"development", "ci", "production"}
    assert settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert settings.log_format in {"json", "console"}


def test_invalid_config_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid configuration raises immediately rather than defaulting (M0 §10)."""
    monkeypatch.setenv("VELITH_LOG_LEVEL", "NOT_A_LEVEL")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()
    get_settings.cache_clear()


def test_logger_emits_structured_info_line(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """The logger constructs and emits at least one INFO line (M0 §2.5, §9)."""
    configure_logging(settings)
    logger = get_logger("velith.sanity")
    with caplog.at_level(logging.INFO):
        logger.info("m0 sanity check ok", extra={"event": "m0_sanity"})
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert info_records, "expected at least one INFO record"
    assert any(r.getMessage() == "m0 sanity check ok" for r in info_records)


def test_json_formatter_produces_machine_parseable_record() -> None:
    """Structured records are valid JSON carrying message and extra context (M0 §9)."""
    record = logging.LogRecord(
        name="velith.sanity",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m0 sanity check ok",
        args=(),
        exc_info=None,
    )
    record.event = "m0_sanity"
    rendered = JsonFormatter().format(record)
    parsed = json.loads(rendered)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "velith.sanity"
    assert parsed["message"] == "m0 sanity check ok"
    assert parsed["event"] == "m0_sanity"
