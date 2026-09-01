from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from database.repositories.person_repository import PersonRepository
from database.repositories.territory_repository import TerritoryRepository
from domain.entities.territory import Territory
from domain.enums.organization_type import OrganizationType
from services.google_organization_search_service import (
    GoogleOrganizationSearchService,
)
from services.generation_service import GenerationService
from services.territory_service import HeaderResolution, TerritoryService
from services.word_bundle_service import WordBundleService
from utils.declension import decline_full_name, rank_genitive

from ui.form_data import PersonFormData
from ui.google_organization_search_dialog import (
    GoogleOrganizationSearchDialog,
)
from ui.organization_window import OrganizationWindow


class PersonListWindow(QDialog):
    """
    Окно базы людей.
    """

    def __init__(
        self,
        repository: PersonRepository,
        parent=None,
        person_form_opener: Callable[..., None] | None = None,
    ):
        super().__init__(parent)

        self.repository = repository
        self.person_form_opener = person_form_opener
        if self.person_form_opener is None and parent is not None:
            self.person_form_opener = getattr(
                parent,
                "open_person_window",
                None,
            )
        self.territory_service = TerritoryService(
            TerritoryRepository()
        )
        self.generation_service = GenerationService()
        self.word_bundle_service = WordBundleService()

        self.setWindowTitle(
            "База людей"
        )

        self.resize(
            900,
            600,
        )
        self.setMinimumSize(700, 450)
        self.setWindowFlag(
            Qt.WindowType.WindowMinMaxButtonsHint,
            True,
        )

        self._setup_ui()

        self.load_people()

    def _setup_ui(self) -> None:
        """
        Создать интерфейс.
        """

        layout = QVBoxLayout(
            self
        )

        # ─────────────────────────────
        # Заголовок
        # ─────────────────────────────

        title = QLabel(
            "База людей"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        title.setObjectName(
            "titleLabel"
        )

        layout.addWidget(
            title
        )

        # ─────────────────────────────
        # Поиск
        # ─────────────────────────────

        search_layout = QHBoxLayout()

        search_label = QLabel(
            "Поиск:"
        )

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText(
            "Введите фамилию..."
        )

        self.search_input.textChanged.connect(
            self.search_people
        )

        search_layout.addWidget(
            search_label
        )

        search_layout.addWidget(
            self.search_input
        )

        layout.addLayout(
            search_layout
        )

        # ─────────────────────────────
        # Таблица
        # ─────────────────────────────

        self.people_table = QTableWidget()

        self.people_table.setColumnCount(
            4
        )

        self.people_table.setHorizontalHeaderLabels(
            (
                "ID",
                "Фамилия",
                "Имя",
                "Отчество",
            )
        )

        self.people_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self.people_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )

        self.people_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        self.people_table.setAlternatingRowColors(
            True
        )

        table_header = self.people_table.horizontalHeader()
        table_header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        for column in range(1, 4):
            table_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch,
            )
        self.people_table.setSortingEnabled(True)
        self.people_table.sortItems(
            0,
            Qt.SortOrder.AscendingOrder,
        )

        self.people_table.doubleClicked.connect(
            self.show_person
        )

        layout.addWidget(
            self.people_table
        )

        # ─────────────────────────────
        # Кнопки
        # ─────────────────────────────

        buttons_layout = QVBoxLayout()
        people_buttons = QHBoxLayout()
        document_buttons = QHBoxLayout()

        self.add_button = QPushButton(
            "Добавить человека"
        )

        self.edit_button = QPushButton(
            "Редактировать"
        )

        self.internet_headers_button = QPushButton(
            "Найти / обновить шапки через Google AI"
        )

        self.generate_button = QPushButton(
            "Сформировать общий Word"
        )

        self.delete_button = QPushButton(
            "Удалить"
        )

        self.close_button = QPushButton(
            "Закрыть"
        )

        self.add_button.clicked.connect(
            self.add_person
        )

        self.edit_button.clicked.connect(
            self.edit_person
        )

        self.internet_headers_button.clicked.connect(
            self.find_headers_online
        )

        self.generate_button.clicked.connect(
            self.generate_documents
        )

        self.delete_button.clicked.connect(
            self.delete_person
        )

        self.close_button.clicked.connect(
            self.close
        )

        people_buttons.addWidget(
            self.add_button
        )

        people_buttons.addWidget(
            self.edit_button
        )

        people_buttons.addWidget(
            self.delete_button
        )

        people_buttons.addStretch()

        people_buttons.addWidget(
            self.close_button
        )

        document_buttons.addWidget(
            self.internet_headers_button
        )

        document_buttons.addWidget(
            self.generate_button
        )

        document_buttons.addStretch()

        buttons_layout.addLayout(people_buttons)
        buttons_layout.addLayout(document_buttons)

        layout.addLayout(
            buttons_layout
        )

    def load_people(self) -> None:
        """
        Загрузить всех людей из базы.
        """

        people = self.repository.get_all()

        self._fill_table(
            people
        )

    def search_people(
        self,
        text: str,
    ) -> None:
        """
        Поиск людей по фамилии.
        """

        text = text.strip()

        if not text:
            self.load_people()
            return

        people = self.repository.search_by_last_name(
            text
        )

        self._fill_table(
            people
        )

    def _fill_table(
        self,
        people,
    ) -> None:
        """
        Заполнить таблицу людьми.
        """

        sorting_enabled = self.people_table.isSortingEnabled()
        table_header = self.people_table.horizontalHeader()
        sort_column = table_header.sortIndicatorSection()
        sort_order = table_header.sortIndicatorOrder()
        self.people_table.setSortingEnabled(False)

        self.people_table.setRowCount(
            0
        )

        for person in people:
            row = self.people_table.rowCount()

            self.people_table.insertRow(
                row
            )

            id_item = QTableWidgetItem()
            id_item.setData(
                Qt.ItemDataRole.DisplayRole,
                person.id,
            )
            self.people_table.setItem(row, 0, id_item)

            self.people_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    person.full_name.last_name
                ),
            )

            self.people_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    person.full_name.first_name
                ),
            )

            self.people_table.setItem(
                row,
                3,
                QTableWidgetItem(
                    person.full_name.middle_name
                ),
            )

        self.people_table.setSortingEnabled(sorting_enabled)
        if sorting_enabled and sort_column >= 0:
            self.people_table.sortItems(sort_column, sort_order)
        self.people_table.resizeColumnToContents(0)

    def select_person(self, person_id: int) -> bool:
        """Выбрать строку человека после создания или обновления."""

        for row in range(self.people_table.rowCount()):
            item = self.people_table.item(row, 0)
            if item is not None and int(item.text()) == person_id:
                self.people_table.selectRow(row)
                self.people_table.scrollToItem(item)
                return True
        return False

    def add_person(self) -> None:
        """
        Открыть форму создания человека.
        """

        if self.person_form_opener is None:
            return

        self.person_form_opener()

        self.load_people()

    def edit_person(self) -> None:
        """
        Редактировать выбранного человека.
        """

        row = self.people_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Редактирование",
                "Сначала выберите человека.",
            )

            return

        person_id_item = self.people_table.item(
            row,
            0,
        )

        if person_id_item is None:
            return

        person_id = int(
            person_id_item.text()
        )

        person = self.repository.get_by_id(
            person_id
        )

        if person is None:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Человек не найден в базе.",
            )

            return

        form_data = PersonFormData.from_person(
            person
        )

        if self.person_form_opener is None:
            return

        self.person_form_opener(
            form_data=form_data,
            person_id=person_id,
        )

        self.load_people()

    def show_person(self) -> None:
        """
        Открыть полную информацию о человеке.
        """

        row = self.people_table.currentRow()

        if row < 0:
            return

        person_id_item = self.people_table.item(
            row,
            0,
        )

        if person_id_item is None:
            return

        person_id = int(
            person_id_item.text()
        )

        person = self.repository.get_by_id(
            person_id
        )

        if person is None:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Человек не найден в базе.",
            )

            return

        self._show_person_details(
            person
        )

    def _show_person_details(
        self,
        person,
    ) -> None:
        """
        Показать полную информацию о человеке.
        """

        full_name = (
            f"{person.full_name.last_name} "
            f"{person.full_name.first_name} "
            f"{person.full_name.middle_name}"
        ).strip()

        passport_text = "Не указан"

        if person.passport is not None:
            passport_text = (
                f"{person.passport.series} "
                f"{person.passport.number}\n"
                f"Кем выдан: "
                f"{person.passport.issued_by}\n"
                f"Дата выдачи: "
                f"{person.passport.issue_date}"
            )

        birth = person.birth

        birth_place = self._format_address(
            birth.place
        )

        registration = self._format_address(
            person.registration_address
        )

        military = person.military

        soch = person.soch_case

        soch_text = (
            f"Дата СОЧ: {soch.soch_date}\n"
            f"Место: {soch.soch_place}\n"
            f"Продолжительность: {soch.duration}\n"
            f"Тип дела: {soch.case_type}\n"
            f"Номер дела: "
            f"{soch.case_number or 'Не указан'}\n"
            f"Процессуальный контроль: "
            f"{soch.procedural_control}\n"
            f"Статья: {soch.article}"
        )

        document = person.document_info

        text = (
            f"<b>ID:</b> {person.id}<br><br>"

            f"<b>ФИО:</b><br>"
            f"{full_name}<br><br>"

            f"<b>Паспорт:</b><br>"
            f"{passport_text.replace(chr(10), '<br>')}"
            f"<br><br>"

            f"<b>Дата рождения:</b><br>"
            f"{birth.birth_date}<br><br>"

            f"<b>Место рождения:</b><br>"
            f"{birth_place}<br><br>"

            f"<b>Адрес регистрации:</b><br>"
            f"{registration}<br><br>"

            f"<b>Военные сведения:</b><br>"
            f"Воинская часть: "
            f"{military.military_unit}<br>"
            f"Звание: {military.rank}<br>"
            f"Должность: {military.position}<br>"
            f"Военный билет: "
            f"{military.military_id}<br><br>"

            f"<b>Сведения о СОЧ:</b><br>"
            f"{soch_text.replace(chr(10), '<br>')}"
            f"<br><br>"

            f"<b>Исходящий документ:</b><br>"
            f"Номер: {document.outgoing_number}<br>"
            f"Дата: {document.outgoing_date}<br>"
            f"ВПГ: {document.vpg}"
        )

        dialog = QDialog(
            self
        )

        dialog.setWindowTitle(
            "Информация о человеке"
        )

        dialog.resize(
            600,
            700,
        )

        layout = QVBoxLayout(
            dialog
        )

        label = QLabel(
            text
        )

        label.setTextFormat(
            Qt.TextFormat.RichText
        )

        label.setWordWrap(
            True
        )

        label.setAlignment(
            Qt.AlignmentFlag.AlignTop
        )

        layout.addWidget(
            label
        )

        close_button = QPushButton(
            "Закрыть"
        )

        close_button.clicked.connect(
            dialog.accept
        )

        layout.addWidget(
            close_button
        )

        dialog.exec()

    @staticmethod
    def _format_address(
        address,
    ) -> str:
        """
        Красиво сформировать адрес.
        """

        parts = []

        if address.region:
            parts.append(
                address.region
            )

        if address.district:
            parts.append(
                address.district
            )

        if address.city:
            parts.append(
                address.city
            )

        if address.locality:
            parts.append(
                address.locality
            )

        if address.street:
            parts.append(
                address.street
            )

        if address.house:
            parts.append(
                f"д. {address.house}"
            )

        if address.apartment:
            parts.append(
                f"кв. {address.apartment}"
            )

        if not parts:
            return "Не указан"

        return ", ".join(parts)

    def delete_person(self) -> None:
        """
        Удалить выбранного человека.
        """

        row = self.people_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Удаление",
                "Сначала выберите человека.",
            )

            return

        person_id_item = self.people_table.item(
            row,
            0,
        )

        if person_id_item is None:
            return

        person_id = int(
            person_id_item.text()
        )

        person = self.repository.get_by_id(
            person_id
        )

        if person is None:
            return

        full_name = (
            f"{person.full_name.last_name} "
            f"{person.full_name.first_name} "
            f"{person.full_name.middle_name}"
        ).strip()

        answer = QMessageBox.question(
            self,
            "Удаление человека",
            (
                f"Удалить человека?\n\n"
                f"{full_name}"
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.repository.delete(
            person_id
        )

        self.load_people()

    def _get_selected_person(self):
        row = self.people_table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Выбор человека",
                "Сначала выберите человека.",
            )
            return None

        person_id_item = self.people_table.item(row, 0)
        if person_id_item is None:
            return None

        person = self.repository.get_by_id(int(person_id_item.text()))
        if person is None:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Человек не найден в базе.",
            )
        return person

    def _show_headers_preview(
        self,
        resolution: HeaderResolution,
        title: str,
    ) -> None:
        """Show the compact header text that will actually go into Word."""

        sections = []

        for index, organization in enumerate(
            resolution.organizations,
            start=1,
        ):
            sections.append(
                f"{index}. {organization.organization_type.value}\n"
                f"{self.generation_service._simple_recipient_header(organization)}\n"
                "Статус: "
                f"{self._verification_status_label(organization.verification_status)}"
            )

        if resolution.missing_types:
            missing = "\n".join(
                f"— {organization_type.value}"
                for organization_type in resolution.missing_types
            )
            sections.append(
                "Не найдены привязки:\n" + missing
            )

        QMessageBox.information(
            self,
            title,
            "\n\n".join(sections),
        )

    @staticmethod
    def _verification_status_label(status: str) -> str:
        """Return a readable label without changing the stored status."""

        return {
            "auto_found": "найдено автоматически",
            "needs_review": "требует проверки",
            "user_verified": "проверено пользователем",
            "verified": "проверено",
            "official": "официальный источник",
            "unverified": "не проверено",
        }.get(status, status)

    def find_headers_online(self) -> None:
        """Find all nine headers again, even when a set is already cached."""

        person = self._get_selected_person()
        if person is None:
            return

        current = self.territory_service.resolve_headers(
            person.registration_address
        )
        if current.organizations:
            answer = QMessageBox.question(
                self,
                "Повторный поиск шапок",
                (
                    f"Для этого адреса уже сохранено шапок: "
                    f"{len(current.organizations)}.\n\n"
                    "Повторно найти все девять шапок в интернете и "
                    "заменить сохранённые варианты?\n\n"
                    "Данные человека не изменятся."
                ),
                (
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        resolution = self._search_and_review_headers(
            person,
            force_refresh=True,
        )
        if resolution is None:
            return
        if resolution.is_complete:
            self._show_headers_preview(
                resolution,
                title="Новые шапки найдены",
            )
        else:
            self._show_header_problems(resolution)

    def generate_documents(self) -> None:
        """Создать полный комплект из пятнадцати запросов."""

        person = self._get_selected_person()
        if person is None:
            return

        resolution = self._ensure_headers_ready(person)
        if resolution is None:
            return

        project_dir = Path(__file__).resolve().parents[2]
        template_dir = project_dir / "templates" / "requests"
        output_dir = project_dir / "output" / str(person.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not template_dir.is_dir():
            QMessageBox.warning(
                self,
                "Нет шаблонов",
                f"Не найден каталог шаблонов:\n{template_dir}",
            )
            return

        overrides = self._request_declension_overrides(person)
        if overrides is None:
            return

        progress = self._progress("Собираю общий Word-файл…")
        bundle_path = output_dir / self.word_bundle_service.bundle_filename(person)
        try:
            with tempfile.TemporaryDirectory(
                prefix="nexusdocs_",
                dir=output_dir,
            ) as temporary_dir:
                generated = self.generation_service.generate_bundle(
                    person=person,
                    organizations=resolution.organizations,
                    template_dir=template_dir,
                    output_dir=Path(temporary_dir),
                    overrides=overrides,
                )
                self.word_bundle_service.create_editable_bundle(
                    generated,
                    bundle_path,
                )
        except Exception as error:
            progress.close()
            QMessageBox.warning(self, "Генерация остановлена", str(error))
            return
        progress.close()

        QMessageBox.information(
            self,
            "Документы готовы",
            "Создан общий редактируемый Word из 15 запросов:\n\n"
            f"{bundle_path}\n\n"
            "Файл можно проверить, при необходимости отредактировать "
            "и распечатать целиком.",
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(bundle_path)))

    def _ensure_headers_ready(self, person):
        """Prepare all nine headers through Alice before Word generation."""

        resolution = self.territory_service.resolve_headers(
            person.registration_address
        )
        targets = list(resolution.missing_types)
        targets.extend(
            organization.organization_type
            for organization in resolution.unverified_organizations
            if organization.organization_type not in targets
        )
        if not targets:
            return resolution
        return self._search_and_review_headers(person)

    def _search_and_review_headers(self, person, force_refresh: bool = False):
        """Search headers; optionally replace the whole cached address set."""

        resolution = self.territory_service.resolve_headers(
            person.registration_address
        )
        targets = self._header_search_targets(
            resolution,
            force_refresh=force_refresh,
        )
        if not targets:
            return resolution

        outcome = self._run_google_search(person)
        if outcome is None:
            return None

        try:
            found_candidates = self._search_candidates_for_database(
                outcome.organizations
            )
            if found_candidates:
                address = person.registration_address
                territory = Territory(
                    id=None,
                    region=address.region,
                    district=address.district,
                    city=address.city,
                    locality=address.locality,
                    street=address.street,
                )
                self.territory_service.repository.save_header_set(
                    territory,
                    found_candidates,
                )
        except Exception as error:
            QMessageBox.warning(
                self,
                "Не удалось сохранить шапки",
                str(error),
            )
            return None

        resolution = self.territory_service.resolve_headers(
            person.registration_address
        )
        if resolution.is_ready_for_generation:
            return resolution

        dialog = OrganizationWindow(parent=self, close_on_save=True)
        dialog.set_address(person.registration_address)
        dialog.set_organizations(resolution.organizations)
        dialog.set_attention_types(
            missing_types=resolution.missing_types,
            unverified_types=(
                organization.organization_type
                for organization in resolution.unverified_organizations
            ),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return self.territory_service.resolve_headers(person.registration_address)

    @staticmethod
    def _search_candidates_for_database(candidates):
        """Keep complete AI candidates and discard synthetic placeholders."""

        return [
            organization
            for organization in candidates
            if (
                organization.source_url
                and organization.recipient
                and organization.postal_address
            )
        ]

    def _run_google_search(self, person):
        """Ask for permission, run Google AI Mode and return nine headers."""

        public_address = (
            GoogleOrganizationSearchService.public_registration_address(
                person.registration_address
            )
        )
        answer = QMessageBox.question(
            self,
            "Поиск через Google AI",
            (
                "Для поиска девяти организаций в Google будет отправлен "
                "адрес регистрации без номера квартиры:\n\n"
                f"{public_address}\n\n"
                "ФИО, паспортные данные и сведения о деле не передаются.\n\n"
                "Продолжить?"
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None

        service = GoogleOrganizationSearchService()
        dialog = GoogleOrganizationSearchDialog(
            person.registration_address,
            parent=self,
            response_parser=(
                lambda text: service.parse_response_for_address(
                    text,
                    person.registration_address,
                )
            ),
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        outcome = dialog.outcome
        dialog.deleteLater()
        if not accepted:
            return None
        return outcome

    @staticmethod
    def _header_search_targets(
        resolution: HeaderResolution,
        force_refresh: bool = False,
    ) -> list[OrganizationType]:
        if force_refresh:
            return list(OrganizationType)

        targets = list(resolution.missing_types)
        targets.extend(
            organization.organization_type
            for organization in resolution.unverified_organizations
            if organization.organization_type not in targets
        )
        return targets

    def _show_header_problems(self, resolution) -> None:
        sections = []
        if resolution.missing_types:
            sections.append(
                "Не найдены:\n"
                + "\n".join(
                    f"— {organization_type.value}"
                    for organization_type in resolution.missing_types
                )
            )
        if resolution.unverified_organizations:
            sections.append(
                "Не подтверждены:\n"
                + "\n".join(
                    f"— {organization.organization_type.value}"
                    for organization in resolution.unverified_organizations
                )
            )
        QMessageBox.warning(
            self,
            "Шапки требуют проверки",
            "\n\n".join(sections),
        )

    def _progress(self, text: str) -> QProgressDialog:
        progress = QProgressDialog(text, "", 0, 0, self)
        progress.setWindowTitle("NexusDocs")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.show()
        QApplication.processEvents()
        return progress

    def _request_declension_overrides(self, person) -> dict[str, str] | None:
        """Show automatically calculated forms and allow manual correction."""

        declined = decline_full_name(person.full_name)
        dialog = QDialog(self)
        dialog.setWindowTitle("Проверка склонений")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Проверьте формы, которые будут использованы во всех 15 запросах."
            )
        )

        form = QFormLayout()
        values = {
            "LAST_NAME_GENITIVE": (
                "Фамилия — родительный падеж",
                declined.last_name_genitive,
            ),
            "FIRST_NAME_GENITIVE": (
                "Имя — родительный падеж",
                declined.first_name_genitive,
            ),
            "MIDDLE_NAME_GENITIVE": (
                "Отчество — родительный падеж",
                declined.middle_name_genitive,
            ),
            "LAST_NAME_INSTRUMENTAL": (
                "Фамилия — творительный падеж",
                declined.last_name_instrumental,
            ),
            "MILITARY_RANK_GENITIVE": (
                "Воинское звание — родительный падеж",
                rank_genitive(person.military.rank),
            ),
        }
        editors: dict[str, QLineEdit] = {}
        for key, (label, value) in values.items():
            editor = QLineEdit(value)
            editors[key] = editor
            form.addRow(label, editor)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {key: editor.text().strip() for key, editor in editors.items()}
