from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from domain.value_objects.document_info import DocumentInfo

from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE


class PersonDocumentWindow(QDialog):
    """
    Окно ввода сведений об исходящем документе.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle("Сведения о документе")
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

        self.outgoing_number_input = QLineEdit()

        self.outgoing_date_input = QDateEdit()
        self.outgoing_date_input.setCalendarPopup(True)
        self.outgoing_date_input.setDate(
            QDate.currentDate()
        )

        self.vpg_input = QSpinBox()
        self.vpg_input.setRange(1, 1000)
        self.vpg_input.setValue(60)

        form_layout.addRow(
            "Исходящий номер:",
            self.outgoing_number_input,
        )

        form_layout.addRow(
            "Дата документа:",
            self.outgoing_date_input,
        )

        form_layout.addRow(
            "ВПГ:",
            self.vpg_input,
        )

        layout.addLayout(form_layout)

        self.save_button = QPushButton(
            "Завершить"
        )

        self.back_button = QPushButton(
            "Назад"
        )

        layout.addWidget(
            self.save_button
        )

        layout.addWidget(
            self.back_button
        )

    def _load_form_data(self) -> None:
        """Заполнить поля существующими сведениями о документе."""

        if self.form_data.document_info is None:
            return

        document_info = self.form_data.document_info

        self.outgoing_number_input.setText(
            document_info.outgoing_number
        )
        self.outgoing_date_input.setDate(
            QDate(
                document_info.outgoing_date.year,
                document_info.outgoing_date.month,
                document_info.outgoing_date.day,
            )
        )
        self.vpg_input.setValue(document_info.vpg)

    def _connect_signals(self) -> None:
        """
        Подключить обработчики событий.
        """

        self.save_button.clicked.connect(
            self.save_form
        )

        self.back_button.clicked.connect(
            self.go_back
        )

    def go_back(self) -> None:
        self.done(BACK_DIALOG_CODE)

    def save_form(self) -> None:
        """
        Проверить и сохранить сведения о документе.
        """

        outgoing_number = (
            self.outgoing_number_input
            .text()
            .strip()
        )

        outgoing_date = (
            self.outgoing_date_input
            .date()
            .toPython()
        )

        vpg = self.vpg_input.value()

        if not outgoing_number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите исходящий номер.",
            )
            return

        self.form_data.document_info = DocumentInfo(
            outgoing_number=outgoing_number,
            outgoing_date=outgoing_date,
            vpg=vpg,
        )

        self.accept()
