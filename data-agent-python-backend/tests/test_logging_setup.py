import logging

from app.observability.logging_setup import configure_logging


def test_configure_logging_writes_to_file(tmp_path) -> None:
    log_path = tmp_path / "app.log"
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    try:
        root.handlers.clear()
        configure_logging(file_path=log_path)

        logging.getLogger("tests.logging").info("file logging works")

        for handler in root.handlers:
            handler.flush()
        assert "file logging works" in log_path.read_text(encoding="utf-8")
    finally:
        for handler in root.handlers[:]:
            handler.close()
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
