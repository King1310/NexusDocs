import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from tests.factories.person_factory import PersonFactory
from ui.request_dispatch_window import RequestDispatchWindow


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


class EmptyRepository:
    @staticmethod
    def get_all():
        return []


def test_dispatch_window_has_two_independent_stages():
    window = RequestDispatchWindow(EmptyRepository())

    assert window.windowTitle() == "Отправка запросов"
    assert window.split_button.text() == "1. Разбить PDF"
    assert window.create_drafts_button.text() == (
        "2. Создать черновики Outlook"
    )
    assert not window.split_button.isEnabled()
    assert window.create_drafts_button.isEnabled()


def test_split_stage_loads_people_without_affecting_package_stage():
    person = PersonFactory.create(7)

    class Repository:
        @staticmethod
        def get_all():
            return [person]

    window = RequestDispatchWindow(Repository())

    assert window.person_combo.currentData() == 7
    assert window.split_button.isEnabled()
    assert window.package_input.text() == ""
