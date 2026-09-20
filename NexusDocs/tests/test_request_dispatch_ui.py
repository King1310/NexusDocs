import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from tests.factories.person_factory import PersonFactory
from ui.request_dispatch_window import RequestDispatchWindow
from ui.request_dispatch_window import _PrepareWordWorker, _SplitScanWorker


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


def test_selecting_reviewed_word_waits_for_explicit_conversion(tmp_path, monkeypatch):
    person = PersonFactory.create(7)

    class Repository:
        @staticmethod
        def get_all():
            return [person]

    window = RequestDispatchWindow(Repository())
    selected = tmp_path / "проверенный пользователем.docx"
    selected.write_bytes(b"saved edits")
    started = []
    monkeypatch.setattr(window, "_start_worker", lambda worker, **kwargs: started.append(worker))
    window.scan_input.setText(str(selected))

    assert started == []
    assert "Преобразовать Word" in window.split_button.text()
    assert window.package_input.text() == ""
    window.split_scan()
    assert len(started) == 1
    assert isinstance(started[0], _PrepareWordWorker)
    assert started[0].docx_path == selected
    assert window.package_input.text() == ""

    pdf = tmp_path / "скан.pdf"
    pdf.write_bytes(b"pdf")
    window.scan_input.setText(str(pdf))
    window.split_scan()
    assert isinstance(started[1], _SplitScanWorker)
    assert window.split_button.text() == "1. Разбить PDF"
