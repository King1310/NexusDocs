from config.settings import Settings
from core.version import Version
from utils.logger import Logger


class Application:

    def __init__(self):

        self.settings = Settings()

        self.settings.ensure_directories()

        self.version = Version(
            major=1,
            minor=0,
            patch=0,
            stage="stable"
        )

        self.logger = Logger(
            self.settings.logs_path / "nexusdocs.log"
        ).instance

        self.logger.info("Application initialized.")
