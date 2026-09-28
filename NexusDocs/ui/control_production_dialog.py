from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re

from PySide6.QtCore import QRegularExpression, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from services.control_production_generation_service import (
    ControlProductionData, ControlProductionGenerationService, INPUT_FIELDS,
)
from ui.unique_request_dialog import UniqueRequestDialog


class ControlProductionDialog(QDialog):
    """Independent, transient-data wizard for the full reference KP pack."""

    TITLES = ("Человек для КП", "Сведения о личности", "Адрес и паспорт",
              "Военная служба", "Уголовное дело", "Проверка комплекта")

    def __init__(self, person_repository, parent=None):
        super().__init__(parent)
        self.person_repository = person_repository
        self.service = ControlProductionGenerationService()
        self.people = []
        self.inputs: dict[str, QLineEdit] = {}
        self.dates: dict[str, QLineEdit] = {}
        self.form_inputs: dict[str, QLineEdit] = {}
        self.previous_forms: dict[str, str] = {}
        self.generated_path: Path | None = None
        self.setWindowTitle("Создать комплект КП")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "nexusdocs-icon-v2.ico")))
        self.resize(920, 730)
        self.setMinimumSize(620, 540)
        self.setStyleSheet(UniqueRequestDialog._dialog_style() + """
            QRadioButton { color: #f3f4f6; font-size: 15px; padding: 10px; }
            QPushButton#primaryButton { background: #3267bb; color: white; border-color: #548be0; }
            QLabel#stepLabel { color: #9fb5d8; font-size: 13px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 20)
        self.step_label = QLabel()
        self.step_label.setObjectName("stepLabel")
        self.title_label = QLabel()
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.step_label)
        layout.addWidget(self.title_label)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self._source_page()
        for group in ("Личность", "Адрес и паспорт", "Военная служба", "Уголовное дело"):
            self._data_page(group)
        self._review_page()
        navigation = QHBoxLayout()
        self.back_button = QPushButton("Назад")
        self.cancel_button = QPushButton("Отмена")
        self.next_button = QPushButton("Далее")
        self.next_button.setObjectName("primaryButton")
        navigation.addWidget(self.back_button)
        navigation.addStretch()
        navigation.addWidget(self.cancel_button)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        self.back_button.clicked.connect(lambda: self._show_step(self.stack.currentIndex() - 1))
        self.cancel_button.clicked.connect(self.reject)
        self.next_button.clicked.connect(self._next)
        self._show_step(0)
        try:
            self.people = self.person_repository.get_all()
            for person in self.people:
                self.person_combo.addItem(f"{person.id} — {person.full_name.full}", person)
        except Exception as error:
            self.source_hint.setText(f"Не удалось прочитать базу: {error}. Можно заполнить вручную.")

    def _page(self) -> QVBoxLayout:
        page = QWidget()
        content = QVBoxLayout(page)
        content.setContentsMargins(0, 0, 12, 0)
        content.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return content

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("hintLabel")
        return label

    def _source_page(self) -> None:
        page = self._page()
        page.addWidget(self._hint("Обложка, карточка контроля, письменные указания и план — в одном Word-файле. "
                                   "Данные используются только для этого комплекта, база не изменяется."))
        choices = QVBoxLayout()
        self.new_person_radio = QRadioButton("Нет в базе — заполнить вручную")
        self.database_radio = QRadioButton("Выбрать из базы")
        self.new_person_radio.setChecked(True)
        choices.addWidget(self.new_person_radio)
        choices.addWidget(self.database_radio)
        page.addLayout(choices)
        self.database_card = QGroupBox("Зарегистрированный человек")
        form = QVBoxLayout(self.database_card)
        self.person_combo = QComboBox()
        UniqueRequestDialog._configure_combo(self.person_combo)
        self.person_combo.addItem("Выберите человека…", None)
        form.addWidget(self.person_combo)
        self.load_button = QPushButton("Подставить данные из базы")
        form.addWidget(self.load_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.source_hint = self._hint("Дату ВУД, сведения о контракте и отсутствующие данные можно заполнить отдельно. "
                                      "Дата исходящего запроса не подставляется вместо даты ВУД.")
        form.addWidget(self.source_hint)
        page.addWidget(self.database_card)
        self.database_card.setVisible(False)
        self.database_radio.toggled.connect(self.database_card.setVisible)
        self.new_person_radio.clicked.connect(self._clear_for_new_person)
        self.load_button.clicked.connect(self._load_person)
        page.addWidget(self._hint("Должности и исполнители пока зафиксированы по образцу: Агиров, Литвинов, Бульбов. "
                                  "Текст о службе по контракту сохраняется. Изначально пустые разделы остаются пустыми."))
        page.addStretch()
        self.loaded_person = None

    def _date_input(self, key: str) -> QLineEdit:
        widget = QLineEdit()
        widget.setPlaceholderText("01.01.2000")
        widget.setMaxLength(10)
        widget.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9.]{0,10}"), widget))
        widget.setToolTip("Введите ДД.ММ.ГГГГ или 8 цифр подряд. Пустое поле — дата не указана.")
        widget.textEdited.connect(lambda text: self._format_typed_date(widget, text))
        self.dates[key] = widget
        return widget

    @staticmethod
    def _format_typed_date(widget: QLineEdit, text: str) -> None:
        if re.fullmatch(r"[0-9]{8}", text):
            widget.setText(f"{text[:2]}.{text[2:4]}.{text[4:]}")

    @staticmethod
    def _read_date(widget: QLineEdit, key: str) -> date | None:
        value = widget.text().strip()
        if not value:
            return None
        if re.fullmatch(r"[0-9]{8}", value):
            value = f"{value[:2]}.{value[2:4]}.{value[4:]}"
        label = {"birth_date": "Дата рождения", "contract_date": "Дата контракта", "vud_date": "Дата ВУД"}[key]
        try:
            if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", value):
                raise ValueError("Incomplete date")
            return datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError as error:
            raise ValueError(f"{label}: введите существующую дату в формате ДД.ММ.ГГГГ или оставьте поле пустым.") from error

    def _data_page(self, group: str) -> None:
        page = self._page()
        page.addWidget(self._hint("Все поля необязательны. Пустой текст останется пустым, "
                                  "вместо незаполненных числовых реквизитов будет 0. Неуказанные даты останутся пустыми."))
        card = QGroupBox(group)
        form = QFormLayout(card)
        UniqueRequestDialog._configure_form(form)
        form.setVerticalSpacing(14)
        for key, label, field_group, example in INPUT_FIELDS:
            if field_group != group:
                continue
            widget = QLineEdit()
            widget.setPlaceholderText(example)
            widget.setMinimumWidth(0)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if key == "passport_series":
                widget.setMaxLength(4)
            elif key == "passport_number":
                widget.setMaxLength(6)
            self.inputs[key] = widget
            form.addRow(label, widget)
            if key == "middle_name":
                form.addRow("Дата рождения", self._date_input("birth_date"))
            elif key == "contract_place":
                form.addRow("Дата контракта", self._date_input("contract_date"))
        if group == "Уголовное дело":
            form.addRow("Дата ВУД", self._date_input("vud_date"))
            form.addRow(self._hint("День ВУД включается в срок: 10 суток = +9 дней, 15 = +14, "
                                  "20 = +19, 25 = +24, КПмес = +29. Статья в образце — только 337 УК РФ."))
        page.addWidget(card)
        page.addStretch()

    def _review_page(self) -> None:
        page = self._page()
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        page.addWidget(self.summary)
        card = QGroupBox("Проверьте склонения — можно исправить")
        form = QFormLayout(card)
        UniqueRequestDialog._configure_form(form)
        for key, label in (("Фамилия_рп", "Родительный: в отношении кого"),
                           ("Фамилия_тп", "Творительный: кем"),
                           ("Фамилия_дп", "Дательный: кому"),
                           ("Звание_рп", "Звание в родительном падеже")):
            widget = QLineEdit()
            self.form_inputs[key] = widget
            form.addRow(label, widget)
        page.addWidget(card)
        page.addWidget(self._hint("Далее выберите, куда сохранить один полный комплект .docx. "
                                  "После создания его можно открыть и редактировать в Word. "
                                  "Пустые строки образца останутся пустыми."))
        page.addStretch()

    def _clear_for_new_person(self) -> None:
        if self.loaded_person is not None:
            for widget in self.inputs.values():
                widget.clear()
            for widget in self.dates.values():
                widget.clear()
            for widget in self.form_inputs.values():
                widget.clear()
            self.previous_forms.clear()
            self.loaded_person = None

    def _load_person(self) -> bool:
        person = self.person_combo.currentData()
        if person is None:
            QMessageBox.warning(self, "Выберите человека", "Выберите человека из списка базы.")
            return False
        if any(widget.text().strip() for widget in self.inputs.values()):
            answer = QMessageBox.question(self, "Подстановка из базы",
                "Заменить введённые данные сведениями выбранного человека?\nБаза при этом не изменится.")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        data = ControlProductionData.from_person(person)
        for key, widget in self.inputs.items():
            widget.setText(data.values.get(key, ""))
        for key, widget in self.dates.items():
            value = getattr(data, key)
            widget.setText(value.strftime("%d.%m.%Y") if value else "")
        for widget in self.form_inputs.values():
            widget.clear()
        self.previous_forms.clear()
        self.loaded_person = person
        self.source_hint.setText(f"Подставлены данные: {person.full_name.full}. "
                                "Недостающие сведения можно заполнить на следующих шагах или оставить пустыми. Изменения не сохраняются в базу.")
        return True

    def _collect(self) -> ControlProductionData:
        data = ControlProductionData(values={key: widget.text().strip() for key, widget in self.inputs.items()},
            overrides={key: widget.text().strip() for key, widget in self.form_inputs.items()
                       if key in self.previous_forms and widget.text().strip() != self.previous_forms[key]})
        for key, widget in self.dates.items():
            setattr(data, key, self._read_date(widget, key))
        return data

    def _show_step(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.step_label.setText(f"Шаг {index + 1} из {len(self.TITLES)}  ·  Комплект КП")
        self.title_label.setText(self.TITLES[index])
        self.back_button.setEnabled(index > 0)
        self.next_button.setText("Создать Word-файл" if index == 5 else "Далее")
        if index == 5:
            data = self._collect()
            forms = data.name_forms()
            for key, widget in self.form_inputs.items():
                if key not in self.previous_forms or widget.text().strip() == self.previous_forms[key]:
                    widget.setText(forms[key])
            self.previous_forms = forms
            slots = self._collect().slots()
            full_name = " ".join(slots[key] for key in ("Фамилия", "Имя", "Отчество") if slots[key])
            lines = [full_name or "ФИО не указано",
                     f"Уголовное дело № {slots['M__уголовного_дела']} · ч. {slots['ч']} ст. 337 УК РФ", ""]
            labels = {"Дата_ВУД": "Дата ВУД / ДатаВудКП", "ДатаВуд10": "10 суток", "ДатаВуд15": "15 суток",
                      "ДатаВуд20": "20 суток", "ДатаВуд25": "25 суток", "ДатаВудКПМес": "КПмес (30 суток)"}
            lines.extend(f"{label}: {slots[key] or 'не указана'}" for key, label in labels.items())
            self.summary.setText("\n".join(lines))

    def _validate_step(self, index: int) -> bool:
        if index == 0:
            if self.database_radio.isChecked():
                if self.person_combo.currentData() is None:
                    raise ValueError("Выберите человека из списка базы.")
                if self.loaded_person is not self.person_combo.currentData():
                    if not self._load_person():
                        return False
            return True
        if index == 5:
            self._collect().slots()
            return True
        if index == 4:
            self._collect().slots()
        return True

    def _next(self) -> None:
        index = self.stack.currentIndex()
        try:
            if not self._validate_step(index):
                return
            if index < 5:
                self._show_step(index + 1)
            else:
                self._generate()
        except ValueError as error:
            QMessageBox.warning(self, "Проверьте данные", str(error))

    def _generate(self) -> None:
        data = self._collect()
        data.slots()
        subject = re.sub(r'[<>:"/\\|?*]', "_", data.values.get("surname", ""))
        filename = "_".join(part for part in ("КП", subject,
                    data.vud_date.strftime("%d.%m.%Y") if data.vud_date else "") if part) + ".docx"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить полный комплект КП", filename, "Word (*.docx)")
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".docx":
            destination = destination.with_suffix(".docx")
            if destination.exists() and QMessageBox.question(self, "Заменить файл?",
                f"Файл {destination.name} уже существует. Заменить его?") != QMessageBox.StandardButton.Yes:
                return
        self.next_button.setEnabled(False)
        try:
            self.generated_path = self.service.generate(data, destination)
        except Exception as error:
            QMessageBox.critical(self, "Не удалось создать КП", str(error))
            return
        finally:
            self.next_button.setEnabled(True)
        answer = QMessageBox.question(self, "Комплект КП создан",
            f"Сохранён полный комплект:\n{self.generated_path}\n\nОткрыть его в Word?")
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.generated_path)))
        self.accept()
