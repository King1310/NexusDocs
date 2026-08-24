from datetime import date

from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.passport import Passport

from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE


class PersonPassportWindow(QDialog):
    """
    Окно ввода паспортных данных.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle("Паспорт")
        self.resize(500, 300)

        self._setup_ui()
        self._load_form_data()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Создать интерфейс окна.
        """

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.series_input = QLineEdit()
        self.number_input = QLineEdit()
        self.issued_by_input = QLineEdit()

        self.issue_date_input = QDateEdit()
        self.issue_date_input.setCalendarPopup(True)

        self.series_input.setPlaceholderText("1234")
        self.number_input.setPlaceholderText("123456")
        self.issued_by_input.setPlaceholderText(
            "Кем выдан паспорт"
        )

        form_layout.addRow(
            "Серия:",
            self.series_input,
        )

        form_layout.addRow(
            "Номер:",
            self.number_input,
        )

        form_layout.addRow(
            "Кем выдан:",
            self.issued_by_input,
        )

        form_layout.addRow(
            "Дата выдачи:",
            self.issue_date_input,
        )

        layout.addLayout(form_layout)

        self.next_button = QPushButton("Далее")
        self.back_button = QPushButton("Назад")

        layout.addWidget(self.next_button)
        layout.addWidget(self.back_button)

    def _load_form_data(self) -> None:
        """
        Заполнить поля существующими паспортными данными.
        """

        if self.form_data.passport is None:
            return

        passport = self.form_data.passport

        self.series_input.setText(
            passport.series
        )

        self.number_input.setText(
            passport.number
        )

        self.issued_by_input.setText(
            passport.issued_by
        )

        self.issue_date_input.setDate(
            passport.issue_date
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

    def go_back(self) -> None:
        self.done(BACK_DIALOG_CODE)

    def save_form(self) -> None:
        """
        Проверить и сохранить паспорт.
        """

        series = (
            self.series_input
            .text()
            .strip()
        )

        number = (
            self.number_input
            .text()
            .strip()
        )

        issued_by = (
            self.issued_by_input
            .text()
            .strip()
        )

        if not series:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите серию паспорта.",
            )
            return

        if not number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите номер паспорта.",
            )
            return

        if not issued_by:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите кем выдан паспорт.",
            )
            return

        issue_date = self.issue_date_input.date()

        passport = Passport(
            series=series,
            number=number,
            issued_by=issued_by,
            issue_date=date(
                issue_date.year(),
                issue_date.month(),
                issue_date.day(),
            ),
        )

        self.form_data.passport = passport

        self.accept()
