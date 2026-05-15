import logging

import structlog


class TestExistingConventions:
    def test_getlogger_pattern_works(self) -> None:
        lgr = logging.getLogger(__name__)
        assert lgr.name == __name__

    def test_structlog_getlogger_works(self) -> None:
        lgr = structlog.get_logger(__name__)
        assert lgr is not None

    def test_aop_compatibility(self) -> None:
        from bff.aop.logging_decorator import log_io

        @log_io
        def sample(x: int) -> int:
            return x * 2

        assert sample(3) == 6
