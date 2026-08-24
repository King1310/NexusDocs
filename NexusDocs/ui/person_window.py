from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.fullname import FullName

from ui.form_data import PersonFormData


class PersonWindow(QDialog):
    """
    Окно ввода основных данных человека.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle(
            "Новый человек"
        )

        self.resize(
            500,
            300,
        )

        self._setup_ui()
        self._load_form_data()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Создать интерфейс окна.
        """

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.last_name_input = QLineEdit()
        self.first_name_input = QLineEdit()
        self.middle_name_input = QLineEdit()

        self.last_name_input.setPlaceholderText(
            "Введите фамилию"
        )

        self.first_name_input.setPlaceholderText(
            "Введите имя"
        )

        self.middle_name_input.setPlaceholderText(
            "Введите отчество"
        )

        form_layout.addRow(
            "Фамилия:",
            self.last_name_input,
        )

        form_layout.addRow(
            "Имя:",
            self.first_name_input,
        )

        form_layout.addRow(
            "Отчество:",
            self.middle_name_input,
        )

        layout.addLayout(
            form_layout
        )

        self.next_button = QPushButton(
            "Далее"
        )

        self.cancel_button = QPushButton(
            "Отмена"
        )

        layout.addWidget(
            self.next_button
        )

        layout.addWidget(
            self.cancel_button
        )

    def _load_form_data(self) -> None:
        """
        Заполнить поля существующими данными.

        Если form_data пустой — ничего не делать.
        """

        if self.form_data.full_name is None:
            return

        full_name = self.form_data.full_name

        self.last_name_input.setText(
            full_name.last_name
        )

        self.first_name_input.setText(
            full_name.first_name
        )

        self.middle_name_input.setText(
            full_name.middle_name
        )

    def _connect_signals(self) -> None:
        """
        Подключить обработчики событий.
        """

        self.next_button.clicked.connect(
            self.save_form
        )

        self.cancel_button.clicked.connect(
            self.reject
        )

    def save_form(self) -> None:
        """
        Проверить и сохранить основные данные.
        """

        last_name = (
            self.last_name_input
            .text()
            .strip()
        )

        first_name = (
            self.first_name_input
            .text()
            .strip()
        )

        middle_name = (
            self.middle_name_input
            .text()
            .strip()
        )

        if not last_name:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите фамилию.",
            )
            return

        if not first_name:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите имя.",
            )
            return

        self.form_data.full_name = FullName(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
        )

        self.accept()