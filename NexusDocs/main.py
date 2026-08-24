import sys
import ctypes

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from database.schema import create_tables
from ui.main_window import APP_ICON_PATH, MainWindow


def main() -> None:
    """
    Точка входа в приложение NexusDocs.
    """

    # Создать таблицы базы данных,
    # если они ещё не существуют.
    create_tables()

    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "NexusDocs.desktop"
        )

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    window = MainWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
