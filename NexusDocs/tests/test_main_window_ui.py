import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui.main_window import APP_ICON_PATH, MainWindow


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_has_icon_and_no_headers_database_button():
    window = MainWindow()

    assert APP_ICON_PATH.is_file()
    assert not window.windowIcon().isNull()
    assert not hasattr(window, "settings_button")
    assert window.new_request_button.text() == "Новый запрос"
    assert window.people_button.text() == "База людей"
    assert window.extension_button.text() == "Сделать продление до 10 суток"
    assert window.dispatch_button.text() == "Отправка запросов"


def test_people_database_is_an_independent_top_level_window():
    class EmptyRepository:
        @staticmethod
        def get_all():
            return []

    main_window = MainWindow()
    main_window.person_repository = EmptyRepository()

    main_window.open_people_database()

    assert main_window.person_list_window.parent() is None
    assert main_window.person_list_window.isWindow()
    assert main_window.person_list_window.person_form_opener is not None
    main_window.person_list_window.close()
    main_window.close()


def test_request_dispatch_is_an_independent_top_level_window():
    class EmptyRepository:
        @staticmethod
        def get_all():
            return []

    main_window = MainWindow()
    main_window.person_repository = EmptyRepository()

    main_window.open_request_dispatch()

    assert main_window.request_dispatch_window.parent() is None
    assert main_window.request_dispatch_window.isWindow()
    main_window.request_dispatch_window.close()
    main_window.close()
