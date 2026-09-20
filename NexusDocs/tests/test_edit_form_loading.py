import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from domain.value_objects.soch_case import SochCase
from tests.factories.person_factory import PersonFactory
from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE, run_form_sequence
from ui.person_birth_window import PersonBirthWindow
from ui.person_document_window import PersonDocumentWindow
from ui.person_military_window import PersonMilitaryWindow
from ui.person_passport_window import PersonPassportWindow
from ui.person_registration_window import PersonRegistrationWindow
from ui.person_soch_window import PersonSochWindow


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def form_data() -> PersonFormData:
    data = PersonFormData.from_person(PersonFactory.create())
    data.soch_case = SochCase(
        soch_date=date(2026, 7, 20),
        soch_place="Балашиха",
        duration="Более 1 месяца",
        case_type="УД",
        case_number="123/2026",
        procedural_control="ВУД",
        article="ч. 5 ст. 337 УК РФ",
        registration_date=date(2026, 7, 25),
        circumstances="Самовольное оставление части",
    )
    return data


def test_birth_window_loads_existing_data(form_data):
    window = PersonBirthWindow(form_data)

    assert window.birth_date_input.date().toPython() == date(1999, 8, 15)
    assert window.region_input.text() == "Московская область"
    assert window.city_input.text() == "Балашиха"
    assert window.street_input.text() == "Советская"
    assert window.house_input.text() == "10"


def test_registration_window_loads_existing_data(form_data):
    window = PersonRegistrationWindow(form_data)

    assert window.region_input.text() == "Московская область"
    assert window.city_input.text() == "Балашиха"
    assert window.street_input.text() == "Ленина"
    assert window.house_input.text() == "15"
    assert window.apartment_input.text() == "20"


def test_military_window_loads_existing_data(form_data):
    window = PersonMilitaryWindow(form_data)

    assert window.military_unit_input.text() == "12345"
    assert window.military_deployment_input.text() == (
        "г. Балашиха Московской области"
    )
    assert window.service_basis_input.currentText() == "по контракту"
    assert window.rank_input.text() == "рядовой"
    assert window.position_input.text() == "стрелок"
    assert window.military_id_input.text() == "АБ1234567"
    assert "Номер жетона:" in {
        label.text() for label in window.findChildren(QLabel)
    }
    assert "Военный билет:" not in {
        label.text() for label in window.findChildren(QLabel)
    }


def test_soch_window_loads_existing_data(form_data):
    window = PersonSochWindow(form_data)

    assert window.soch_date_input.date().toPython() == date(2026, 7, 20)
    assert "Дата регистрации:" not in {
        label.text() for label in window.findChildren(QLabel)
    }
    assert window.circumstances_input.currentText() == (
        "Самовольное оставление части"
    )
    assert window.soch_place_input.text() == "Балашиха"
    assert window.duration_input.currentText() == "Более 1 месяца"
    assert window.case_type_input.currentText() == "УД"
    assert window.case_number_input.text() == "123/2026"
    assert window.procedural_control_input.currentText() == "ВУД"
    assert window.article_input.text() == "ч. 5 ст. 337 УК РФ"


@pytest.mark.parametrize(
    ("duration", "article"),
    (
        ("Более 1 месяца", "ч. 5 ст. 337 УК РФ"),
        ("Более 10 суток, но не более месяца", "ч. 3.1 ст. 337 УК РФ"),
        ("Более двух суток, но не более 10 дней", "ч. 2.1 ст. 337 УК РФ"),
    ),
)
def test_soch_duration_updates_article(form_data, duration, article):
    window = PersonSochWindow(form_data)

    window.duration_input.setCurrentText(duration)

    assert window.article_input.text() == article


def test_mp_case_hides_and_does_not_require_case_number(form_data, monkeypatch):
    window = PersonSochWindow(form_data)
    warnings = []
    monkeypatch.setattr(
        "ui.person_soch_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )

    window.case_type_input.setCurrentText("МП")
    window.save_form()

    assert window.case_number_label.isHidden()
    assert window.case_number_input.isHidden()
    assert warnings == []
    assert window.result() == QDialog.DialogCode.Accepted
    assert form_data.soch_case is not None
    assert form_data.soch_case.case_type == "МП"
    assert form_data.soch_case.case_number is None
    assert form_data.soch_case.registration_date == date(2026, 7, 25)


def test_document_window_loads_existing_data(form_data):
    window = PersonDocumentWindow(form_data)

    assert window.outgoing_number_input.text() == "123/1"
    assert window.outgoing_date_input.date().toPython() == date.today()
    assert window.vpg_input.value() == 60


@pytest.mark.parametrize(
    "window_type",
    (
        PersonPassportWindow,
        PersonBirthWindow,
        PersonRegistrationWindow,
        PersonMilitaryWindow,
        PersonSochWindow,
        PersonDocumentWindow,
    ),
)
def test_back_button_returns_navigation_code(form_data, window_type):
    window = window_type(form_data)

    window.back_button.click()

    assert window.result() == BACK_DIALOG_CODE


def test_form_sequence_reopens_previous_step_after_back():
    opened_steps = []

    class FirstStep:
        results = [QDialog.DialogCode.Accepted, QDialog.DialogCode.Accepted]

        def __init__(self, form_data, parent):
            opened_steps.append("first")

        def exec(self):
            return self.results.pop(0)

    class SecondStep:
        results = [BACK_DIALOG_CODE, QDialog.DialogCode.Accepted]

        def __init__(self, form_data, parent):
            opened_steps.append("second")

        def exec(self):
            return self.results.pop(0)

    assert run_form_sequence(
        parent=None,
        form_data=PersonFormData(),
        dialog_types=(FirstStep, SecondStep),
    )
    assert opened_steps == ["first", "second", "first", "second"]
