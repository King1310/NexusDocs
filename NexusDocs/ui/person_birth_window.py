from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.address import Address
from domain.value_objects.birth import Birth

from ui.form_data import PersonFormData
from ui.form_navigation import BACK_DIALOG_CODE


class PersonBirthWindow(QDialog):
    """
    Окно ввода даты и места рождения.
    """

    def __init__(
        self,
        form_data: PersonFormData,
        parent=None,
    ):
        super().__init__(parent)

        self.form_data = form_data

        self.setWindowTitle("Дата и место рождения")
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

        self.birth_date_input = QDateEdit()
        self.birth_date_input.setCalendarPopup(True)

        self.region_input = QLineEdit()
        self.district_input = QLineEdit()
        self.city_input = QLineEdit()
        self.locality_input = QLineEdit()
        self.street_input = QLineEdit()
        self.house_input = QLineEdit()

        self.region_input.setPlaceholderText(
            "Например: Московская область"
        )

        self.district_input.setPlaceholderText(
            "Например: Раменский район"
        )

        self.city_input.setPlaceholderText(
            "Например: Балашиха"
        )

        self.locality_input.setPlaceholderText(
            "Например: с. Ивановское"
        )

        self.street_input.setPlaceholderText(
            "Например: Ленина"
        )

        self.house_input.setPlaceholderText(
            "Например: 10"
        )

        form_layout.addRow(
            "Дата рождения:",
            self.birth_date_input,
        )

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

        layout.addLayout(form_layout)

        self.next_button = QPushButton(
            "Далее"
        )

        self.back_button = QPushButton(
            "Назад"
        )

        layout.addWidget(self.next_button)
        layout.addWidget(self.back_button)

    def _load_form_data(self) -> None:
        """Заполнить поля существующими данными о рождении."""

        if self.form_data.birth is None:
            return

        birth = self.form_data.birth
        place = birth.place

        self.birth_date_input.setDate(
            QDate(
                birth.birth_date.year,
                birth.birth_date.month,
                birth.birth_date.day,
            )
        )
        self.region_input.setText(place.region)
        self.district_input.setText(place.district)
        self.city_input.setText(place.city)
        self.locality_input.setText(place.locality)
        self.street_input.setText(place.street)
        self.house_input.setText(place.house)

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
        Проверить и сохранить данные о рождении.
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

        if not region:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Введите регион.",
            )
            return


        birth_qdate = (
            self.birth_date_input.date()
        )

        birth_date = date(
            birth_qdate.year(),
            birth_qdate.month(),
            birth_qdate.day(),
        )

        place = Address(
            region=region,
            district=district,
            city=city,
            locality=locality,
            street=street,
            house=house,
        )

        self.form_data.birth = Birth(
            birth_date=birth_date,
            place=place,
        )

        self.accept()
