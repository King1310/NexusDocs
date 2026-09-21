from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxcompose.composer import Composer

from domain.entities.person import Person
from services.request_catalog import REQUEST_CATALOG


class WordBundleService:
    """Собирает общий редактируемый Word из всех запросов."""

    BOOKMARK_PREFIX = "NEXUSDOCS_REQUEST_"
    FOOTERLESS_CONTINUATIONS = frozenset({9, 11})

    def create_editable_bundle(
        self,
        source_documents: Sequence[Path],
        output_path: Path,
    ) -> Path:
        if len(source_documents) != len(REQUEST_CATALOG):
            raise ValueError("Для общего Word требуется ровно 15 запросов.")
        missing = [path for path in source_documents if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Не найден документ: {missing[0]}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        master = Document(source_documents[0])
        self._add_request_bookmark(master, REQUEST_CATALOG[0].number)
        composer = Composer(master)

        for request, source_path in zip(
            REQUEST_CATALOG[1:],
            source_documents[1:],
            strict=True,
        ):
            source = Document(source_path)
            self._add_request_bookmark(source, request.number)

            section = master.add_section(WD_SECTION.NEW_PAGE)
            self._copy_section_layout(source.sections[0]._sectPr, section._sectPr)
            composer.append(source)
            self._copy_section_layout(
                source.sections[-1]._sectPr,
                master.sections[-1]._sectPr,
            )

        composer.save(output_path)
        self._restore_section_stories(source_documents, output_path)
        self._normalize_request_footers(source_documents, output_path)
        return output_path

    @staticmethod
    def bundle_filename(person: Person) -> str:
        base = (
            f"{person.full_name.last_name}"
            f"{person.full_name.first_name[:1]}"
            f"{person.full_name.middle_name[:1]}_"
            f"{person.document_info.outgoing_date:%d.%m.%Y}_"
            "все_запросы"
        )
        return re.sub(r'[<>:"/\\|?*]', "_", base) + ".docx"

    @classmethod
    def _bookmark_name(cls, request_number: int) -> str:
        return f"{cls.BOOKMARK_PREFIX}{request_number:02d}"

    @classmethod
    def _add_request_bookmark(cls, document, request_number: int) -> None:
        if not document.paragraphs:
            document.add_paragraph()
        paragraph = document.paragraphs[0]._p
        bookmark_id = str(1000 + request_number)
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), bookmark_id)
        start.set(qn("w:name"), cls._bookmark_name(request_number))
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), bookmark_id)
        paragraph.insert(0, start)
        paragraph.insert(1, end)

    @staticmethod
    def _copy_section_layout(source_sect_pr, target_sect_pr) -> None:
        layout_tags = (
            "pgSz",
            "pgMar",
            "paperSrc",
            "pgBorders",
            "lnNumType",
            "pgNumType",
            "cols",
            "docGrid",
        )
        for tag in layout_tags:
            qualified = qn(f"w:{tag}")
            for existing in list(target_sect_pr.findall(qualified)):
                target_sect_pr.remove(existing)
            source_element = source_sect_pr.find(qualified)
            if source_element is not None:
                target_sect_pr.append(deepcopy(source_element))

    @classmethod
    def _restore_section_stories(
        cls,
        source_documents: Sequence[Path],
        output_path: Path,
    ) -> None:
        """Вернуть каждому разделу собственные колонтитулы исходного файла."""

        combined = Document(output_path)
        target_index = 0
        for source_path in source_documents:
            source = Document(source_path)
            for source_section in source.sections:
                if target_index >= len(combined.sections):
                    raise ValueError("Не удалось сопоставить разделы общего Word.")
                target_section = combined.sections[target_index]
                cls._clone_story(source_section.header, target_section.header)
                cls._clone_story(source_section.footer, target_section.footer)
                target_index += 1

        if target_index != len(combined.sections):
            raise ValueError("В общем Word обнаружены лишние разделы.")
        combined.save(output_path)

    @classmethod
    def _normalize_request_footers(
        cls,
        source_documents: Sequence[Path],
        output_path: Path,
    ) -> None:
        """Keep one outgoing request number on every section of that request."""

        combined = Document(output_path)
        target_index = 0
        for request, source_path in zip(
            REQUEST_CATALOG,
            source_documents,
            strict=True,
        ):
            section_count = len(Document(source_path).sections)
            request_sections = combined.sections[
                target_index : target_index + section_count
            ]
            if len(request_sections) != section_count:
                raise ValueError("Не удалось сопоставить колонтитулы запросов.")

            first_footer = request_sections[0].footer
            for section_index, section in enumerate(request_sections):
                if (
                    section_index
                    and request.number in cls.FOOTERLESS_CONTINUATIONS
                ):
                    cls._clear_story(section.footer)
                    continue
                if section_index and not cls._story_has_text(section.footer):
                    cls._clone_story(first_footer, section.footer)
                cls._replace_footer_request_number(
                    section.footer,
                    request.number,
                )
            target_index += section_count

        if target_index != len(combined.sections):
            raise ValueError("В общем Word обнаружены лишние разделы.")
        combined.save(output_path)

    @staticmethod
    def _clear_story(story) -> None:
        story.is_linked_to_previous = False
        element = story._element
        for child in list(element):
            element.remove(child)
        element.append(OxmlElement("w:p"))

    @staticmethod
    def _story_has_text(story) -> bool:
        return any(
            text.strip()
            for paragraph in story.paragraphs
            for text in (paragraph.text,)
        ) or any(
            paragraph.text.strip()
            for table in story.tables
            for row in table.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        )

    @classmethod
    def _replace_footer_request_number(cls, story, request_number: int) -> None:
        for paragraph in story.paragraphs:
            cls._replace_request_number_in_paragraph(paragraph, request_number)
        for table in story.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        cls._replace_request_number_in_paragraph(
                            paragraph,
                            request_number,
                        )

    @staticmethod
    def _replace_request_number_in_paragraph(paragraph, request_number: int) -> None:
        combined = "".join(run.text for run in paragraph.runs)
        replaced = re.sub(
            r"/\d{1,2}(-\d{2}\b)",
            rf"/{request_number}\1",
            combined,
        )
        if replaced == combined or not paragraph.runs:
            return
        paragraph.runs[0].text = replaced
        for run in paragraph.runs[1:]:
            run.text = ""

    @staticmethod
    def _clone_story(source_story, target_story) -> None:
        target_story.is_linked_to_previous = False
        target = target_story._element
        for child in list(target):
            target.remove(child)
        for child in source_story._element:
            target.append(deepcopy(child))
