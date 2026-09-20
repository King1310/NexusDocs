from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from database.repositories.person_repository import PersonRepository
from services.person_service import PersonService

from ui.form_data import PersonFormData
from ui.form_navigation import run_form_sequence
from ui.person_window import PersonWindow
from ui.person_investigator_window import PersonInvestigatorWindow
from ui.person_passport_window import PersonPassportWindow
from ui.person_birth_window import PersonBirthWindow
from ui.person_registration_window import PersonRegistrationWindow
from ui.person_military_window import PersonMilitaryWindow
from ui.person_soch_window import PersonSochWindow
from ui.person_document_window import PersonDocumentWindow
from ui.person.person_list_window import PersonListWindow
from ui.request_dispatch_window import RequestDispatchWindow
from ui.styles import MAIN_WINDOW_STYLE


APP_ICON_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "nexusdocs-icon-v2.ico"
)


class MainWindow(QMainWindow):
    """
    Главное окно приложения NexusDocs.
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle("NexusDocs")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(900, 600)

        self.person_repository = PersonRepository()

        self.person_service = PersonService(
            repository=self.person_repository
        )

        self._setup_ui()
        self._connect_signals()

        self.person_list_window = None
        self.request_dispatch_window = None

    def _setup_ui(self) -> None:
        """
        Создать интерфейс главного окна.
        """

        central_widget = QWidget()

        self.setCentralWidget(
            central_widget
        )

        layout = QVBoxLayout(
            central_widget
        )

        layout.setContentsMargins(
            40,
            40,
            40,
            40,
        )

        layout.setSpacing(12)

        layout.addStretch()

        self.title_label = QLabel(
            "NexusDocs"
        )

        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.title_label.setObjectName(
            "titleLabel"
        )

        layout.addWidget(
            self.title_label
        )

        self.subtitle_label = QLabel(
            "Система подготовки запросов"
        )

        self.subtitle_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.subtitle_label.setObjectName(
            "subtitleLabel"
        )

        layout.addWidget(
            self.subtitle_label
        )

        layout.addSpacing(30)

        self.new_request_button = QPushButton(
            "Новый запрос"
        )

        self.people_button = QPushButton(
            "База людей"
        )

        self.extension_button = QPushButton(
            "Сделать продление до 10 суток"
        )

        self.dispatch_button = QPushButton(
            "Отправка запросов"
        )

        buttons = (
            self.new_request_button,
            self.extension_button,
            self.dispatch_button,
            self.people_button,
        )

        for button in buttons:
            button.setFixedWidth(260)
            button.setMinimumHeight(45)

            layout.addWidget(
                button,
                alignment=Qt.AlignmentFlag.AlignCenter,
            )

        layout.addStretch()

        self._apply_styles()

    def _apply_styles(self) -> None:
        """
        Применить внешний стиль.
        """

        self.setStyleSheet(
            MAIN_WINDOW_STYLE
        )

    def _connect_signals(self) -> None:
        """
        Подключить обработчики событий.
        """

        self.new_request_button.clicked.connect(
            lambda: self.open_person_window()
        )

        self.people_button.clicked.connect(
            self.open_people_database
        )

        self.extension_button.clicked.connect(
            self.open_extension_person_picker
        )

        self.dispatch_button.clicked.connect(
            self.open_request_dispatch
        )

    def open_request_dispatch(self) -> None:
        """Открыть независимое окно разбиения PDF и подготовки писем."""

        if (
            self.request_dispatch_window is None
            or not self.request_dispatch_window.isVisible()
        ):
            self.request_dispatch_window = RequestDispatchWindow(
                repository=self.person_repository,
                parent=None,
            )
            self.request_dispatch_window.show()
        else:
            self.request_dispatch_window.activateWindow()
            self.request_dispatch_window.raise_()

    def open_extension_person_picker(self) -> None:
        """Выбрать зарегистрированного человека и создать продление."""

        people = self.person_repository.get_all()
        if not people:
            QMessageBox.warning(
                self,
                "Продление до 10 суток",
                "В базе пока нет людей.",
            )
            return

        labels = [
            f"{person.id} — {person.full_name.full}"
            for person in people
        ]
        selected_label, accepted = QInputDialog.getItem(
            self,
            "Продление до 10 суток",
            "Выберите человека:",
            labels,
            0,
            False,
        )
        if not accepted:
            return

        selected_index = labels.index(selected_label)
        person = people[selected_index]
        self.open_people_database()
        self.person_list_window.select_person(person.id)
        self.person_list_window.generate_extension()

    def open_people_database(self) -> None:
        """
        Открыть базу людей.
        """

        if (
            self.person_list_window is None
            or not self.person_list_window.isVisible()
        ):
            self.person_list_window = PersonListWindow(
                repository=self.person_repository,
                parent=None,
                person_form_opener=self.open_person_window,
            )

            self.person_list_window.show()

        else:
            self.person_list_window.activateWindow()
            self.person_list_window.raise_()

    def open_person_window(
        self,
        form_data: PersonFormData | None = None,
        person_id: int | None = None,
    ) -> None:
        """
        Запустить последовательное заполнение
        данных человека.

        Если person_id указан — выполняется
        редактирование существующего человека.
        """

        if form_data is None:
            form_data = PersonFormData()

        form_steps = (
            PersonInvestigatorWindow,
            PersonWindow,
            PersonPassportWindow,
            PersonBirthWindow,
            PersonRegistrationWindow,
            PersonMilitaryWindow,
            PersonSochWindow,
            PersonDocumentWindow,
        )
        if not run_form_sequence(self, form_data, form_steps):
            return

        # ─────────────────────────────
        # Сохранение
        # ─────────────────────────────

        try:
            is_new_person = person_id is None
            if person_id is None:
                person = self.person_service.save(
                    form_data
                )

                print(
                    "===== PERSON SAVED ====="
                )

            else:
                person = self.person_service.update(
                    person_id=person_id,
                    form_data=form_data,
                )

                print(
                    "===== PERSON UPDATED ====="
                )

            print(
                f"ID: {person.id}"
            )

            print(
                f"ФИО: {person.full_name}"
            )

        except ValueError as error:
            print(
                f"Ошибка заполнения: {error}"
            )
            return

        self.open_people_database()
        self.person_list_window.load_people()
        self.person_list_window.select_person(person.id)

        if is_new_person:
            self.person_list_window.generate_documents()
