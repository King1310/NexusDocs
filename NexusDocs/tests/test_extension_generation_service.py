from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Twips

from services.extension_generation_service import ExtensionGenerationService
from tests.factories.person_factory import PersonFactory


TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "extensions"
    / "extension_to_10_days.docx"
)


def _all_text(path: Path) -> str:
    document = Document(path)
    def collect(container):
        for paragraph in container.paragraphs:
            yield paragraph.text
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from collect(cell)

    parts = list(collect(document))
    return "\n".join(parts).replace("\u00a0", " ")


def test_generates_extension_with_calculated_dates_and_no_times(tmp_path):
    person = PersonFactory.create()
    person = replace(
        person,
        military=replace(
            person.military,
            military_unit="в/ч 95375",
            military_deployment="г. Ясиноватая ДНР",
            service_basis="по мобилизации",
            rank="старшина",
            position="заместитель командира взвода",
        ),
        soch_case=replace(
            person.soch_case,
            soch_date=date(2026, 8, 10),
            registration_date=date(2026, 7, 25),
            circumstances="Неявка в срок",
            article="ч. 2.1 ст. 337 УК РФ",
        ),
        document_info=replace(
            person.document_info,
            outgoing_date=date(2026, 8, 17),
        ),
    )

    output = ExtensionGenerationService().generate(
        person,
        TEMPLATE_PATH,
        tmp_path,
    )
    text = _all_text(output)

    assert output.name == "ИвановИИ_17.08.2026_продление_до_10_суток.docx"
    assert "17.08.2026" in text
    assert "19.08.2026" in text
    assert "26.08.2026" in text
    assert "25.07.2026" not in text
    assert "по мобилизации в в/части 95375" in text
    assert "Иванова Ивана Ивановича" in text
    assert "старшины Иванова И.И." in text
    assert "ч. 2.1 ст. 337 УК РФ" in text
    assert "совершил неявку в срок без уважительных причин" in text
    assert "собственный рапорт об обнаружении" in text
    assert "рапорт старшего следователя-криминалиста" not in text
    assert "Саркисяна А.К." not in text
    assert "заместителем руководителя военного следственного отдела" in text
    assert "Литвиновым В.Н." in text
    assert "Заместитель руководителя военного следственного отдела" in text
    assert "Заместитель руководителя\nвоенного следственного отдела" in text
    assert "Литвинов В.Н." in text
    assert "В.Н. Литвинов" in text
    assert "Агиров" not in text
    assert "уклонение от прохождения установленного законом порядка" in text
    assert "незаконное нахождение вне сферы воинских правоотношений было прекращено" in text
    assert "Около 00 часов" not in text
    assert "Около 15 часов" not in text
    assert "{{" not in text
    assert "Шмел" not in text

    document = Document(output)
    assert (
        "Заместитель руководителя ВСО СК\n"
        "России по Власихинскому гарнизону"
        in document.paragraphs[1].text.replace("\u00a0", " ")
    )
    for start in (
        "По материалам доследственной проверки",
        "Из материалов проверки следует",
        "В 3-х суточный срок доследственной проверки",
        "Ходатайствовать перед заместителем руководителя",
    ):
        paragraph = next(
            p for p in document.paragraphs
            if p.text.replace("\u00a0", " ").startswith(start)
        )
        assert "\n" not in paragraph.text
    assert all(
        "\n" not in paragraph.text
        for paragraph in document.paragraphs
        if paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    )
    assert "п. 3 ч. 1 и" in document.paragraphs[70].text
    approval_table = document.tables[1]
    assert approval_table.alignment == WD_TABLE_ALIGNMENT.RIGHT
    assert approval_table._tbl.tblPr.find(qn("w:tblpPr")) is None
    assert not list(approval_table._tbl.iter(qn("w:framePr")))
    assert [column.get(qn("w:w")) for column in approval_table._tbl.tblGrid] == ["5259"]
    assert approval_table._tbl.tblPr.find(qn("w:tblW")).get(qn("w:w")) == "5259"
    assert "В.Н. Литвинов" in " ".join(approval_table._tbl.xpath(".//w:t/text()"))
    assert "19» августа 2026" in approval_table.cell(0, 0).text
    assert document.paragraphs[25].paragraph_format.line_spacing.pt == 12
    assert sum(
        document.paragraphs[index].paragraph_format.line_spacing.pt
        for index in range(26, 30)
    ) == 12
    assert [document.paragraphs[index].text for index in range(30, 33)] == [
        "ПОСТАНОВЛЕНИЕ",
        "о возбуждении перед руководителем следственного органа ходатайства ",
        "о продлении срока проверки сообщения о преступлении",
    ]
    assert all(
        document.paragraphs[index].alignment == WD_ALIGN_PARAGRAPH.CENTER
        for index in range(30, 33)
    )
    assert document.sections[1].footer_distance == Twips(Mm(3).twips)
    assert document.sections[0].footer_distance == Document(TEMPLATE_PATH).sections[0].footer_distance
    assert document.sections[2].footer_distance == Document(TEMPLATE_PATH).sections[2].footer_distance


def test_motion_approval_layout_preserves_content_and_is_idempotent():
    document = Document(TEMPLATE_PATH)
    original_text = document.element.body.xpath(".//w:t/text()")
    original_breaks = len(document.element.body.xpath(".//w:sectPr"))
    ExtensionGenerationService._prepare_motion_approval_layout(document)
    first_pass = document.element.xml

    assert document.element.body.xpath(".//w:t/text()") == original_text
    assert len(document.element.body.xpath(".//w:sectPr")) == original_breaks
    ExtensionGenerationService._prepare_motion_approval_layout(document)
    assert document.element.xml == first_pass


def test_generates_second_supported_circumstance(tmp_path):
    person = PersonFactory.create()
    person = replace(
        person,
        soch_case=replace(
            person.soch_case,
            circumstances="Самовольное оставление части",
        ),
    )

    output = ExtensionGenerationService().generate(
        person,
        TEMPLATE_PATH,
        tmp_path,
    )

    text = _all_text(output)
    assert (
        "совершил самовольное оставление части без уважительных причин – "
        "в/часть 12345, дислоцированную в г. Балашиха Московской области."
        in text
    )
    assert "самовольное оставление в/части" not in text


def test_reports_all_new_fields_missing_for_legacy_person():
    person = PersonFactory.create()
    person = replace(
        person,
        military=replace(
            person.military,
            military_deployment="",
            service_basis="",
        ),
        soch_case=replace(
            person.soch_case,
            registration_date=None,
            circumstances="",
        ),
    )

    assert ExtensionGenerationService.missing_fields(person) == (
        "Дислокация в/части",
        "Условия призыва",
        "Обстоятельства СОЧ",
    )


def test_extension_dates_use_outgoing_date_for_legacy_person():
    person = PersonFactory.create()
    person = replace(
        person,
        soch_case=replace(person.soch_case, registration_date=None),
        document_info=replace(
            person.document_info,
            outgoing_date=date(2026, 12, 30),
        ),
    )

    replacements = ExtensionGenerationService._build_replacements(person)

    assert ExtensionGenerationService.missing_fields(person) == ()
    assert replacements["{{REGISTRATION_DATE}}"] == "30.12.2026"
    assert replacements["{{THREE_DAY_DATE}}"] == "01.01.2027"
    assert replacements["{{TEN_DAY_DATE}}"] == "08.01.2027"
    assert "30.12.2026" in ExtensionGenerationService.filename(person)
