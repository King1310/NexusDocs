from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
import re

from docx import Document

from domain.entities.person import Person
from services.generation_service import GenerationService
from utils.declension import decline_full_name, rank_genitive


class ExtensionGenerationService:
    """Создаёт трёхстраничное продление срока проверки до десяти суток."""

    CIRCUMSTANCE_NO_SHOW = "Неявка в срок"
    CIRCUMSTANCE_AWOL = "Самовольное оставление части"
    CIRCUMSTANCE_CHOICES = (
        CIRCUMSTANCE_NO_SHOW,
        CIRCUMSTANCE_AWOL,
    )
    MONTHS_GENITIVE = (
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )

    def __init__(self) -> None:
        self._replacement_service = GenerationService()

    @classmethod
    def missing_fields(cls, person: Person) -> tuple[str, ...]:
        required = (
            ("Дислокация в/части", person.military.military_deployment),
            ("Условия призыва", person.military.service_basis),
            ("Дата исходящего документа", person.document_info.outgoing_date),
            ("Обстоятельства СОЧ", person.soch_case.circumstances),
        )
        return tuple(label for label, value in required if not value)

    def generate(
        self,
        person: Person,
        template_path: Path,
        output_dir: Path,
        overrides: Mapping[str, str] | None = None,
    ) -> Path:
        if not template_path.is_file():
            raise FileNotFoundError(f"Шаблон продления не найден: {template_path}")

        missing = self.missing_fields(person)
        if missing:
            raise ValueError(
                "Не заполнены данные для продления: " + ", ".join(missing)
            )
        if person.soch_case.circumstances not in self.CIRCUMSTANCE_CHOICES:
            raise ValueError(
                "Выберите одно из двух обстоятельств СОЧ через «Редактировать»."
            )

        document = Document(template_path)
        self._replacement_service._prepare_investigator_lines(document)
        replacements = self._build_replacements(person, overrides)
        self._replacement_service._replace_in_container(document, replacements)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / self.filename(person)
        document.save(output_path)
        return output_path

    @classmethod
    def filename(cls, person: Person) -> str:
        outgoing_date = person.document_info.outgoing_date
        date_part = (
            outgoing_date.strftime("%d.%m.%Y")
            if outgoing_date is not None
            else "без_даты"
        )
        base = (
            f"{person.full_name.last_name}"
            f"{person.full_name.first_name[:1]}"
            f"{person.full_name.middle_name[:1]}_"
            f"{date_part}_продление_до_10_суток.docx"
        )
        return re.sub(r'[<>:"/\\|?*]', "_", base)

    @classmethod
    def _build_replacements(
        cls,
        person: Person,
        overrides: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        manual = dict(overrides or {})
        declined = decline_full_name(person.full_name)
        last_genitive = manual.get(
            "LAST_NAME_GENITIVE",
            declined.last_name_genitive,
        )
        first_genitive = manual.get(
            "FIRST_NAME_GENITIVE",
            declined.first_name_genitive,
        )
        middle_genitive = manual.get(
            "MIDDLE_NAME_GENITIVE",
            declined.middle_name_genitive,
        )
        rank_in_genitive = manual.get(
            "MILITARY_RANK_GENITIVE",
            rank_genitive(person.military.rank),
        )

        outgoing_date = person.document_info.outgoing_date
        if outgoing_date is None:
            raise ValueError("Не заполнена дата исходящего документа.")
        three_day_date = outgoing_date + timedelta(days=2)
        ten_day_date = outgoing_date + timedelta(days=9)
        military_unit = GenerationService._military_unit_value(
            person.military.military_unit
        )

        return {
            **person.investigator.replacements(),
            "{{FULL_NAME_INITIALS}}": person.full_name.initials,
            "{{FULL_NAME_INITIALS_GENITIVE}}": (
                f"{last_genitive} "
                f"{person.full_name.first_name[:1]}."
                f"{person.full_name.middle_name[:1]}."
            ),
            "{{FULL_NAME_GENITIVE}}": (
                f"{last_genitive} {first_genitive} {middle_genitive}"
            ),
            "{{MILITARY_UNIT}}": military_unit,
            "{{MILITARY_RANK}}": person.military.rank,
            "{{MILITARY_RANK_GENITIVE}}": rank_in_genitive,
            "{{MILITARY_POSITION}}": person.military.position,
            "{{MILITARY_DEPLOYMENT}}": person.military.military_deployment,
            "{{SERVICE_BASIS}}": person.military.service_basis,
            "{{ARTICLE}}": person.soch_case.article,
            "{{SOCH_DATE}}": cls._numeric_date(person.soch_case.soch_date),
            # Retain the existing template token with the unified document date.
            "{{REGISTRATION_DATE}}": cls._numeric_date(outgoing_date),
            "{{THREE_DAY_DATE}}": cls._numeric_date(three_day_date),
            "{{TEN_DAY_DATE}}": cls._numeric_date(ten_day_date),
            "{{THREE_DAY_LONG_COMPACT}}": cls._long_date(
                three_day_date,
                compact_year=True,
            ),
            "{{THREE_DAY_LONG}}": cls._long_date(three_day_date),
            "{{TEN_DAY_LONG}}": cls._long_date(ten_day_date),
            "{{THREE_DAY_DAY}}": f"{three_day_date.day:02d}",
            "{{THREE_DAY_MONTH}}": cls.MONTHS_GENITIVE[three_day_date.month],
            "{{THREE_DAY_YEAR_PREFIX}}": str(three_day_date.year)[:2],
            "{{THREE_DAY_YEAR_SUFFIX}}": str(three_day_date.year)[2:],
            "{{SOCH_CIRCUMSTANCE_SENTENCE}}": cls._circumstance_sentence(
                person,
                military_unit,
            ),
        }

    @staticmethod
    def _numeric_date(value: date) -> str:
        return value.strftime("%d.%m.%Y")

    @classmethod
    def _long_date(cls, value: date, compact_year: bool = False) -> str:
        before_year_suffix = "" if compact_year else " "
        return (
            f"«{value.day:02d}» {cls.MONTHS_GENITIVE[value.month]} "
            f"{value.year}{before_year_suffix}г."
        )

    @classmethod
    def _circumstance_sentence(
        cls,
        person: Person,
        military_unit: str,
    ) -> str:
        prefix = f"{person.soch_case.soch_date:%d.%m.%Y} {person.full_name.initials}"
        deployment = person.military.military_deployment
        if person.soch_case.circumstances == cls.CIRCUMSTANCE_NO_SHOW:
            return (
                f"{prefix} совершил неявку в срок без уважительных причин "
                f"на службу в в/часть {military_unit}, дислоцированную "
                f"в {deployment}."
            )
        return (
            f"{prefix} совершил самовольное оставление в/части "
            f"{military_unit}, дислоцированной в {deployment}, "
            "без уважительных причин."
        )
