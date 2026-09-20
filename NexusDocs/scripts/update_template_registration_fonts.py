"""Apply narrow, idempotent fixes without rewriting unrelated DOCX parts."""

from pathlib import Path
import os
import sys
import tempfile
from zipfile import ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.generation_service import GenerationService


def update_template(path: Path) -> bool:
    document = Document(path)
    before = etree.tostring(document.element)
    GenerationService._remove_actual_residence(document)
    # Extension forms have several independent document sizes and no recipient
    # header; leave their table fields and resolution blocks as authored.
    if path.parent.name == "requests":
        recipients = GenerationService._recipient_paragraphs(document)
        size = GenerationService._body_font_size(document, recipients)
        if size is not None:
            for element in recipients:
                paragraph = Paragraph(element, document)
                for node in GenerationService._paragraph_text_nodes(element):
                    run = Run(node.getparent(), paragraph)
                    current = run.font.size or paragraph.style.font.size
                    if current is None:
                        current = document.styles["Normal"].font.size
                    if current is not None and current.pt == size:
                        continue
                    run.font.size = Pt(size)
                    properties = run._element.get_or_add_rPr()
                    complex_size = properties.find(qn("w:szCs"))
                    if complex_size is None:
                        complex_size = OxmlElement("w:szCs")
                        properties.append(complex_size)
                    complex_size.set(qn("w:val"), str(round(size * 2)))
    if etree.tostring(document.element) == before:
        return False

    descriptor, name = tempfile.mkstemp(dir=path.parent, suffix=".docx")
    os.close(descriptor)
    temporary = Path(name)
    try:
        with ZipFile(path) as source, ZipFile(temporary, "w") as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "word/document.xml":
                    content = etree.tostring(
                        document.element, xml_declaration=True,
                        encoding="UTF-8", standalone=True,
                    )
                target.writestr(info, content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "templates"
    for template in sorted(root.glob("*/*.docx")):
        if not template.name.startswith("~$") and update_template(template):
            print(template.relative_to(root))
