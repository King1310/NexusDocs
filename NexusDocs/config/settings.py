from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Settings:
    """
    Глобальные настройки приложения.
    """

    APP_NAME: str = "NexusDocs"

    DATABASE_NAME: str = "nexusdocs.db"

    BASE_DIR: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
    )

    @property
    def database_path(self) -> Path:
        return self.BASE_DIR / self.DATABASE_NAME

    @property
    def logs_path(self) -> Path:
        return self.BASE_DIR / "logs"

    @property
    def templates_path(self) -> Path:
        return self.BASE_DIR / "templates"

    @property
    def output_path(self) -> Path:
        return self.BASE_DIR / "output"

    @property
    def cache_path(self) -> Path:
        return self.BASE_DIR / "cache"

    @property
    def assets_path(self) -> Path:
        return self.BASE_DIR / "assets"

    def ensure_directories(self) -> None:
        """
        Создаёт необходимые директории приложения.
        """

        directories = (
            self.logs_path,
            self.templates_path,
            self.output_path,
            self.cache_path,
            self.assets_path,
        )

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)