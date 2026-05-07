from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable


class GuiLogHandler(logging.Handler):
    """Handler do wysyłania logów bezpośrednio do GUI."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self.callback(self.format(record))


def setup_logging(log_file: Path, gui_callback: Callable[[str], None] | None = None) -> logging.Logger:
    logger = logging.getLogger("werhe_tool")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    if gui_callback:
        gh = GuiLogHandler(gui_callback)
        gh.setFormatter(formatter)
        logger.addHandler(gh)

    return logger
