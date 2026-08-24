from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.repositories.territory_repository import TerritoryRepository
from domain.entities.organization import Organization
from domain.entities.territory import Territory
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.browser_organization_search_service import (
    BrowserOrganizationSearchService,
)


_TAB_TITLES = {
    OrganizationType.MILITARY_COMMISSARIAT: "Военкомат",
    OrganizationType.MILITARY_COMMANDANT: "Комендатура",
    OrganizationType.NARCOLOGY: "Наркология",
    OrganizationType.PSYCHIATRY: "Психиатрия",
    OrganizationType.HOSPITAL: "Больница",
    OrganizationType.TFOMS: "ТФОМС",
    OrganizationType.ADMINISTRATION: "Администрация",
    OrganizationType.CONTRACT_SERVICE_POINT: "Пункт отбора",
    OrganizationType.ELECTION_COMMISSION: "ТИК",
}


@dataclass(slots=True)
class OrganizationFields:
    recipient: QTextEdit
    postal_address: QTextEdit
    phones: QTextEdit
    email: QLineEdit
    fax: QLineEdit
    source_url: QLineEdit
    verification_note: QTextEdit
    status: QComboBox
    verified_at: QDateEdit


class OrganizationWindow(QDialog):
    """Редактор территориальных привязок для девяти шапок."""

    def __init__(self, parent=None, close_on_save: bool = False):
        super().__init__(parent)
        self.repository = TerritoryRepository()
        self.browser_search_service = BrowserOrganizationSearchService()
        self.close_on_save = close_on_save
        self.search_address = Address("", "", "", "", "", "")
        self.organization_fields: dict[
            OrganizationType, OrganizationFields
        ] = {}

        self.setWindowTitle("База шапок")
        self.resize(980, 760)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("База организаций и территориальных шапок")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        territory_box = QGroupBox("Территория действия")
        territory_layout = QGridLayout(territory_box)
        self.region_input = QLineEdit()
        self.district_input = QLineEdit()
        self.city_input = QLineEdit()
        self.locality_input = QLineEdit()
        self.street_input = QLineEdit()
        territory_inputs = (
            ("Регион*", self.region_input),
            ("Район / округ", self.district_input),
            ("Город", self.city_input),
            ("Населённый пункт", self.locality_input),
            ("Улица", self.street_input),
        )
        for index, (label, widget) in enumerate(territory_inputs):
            row, column = divmod(index, 2)
            territory_layout.addWidget(QLabel(label), row, column * 2)
            territory_layout.addWidget(widget, row, column * 2 + 1)

        self.load_button = QPushButton("Загрузить территорию")
        self.load_button.clicked.connect(self.load_territory)
        territory_layout.addWidget(self.load_button, 2, 3)
        layout.addWidget(territory_box)

        self.hint_label = QLabel(
            "Большинство полей заполняет бесплатный автопоиск. Вкладки "
            "«заполнить» и «проверить» требуют внимания: при необходимости "
            "используйте запасные кнопки Яндекса или Google, исправьте "
            "реквизиты и измените статус на «Проверено пользователем». "
            "Пустая вкладка не изменяет сохранённую шапку."
        )
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.tabs = QTabWidget()
        for organization_type in OrganizationType:
            self.tabs.addTab(
                self._create_organization_tab(organization_type),
                _TAB_TITLES[organization_type],
            )
        layout.addWidget(self.tabs)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Сохранить шапки")
        self.close_button = QPushButton("Закрыть")
        self.save_button.clicked.connect(self.save_headers)
        self.close_button.clicked.connect(self.close)
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def _create_organization_tab(
        self,
        organization_type: OrganizationType,
    ) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        yandex_button = QPushButton("Искать в Яндексе")
        google_button = QPushButton("Искать в Google")
        yandex_button.clicked.connect(
            lambda: self._open_search(organization_type, "yandex")
        )
        google_button.clicked.connect(
            lambda: self._open_search(organization_type, "google")
        )
        search_layout.addWidget(yandex_button)
        search_layout.addWidget(google_button)
        search_layout.addStretch()

        recipient = QTextEdit()
        recipient.setPlaceholderText("Кому и полное наименование организации")
        recipient.setMaximumHeight(90)
        postal_address = QTextEdit()
        postal_address.setPlaceholderText("Почтовый адрес")
        postal_address.setMaximumHeight(70)
        phones = QTextEdit()
        phones.setPlaceholderText("+7 (...) ...\n+7 (...) ...")
        phones.setMaximumHeight(60)
        email = QLineEdit()
        fax = QLineEdit()
        source_url = QLineEdit()
        source_url.setPlaceholderText("Официальная страница или документ")
        verification_note = QTextEdit()
        verification_note.setPlaceholderText(
            "Что подтверждено источником и что требует ручной проверки"
        )
        verification_note.setMaximumHeight(60)
        source_widget = QWidget()
        source_layout = QHBoxLayout(source_widget)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(source_url)
        source_button = QPushButton("Открыть")
        source_button.clicked.connect(
            lambda: self._open_source(source_url.text())
        )
        source_layout.addWidget(source_button)
        status = QComboBox()
        status.addItem("Не проверено", "unverified")
        status.addItem("Требует проверки", "needs_review")
        status.addItem("Найдено автоматически", "auto_found")
        status.addItem("Официальный источник", "official")
        status.addItem("Проверено", "verified")
        status.addItem("Проверено пользователем", "user_verified")
        verified_at = QDateEdit(QDate.currentDate())
        verified_at.setCalendarPopup(True)
        verified_at.setDisplayFormat("dd.MM.yyyy")

        form.addRow("Бесплатный поиск", search_widget)
        form.addRow("Адресат*", recipient)
        form.addRow("Почтовый адрес*", postal_address)
        form.addRow("Телефоны", phones)
        form.addRow("Электронная почта", email)
        form.addRow("Факс", fax)
        form.addRow("Источник", source_widget)
        form.addRow("Комментарий проверки", verification_note)
        form.addRow("Статус", status)
        form.addRow("Дата проверки", verified_at)

        self.organization_fields[organization_type] = OrganizationFields(
            recipient=recipient,
            postal_address=postal_address,
            phones=phones,
            email=email,
            fax=fax,
            source_url=source_url,
            verification_note=verification_note,
            status=status,
            verified_at=verified_at,
        )
        return tab

    def _territory(self) -> Territory:
        return Territory(
            id=None,
            region=self.region_input.text().strip(),
            district=self.district_input.text().strip(),
            city=self.city_input.text().strip(),
            locality=self.locality_input.text().strip(),
            street=self.street_input.text().strip(),
        )

    def load_territory(self) -> None:
        territory = self._territory()
        if not territory.region:
            QMessageBox.warning(self, "Территория", "Укажите регион.")
            return

        organizations = self.repository.get_bound_organizations(territory)
        self._clear_organization_fields()
        self.set_organizations(organizations.values(), clear=False)

        QMessageBox.information(
            self,
            "База шапок",
            f"Загружено шапок: {len(organizations)} из 9.",
        )

    def set_address(self, address: Address) -> None:
        self.search_address = address
        self.region_input.setText(address.region)
        self.district_input.setText(address.district)
        self.city_input.setText(address.city)
        self.locality_input.setText(address.locality)
        self.street_input.setText(address.street)

    def set_attention_types(
        self,
        missing_types=(),
        unverified_types=(),
    ) -> None:
        missing = set(missing_types)
        unverified = set(unverified_types)
        for index, organization_type in enumerate(OrganizationType):
            suffix = ""
            if organization_type in missing:
                suffix = " — заполнить"
            elif organization_type in unverified:
                suffix = " — проверить"
            self.tabs.setTabText(index, _TAB_TITLES[organization_type] + suffix)

        attention = missing or unverified
        if attention:
            first = next(
                item for item in OrganizationType if item in attention
            )
            self.tabs.setCurrentIndex(list(OrganizationType).index(first))

    def set_organizations(
        self,
        organizations,
        clear: bool = True,
    ) -> None:
        if clear:
            self._clear_organization_fields()
        for organization in organizations:
            organization_type = organization.organization_type
            fields = self.organization_fields[organization_type]
            fields.recipient.setPlainText(organization.recipient)
            fields.postal_address.setPlainText(organization.postal_address)
            fields.phones.setPlainText("\n".join(organization.phones))
            fields.email.setText(organization.email)
            fields.fax.setText(organization.fax)
            fields.source_url.setText(organization.source_url)
            fields.verification_note.setPlainText(
                organization.verification_note
            )
            index = fields.status.findData(organization.verification_status)
            fields.status.setCurrentIndex(max(index, 0))
            date = QDate.fromString(organization.verified_at, "yyyy-MM-dd")
            if date.isValid():
                fields.verified_at.setDate(date)

    def save_headers(self) -> None:
        territory = self._territory()
        if not territory.region:
            QMessageBox.warning(self, "Территория", "Укажите регион.")
            return

        organizations: list[Organization] = []
        for organization_type, fields in self.organization_fields.items():
            recipient = fields.recipient.toPlainText().strip()
            postal_address = fields.postal_address.toPlainText().strip()
            if not recipient and not postal_address:
                continue
            if not recipient or not postal_address:
                self.tabs.setCurrentIndex(list(OrganizationType).index(organization_type))
                QMessageBox.warning(
                    self,
                    "Неполная шапка",
                    f"Заполните адресата и адрес: {organization_type.value}.",
                )
                return

            phones = tuple(
                line.strip()
                for line in fields.phones.toPlainText().splitlines()
                if line.strip()
            )
            status = fields.status.currentData()
            verified_at = (
                fields.verified_at.date().toString("yyyy-MM-dd")
                if status
                in {"official", "verified", "user_verified", "auto_found"}
                else ""
            )
            organizations.append(
                Organization(
                    id=None,
                    organization_type=organization_type,
                    recipient=recipient,
                    postal_address=postal_address,
                    phones=phones,
                    email=fields.email.text().strip(),
                    fax=fields.fax.text().strip(),
                    source_url=fields.source_url.text().strip(),
                    verification_status=status,
                    verified_at=verified_at,
                    verification_note=(
                        fields.verification_note.toPlainText().strip()
                    ),
                )
            )

        if not organizations:
            QMessageBox.warning(
                self,
                "База шапок",
                "Заполните хотя бы одну организацию.",
            )
            return

        self.repository.save_header_set(territory, organizations)
        QMessageBox.information(
            self,
            "База шапок",
            f"Сохранено шапок: {len(organizations)}.",
        )
        if self.close_on_save:
            self.accept()

    def _clear_organization_fields(self) -> None:
        for fields in self.organization_fields.values():
            fields.recipient.clear()
            fields.postal_address.clear()
            fields.phones.clear()
            fields.email.clear()
            fields.fax.clear()
            fields.source_url.clear()
            fields.verification_note.clear()
            fields.status.setCurrentIndex(0)
            fields.verified_at.setDate(QDate.currentDate())

    def _open_source(self, source_url: str) -> None:
        source_url = source_url.strip()
        if not source_url.startswith(("https://", "http://")):
            QMessageBox.warning(
                self,
                "Источник",
                "Укажите корректную интернет-ссылку.",
            )
            return
        QDesktopServices.openUrl(QUrl(source_url))

    def _open_search(
        self,
        organization_type: OrganizationType,
        engine: str,
    ) -> None:
        address = Address(
            region=self.region_input.text().strip(),
            district=self.district_input.text().strip(),
            city=self.city_input.text().strip(),
            locality=self.locality_input.text().strip(),
            street=self.street_input.text().strip(),
            house=self.search_address.house,
            apartment="",
        )
        if not address.region:
            QMessageBox.warning(
                self,
                "Бесплатный поиск",
                "Сначала укажите регион территории.",
            )
            return
        search_url = self.browser_search_service.url(
            address,
            organization_type,
            engine,
        )
        if not QDesktopServices.openUrl(QUrl(search_url)):
            QMessageBox.warning(
                self,
                "Бесплатный поиск",
                "Не удалось открыть браузер.",
            )
