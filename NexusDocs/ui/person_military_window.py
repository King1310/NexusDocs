from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.military import Military

from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE


class PersonMilitaryWindow(QDialog):
    """
    Окно ввода военных сведений.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle("Военные сведения")
        self.resize(500, 350)

        self._setup_ui()
        self._load_form_data()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Создать интерфейс окна.
        """

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.military_unit_input = QLineEdit()
        self.rank_input = QLineEdit()
        self.position_input = QLineEdit()
        self.military_id_input = QLineEdit()

        self.military_unit_input.setPlaceholderText(
            "Например: в/ч 12345"
        )

        self.rank_input.setPlaceholderText(
            "Например: рядовой"
        )

        self.position_input.setPlaceholderText(
            "Например: стрелок"
        )

        self.military_id_input.setPlaceholderText(
            "Например: АБ1234567"
        )

        form_layout.addRow(
            "Воинская часть:",
            self.military_unit_input,
        )

        form_layout.addRow(
            "Воинское звание:",
            self.rank_input,
        )

        form_layout.addRow(
            "Должность:",
            self.position_input,
        )

        form_layout.addRow(
            "Военный билет:",
            self.military_id_input,
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
        """Заполнить поля существующими военными сведениями."""

        if self.form_data.military is None:
            return

        military = self.form_data.military

        self.military_unit_input.setText(military.military_unit)
        self.rank_input.setText(military.rank)
        self.position_input.setText(military.position)
        self.military_id_input.setText(military.military_id)

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
        Проверить и сохранить военные сведения.
        """

        military_unit = (
            self.military_unit_input
            .text()
            .strip()
        )

        rank = (
            self.rank_input
            .text()
            .strip()
        )

        position = (
            self.position_input
            .text()
            .strip()
        )

        military_id = (
            self.military_id_input
            .text()
            .strip()
        )

        if not military_unit:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите воинскую часть.",
            )
            return

        if not rank:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите воинское звание.",
            )
            return

        if not position:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите должность.",
            )
            return

        if not military_id:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите номер военного билета.",
            )
            return

        self.form_data.military = Military(
            military_unit=military_unit,
            rank=rank,
            position=position,
            military_id=military_id,
        )

        self.accept()
