from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import re
import tempfile

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.repositories.custom_recipient_repository import (
    CustomRecipientRepository,
)
from database.repositories.person_repository import PersonRepository
from database.repositories.territory_repository import TerritoryRepository
from domain.entities.custom_recipient import CustomRecipient
from domain.entities.person import Person
from domain.enums.registration_mode import RegistrationMode
from domain.value_objects.address import Address
from domain.value_objects.birth import Birth
from domain.value_objects.document_info import DocumentInfo
from domain.value_objects.fullname import FullName
from domain.value_objects.investigator import INVESTIGATORS
from domain.value_objects.military import Military
from domain.value_objects.passport import Passport
from domain.value_objects.soch_case import SochCase
from services.document_signature_service import DocumentSignatureService
from services.generation_service import GenerationService
from services.google_single_organization_search_service import (
    GoogleSingleOrganizationHeader,
    GoogleSingleOrganizationSearchService,
)
from services.request_catalog import REQUEST_CATALOG, RequestTemplate
from services.territory_service import TerritoryService
from services.unique_request_generation_service import (
    UniqueRequestGenerationService,
)
from ui.google_organization_search_dialog import GoogleOrganizationSearchDialog
from utils.declension import decline_full_name, rank_genitive


class UniqueRequestDialog(QDialog):
    """Пошаговое создание одного запроса на выбранного человека."""

    PAGE_EXECUTOR = 0
    PAGE_TEMPLATE = 1
    PAGE_SUBJECT = 2
    PAGE_SUBJECT_DATA = 3
    PAGE_RECIPIENT = 4
    PAGE_REGISTRATION = 5

    MODE_TEMPLATE = "template"
    MODE_TERRITORY = "territory"
    MODE_SAVED = "saved"
    MODE_GOOGLE = "google"
    MODE_MANUAL = "manual"
    MODE_UNIT_NUMBER = "unit_number"

    def __init__(
        self,
        person_repository: PersonRepository | None = None,
        parent=None,
        *,
        custom_recipient_repository: CustomRecipientRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self.person_repository = person_repository or PersonRepository()
        self.custom_recipient_repository = (
            custom_recipient_repository or CustomRecipientRepository()
        )
        self.territory_service = TerritoryService(TerritoryRepository())
        self.search_service = GoogleSingleOrganizationSearchService()
        self.generation_service = UniqueRequestGenerationService()
        self.signature_service = DocumentSignatureService()
        self.people = self.person_repository.get_all()
        self._territory_organization = None
        self._google_result: GoogleSingleOrganizationHeader | None = None

        self.setWindowTitle("Создать уникальный запрос")
        self.resize(780, 680)
        self.setMinimumSize(680, 560)
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setStyleSheet(self._dialog_style())
        self._setup_ui()
        self._refresh_subject_fields()
        self._refresh_recipient_modes()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.step_label = QLabel()
        self.step_label.setObjectName("titleLabel")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.step_label)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._executor_page())
        self.pages.addWidget(self._template_page())
        self.pages.addWidget(self._subject_page())
        self.pages.addWidget(self._subject_data_page())
        self.pages.addWidget(self._recipient_page())
        self.pages.addWidget(self._registration_page())
        self.pages.currentChanged.connect(self._update_navigation)
        layout.addWidget(self.pages, 1)

        navigation = QHBoxLayout()
        self.back_button = QPushButton("Назад")
        self.next_button = QPushButton("Далее")
        self.create_button = QPushButton("Создать Word")
        self.cancel_button = QPushButton("Отмена")
        self.back_button.clicked.connect(self._back)
        self.next_button.clicked.connect(self._next)
        self.create_button.clicked.connect(self._generate)
        self.cancel_button.clicked.connect(self.reject)
        navigation.addWidget(self.back_button)
        navigation.addStretch()
        navigation.addWidget(self.cancel_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.create_button)
        layout.addLayout(navigation)
        self._update_navigation()

    def _executor_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        card = self._card("Исполнитель запроса")
        form = QFormLayout(card)
        self._configure_form(form)
        hint = QLabel(
            "Исполнитель будет заменён только в этом запросе. "
            "Карточка человека в базе не изменится."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.executor_combo = QComboBox()
        self._configure_combo(self.executor_combo)
        for investigator in INVESTIGATORS:
            self.executor_combo.addItem(investigator.display_name, investigator)
        form.addRow("Исполнитель", self.executor_combo)
        page_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        page_layout.addStretch()
        return page

    def _template_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        card = self._card("Основа документа")
        form = QFormLayout(card)
        self._configure_form(form)
        self.template_combo = QComboBox()
        self._configure_combo(self.template_combo)
        for request in REQUEST_CATALOG:
            self.template_combo.addItem(
                f"{request.number}. {request.title}",
                request,
            )
        self.template_combo.currentIndexChanged.connect(
            self._on_template_changed
        )
        form.addRow("Шаблон запроса", self.template_combo)
        note = QLabel(
            "Будет создан только выбранный запрос. Если исходный шаблон "
            "многостраничный, все его страницы сохранятся."
        )
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        form.addRow(note)
        page_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        page_layout.addStretch()
        return page

    def _subject_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        card = self._card("На кого готовится запрос")
        form = QFormLayout(card)
        self._configure_form(form)
        self.person_combo = QComboBox()
        self._configure_combo(self.person_combo)
        for person in self.people:
            self.person_combo.addItem(
                f"{person.id} — {person.full_name.full}",
                person,
            )
        if not self.people:
            self.person_combo.addItem("В базе пока нет людей", None)
            self.person_combo.setEnabled(False)
        self.person_combo.currentIndexChanged.connect(self._on_subject_changed)
        self.not_in_database_checkbox = QCheckBox("Человека нет в базе")
        self.not_in_database_checkbox.toggled.connect(self._on_subject_changed)
        form.addRow("Человек из базы", self.person_combo)
        form.addRow("", self.not_in_database_checkbox)
        note = QLabel(
            "Для человека не из базы приложение запросит только сведения, "
            "которые реально используются выбранным шаблоном, и не сохранит "
            "его карточку."
        )
        note.setObjectName("hintLabel")
        note.setWordWrap(True)
        form.addRow(note)
        page_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        page_layout.addStretch()
        return page

    def _subject_data_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        root = QVBoxLayout(content)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        self.subject_fields_hint = QLabel()
        self.subject_fields_hint.setObjectName("hintLabel")
        self.subject_fields_hint.setWordWrap(True)
        root.addWidget(self.subject_fields_hint)

        form = QFormLayout()
        self._configure_form(form)
        self.subject_rows: dict[str, tuple[QLabel, QWidget]] = {}

        names = QWidget()
        names_layout = QHBoxLayout(names)
        names_layout.setContentsMargins(0, 0, 0, 0)
        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("Фамилия")
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("Имя")
        self.middle_name_input = QLineEdit()
        self.middle_name_input.setPlaceholderText("Отчество")
        names_layout.addWidget(self.last_name_input)
        names_layout.addWidget(self.first_name_input)
        names_layout.addWidget(self.middle_name_input)
        self._add_subject_row(form, "full_name", "ФИО", names)

        self.birth_date_input = self._date_edit()
        self._add_subject_row(
            form, "birth_date", "Дата рождения", self.birth_date_input
        )
        self.birth_place_input = QLineEdit()
        self.birth_place_input.setPlaceholderText(
            "Например: Московская область, г. Балашиха"
        )
        self._add_subject_row(
            form, "birth_place", "Место рождения", self.birth_place_input
        )
        self.registration_address_input = QLineEdit()
        self.registration_address_input.setPlaceholderText(
            "Полный адрес регистрации"
        )
        self._add_subject_row(
            form,
            "registration_address",
            "Адрес регистрации",
            self.registration_address_input,
        )

        passport = QWidget()
        passport_layout = QHBoxLayout(passport)
        passport_layout.setContentsMargins(0, 0, 0, 0)
        self.passport_series_input = QLineEdit()
        self.passport_series_input.setPlaceholderText("Серия, 4 цифры")
        self.passport_number_input = QLineEdit()
        self.passport_number_input.setPlaceholderText("Номер, 6 цифр")
        self.passport_issued_input = QLineEdit()
        self.passport_issued_input.setPlaceholderText("Кем выдан")
        self.passport_date_input = self._date_edit()
        passport_layout.addWidget(self.passport_series_input)
        passport_layout.addWidget(self.passport_number_input)
        passport_layout.addWidget(self.passport_issued_input, 2)
        passport_layout.addWidget(self.passport_date_input)
        self._add_subject_row(form, "passport", "Паспорт", passport)

        self.military_unit_input = QLineEdit()
        self.military_unit_input.setPlaceholderText("Только номер части")
        self._add_subject_row(
            form, "military_unit", "Войсковая часть", self.military_unit_input
        )
        self.military_rank_input = QLineEdit()
        self.military_rank_input.setPlaceholderText("Например: рядовой")
        self._add_subject_row(
            form, "military_rank", "Воинское звание", self.military_rank_input
        )
        self.soch_date_input = self._date_edit()
        self._add_subject_row(form, "soch_date", "Дата СОЧ", self.soch_date_input)

        self.case_type_input = QComboBox()
        self.case_type_input.addItems(("МП", "УД"))
        self.case_type_input.currentTextChanged.connect(
            self._update_case_number_state
        )
        self._configure_combo(self.case_type_input)
        self._add_subject_row(form, "case_type", "Тип дела", self.case_type_input)
        self.case_number_input = QLineEdit()
        self.case_number_input.setPlaceholderText("Номер требуется только для УД")
        self._add_subject_row(
            form, "case_number", "Номер уголовного дела", self.case_number_input
        )
        self.article_input = QLineEdit()
        self.article_input.setPlaceholderText("Например: ч. 5 ст. 337 УК РФ")
        self._add_subject_row(form, "article", "Статья и часть УК РФ", self.article_input)
        root.addLayout(form)
        root.addStretch()
        return page

    def _recipient_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        root = QVBoxLayout(content)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        self.recipient_mode_combo = QComboBox()
        self._configure_combo(self.recipient_mode_combo)
        self.recipient_mode_combo.currentIndexChanged.connect(
            self._update_recipient_controls
        )
        mode_form = QFormLayout()
        self._configure_form(mode_form)
        mode_form.addRow("Источник шапки", self.recipient_mode_combo)
        root.addLayout(mode_form)

        self.unit_number_box = QGroupBox("Запрос в другую войсковую часть")
        unit_form = QFormLayout(self.unit_number_box)
        self._configure_form(unit_form)
        self.target_unit_input = QLineEdit()
        self.target_unit_input.setPlaceholderText("Например: 33790")
        unit_form.addRow("Номер части", self.target_unit_input)
        unit_note = QLabel(
            "Адресат будет заполнен автоматически. Почтовый адрес при "
            "необходимости допишите в Word; в справочник такая шапка не сохраняется."
        )
        unit_note.setObjectName("hintLabel")
        unit_note.setWordWrap(True)
        unit_form.addRow(unit_note)
        root.addWidget(self.unit_number_box)

        self.saved_box = QGroupBox("Сохранённая организация")
        saved_layout = QFormLayout(self.saved_box)
        self._configure_form(saved_layout)
        self.saved_search_input = QLineEdit()
        self.saved_search_input.setPlaceholderText("Поиск по короткому названию")
        self.saved_search_input.textChanged.connect(self._load_saved_recipients)
        self.saved_recipient_combo = QComboBox()
        self._configure_combo(self.saved_recipient_combo)
        self.saved_recipient_combo.currentIndexChanged.connect(
            self._fill_from_saved_recipient
        )
        saved_layout.addRow("Найти", self.saved_search_input)
        saved_layout.addRow("Организация", self.saved_recipient_combo)
        root.addWidget(self.saved_box)

        self.google_box = QGroupBox("Поиск через Google AI")
        google_layout = QFormLayout(self.google_box)
        self._configure_form(google_layout)
        google_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.google_name_input = QLineEdit()
        self.google_name_input.setPlaceholderText("Например: 425 ВКГ")
        self.google_location_input = QLineEdit()
        self.google_location_input.setPlaceholderText(
            "Необязательно: город или регион для уточнения"
        )
        self.google_search_button = QPushButton("Найти и заполнить шапку")
        self.google_search_button.clicked.connect(self._search_google)
        google_layout.addRow("Название организации*", self.google_name_input)
        google_layout.addRow("Город или регион", self.google_location_input)
        google_layout.addRow("", self.google_search_button)
        root.addWidget(self.google_box)

        self.manual_box = QGroupBox("Реквизиты нового запроса")
        manual_layout = QFormLayout(self.manual_box)
        self._configure_form(manual_layout)
        # Long Russian labels otherwise make the scroll content wider than its
        # viewport and cut off the editors' right edges at the minimum size.
        manual_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.lookup_name_input = QLineEdit()
        self.lookup_name_input.setPlaceholderText("Короткое имя, например: 425 ВКГ")
        self.recipient_input = QTextEdit()
        self.recipient_input.setPlaceholderText(
            "Кому и полное наименование организации"
        )
        self.recipient_input.setMaximumHeight(85)
        self.postal_address_input = QTextEdit()
        self.postal_address_input.setPlaceholderText(
            "Полный почтовый адрес организации с индексом"
        )
        self.postal_address_input.setMaximumHeight(65)
        self.phones_input = QTextEdit()
        self.phones_input.setPlaceholderText(
            "+7 (...) ...\n+7 (...) ... — максимум два телефона"
        )
        self.phones_input.setMaximumHeight(60)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Электронная почта")
        self.save_recipient_checkbox = QCheckBox(
            "Сохранить шапку в справочник"
        )
        self.save_recipient_checkbox.setToolTip(
            "Организация будет доступна в этой категории для следующих запросов."
        )
        self.save_recipient_checkbox.setChecked(True)
        self.header_preview = QTextEdit()
        self.header_preview.setReadOnly(True)
        self.header_preview.setMaximumHeight(145)
        for widget in (
            self.recipient_input,
            self.postal_address_input,
            self.phones_input,
        ):
            widget.textChanged.connect(self._update_header_preview)
        self.email_input.textChanged.connect(self._update_header_preview)
        manual_layout.addRow(
            "Короткое имя (для справочника)",
            self.lookup_name_input,
        )
        manual_layout.addRow("Адресат и организация*", self.recipient_input)
        manual_layout.addRow("Почтовый адрес*", self.postal_address_input)
        manual_layout.addRow("Телефоны", self.phones_input)
        manual_layout.addRow("Электронная почта", self.email_input)
        manual_layout.addRow("", self.save_recipient_checkbox)
        manual_layout.addRow("Так шапка попадёт в Word", self.header_preview)
        root.addWidget(self.manual_box)
        root.addStretch()
        return page

    def _registration_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        card = self._card("Исходящие реквизиты")
        form = QFormLayout(card)
        self._configure_form(form)
        self.registration_mode_combo = QComboBox()
        self._configure_combo(self.registration_mode_combo)
        for mode in RegistrationMode:
            self.registration_mode_combo.addItem(mode.value, mode)
        self.registration_mode_combo.currentIndexChanged.connect(
            self._update_registration_controls
        )
        self.outgoing_number_input = QLineEdit()
        self.outgoing_number_input.setPlaceholderText(
            "Новый исходящий номер для этого запроса"
        )
        self.outgoing_date_input = self._date_edit(QDate.currentDate())
        form.addRow("Регистрация", self.registration_mode_combo)
        form.addRow("Исходящий номер*", self.outgoing_number_input)
        form.addRow("Дата исходящего*", self.outgoing_date_input)
        self.registration_note = QLabel(
            "При регистрации позже верхние поля номера и даты останутся "
            "пустыми, а нижний блок исходящих реквизитов будет удалён."
        )
        self.registration_note.setObjectName("hintLabel")
        self.registration_note.setWordWrap(True)
        form.addRow(self.registration_note)
        page_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        page_layout.addStretch()
        return page

    @staticmethod
    def _card(title: str) -> QGroupBox:
        card = QGroupBox(title)
        card.setMaximumWidth(820)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return card

    @staticmethod
    def _configure_form(form: QFormLayout) -> None:
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

    @staticmethod
    def _configure_combo(combo: QComboBox) -> None:
        combo.setMinimumWidth(0)
        combo.setMinimumContentsLength(16)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    @staticmethod
    def _dialog_style() -> str:
        return """
        QDialog, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
            background-color: #1e1e1e;
            color: #f3f4f6;
        }
        QLabel {
            color: #f3f4f6;
            font-size: 14px;
        }
        QLabel#titleLabel {
            color: #ffffff;
            font-size: 26px;
            font-weight: 650;
            padding: 14px 4px 18px 4px;
        }
        QLabel#hintLabel {
            color: #aeb4be;
            line-height: 1.35;
        }
        QGroupBox {
            background-color: #262626;
            color: #ffffff;
            border: 1px solid #414141;
            border-radius: 10px;
            margin-top: 14px;
            padding: 18px 14px 14px 14px;
            font-size: 14px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 6px;
            color: #d9dde5;
        }
        QLineEdit, QTextEdit, QComboBox, QDateEdit {
            background-color: #303030;
            color: #ffffff;
            border: 1px solid #505050;
            border-radius: 7px;
            padding: 7px 9px;
            selection-background-color: #2563eb;
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus {
            border: 1px solid #6da7ff;
        }
        QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled,
        QDateEdit:disabled {
            background-color: #252525;
            color: #858585;
            border-color: #383838;
        }
        QComboBox QAbstractItemView {
            background-color: #303030;
            color: #ffffff;
            border: 1px solid #505050;
            selection-background-color: #3b65a0;
        }
        QCheckBox {
            color: #f3f4f6;
            spacing: 8px;
        }
        QPushButton {
            background-color: #f5f5f5;
            color: #171717;
            border: 1px solid #d7d7d7;
            border-radius: 8px;
            padding: 8px 18px;
            min-height: 20px;
            font-size: 14px;
        }
        QPushButton:hover {
            background-color: #ffffff;
            border-color: #ffffff;
        }
        QPushButton:pressed {
            background-color: #dedede;
        }
        QPushButton:disabled {
            background-color: #3a3a3a;
            color: #777777;
            border-color: #454545;
        }
        QScrollArea {
            border: none;
        }
        QScrollBar:vertical {
            background: #222222;
            width: 10px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #555555;
            border-radius: 5px;
            min-height: 28px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        """

    @staticmethod
    def _date_edit(value: QDate | None = None) -> QDateEdit:
        editor = QDateEdit()
        if value is None:
            editor.setMinimumDate(QDate(1800, 1, 1))
            editor.setSpecialValueText("Выберите дату")
            editor.setDate(editor.minimumDate())
        else:
            editor.setDate(value)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("dd.MM.yyyy")
        return editor

    @staticmethod
    def _date_selected(editor: QDateEdit) -> bool:
        return editor.date() != editor.minimumDate()

    def _add_subject_row(
        self,
        form: QFormLayout,
        key: str,
        label_text: str,
        widget: QWidget,
    ) -> None:
        label = QLabel(label_text)
        form.addRow(label, widget)
        self.subject_rows[key] = (label, widget)

    @property
    def selected_request(self) -> RequestTemplate:
        return self.template_combo.currentData()

    def _current_person(self) -> Person | None:
        if self.not_in_database_checkbox.isChecked():
            return None
        return self.person_combo.currentData()

    def _page_order(self) -> list[int]:
        result = [self.PAGE_EXECUTOR, self.PAGE_TEMPLATE, self.PAGE_SUBJECT]
        if self.not_in_database_checkbox.isChecked():
            result.append(self.PAGE_SUBJECT_DATA)
        result.extend((self.PAGE_RECIPIENT, self.PAGE_REGISTRATION))
        return result

    def _next(self) -> None:
        if not self._validate_page(self.pages.currentIndex()):
            return
        order = self._page_order()
        position = order.index(self.pages.currentIndex())
        if position + 1 < len(order):
            self.pages.setCurrentIndex(order[position + 1])

    def _back(self) -> None:
        order = self._page_order()
        position = order.index(self.pages.currentIndex())
        if position:
            self.pages.setCurrentIndex(order[position - 1])

    def _update_navigation(self, *_args) -> None:
        order = self._page_order()
        current = self.pages.currentIndex()
        position = order.index(current) if current in order else 0
        self.back_button.setEnabled(position > 0)
        final = position == len(order) - 1
        self.next_button.setVisible(not final)
        self.create_button.setVisible(final)
        titles = {
            self.PAGE_EXECUTOR: "1. Выберите исполнителя",
            self.PAGE_TEMPLATE: "2. Выберите один из 15 шаблонов",
            self.PAGE_SUBJECT: "3. Выберите человека",
            self.PAGE_SUBJECT_DATA: "4. Введите только нужные сведения",
            self.PAGE_RECIPIENT: "Шапка и организация",
            self.PAGE_REGISTRATION: "Регистрация нового запроса",
        }
        self.step_label.setText(titles[current])

    def _on_template_changed(self, *_args) -> None:
        # An addressee from the previous template must never leak into a new
        # document whose destination category may be entirely different.
        if hasattr(self, "recipient_mode_combo"):
            self.recipient_mode_combo.setCurrentIndex(-1)
            self._google_result = None
            self.saved_search_input.clear()
            self.google_name_input.clear()
            self.google_location_input.clear()
            self.target_unit_input.clear()
            self._clear_header_fields()
        self._refresh_subject_fields()
        self._refresh_recipient_modes()

    def _on_subject_changed(self, *_args) -> None:
        self.person_combo.setEnabled(
            bool(self.people) and not self.not_in_database_checkbox.isChecked()
        )
        self._refresh_recipient_modes()
        self._update_navigation()

    def _refresh_subject_fields(self) -> None:
        required = {
            spec.key
            for spec in self.generation_service.required_subject_fields(
                self.selected_request
            )
        }
        for key, (label, widget) in self.subject_rows.items():
            visible = key in required
            label.setVisible(visible)
            widget.setVisible(visible)
        self.subject_fields_hint.setText(
            f"Для шаблона «{self.selected_request.title}» показаны только "
            "используемые в документе сведения. Все показанные поля нужны "
            "для этого текста; номер дела — только для УД. "
            "Карточка в базе создаваться не будет."
        )
        self._update_case_number_state()

    def _update_case_number_state(self, *_args) -> None:
        label, widget = self.subject_rows["case_number"]
        needed = (
            label.isVisible()
            and self.case_type_input.currentText() == "УД"
        )
        label.setText("Номер уголовного дела" if needed else "Номер дела")
        widget.setEnabled(needed)
        if not needed:
            self.case_number_input.clear()

    def _refresh_recipient_modes(self) -> None:
        if not hasattr(self, "recipient_mode_combo"):
            return
        request = self.selected_request
        current_person = self._current_person()
        self._territory_organization = None
        if request.organization_type is not None and current_person is not None:
            resolution = self.territory_service.resolve_headers(
                current_person.registration_address
            )
            self._territory_organization = next(
                (
                    organization
                    for organization in resolution.organizations
                    if organization.organization_type is request.organization_type
                ),
                None,
            )

        previous = self.recipient_mode_combo.currentData()
        self.recipient_mode_combo.blockSignals(True)
        self.recipient_mode_combo.clear()
        if not request.requires_resolved_header:
            self.recipient_mode_combo.addItem(
                "Использовать шапку из шаблона",
                self.MODE_TEMPLATE,
            )
        if request.number == 1:
            self.recipient_mode_combo.addItem(
                "Другая войсковая часть — ввести только номер",
                self.MODE_UNIT_NUMBER,
            )
        if self._territory_organization is not None:
            self.recipient_mode_combo.addItem(
                "Использовать территориальную шапку человека",
                self.MODE_TERRITORY,
            )
        self.recipient_mode_combo.addItem(
            "Выбрать сохранённую организацию",
            self.MODE_SAVED,
        )
        self.recipient_mode_combo.addItem(
            "Найти конкретную организацию через Google AI",
            self.MODE_GOOGLE,
        )
        self.recipient_mode_combo.addItem(
            "Ввести или изменить шапку вручную",
            self.MODE_MANUAL,
        )
        index = self.recipient_mode_combo.findData(previous)
        if index < 0:
            if request.requires_resolved_header and self._territory_organization:
                index = self.recipient_mode_combo.findData(self.MODE_TERRITORY)
            elif not request.requires_resolved_header:
                index = self.recipient_mode_combo.findData(self.MODE_TEMPLATE)
            else:
                index = self.recipient_mode_combo.findData(self.MODE_SAVED)
        self.recipient_mode_combo.setCurrentIndex(max(index, 0))
        self.recipient_mode_combo.blockSignals(False)
        self._load_saved_recipients()
        if (
            request.requires_resolved_header
            and self.recipient_mode_combo.currentData() == self.MODE_SAVED
            and self.saved_recipient_combo.count() == 0
        ):
            self.recipient_mode_combo.setCurrentIndex(
                self.recipient_mode_combo.findData(self.MODE_GOOGLE)
            )
        self._update_recipient_controls()

    def _load_saved_recipients(self, *_args) -> None:
        if not hasattr(self, "saved_recipient_combo"):
            return
        entries = self.custom_recipient_repository.search(
            self.selected_request.slug,
            self.saved_search_input.text(),
        )
        current_id = (
            self.saved_recipient_combo.currentData().id
            if self.saved_recipient_combo.currentData() is not None
            else None
        )
        self.saved_recipient_combo.blockSignals(True)
        self.saved_recipient_combo.clear()
        for entry in entries:
            self.saved_recipient_combo.addItem(entry.lookup_name, entry)
        if current_id is not None:
            for index in range(self.saved_recipient_combo.count()):
                if self.saved_recipient_combo.itemData(index).id == current_id:
                    self.saved_recipient_combo.setCurrentIndex(index)
                    break
        self.saved_recipient_combo.blockSignals(False)
        self._fill_from_saved_recipient()

    def _update_recipient_controls(self, *_args) -> None:
        mode = self.recipient_mode_combo.currentData()
        self.unit_number_box.setVisible(mode == self.MODE_UNIT_NUMBER)
        self.saved_box.setVisible(mode == self.MODE_SAVED)
        self.google_box.setVisible(mode == self.MODE_GOOGLE)
        editable = mode in {self.MODE_GOOGLE, self.MODE_MANUAL}
        self.manual_box.setVisible(editable or mode == self.MODE_SAVED)
        for widget in (
            self.lookup_name_input,
            self.recipient_input,
            self.postal_address_input,
            self.phones_input,
            self.email_input,
            self.save_recipient_checkbox,
        ):
            widget.setEnabled(editable)
        if mode == self.MODE_SAVED:
            self._fill_from_saved_recipient()
        elif mode == self.MODE_GOOGLE:
            self.save_recipient_checkbox.setChecked(True)

    def _fill_from_saved_recipient(self, *_args) -> None:
        if self.recipient_mode_combo.currentData() != self.MODE_SAVED:
            return
        recipient = self.saved_recipient_combo.currentData()
        if recipient is None:
            self._clear_header_fields()
            return
        self._fill_header_fields(
            recipient.lookup_name,
            recipient.recipient,
            recipient.postal_address,
            recipient.phones,
            recipient.email,
        )

    def _search_google(self) -> None:
        try:
            request = self.search_service.build_request(
                self.selected_request,
                self.google_name_input.text(),
                self.google_location_input.text(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Поиск организации", str(error))
            return
        dialog = GoogleOrganizationSearchDialog(
            Address("", "", "", "", "", ""),
            self,
            request=request,
            response_parser=lambda text: self.search_service.parse_response(
                text, request
            ),
            result_description="одну готовую шапку",
            service=self.search_service,
            window_title="Поиск организации через Google AI",
            collect_button_text="Забрать готовую шапку",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._google_result = dialog.outcome
        result = self._google_result
        self._fill_header_fields(
            result.lookup_name,
            result.recipient,
            result.postal_address,
            result.phones,
            result.email,
        )

    def _clear_header_fields(self) -> None:
        self._fill_header_fields("", "", "", (), "")

    def _fill_header_fields(
        self,
        lookup_name: str,
        recipient: str,
        postal_address: str,
        phones: tuple[str, ...],
        email: str,
    ) -> None:
        self.lookup_name_input.setText(lookup_name)
        self.recipient_input.setPlainText(recipient)
        self.postal_address_input.setPlainText(postal_address)
        self.phones_input.setPlainText("\n".join(phones))
        self.email_input.setText(email)
        self._update_header_preview()

    def _phones(self) -> tuple[str, ...]:
        return tuple(
            line.strip()
            for line in self.phones_input.toPlainText().splitlines()
            if line.strip()
        )

    def _header_text(self) -> str:
        parts = [
            self.recipient_input.toPlainText().strip(),
            self.postal_address_input.toPlainText().strip(),
        ]
        phones = self._phones()
        if phones:
            parts.append("тел.: " + ",\n".join(phones[:2]))
        email = self.email_input.text().strip()
        if email:
            parts.append(f"эл. почта: {email}")
        return "\n\n".join(part for part in parts if part)

    def _update_header_preview(self, *_args) -> None:
        self.header_preview.setPlainText(self._header_text())

    def _update_registration_controls(self, *_args) -> None:
        filled = self.registration_mode_combo.currentData() is RegistrationMode.FILLED
        self.outgoing_number_input.setEnabled(filled)
        self.outgoing_date_input.setEnabled(filled)

    def _validate_page(self, page: int) -> bool:
        if page == self.PAGE_SUBJECT:
            if not self.not_in_database_checkbox.isChecked() and self._current_person() is None:
                return self._warn("Выберите человека или отметьте «Человека нет в базе».")
        elif page == self.PAGE_SUBJECT_DATA:
            missing = self._missing_subject_fields()
            if missing:
                return self._warn("Заполните поля:\n— " + "\n— ".join(missing))
        elif page == self.PAGE_RECIPIENT:
            mode = self.recipient_mode_combo.currentData()
            if mode == self.MODE_UNIT_NUMBER and not self._target_unit_number():
                return self._warn("Укажите номер воинской части.")
            if mode == self.MODE_SAVED and self.saved_recipient_combo.currentData() is None:
                return self._warn(
                    "Для этой категории нет подходящей сохранённой организации. "
                    "Выберите поиск Google AI или ручной ввод."
                )
            if mode in {self.MODE_GOOGLE, self.MODE_MANUAL}:
                if (
                    self.save_recipient_checkbox.isChecked()
                    and not self.lookup_name_input.text().strip()
                ):
                    return self._warn("Укажите короткое имя организации.")
                if not self.recipient_input.toPlainText().strip():
                    return self._warn("Укажите адресата и название организации.")
                if not self.postal_address_input.toPlainText().strip():
                    return self._warn("Укажите почтовый адрес организации.")
                if len(self._phones()) > 2:
                    return self._warn("Можно указать не более двух телефонов.")
        elif page == self.PAGE_REGISTRATION:
            if (
                self.registration_mode_combo.currentData() is RegistrationMode.FILLED
                and not self.outgoing_number_input.text().strip()
            ):
                return self._warn("Укажите новый исходящий номер.")
        return True

    def _missing_subject_fields(self) -> list[str]:
        required = {
            spec.key
            for spec in self.generation_service.required_subject_fields(
                self.selected_request
            )
        }
        missing: list[str] = []
        if "full_name" in required and not all(
            editor.text().strip()
            for editor in (
                self.last_name_input,
                self.first_name_input,
                self.middle_name_input,
            )
        ):
            missing.append("фамилия, имя и отчество")
        if "birth_date" in required and not self._date_selected(
            self.birth_date_input
        ):
            missing.append("дата рождения")
        if "soch_date" in required and not self._date_selected(
            self.soch_date_input
        ):
            missing.append("дата СОЧ")
        simple = {
            "birth_place": (self.birth_place_input, "место рождения"),
            "registration_address": (
                self.registration_address_input,
                "адрес регистрации",
            ),
            "military_unit": (self.military_unit_input, "войсковая часть"),
            "military_rank": (self.military_rank_input, "воинское звание"),
            "article": (self.article_input, "статья и часть УК РФ"),
        }
        for key, (editor, label) in simple.items():
            if key in required and not editor.text().strip():
                missing.append(label)
        if "passport" in required:
            passport_values = (
                self.passport_series_input.text().strip(),
                self.passport_number_input.text().strip(),
                self.passport_issued_input.text().strip(),
            )
            if not all(passport_values):
                missing.append("полные паспортные данные")
            if not self._date_selected(self.passport_date_input):
                missing.append("дата выдачи паспорта")
            if passport_values[0] and not re.fullmatch(r"\d{4}", passport_values[0]):
                missing.append("серия паспорта — ровно 4 цифры")
            if passport_values[1] and not re.fullmatch(r"\d{6}", passport_values[1]):
                missing.append("номер паспорта — ровно 6 цифр")
        if (
            "case_number" in required
            and self.case_type_input.currentText() == "УД"
            and not self.case_number_input.text().strip()
        ):
            missing.append("номер уголовного дела")
        return missing

    def _warn(self, message: str) -> bool:
        QMessageBox.warning(self, "Нужно заполнить данные", message)
        return False

    def _build_transient_person(self) -> Person:
        today = date.today()
        passport = None
        required = {
            spec.key
            for spec in self.generation_service.required_subject_fields(
                self.selected_request
            )
        }
        if "passport" in required:
            passport = Passport(
                series=self.passport_series_input.text().strip(),
                number=self.passport_number_input.text().strip(),
                issued_by=self.passport_issued_input.text().strip(),
                issue_date=self._python_date(self.passport_date_input.date()),
            )
        case_type = self.case_type_input.currentText()
        registration = self.registration_address_input.text().strip()
        birth_place = self.birth_place_input.text().strip()
        return Person(
            # The entity requires a positive ID. This value is never persisted;
            # output routing uses an explicit transient flag instead of the ID.
            id=1,
            full_name=FullName(
                self.last_name_input.text().strip(),
                self.first_name_input.text().strip(),
                self.middle_name_input.text().strip(),
            ),
            passport=passport,
            birth=Birth(
                self._python_date(self.birth_date_input.date()),
                Address(birth_place, "", "", "", "", ""),
            ),
            registration_address=Address(
                registration, "", "", "", "", ""
            ),
            military=Military(
                military_unit=self.military_unit_input.text().strip(),
                rank=self.military_rank_input.text().strip(),
                position="",
                military_id="",
            ),
            soch_case=SochCase(
                soch_date=self._python_date(self.soch_date_input.date()),
                soch_place="",
                duration="",
                case_type=case_type,
                case_number=(
                    self.case_number_input.text().strip()
                    if case_type == "УД"
                    else None
                ),
                procedural_control="",
                article=self.article_input.text().strip(),
            ),
            document_info=DocumentInfo("", today),
            investigator=self.executor_combo.currentData(),
        )

    @staticmethod
    def _python_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _selected_recipient(self) -> tuple[object | None, str | None]:
        mode = self.recipient_mode_combo.currentData()
        if mode == self.MODE_TEMPLATE:
            return None, None
        if mode == self.MODE_UNIT_NUMBER:
            return None, f"Командиру войсковой части № {self._target_unit_number()}"
        if mode == self.MODE_TERRITORY:
            return self._territory_organization, None
        return None, self._header_text()

    def _target_unit_number(self) -> str:
        value = GenerationService._military_unit_value(
            self.target_unit_input.text().strip()
        )
        return re.sub(r"^№\s*", "", value).strip()

    def _declension_overrides(self, person: Person) -> dict[str, str]:
        declined = decline_full_name(person.full_name)
        return {
            "LAST_NAME_GENITIVE": declined.last_name_genitive,
            "FIRST_NAME_GENITIVE": declined.first_name_genitive,
            "MIDDLE_NAME_GENITIVE": declined.middle_name_genitive,
            "LAST_NAME_INSTRUMENTAL": declined.last_name_instrumental,
            "MILITARY_RANK_GENITIVE": rank_genitive(person.military.rank),
        }

    def _generate(self) -> None:
        if not self._validate_page(self.PAGE_REGISTRATION):
            return
        if not self._validate_page(self.PAGE_RECIPIENT):
            self.pages.setCurrentIndex(self.PAGE_RECIPIENT)
            return
        is_transient = self.not_in_database_checkbox.isChecked()
        if is_transient:
            if not self._validate_page(self.PAGE_SUBJECT_DATA):
                self.pages.setCurrentIndex(self.PAGE_SUBJECT_DATA)
                return
        else:
            person = self._current_person()
            if person is None:
                self.pages.setCurrentIndex(self.PAGE_SUBJECT)
                self._warn("Выберите человека.")
                return

        try:
            if is_transient:
                person = self._build_transient_person()
            mode = self.registration_mode_combo.currentData()
            outgoing_date = self._python_date(self.outgoing_date_input.date())
            document_info = DocumentInfo(
                outgoing_number=(
                    self.outgoing_number_input.text().strip()
                    if mode is RegistrationMode.FILLED
                    else ""
                ),
                outgoing_date=outgoing_date,
                vpg=person.document_info.vpg,
            )
            person = replace(
                person,
                investigator=self.executor_combo.currentData(),
                document_info=document_info,
            )
            organization, recipient_header = self._selected_recipient()
            final_path = self._create_document(
                person,
                organization,
                recipient_header,
                mode,
                is_transient=is_transient,
            )
        except Exception as error:
            QMessageBox.warning(self, "Запрос не создан", str(error))
            return

        try:
            self._save_recipient_if_requested()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Word создан, но шапка не сохранена",
                f"Документ создан:\n{final_path}\n\n"
                f"Сохранить организацию в справочник не удалось: {error}",
            )

        QMessageBox.information(
            self,
            "Уникальный запрос готов",
            "Создан один редактируемый Word-файл с подписью:\n\n"
            f"{final_path}\n\n"
            "Дальнейшие изменения можно внести непосредственно в Word.",
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(final_path)))
        self.accept()

    def _save_recipient_if_requested(self) -> None:
        mode = self.recipient_mode_combo.currentData()
        if mode not in {self.MODE_GOOGLE, self.MODE_MANUAL}:
            return
        if not self.save_recipient_checkbox.isChecked():
            return
        result = self._google_result if mode == self.MODE_GOOGLE else None
        recipient = CustomRecipient(
            id=None,
            template_slug=self.selected_request.slug,
            lookup_name=self.lookup_name_input.text(),
            recipient=self.recipient_input.toPlainText(),
            postal_address=self.postal_address_input.toPlainText(),
            phones=self._phones(),
            email=self.email_input.text(),
            source_url=result.source_url if result else "",
            verification_status=(
                result.verification_status if result else "user_verified"
            ),
            verified_at=date.today().isoformat(),
            verification_note=(
                result.verification_note
                if result
                else "Введено и подтверждено пользователем."
            ),
        )
        self.custom_recipient_repository.upsert(recipient)

    def _create_document(
        self,
        person: Person,
        organization,
        recipient_header: str | None,
        registration_mode: RegistrationMode,
        *,
        is_transient: bool = False,
        output_root: Path | None = None,
    ) -> Path:
        project_dir = Path(__file__).resolve().parents[1]
        template_dir = project_dir / "templates" / "requests"
        output_root = output_root or project_dir / "output"
        if not is_transient:
            output_dir = output_root / str(person.id) / "Уникальные запросы"
        else:
            subject = self._safe_filename(person.full_name.initials)
            output_dir = output_root / "Уникальные запросы" / subject
        output_dir.mkdir(parents=True, exist_ok=True)

        date_part = (
            f"{person.document_info.outgoing_date:%d.%m.%Y}"
            if registration_mode is RegistrationMode.FILLED
            else "без регистрации"
        )
        filename = self._safe_filename(
            f"{person.full_name.last_name}"
            f"{person.full_name.first_name[:1]}"
            f"{person.full_name.middle_name[:1]}_"
            f"{date_part}_{self.selected_request.slug}.docx"
        )
        final_path = self._unused_path(output_dir / filename)
        with tempfile.TemporaryDirectory(
            prefix="nexusdocs_unique_",
            dir=output_dir,
        ) as temporary_dir:
            source = self.generation_service.generate(
                person=person,
                request=self.selected_request,
                template_dir=template_dir,
                output_dir=Path(temporary_dir),
                organization=organization,
                recipient_header=recipient_header,
                registration_mode=registration_mode,
                overrides=self._declension_overrides(person),
            )
            self.signature_service.create_signed_copy(
                source,
                final_path,
                person.investigator,
            )
        return final_path

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', "_", value)

    @staticmethod
    def _unused_path(path: Path) -> Path:
        candidate = path
        index = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            index += 1
        return candidate


__all__ = ("UniqueRequestDialog",)
