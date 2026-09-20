from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.soch_case import SochCase

from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE


class PersonSochWindow(QDialog):
    """
    Окно ввода сведений по делу о СОЧ.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle("Сведения о СОЧ")
        self.resize(550, 450)

        self._setup_ui()
        self._load_form_data()
        self._connect_signals()
        self._update_article()
        self._update_case_number_state()

    def _setup_ui(self) -> None:
        """
        Создать интерфейс окна.
        """

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.soch_date_input = QDateEdit()
        self.soch_date_input.setCalendarPopup(True)
        self.soch_date_input.setDate(
            QDate.currentDate()
        )

        self.circumstances_input = QComboBox()
        self.circumstances_input.addItems(
            [
                "Неявка в срок",
                "Самовольное оставление части",
            ]
        )

        self.soch_place_input = QLineEdit()

        self.duration_input = QComboBox()

        self.duration_input.addItems(
            [
                "Более 1 месяца",
                "Более 10 суток, но не более месяца",
                "Более двух суток, но не более 10 дней",
            ]
        )

        self.case_type_input = QComboBox()

        self.case_type_input.addItems(
            [
                "УД",
                "МП",
            ]
        )

        self.case_number_input = QLineEdit()

        self.case_number_label = QLabel(
            "Номер дела:"
        )

        self.procedural_control_input = QComboBox()

        self.procedural_control_input.addItems(
            [
                "ВУД",
                "принятие",
            ]
        )

        self.article_input = QLineEdit()
        self.article_input.setReadOnly(True)

        form_layout.addRow(
            "Дата СОЧ:",
            self.soch_date_input,
        )

        form_layout.addRow(
            "Обстоятельства СОЧ:",
            self.circumstances_input,
        )

        form_layout.addRow(
            "Место СОЧ:",
            self.soch_place_input,
        )

        form_layout.addRow(
            "Продолжительность:",
            self.duration_input,
        )

        form_layout.addRow(
            "Тип дела:",
            self.case_type_input,
        )

        form_layout.addRow(
            self.case_number_label,
            self.case_number_input,
        )

        form_layout.addRow(
            "Процессуальный контроль:",
            self.procedural_control_input,
        )

        form_layout.addRow(
            "Статья:",
            self.article_input,
        )

        layout.addLayout(form_layout)

        self.next_button = QPushButton(
            "Далее"
        )

        self.back_button = QPushButton(
            "Назад"
        )

        layout.addWidget(
            self.next_button
        )

        layout.addWidget(
            self.back_button
        )

    def _load_form_data(self) -> None:
        """Заполнить поля существующими сведениями о СОЧ."""

        if self.form_data.soch_case is None:
            return

        soch_case = self.form_data.soch_case

        self.soch_date_input.setDate(
            QDate(
                soch_case.soch_date.year,
                soch_case.soch_date.month,
                soch_case.soch_date.day,
            )
        )
        if soch_case.circumstances:
            self.circumstances_input.setCurrentText(
                soch_case.circumstances
            )
        self.soch_place_input.setText(soch_case.soch_place)
        self.duration_input.setCurrentText(soch_case.duration)
        self.case_type_input.setCurrentText(soch_case.case_type)
        self.case_number_input.setText(soch_case.case_number or "")
        self.procedural_control_input.setCurrentText(
            soch_case.procedural_control
        )

    def _connect_signals(self) -> None:
        """
        Подключить обработчики событий.
        """

        self.next_button.clicked.connect(
            self.save_form
        )

        self.back_button.clicked.connect(
            self.go_back
        )

        self.duration_input.currentIndexChanged.connect(
            self._update_article
        )

        self.case_type_input.currentIndexChanged.connect(
            self._update_case_number_state
        )

    def go_back(self) -> None:
        self.done(BACK_DIALOG_CODE)

    def _update_article(self) -> None:
        """
        Автоматически определить статью
        по продолжительности СОЧ.
        """

        articles = {
            0: "ч. 5 ст. 337 УК РФ",
            1: "ч. 3.1 ст. 337 УК РФ",
            2: "ч. 2.1 ст. 337 УК РФ",
        }

        article = articles[
            self.duration_input.currentIndex()
        ]

        self.article_input.setText(
            article
        )

    def _update_case_number_state(self) -> None:
        """
        Показывать номер дела только для УД.
        """

        is_ud = (
            self.case_type_input.currentText()
            == "УД"
        )

        self.case_number_label.setVisible(
            is_ud
        )

        self.case_number_input.setVisible(
            is_ud
        )

        if not is_ud:
            self.case_number_input.clear()

    def save_form(self) -> None:
        """
        Проверить и сохранить сведения по СОЧ.
        """

        soch_date = (
            self.soch_date_input
            .date()
            .toPython()
        )

        circumstances = (
            self.circumstances_input
            .currentText()
            .strip()
        )

        soch_place = (
            self.soch_place_input
            .text()
            .strip()
        )

        duration = (
            self.duration_input
            .currentText()
            .strip()
        )

        case_type = (
            self.case_type_input
            .currentText()
            .strip()
        )

        case_number = (
            self.case_number_input
            .text()
            .strip()
        )

        procedural_control = (
            self.procedural_control_input
            .currentText()
            .strip()
        )

        article = (
            self.article_input
            .text()
            .strip()
        )

        if not soch_place:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите место СОЧ.",
            )
            return

        if case_type == "УД" and not case_number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите номер дела.",
            )
            return

        if case_type != "УД":
            case_number = None

        self.form_data.soch_case = SochCase(
            soch_date=soch_date,
            soch_place=soch_place,
            duration=duration,
            case_type=case_type,
            case_number=case_number,
            procedural_control=procedural_control,
            article=article,
            # Keep old stored values intact; document dates come from DocumentInfo.
            registration_date=(
                self.form_data.soch_case.registration_date
                if self.form_data.soch_case is not None
                else None
            ),
            circumstances=circumstances,
        )

        self.accept()
