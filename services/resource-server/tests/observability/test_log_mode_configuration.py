import logging

import pytest
import structlog

from resource_server.core.config import AppSettings
from resource_server.observability.logging import (
    _json_renderer,
    _plain_renderer,
    configure_logging,
)


class TestLogModeConfiguration:
    def test_default_log_mode_is_plain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOG_MODE", raising=False)
        settings = AppSettings()
        assert settings.log_mode == "plain"

    def test_json_mode_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_MODE", "json")
        settings = AppSettings()
        assert settings.log_mode == "json"

    def test_invalid_mode_falls_back_to_plain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_MODE", "yaml")
        with pytest.warns(UserWarning, match="Invalid LOG_MODE 'yaml'"):
            settings = AppSettings()
        assert settings.log_mode == "plain"

    def test_mode_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_MODE", "JSON")
        settings = AppSettings()
        assert settings.log_mode == "json"

    def test_configure_logging_plain_uses_processor_formatter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_MODE", "plain")
        settings = AppSettings()
        configure_logging(settings)
        root = logging.getLogger()
        assert any(
            isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
            for h in root.handlers
        )

    def test_configure_logging_plain_uses_plain_renderer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_MODE", "plain")
        settings = AppSettings()
        configure_logging(settings)
        root = logging.getLogger()
        pf = next(
            h.formatter
            for h in root.handlers
            if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
        )
        assert pf.processors[-1] is _plain_renderer

    def test_configure_logging_json_uses_json_renderer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_MODE", "json")
        settings = AppSettings()
        configure_logging(settings)
        root = logging.getLogger()
        pf = next(
            h.formatter
            for h in root.handlers
            if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
        )
        assert pf.processors[-1] is _json_renderer

    def test_log_level_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("LOG_MODE", "plain")
        settings = AppSettings()
        configure_logging(settings)
        root = logging.getLogger()
        assert root.level == logging.WARNING
