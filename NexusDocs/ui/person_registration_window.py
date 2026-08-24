from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.address import Address

from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE


class PersonRegistrationWindow(QDialog):
    """
    Окно ввода адреса регистрации.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle("Адрес регистрации")
        self.resize(500, 450)

        self._setup_ui()
        self._load_form_data()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Создать интерфейс окна.
        """

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.region_input = QLineEdit()
        self.district_input = QLineEdit()
        self.city_input = QLineEdit()
        self.locality_input = QLineEdit()
        self.street_input = QLineEdit()
        self.house_input = QLineEdit()
        self.apartment_input = QLineEdit()

        form_layout.addRow(
            "Регион:",
            self.region_input,
        )

        form_layout.addRow(
            "Район:",
            self.district_input,
        )

        form_layout.addRow(
            "Город:",
            self.city_input,
        )

        form_layout.addRow(
            "Населённый пункт:",
            self.locality_input,
        )

        form_layout.addRow(
            "Улица:",
            self.street_input,
        )

        form_layout.addRow(
            "Дом:",
            self.house_input,
        )

        form_layout.addRow(
            "Квартира:",
            self.apartment_input,
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
        """Заполнить поля существующим адресом регистрации."""

        if self.form_data.registration_address is None:
            return

        address = self.form_data.registration_address

        self.region_input.setText(address.region)
        self.district_input.setText(address.district)
        self.city_input.setText(address.city)
        self.locality_input.setText(address.locality)
        self.street_input.setText(address.street)
        self.house_input.setText(address.house)
        self.apartment_input.setText(address.apartment)

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
        Проверить и сохранить адрес регистрации.
        """

        region = (
            self.region_input
            .text()
            .strip()
        )

        district = (
            self.district_input
            .text()
            .strip()
        )

        city = (
            self.city_input
            .text()
            .strip()
        )

        locality = (
            self.locality_input
            .text()
            .strip()
        )

        street = (
            self.street_input
            .text()
            .strip()
        )

        house = (
            self.house_input
            .text()
            .strip()
        )

        apartment = (
            self.apartment_input
            .text()
            .strip()
        )

        if not region:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите регион.",
            )
            return



        self.form_data.registration_address = Address(
            region=region,
            district=district,
            city=city,
            locality=locality,
            street=street,
            house=house,
            apartment=apartment,
        )

        self.accept()
