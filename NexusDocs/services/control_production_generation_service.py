from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

from lxml import etree

from domain.entities.person import Person
from domain.value_objects.fullname import FullName
from utils.declension import decline_full_name, rank_genitive


# Only data explicitly marked in the reference. Empty reference sections are
# deliberately absent from both this schema and the dialog.
INPUT_FIELDS = (
    ("surname", "Фамилия", "Личность", "Шмелёв"),
    ("first_name", "Имя", "Личность", "Виктор"),
    ("middle_name", "Отчество", "Личность", "Юрьевич"),
    ("birth_place", "Место рождения", "Личность", "Город / населённый пункт"),
    ("citizenship", "Гражданство", "Личность", "Российская Федерация"),
    ("nationality", "Национальность", "Личность", "По данным материалов дела"),
    ("education", "Образование", "Личность", "По данным материалов дела"),
    ("marital_status", "Семейное положение", "Личность", "По данным материалов дела"),
    ("residence", "Место жительства", "Адрес и паспорт", "Регион, город / населённый пункт"),
    ("address", "Адрес жительства", "Адрес и паспорт", "Улица, дом, квартира"),
    ("passport_series", "Серия паспорта", "Адрес и паспорт", "4 цифры"),
    ("passport_number", "Номер паспорта", "Адрес и паспорт", "6 цифр"),
    ("passport_issuer", "Кем и когда выдан паспорт", "Адрес и паспорт", "Орган выдачи и дата"),
    ("unit", "Номер войсковой части", "Военная служба", "Только номер, например 72164"),
    ("rank", "Воинское звание", "Военная служба", "майор"),
    ("position", "Воинская должность", "Военная служба", "Наименование должности"),
    ("contract_place", "Где подписан контракт", "Военная служба", "Пункт отбора / военкомат"),
    ("personal_number", "Личный номер", "Военная служба", "По данным материалов дела"),
    ("case_number", "Номер уголовного дела", "Уголовное дело", "Полный номер"),
    ("article_part", "Часть статьи 337 УК РФ", "Уголовное дело", "Например 2.1 или 5"),
)
DIRECT_SLOTS = {
    "surname": "Фамилия", "first_name": "Имя", "middle_name": "Отчество",
    "birth_place": "Место_рождения", "citizenship": "Гражданство",
    "nationality": "Национальность", "education": "Образование",
    "marital_status": "Семейное_положение", "residence": "Место_жительства",
    "address": "Адрес_жительства", "passport_series": "Серия_паспорта",
    "passport_number": "Номер_паспорта", "passport_issuer": "Кем_и_когда_выдан_паспорт",
    "unit": "вчасть", "rank": "воинское_звание", "position": "воинская_должность",
    "contract_place": "ГдеПодписалКонтракт", "personal_number": "Личный_номер",
    "case_number": "M__уголовного_дела", "article_part": "ч",
}
# Identifiers that the user wants rendered as 0 when omitted. Personal military
# numbers are alphanumeric (АБ-123456), so that field remains text, not a number.
NUMERIC_FIELDS = frozenset({"passport_series", "passport_number", "unit", "case_number", "article_part"})
DATE_OFFSETS = {"Дата_ВУД": 0, "ДатаВудКП": 0, "ДатаВуд10": 9,
                "ДатаВуд15": 14, "ДатаВуд20": 19, "ДатаВуд25": 24,
                "ДатаВудКПМес": 29}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SLOT = re.compile(r"\{\{([^{}]+)}}")
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "control_production" / "control_production.docx"


def normalize_unit(value: str) -> str:
    return re.sub(r"^(?:войсковая\s+часть|в/\s*(?:часть|части|ч))\s*№?\s*|^№\s*",
                  "", value.strip(), flags=re.IGNORECASE).strip()


@dataclass(slots=True)
class ControlProductionData:
    values: dict[str, str] = field(default_factory=dict)
    vud_date: date | None = None
    birth_date: date | None = None
    contract_date: date | None = None
    overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_person(cls, person: Person) -> ControlProductionData:
        address = person.registration_address
        values = {
            "surname": person.full_name.last_name, "first_name": person.full_name.first_name,
            "middle_name": person.full_name.middle_name, "birth_place": person.birth.place.full,
            "residence": ", ".join(x for x in (address.region, address.district,
                                             address.city, address.locality) if x),
            "address": ", ".join(x for x in (address.street,
                f"д. {address.house}" if address.house else "",
                f"кв. {address.apartment}" if address.apartment else "") if x),
            "unit": normalize_unit(person.military.military_unit), "rank": person.military.rank,
            "position": person.military.position, "personal_number": person.military.military_id,
            "case_number": person.soch_case.case_number or "",
        }
        match = re.search(r"ч\.\s*(\d+(?:\.\d+)?)\s+ст\.\s*337\b",
                          person.soch_case.article, re.IGNORECASE)
        if match:
            values["article_part"] = match.group(1)
        if person.passport:
            values.update(passport_series=person.passport.series,
                          passport_number=person.passport.number,
                          passport_issuer=f"{person.passport.issued_by}, {person.passport.issue_date:%d.%m.%Y}")
        # An outgoing request date or SOCH date is NOT a VUD date.
        return cls(values=values, birth_date=person.birth.birth_date)

    def validate(self) -> None:
        # Blank fields are valid. Format checks apply only to supplied values.
        part = self.values.get("article_part", "").strip()
        if part and part not in {"0", "1", "2", "2.1", "3", "3.1", "4", "5"}:
            raise ValueError("Укажите часть статьи 337: 1, 2, 2.1, 3, 3.1, 4 или 5.")
        for key, length, label in (("passport_series", 4, "Серия паспорта"),
                                   ("passport_number", 6, "Номер паспорта")):
            value = self.values.get(key, "").strip()
            if value and value != "0" and not re.fullmatch(rf"\d{{{length}}}", value):
                raise ValueError(f"{label}: требуется {length} цифр.")
        if self.vud_date is not None:
            try:
                self.vud_date + timedelta(days=29)
            except OverflowError as error:
                raise ValueError("Дата ВУД выходит за допустимый диапазон сроков.") from error

    def name_forms(self) -> dict[str, str]:
        if not self.values.get("surname", "").strip():
            return {"Фамилия_рп": "", "Фамилия_тп": "", "Фамилия_дп": "",
                    "Звание_рп": rank_genitive(self.values.get("rank", "").strip())}
        name = FullName(*(self.values.get(key, "").strip()
                          for key in ("surname", "first_name", "middle_name")))
        declined = decline_full_name(name)
        genitive = declined.last_name_genitive
        if name.middle_name.lower().endswith(("на", "ична")):
            dative = genitive
        elif genitive.endswith("ого"):
            dative = genitive[:-3] + "ому"
        elif genitive.endswith("его"):
            dative = genitive[:-3] + "ему"
        elif genitive.endswith("а") and genitive != name.last_name:
            dative = genitive[:-1] + "у"
        elif genitive.endswith("я") and genitive != name.last_name:
            dative = genitive[:-1] + "ю"
        elif name.last_name.endswith(("а", "я")):
            dative = name.last_name[:-1] + "е"
        else:
            dative = name.last_name
        return {"Фамилия_рп": genitive, "Фамилия_тп": declined.last_name_instrumental,
                "Фамилия_дп": dative, "Звание_рп": rank_genitive(self.values.get("rank", ""))}

    def slots(self) -> dict[str, str]:
        self.validate()
        slots = {slot: self.values.get(key, "").strip() for key, slot in DIRECT_SLOTS.items()}
        slots["вчасть"] = normalize_unit(slots["вчасть"])
        slots["M__уголовного_дела"] = re.sub(r"^№\s*", "", slots["M__уголовного_дела"])
        for key in NUMERIC_FIELDS:
            if not slots[DIRECT_SLOTS[key]]:
                slots[DIRECT_SLOTS[key]] = "0"
        forms = self.name_forms()
        slots.update(forms)
        for key, value in self.overrides.items():
            if key not in forms:
                raise ValueError(f"Неизвестное поле склонения: {key}")
            slots[key] = value.strip()
        slots["Инициалы"] = "".join(value[0] + "." for value in (slots["Имя"], slots["Отчество"]) if value)
        slots["Дата_рождения"] = self.birth_date.strftime("%d.%m.%Y") if self.birth_date else ""
        slots["ДатаКонтракта"] = self.contract_date.strftime("%d.%m.%Y") if self.contract_date else ""
        slots.update({key: (self.vud_date + timedelta(days=days)).strftime("%d.%m.%Y") if self.vud_date else ""
                      for key, days in DATE_OFFSETS.items()})
        if any("{{" in value or "}}" in value or any(ord(c) < 32 for c in value)
               for value in slots.values()):
            raise ValueError("Поля не должны содержать разметку или управляющие символы.")
        return slots


class ControlProductionGenerationService:
    """A single complete KP package; no Person creation or database writes."""

    def generate(self, data: ControlProductionData, destination: Path,
                 template_path: Path = TEMPLATE_PATH) -> Path:
        slots = data.slots()
        destination = Path(destination)
        if destination.suffix.lower() != ".docx":
            raise ValueError("Для комплекта КП нужен файл .docx.")
        if destination.resolve() in {Path(template_path).resolve(), TEMPLATE_PATH.with_name("reference.docx").resolve()}:
            raise ValueError("Нельзя перезаписать шаблон КП.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(suffix=".docx", dir=destination.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            with ZipFile(template_path) as source, ZipFile(temporary, "w") as target:
                root = etree.fromstring(source.read("word/document.xml"))
                found = set()
                for node in root.iter(W + "t"):
                    def substitute(match: re.Match) -> str:
                        key = match.group(1)
                        if key not in slots:
                            raise ValueError(f"Неизвестное поле шаблона: {key}")
                        found.add(key)
                        return slots[key]
                    node.text = SLOT.sub(substitute, node.text or "")
                    if node.text.startswith(" ") or node.text.endswith(" "):
                        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if found != set(slots):
                    raise ValueError("Набор полей шаблона КП изменился: " + ", ".join(sorted(set(slots) - found)))
                changed = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                for item in source.infolist():
                    target.writestr(item, changed if item.filename == "word/document.xml"
                                    else source.read(item.filename))
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
