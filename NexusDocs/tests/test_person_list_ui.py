import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from types import SimpleNamespace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from domain.value_objects.fullname import FullName
from dataclasses import replace
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
    assert window.generate_extension_button.text() == (
        "Сформировать продление до 10 суток"
    )
    assert not hasattr(window, "signed_scan_button")


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


def test_search_is_case_insensitive_and_supports_id_full_name_and_yo():
    people = []
    for person_id, full_name in (
        (42, FullName("Иванов", "Илья", "Игоревич")),
        (7, FullName("Семёнов", "Пётр", "Петрович")),
        (15, FullName("Орлова", "Анна", "Сергеевна")),
    ):
        person = PersonFactory.create(person_id)
        person.full_name = full_name
        people.append(person)

    class Repository:
        @staticmethod
        def get_all():
            return list(people)

    window = PersonListWindow(Repository())

    for query, expected_ids in (
        ("  иВаНоВ  ", [42]),
        ("семенов", [7]),
        ("ПЕТР   петрович", [7]),
        ("иванов и.и.", [42]),
        ("42", [42]),
        ("7", [7]),
        ("анна орлова", [15]),
    ):
        window.search_input.setText(query)
        assert [
            window.people_table.item(row, 0).data(
                Qt.ItemDataRole.DisplayRole
            )
            for row in range(window.people_table.rowCount())
        ] == expected_ids


def test_corner_button_clears_search_and_sorting_without_a_label():
    people = []
    for person_id, last_name in ((9, "Яковлев"), (3, "Белов"), (6, "Орлов")):
        person = PersonFactory.create(person_id)
        person.full_name = FullName(last_name, "Иван", "Иванович")
        people.append(person)

    class Repository:
        @staticmethod
        def get_all():
            return list(people)

    window = PersonListWindow(Repository())
    assert window.reset_filters_button is not None
    assert window.reset_filters_button.text() == ""

    window.search_input.setText("белов")
    window.people_table.sortItems(1, Qt.SortOrder.DescendingOrder)
    assert window.people_table.rowCount() == 1

    window.reset_filters_button.click()

    assert window.search_input.text() == ""
    assert window.people_table.horizontalHeader().sortIndicatorSection() == -1
    assert window.people_table.rowCount() == 3
    assert [
        window.people_table.item(row, 0).data(Qt.ItemDataRole.DisplayRole)
        for row in range(window.people_table.rowCount())
    ] == [9, 3, 6]
    assert window.people_table.isSortingEnabled()


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


def test_new_generation_never_reuses_reviewed_word_path(tmp_path):
    reviewed = tmp_path / "комплект.docx"
    reviewed.write_bytes(b"saved manual edits")
    second = reviewed.with_name("комплект_2.docx")
    second.write_bytes(b"another saved copy")
    assert PersonListWindow._unused_document_path(reviewed).name == "комплект_3.docx"
    assert reviewed.read_bytes() == b"saved manual edits"


def test_generation_creates_one_signed_word_and_no_unsigned_copy(tmp_path, monkeypatch):
    person = PersonFactory.create(7)
    project = tmp_path / "NexusDocs"
    (project / "templates" / "requests").mkdir(parents=True)

    class Repository:
        @staticmethod
        def get_all():
            return [person]

    class Generation:
        @staticmethod
        def generate_bundle(**kwargs):
            return [tmp_path / "request.docx"]

    class Bundles:
        @staticmethod
        def bundle_filename(selected):
            assert selected is person
            return "ИвановИИ_07.09.2026_все_запросы.docx"

        @staticmethod
        def create_editable_bundle(sources, destination):
            destination.write_bytes(b"assembled")

    signed_calls = []

    class Signatures:
        @staticmethod
        def create_signed_copy(source, destination, investigator):
            signed_calls.append((source, destination, investigator))
            destination.write_bytes(b"signed")

    class Extensions:
        @staticmethod
        def missing_fields(selected):
            return ["not generated in this test"]

    window = PersonListWindow(Repository())
    window.generation_service = Generation()
    window.word_bundle_service = Bundles()
    window.document_signature_service = Signatures()
    window.extension_generation_service = Extensions()
    monkeypatch.setattr(window, "_get_selected_person", lambda: person)
    monkeypatch.setattr(
        window,
        "_ensure_headers_ready",
        lambda selected: SimpleNamespace(organizations=()),
    )
    monkeypatch.setattr(window, "_request_declension_overrides", lambda selected: {})
    monkeypatch.setattr(window, "_project_directory", lambda: project)
    monkeypatch.setattr(
        window,
        "_progress",
        lambda message: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(window, "_show_missing_extension_fields", lambda fields: None)
    warnings = []
    messages = []
    opened = []
    monkeypatch.setattr(
        "ui.person.person_list_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )
    monkeypatch.setattr(
        "ui.person.person_list_window.QMessageBox.information",
        lambda *args: messages.append(args),
    )
    monkeypatch.setattr(
        "ui.person.person_list_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()),
    )

    window.generate_documents()

    expected = project / "output" / "7" / "ИвановИИ_07.09.2026_все_запросы.docx"
    assert warnings == []
    assert expected.read_bytes() == b"signed"
    assert len(signed_calls) == 1
    assert [Path(value) for value in opened] == [expected]
    assert "один редактируемый комплект" in messages[0][2]
    assert not list(expected.parent.glob("*_без_подписи.docx"))


def test_extension_for_legacy_person_points_to_edit(monkeypatch):
    person = PersonFactory.create()
    person = replace(
        person,
        military=replace(
            person.military,
            military_deployment="",
            service_basis="",
        ),
        soch_case=replace(
            person.soch_case,
            registration_date=None,
            circumstances="",
        ),
    )

    class Repository:
        @staticmethod
        def get_all():
            return [person]

        @staticmethod
        def get_by_id(person_id):
            return person if person_id == person.id else None

    warnings = []
    monkeypatch.setattr(
        "ui.person.person_list_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )
    window = PersonListWindow(Repository())
    window.select_person(person.id)

    assert window.generate_extension() is None
    assert warnings
    message = warnings[0][2]
    assert "не все данные заполнены" in message
    assert "Дислокация в/части" in message
    assert "Дата регистрации" not in message
    assert "Редактировать" in message
