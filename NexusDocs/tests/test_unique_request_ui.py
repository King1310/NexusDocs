import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QDate, QPoint
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea
from docx import Document

from domain.enums.registration_mode import RegistrationMode

from ui.unique_request_dialog import UniqueRequestDialog


class _EmptyPeople:
    @staticmethod
    def get_all():
        return []


class _EmptyRecipients:
    @staticmethod
    def search(_template_slug, _query):
        return []

    @staticmethod
    def upsert(_recipient):
        raise AssertionError("Сохранение в этом тесте не ожидалось")


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dialog():
    value = UniqueRequestDialog(
        person_repository=_EmptyPeople(),
        custom_recipient_repository=_EmptyRecipients(),
    )
    yield value
    value.close()


def test_wizard_starts_with_executor_and_offers_all_templates(dialog):
    assert dialog.pages.currentIndex() == dialog.PAGE_EXECUTOR
    assert dialog.executor_combo.count() == 3
    assert dialog.template_combo.count() == 15
    assert dialog.not_in_database_checkbox.text() == "Человека нет в базе"


def test_not_in_database_adds_minimal_subject_page(dialog):
    dialog.not_in_database_checkbox.setChecked(True)
    mvd_index = next(
        index
        for index in range(dialog.template_combo.count())
        if dialog.template_combo.itemData(index).number == 10
    )
    dialog.template_combo.setCurrentIndex(mvd_index)

    visible_fields = {
        key for key, (label, _widget) in dialog.subject_rows.items()
        if not label.isHidden()
    }

    assert dialog.PAGE_SUBJECT_DATA in dialog._page_order()
    assert visible_fields == {
        "full_name",
        "birth_date",
        "birth_place",
        "registration_address",
        "case_type",
        "case_number",
    }


def test_fixed_template_can_keep_original_header(dialog):
    first_index = next(
        index
        for index in range(dialog.template_combo.count())
        if dialog.template_combo.itemData(index).number == 1
    )
    dialog.template_combo.setCurrentIndex(first_index)

    assert dialog.recipient_mode_combo.findData(dialog.MODE_TEMPLATE) >= 0
    assert dialog.recipient_mode_combo.findData(dialog.MODE_GOOGLE) >= 0
    assert dialog.recipient_mode_combo.findData(dialog.MODE_MANUAL) >= 0


def test_manual_editor_uses_hints_not_document_values(dialog):
    dialog.recipient_mode_combo.setCurrentIndex(
        dialog.recipient_mode_combo.findData(dialog.MODE_MANUAL)
    )

    assert dialog.lookup_name_input.text() == ""
    assert "425 ВКГ" in dialog.lookup_name_input.placeholderText()
    assert dialog.save_recipient_checkbox.isChecked()


def test_changing_template_clears_previous_manual_recipient(dialog):
    dialog.recipient_mode_combo.setCurrentIndex(
        dialog.recipient_mode_combo.findData(dialog.MODE_MANUAL)
    )
    dialog.recipient_input.setPlainText("Командиру старой части")
    dialog.postal_address_input.setPlainText("123456, старый адрес")
    dialog.target_unit_input.setText("33790")

    dialog.template_combo.setCurrentIndex(1)

    assert not dialog.recipient_input.toPlainText()
    assert not dialog.postal_address_input.toPlainText()
    assert not dialog.target_unit_input.text()


def test_dynamic_template_without_saved_header_opens_search_mode(dialog):
    dynamic_index = next(
        index for index in range(dialog.template_combo.count())
        if dialog.template_combo.itemData(index).requires_resolved_header
    )
    dialog.template_combo.setCurrentIndex(dynamic_index)

    assert dialog.recipient_mode_combo.currentData() == dialog.MODE_GOOGLE


def test_register_later_disables_number_and_date(dialog):
    later_index = dialog.registration_mode_combo.findData(
        next(
            mode
            for mode in (
                dialog.registration_mode_combo.itemData(index)
                for index in range(dialog.registration_mode_combo.count())
            )
            if mode.name == "LATER"
        )
    )
    dialog.registration_mode_combo.setCurrentIndex(later_index)

    assert not dialog.outgoing_number_input.isEnabled()
    assert not dialog.outgoing_date_input.isEnabled()


def test_comboboxes_stay_inside_pages_at_minimum_window_size(dialog):
    dialog.resize(dialog.minimumSize())
    dialog.show()
    QApplication.processEvents()

    dialog.pages.setCurrentIndex(dialog.PAGE_TEMPLATE)
    QApplication.processEvents()
    template_right = dialog.template_combo.mapTo(
        dialog.pages.currentWidget(), QPoint(dialog.template_combo.width(), 0)
    ).x()
    assert template_right <= dialog.pages.currentWidget().width()

    dialog.not_in_database_checkbox.setChecked(True)
    dialog.pages.setCurrentIndex(dialog.PAGE_SUBJECT_DATA)
    QApplication.processEvents()
    subject_scroll = dialog.pages.currentWidget().findChild(QScrollArea)
    for editor in (
        dialog.birth_date_input, dialog.passport_date_input,
        dialog.soch_date_input, dialog.case_type_input,
    ):
        if not editor.isVisible():
            continue
        right = editor.mapTo(
            subject_scroll.viewport(), QPoint(editor.width(), 0)
        ).x()
        assert right <= subject_scroll.viewport().width()

    dialog.pages.setCurrentIndex(dialog.PAGE_RECIPIENT)
    scroll = dialog.pages.currentWidget().findChild(QScrollArea)
    for mode in (dialog.MODE_MANUAL, dialog.MODE_GOOGLE, dialog.MODE_SAVED):
        dialog.recipient_mode_combo.setCurrentIndex(
            dialog.recipient_mode_combo.findData(mode)
        )
        QApplication.processEvents()
        mode_right = dialog.recipient_mode_combo.mapTo(
            scroll.viewport(), QPoint(dialog.recipient_mode_combo.width(), 0)
        ).x()
        assert mode_right <= scroll.viewport().width(), mode


def test_new_person_can_use_only_target_unit_number(dialog, monkeypatch, tmp_path):
    dialog.not_in_database_checkbox.setChecked(True)
    dialog.last_name_input.setText("Иванов")
    dialog.first_name_input.setText("Иван")
    dialog.middle_name_input.setText("Иванович")
    dialog.birth_date_input.setDate(QDate(1990, 1, 1))
    dialog.military_unit_input.setText("01007")
    dialog.military_rank_input.setText("рядовой")
    dialog.article_input.setText("ч. 5 ст. 337 УК РФ")
    dialog.recipient_mode_combo.setCurrentIndex(
        dialog.recipient_mode_combo.findData(dialog.MODE_UNIT_NUMBER)
    )
    dialog.target_unit_input.setText("в/ч 33790")
    dialog.registration_mode_combo.setCurrentIndex(
        dialog.registration_mode_combo.findData(RegistrationMode.LATER)
    )
    assert dialog._validate_page(dialog.PAGE_SUBJECT_DATA)
    assert dialog._validate_page(dialog.PAGE_RECIPIENT)

    created = {}

    def fake_create(person, organization, header, mode, *, is_transient):
        created.update(
            person=person, organization=organization, header=header,
            mode=mode, is_transient=is_transient,
        )
        return tmp_path / "unique.docx"

    monkeypatch.setattr(dialog, "_create_document", fake_create)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(
        "ui.unique_request_dialog.QDesktopServices.openUrl", lambda *args: True
    )
    dialog._generate()

    assert created["person"].id > 0
    assert created["is_transient"] is True
    assert created["organization"] is None
    assert created["header"] == "Командиру войсковой части № 33790"
    assert created["mode"] is RegistrationMode.LATER


def test_new_person_unit_request_creates_word_outside_people_database(
    dialog, tmp_path,
):
    dialog.not_in_database_checkbox.setChecked(True)
    dialog.last_name_input.setText("Иванов")
    dialog.first_name_input.setText("Иван")
    dialog.middle_name_input.setText("Иванович")
    dialog.birth_date_input.setDate(QDate(1990, 1, 1))
    dialog.military_unit_input.setText("01007")
    dialog.military_rank_input.setText("рядовой")
    dialog.article_input.setText("ч. 5 ст. 337 УК РФ")
    dialog.recipient_mode_combo.setCurrentIndex(
        dialog.recipient_mode_combo.findData(dialog.MODE_UNIT_NUMBER)
    )
    dialog.target_unit_input.setText("33790")

    person = dialog._build_transient_person()
    organization, header = dialog._selected_recipient()
    output = dialog._create_document(
        person, organization, header, RegistrationMode.LATER,
        is_transient=True, output_root=tmp_path,
    )

    assert output.is_file()
    assert output.is_relative_to(tmp_path / "Уникальные запросы")
    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert "Командиру войсковой части № 33790" in text.replace("\u00a0", " ")
    assert "в/части 01007" in text.replace("\u00a0", " ")
    assert "01.01.1990" in text
    assert f"{date.today():%d.%m.%Y} г.р." not in text


def test_new_person_must_choose_birth_date_instead_of_using_today(dialog):
    dialog.not_in_database_checkbox.setChecked(True)
    assert not dialog._date_selected(dialog.birth_date_input)
    assert "дата рождения" in dialog._missing_subject_fields()
