import logging
from pathlib import Path


class Logger:

    def __init__(self, log_file: Path):

        self._logger = logging.getLogger("NexusDocs")

        if self._logger.handlers:
            return

        self._logger.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s"
        )

        file_handler = logging.FileHandler(
            log_file,
            encoding="utf-8"
        )

        console_handler = logging.StreamHandler()

        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self._logger.addHandler(file_handler)
        self._logger.addHandler(console_handler)

    @property
    def instance(self) -> logging.Logger:
        return self._logger