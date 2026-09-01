import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from domain.value_objects.fullname import FullName
from tests.factories.person_factory import PersonFactory
from ui.person.person_list_window import PersonListWindow


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


class EmptyRepository:
    @staticmethod
    def get_all():
        return []


def test_person_table_window_is_resizable_and_has_no_obsolete_buttons():
    window = PersonListWindow(EmptyRepository())

    assert window.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    assert window.minimumWidth() == 700
    assert window.people_table.horizontalHeader().sectionResizeMode(1) == (
        QHeaderView.ResizeMode.Stretch
    )
    assert not hasattr(window, "refresh_button")
    assert not hasattr(window, "headers_button")
    assert not hasattr(window, "export_pdf_button")
    assert not hasattr(window, "export_documents_to_pdf")
    assert "Google AI" in window.internet_headers_button.text()


def test_id_and_last_name_columns_sort_in_both_directions():
    window = PersonListWindow(EmptyRepository())
    people = []
    for person_id, last_name in ((10, "Яковлев"), (2, "Белов"), (1, "Алексеев")):
        person = PersonFactory.create(person_id)
        person.full_name = FullName(last_name, "Иван", "Иванович")
        people.append(person)
    window._fill_table(people)

    assert window.people_table.isSortingEnabled()

    window.people_table.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert [
        window.people_table.item(row, 0).data(Qt.ItemDataRole.DisplayRole)
        for row in range(window.people_table.rowCount())
    ] == [1, 2, 10]

    window.people_table.sortItems(0, Qt.SortOrder.DescendingOrder)
    assert [
        window.people_table.item(row, 0).data(Qt.ItemDataRole.DisplayRole)
        for row in range(window.people_table.rowCount())
    ] == [10, 2, 1]

    window.people_table.sortItems(1, Qt.SortOrder.AscendingOrder)
    assert [
        window.people_table.item(row, 1).text()
        for row in range(window.people_table.rowCount())
    ] == ["Алексеев", "Белов", "Яковлев"]

    window.people_table.sortItems(1, Qt.SortOrder.DescendingOrder)
    assert [
        window.people_table.item(row, 1).text()
        for row in range(window.people_table.rowCount())
    ] == ["Яковлев", "Белов", "Алексеев"]


def test_independent_people_window_uses_form_opener_callback():
    calls = []
    window = PersonListWindow(
        EmptyRepository(),
        parent=None,
        person_form_opener=lambda **kwargs: calls.append(kwargs),
    )

    window.add_person()

    assert window.parent() is None
    assert calls == [{}]


def test_internal_header_status_has_readable_ui_label():
    assert PersonListWindow._verification_status_label("auto_found") == (
        "найдено автоматически"
    )
    assert PersonListWindow._verification_status_label("needs_review") == (
        "требует проверки"
    )
