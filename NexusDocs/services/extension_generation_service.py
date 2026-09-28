from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from docx.text.paragraph import Paragraph

from domain.entities.person import Person
from services.generation_service import GenerationService
from services.word_typography_service import protect_word_line_breaks
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
        self._prepare_extension_template(document)
        self._replacement_service._prepare_investigator_lines(document)
        replacements = self._build_replacements(person, overrides)
        self._replacement_service._replace_in_container(document, replacements)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / self.filename(person)
        document.save(output_path)
        protect_word_line_breaks(output_path)
        return output_path

    @staticmethod
    def _prepare_extension_template(document) -> None:
        """Keep the approval block intact and let body text wrap naturally."""
        def paragraphs(container):
            yield from container.paragraphs
            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        yield from paragraphs(cell)

        for paragraph in paragraphs(document):
            content = paragraph.text.strip()
            if content.startswith("Заместитель руководителя ВСО СК России"):
                # The approval block has an intentional two-line arrangement;
                # unlike the body, its break must remain fixed.
                GenerationService._replace_in_paragraph(
                    paragraph,
                    {"ВСО СК России \nпо Власихинскому гарнизону":
                     "ВСО СК\nРоссии по Власихинскому гарнизону"},
                )
            if content == "Руководитель":
                GenerationService._replace_in_paragraph(
                    paragraph, {"Руководитель": "Заместитель руководителя"}
                )
            elif content.startswith("Руководитель военного следственного отдела"):
                GenerationService._replace_in_paragraph(
                    paragraph, {"Руководитель": "Заместитель руководителя"}
                )
            if "Агиров" in content:
                GenerationService._replace_in_paragraph(
                    paragraph, {"О.Р. Агиров": "В.Н. Литвинов"}
                )

        # These old hard line breaks sit inside justified body paragraphs.
        # Word then stretches the preceding line and may push the final
        # signature onto a fourth page. Leave wrapping to Word instead.
        for paragraph in document.paragraphs:
            if paragraph.alignment != WD_ALIGN_PARAGRAPH.JUSTIFY:
                continue
            for run in paragraph.runs:
                # Some source paragraphs already contain hidden NBSP chains.
                # Reset those as well before the narrow semantic rule runs.
                normalized = run.text.replace("\u00a0", " ")
                normalized = re.sub(r"[ \t]*\n[ \t]*", " ", normalized)
                if normalized != run.text:
                    run.text = normalized

        ExtensionGenerationService._prepare_motion_approval_layout(document)

        compact_gaps = {33: 5, 35: 5, 37: 4, 39: 4,
                        48: 4, 50: 4, 52: 6, 56: 6}
        for index, points in compact_gaps.items():
            if index >= len(document.paragraphs):
                continue
            paragraph = document.paragraphs[index]
            if not paragraph.text.strip():
                paragraph.paragraph_format.line_spacing = Pt(points)

    @staticmethod
    def _prepare_motion_approval_layout(document) -> None:
        """Keep the resolution title below, never beside, the approval block."""
        for table in document.tables:
            text = " ".join(table._tbl.xpath(".//w:t/text()"))
            if "{{THREE_DAY_LONG}}" not in text or "подпись" not in text:
                continue

            # A floating table does not reserve height in the text flow. Shrunk
            # blank paragraphs therefore let the centered title wrap around it.
            # Keep the same right-hand table, widths, borders and contents, but
            # make it inline so Word must put the title underneath the date.
            properties = table._tbl.tblPr
            for tag in ("w:tblpPr", "w:tblOverlap"):
                for element in list(properties.findall(qn(tag))):
                    properties.remove(element)
            table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            width = properties.find(qn("w:tblW"))
            if width is not None:
                width.set(qn("w:type"), "dxa")
                width.set(qn("w:w"), str(sum(
                    int(column.get(qn("w:w")))
                    for column in table._tbl.tblGrid
                )))
            for frame in list(table._tbl.iter(qn("w:framePr"))):
                frame.getparent().remove(frame)

            # Previously these empty paragraphs reserved room for the floating
            # table. Its inline height now does that; leave one 12 pt visual gap
            # without deleting paragraphs or changing the three-line title.
            gaps = []
            for following in table._tbl.itersiblings():
                if following.tag != qn("w:p"):
                    break
                paragraph = Paragraph(following, document)
                if paragraph.text.strip():
                    break
                if following.xpath("./w:pPr/w:sectPr"):
                    break
                gaps.append(paragraph)
            for index, paragraph in enumerate(gaps):
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = Pt(
                    max(1, 12 - len(gaps) + 1) if index == len(gaps) - 1 else 1
                )

            # Change only this page's footer distance, not typography or the
            # page-one/instructions margins. Its section ends after the motion.
            section_end = next((
                section
                for following in table._tbl.itersiblings()
                for section in following.xpath("./w:pPr/w:sectPr")
            ), None)
            if section_end is not None:
                margins = section_end.find(qn("w:pgMar"))
                if margins is not None:
                    margins.set(qn("w:footer"), str(Mm(3).twips))
            break

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
            "{{RETURN_TO_DEPARTMENT_SENTENCE}}": cls._return_to_department_sentence(
                person,
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
            f"{prefix} совершил самовольное оставление части без "
            f"уважительных причин – в/часть {military_unit}, "
            f"дислоцированную в {deployment}."
        )

    @classmethod
    def _return_to_department_sentence(cls, person: Person) -> str:
        return (
            f"{cls._numeric_date(person.document_info.outgoing_date)} "
            f"{person.full_name.initials} добровольно обратился в ВСО СК России "
            "по Власихинскому гарнизону, расположенный по адресу: Московская "
            "область, пос. Власиха, ул. Лесная, д. 37, где заявил о себе как о "
            "военнослужащем, совершившим уклонение от прохождения установленного "
            "законом порядка прохождения военной службы, в связи с чем его "
            "незаконное нахождение вне сферы воинских правоотношений было "
            "прекращено."
        )
