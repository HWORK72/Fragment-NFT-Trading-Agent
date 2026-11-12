import io
import logging
from pathlib import Path
import sys
from typing import Final, TextIO

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent
LOG_FILE_PATH: Final[Path] = BASE_DIR / "logs.txt"


class ImmediateFlushFileHandler(logging.FileHandler):
    def __init__(self, filename: Path) -> None:
        super().__init__(
            filename=str(filename),
            mode="w",
            encoding="utf-8",
            delay=False,
        )

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()

    def write_raw_line(self, text: str) -> None:
        if self.stream is not None:
            self.stream.write(text)
            self.flush()


class ConsoleToLogStream(io.TextIOBase):
    def __init__(self, original_stream: TextIO, file_handler: ImmediateFlushFileHandler) -> None:
        self._original_stream: TextIO = original_stream
        self._file_handler: ImmediateFlushFileHandler = file_handler

    def write(self, text: str) -> int:
        written: int = self._original_stream.write(text)
        self._original_stream.flush()
        self._file_handler.write_raw_line(text)
        return written

    def flush(self) -> None:
        self._original_stream.flush()
        self._file_handler.flush()

    def isatty(self) -> bool:
        return getattr(self._original_stream, "isatty", lambda: False)()


_UNIFIED_FILE_HANDLER: ImmediateFlushFileHandler | None = None
_OriginalStdout: TextIO = sys.stdout
_OriginalStderr: TextIO = sys.stderr


def _initialize_unified_logging() -> ImmediateFlushFileHandler:
    global _UNIFIED_FILE_HANDLER
    if _UNIFIED_FILE_HANDLER is not None:
        return _UNIFIED_FILE_HANDLER

    handler: ImmediateFlushFileHandler = ImmediateFlushFileHandler(LOG_FILE_PATH)
    formatter: logging.Formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    stream_handler: logging.StreamHandler = logging.StreamHandler(_OriginalStdout)
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.addHandler(stream_handler)

    sys.stdout = ConsoleToLogStream(_OriginalStdout, handler)
    sys.stderr = ConsoleToLogStream(_OriginalStderr, handler)

    _UNIFIED_FILE_HANDLER = handler
    return handler


def get_logger(name: str) -> logging.Logger:
    handler: ImmediateFlushFileHandler = _initialize_unified_logging()
    child_logger: logging.Logger = logging.getLogger(name)
    child_logger.setLevel(logging.INFO)
    child_logger.propagate = False

    if not child_logger.handlers:
        formatter: logging.Formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s"
        )
        stream_handler: logging.StreamHandler = logging.StreamHandler(_OriginalStdout)
        stream_handler.setFormatter(formatter)
        child_logger.addHandler(handler)
        child_logger.addHandler(stream_handler)

    return child_logger


logger: logging.Logger = get_logger("FragmentCore")