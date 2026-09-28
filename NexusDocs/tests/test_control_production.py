import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QLineEdit, QMessageBox, QPushButton

from services.control_production_generation_service import (
    ControlProductionData, ControlProductionGenerationService, DATE_OFFSETS,
    DIRECT_SLOTS, INPUT_FIELDS, NUMERIC_FIELDS, TEMPLATE_PATH, W, normalize_unit,
)
from ui.control_production_dialog import ControlProductionDialog


def sample():
    return ControlProductionData(values=dict(
        surname="Плетенёв", first_name="Роман", middle_name="Сергеевич",
        birth_place="г. Москва", citizenship="Российская Федерация", nationality="русский",
        education="среднее профессиональное", marital_status="женат",
        residence="Московская область, пос. Власиха", address="ул. Лесная, д. 37, кв. 2",
        passport_series="4515", passport_number="123456",
        passport_issuer="ОМВД России, 01.06.2015", unit="72164", rank="майор",
        position="начальник штаба — заместитель командира батальона",
        contract_place="Военного комиссариата города Москвы", personal_number="АБ-123456",
        case_number="12602000000000001", article_part="5",
    ), vud_date=date(2026, 9, 27), birth_date=date(1987, 7, 19), contract_date=date(2020, 5, 12))


def xml(path):
    with ZipFile(path) as package:
        return etree.fromstring(package.read("word/document.xml"))


def text(root):
    return "".join(node.text or "" for node in root.iter(W + "t"))


@pytest.mark.parametrize("start", [date(2026, 9, 27), date(2026, 12, 31), date(2024, 2, 20)])
def test_inclusive_dates_and_month_is_thirty_days(start):
    data = sample()
    data.vud_date = start
    slots = data.slots()
    for key, days in DATE_OFFSETS.items():
        assert slots[key] == (start + timedelta(days=days)).strftime("%d.%m.%Y")
    assert slots["ДатаВудКП"] == slots["Дата_ВУД"]


def test_complete_bundle_preserves_package_and_geometry(tmp_path):
    output = tmp_path / "full.docx"
    data = sample()
    ControlProductionGenerationService().generate(data, output)
    with ZipFile(TEMPLATE_PATH) as template, ZipFile(output) as generated:
        assert template.namelist() == generated.namelist()
        for name in template.namelist():
            if name != "word/document.xml":
                assert template.read(name) == generated.read(name)
    original, result = xml(TEMPLATE_PATH), xml(output)
    document_text = text(result)
    assert "{{" not in document_text and "MERGEFIELD" not in etree.tostring(result).decode()
    for title in ("КАРТОЧКА", "ПИСЬМЕННЫЕ", "ПЛАН", "Бульбов", "Агиров", "Литвинов"):
        assert title in document_text
    assert "Плетенёва" in document_text and "Плетенёвым" in document_text and "Плетенёву" in document_text
    assert "ПК {{ПК}}" not in document_text
    for tag in ("sectPr", "tblPr", "tblGrid", "trPr", "tcPr", "pPr", "rPr"):
        assert [etree.tostring(n) for n in original.iter(W + tag)] == [etree.tostring(n) for n in result.iter(W + tag)]
    assert len(list(result.iter(W + "tbl"))) == len(list(original.iter(W + "tbl")))
    assert len(list(result.iter(W + "r"))) == len(list(original.iter(W + "r")))


def test_only_marked_slots_changed_in_prepared_template():
    reference = TEMPLATE_PATH.with_name("reference.docx")
    source, template = xml(reference), xml(TEMPLATE_PATH)
    assert not list(template.iter(W + "fldChar"))
    assert not list(template.iter(W + "instrText"))
    for tag in ("sectPr", "tblPr", "tblGrid", "trPr", "tcPr", "pPr"):
        assert [etree.tostring(n) for n in source.iter(W + tag)] == [etree.tostring(n) for n in template.iter(W + tag)]
    ns = {"w": W[1:-1]}
    # All originally empty cells are left byte-for-byte intact.
    source_cells = list(source.iter(W + "tc"))
    template_cells = list(template.iter(W + "tc"))
    for before, after in zip(source_cells, template_cells, strict=True):
        if not before.xpath(".//w:t|.//w:fldChar", namespaces=ns):
            assert etree.tostring(before) == etree.tostring(after)
    settings = etree.fromstring(ZipFile(TEMPLATE_PATH).read("word/settings.xml"))
    assert settings.find(W + "mailMerge") is None


def test_swapped_dates_only_in_specific_plan_row(tmp_path):
    path = ControlProductionGenerationService().generate(sample(), tmp_path / "kp.docx")
    rows = [row for row in xml(path).iter(W + "tr") if "Представить уголовное дело на изучение" in text(row)]
    assert len(rows) == 1
    cells = list(rows[0].findall(W + "tc"))
    assert "16.10.2026" in text(cells[1])
    assert "26.10.2026" in text(cells[2])


@pytest.mark.parametrize("key", DIRECT_SLOTS)
def test_every_marked_field_can_be_omitted(key):
    data = sample()
    data.values.pop(key)
    assert data.slots()[DIRECT_SLOTS[key]] == ("0" if key in NUMERIC_FIELDS else "")


def test_failed_generation_does_not_damage_existing_file(tmp_path):
    output = tmp_path / "existing.docx"
    output.write_bytes(b"original")
    data = sample()
    data.values["surname"] = "{{another}}"
    with pytest.raises(ValueError):
        ControlProductionGenerationService().generate(data, output)
    assert output.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [output]


def test_declensions_can_be_overridden():
    data = sample()
    data.overrides["Фамилия_дп"] = "Другое склонение"
    assert data.slots()["Фамилия_дп"] == "Другое склонение"
    assert data.slots()["Инициалы"] == "Р.С."


def test_case_number_does_not_repeat_number_sign():
    data = sample()
    data.values["case_number"] = "№ 1.26.0200.2402.000152"
    assert data.slots()["M__уголовного_дела"] == "1.26.0200.2402.000152"


def test_no_birth_or_contract_date_is_invented():
    data = sample()
    data.contract_date = None
    assert data.slots()["ДатаКонтракта"] == ""


def test_entirely_blank_data_generates_complete_bundle(tmp_path):
    data = ControlProductionData()
    slots = data.slots()
    assert set(slots) == set(sample().slots())
    assert {key for key, value in slots.items() if value == "0"} == {DIRECT_SLOTS[key] for key in NUMERIC_FIELDS}
    assert all(value in ("", "0") for value in slots.values())
    path = ControlProductionGenerationService().generate(data, tmp_path / "empty.docx")
    result = text(xml(path))
    assert "{{" not in result and "Не указана" not in result
    assert "ч. 0 ст. 337 УК РФ" in result
    assert "Бульбов" in result and "ПЛАН" in result and "КАРТОЧКА" in result


def test_only_vud_date_is_enough_for_all_deadlines():
    slots = ControlProductionData(vud_date=date(2026, 9, 27)).slots()
    assert slots["ДатаВудКПМес"] == "26.10.2026"
    assert slots["Дата_рождения"] == slots["ДатаКонтракта"] == ""


@pytest.mark.parametrize("first,middle,initials", [("", "", ""), ("Роман", "", "Р."), ("", "Сергеевич", "С.")])
def test_partial_initials_are_safe(first, middle, initials):
    data = ControlProductionData(values={"first_name": first, "middle_name": middle})
    assert data.slots()["Инициалы"] == initials
    assert data.slots()["Фамилия_рп"] == ""


def test_all_steps_can_be_skipped_and_empty_docx_saved(app, tmp_path, monkeypatch):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    assert all("*" not in label.text() for label in dialog.findChildren(QLabel))
    path = tmp_path / "empty.docx"
    defaults = []
    def select_file(*args):
        defaults.append(args[2])
        return str(path), ""
    monkeypatch.setattr(QFileDialog, "getSaveFileName", select_file)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args)))
    for _ in range(6):
        dialog._next()
    assert path.is_file() and dialog.generated_path == path
    assert defaults == ["КП.docx"]
    assert all(widget.text() == "" for widget in dialog.form_inputs.values())
    dialog.close()


def test_dates_can_be_cleared_and_do_not_generate_fake_deadlines(app):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    fill_dialog(dialog, sample())
    for key in dialog.dates:
        dialog.dates[key].clear()
    data = dialog._collect()
    assert data.vud_date is None and data.birth_date is None and data.contract_date is None
    assert all(data.slots()[key] == "" for key in DATE_OFFSETS)
    dialog.close()


def test_date_can_be_typed_as_digits_and_cleared_with_keyboard(app):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    widget = dialog.dates["birth_date"]
    assert isinstance(widget, QLineEdit)
    assert widget.text() == "" and widget.placeholderText() == "01.01.2000"
    assert not any(button.text() == "Очистить" for button in dialog.findChildren(QPushButton))
    QTest.keyClicks(widget, "19071987")
    assert widget.text() == "19.07.1987"
    assert dialog._collect().birth_date == date(1987, 7, 19)
    QTest.keyClick(widget, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(widget, Qt.Key.Key_Backspace)
    assert widget.text() == "" and dialog._collect().birth_date is None
    dialog.close()


@pytest.mark.parametrize("value", ["31.02.2026", "29.02.2025", "01.01.20", "1.1.2000"])
def test_invalid_or_incomplete_date_has_clear_error(app, value):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    dialog.dates["vud_date"].setText(value)
    with pytest.raises(ValueError, match="Дата ВУД"):
        dialog._collect()
    dialog.close()


def test_formatted_date_and_leap_day_can_be_entered(app):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    QTest.keyClicks(dialog.dates["contract_date"], "29.02.2024")
    assert dialog._collect().contract_date == date(2024, 2, 29)
    dialog.close()


def test_explicitly_cleared_declension_stays_empty_after_navigation(app):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    fill_dialog(dialog, sample())
    dialog._show_step(5)
    dialog.form_inputs["Фамилия_рп"].clear()
    dialog._show_step(1)
    dialog._show_step(5)
    assert dialog._collect().slots()["Фамилия_рп"] == ""
    dialog.close()


def test_kp_db_mode_requires_explicit_person_selection(app, monkeypatch):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    dialog.database_radio.setChecked(True)
    dialog._next()
    assert dialog.stack.currentIndex() == 0
    assert warnings == ["Выберите человека из списка базы."]
    dialog.close()


def test_review_updates_auto_forms_after_name_change_but_retains_override(app):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    fill_dialog(dialog, sample())
    dialog._show_step(5)
    dialog.form_inputs["Фамилия_тп"].setText("Ручное склонение")
    dialog._show_step(1)
    dialog.inputs["surname"].setText("Иванов")
    dialog._show_step(5)
    assert dialog.form_inputs["Фамилия_рп"].text() == "Иванова"
    assert dialog.form_inputs["Фамилия_дп"].text() == "Иванову"
    assert dialog.form_inputs["Фамилия_тп"].text() == "Ручное склонение"
    dialog.close()


@pytest.mark.parametrize("value", ["72164", "в/ч 72164", "в/часть № 72164", "Войсковая часть 72164"])
def test_unit_without_duplicate_prefix(value):
    assert normalize_unit(value) == "72164"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class ReadOnlyRepository:
    def __init__(self, people=()):
        self.people = list(people)

    def get_all(self):
        return self.people


def fill_dialog(dialog, data):
    for key, widget in dialog.inputs.items():
        widget.setText(data.values[key])
    for key, widget in dialog.dates.items():
        value = getattr(data, key)
        widget.setText(value.strftime("%d.%m.%Y") if value else "")


def test_new_person_wizard_generates_without_any_db_write(app, tmp_path, monkeypatch):
    dialog = ControlProductionDialog(ReadOnlyRepository())
    assert set(dialog.inputs) == {key for key, *_ in INPUT_FIELDS}
    assert not any(key in dialog.inputs for key in ("defender", "awards", "ПК", "investigator"))
    assert all(widget.text() == "" for widget in dialog.dates.values())
    fill_dialog(dialog, sample())
    dialog._show_step(5)
    assert "26.10.2026" in dialog.summary.text()
    path = tmp_path / "kp.docx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog._generate()
    assert path.is_file() and dialog.generated_path == path
    dialog.close()


def test_db_copy_does_not_use_request_date_as_vud(app):
    from tests.factories.person_factory import PersonFactory
    person = PersonFactory.create()
    snapshot = deepcopy(person)
    data = ControlProductionData.from_person(person)
    assert data.vud_date is None and data.contract_date is None
    assert data.birth_date == person.birth.birth_date
    data.values["surname"] = "Изменённая"
    assert person == snapshot
    dialog = ControlProductionDialog(ReadOnlyRepository([person]))
    dialog.database_radio.setChecked(True)
    dialog.person_combo.setCurrentIndex(1)
    assert dialog._load_person()
    assert dialog.inputs["surname"].text() == person.full_name.last_name
    assert dialog.dates["vud_date"].text() == ""
    dialog.inputs["surname"].setText("Другое имя")
    assert person == snapshot
    dialog.new_person_radio.click()
    assert dialog.inputs["surname"].text() == ""
    dialog.close()


def test_main_window_opens_independent_kp_dialog(app):
    from ui.main_window import MainWindow
    window = MainWindow()
    window.person_repository = ReadOnlyRepository()
    window.open_control_production()
    dialog = window.control_production_dialog
    assert dialog.parent() is None and dialog.isWindow()
    window.open_control_production()
    assert window.control_production_dialog is dialog
    dialog.close()
    window.close()
