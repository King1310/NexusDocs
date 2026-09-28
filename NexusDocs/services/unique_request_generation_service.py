from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import tempfile

from docx import Document
from docx.enum.section import WD_SECTION
from docxcompose.composer import Composer

from domain.entities.organization import Organization
from domain.entities.person import Person
from domain.enums.registration_mode import RegistrationMode
from services.generation_service import GenerationService
from services.request_catalog import RequestTemplate
from services.request_catalog import REQUEST_CATALOG
from services.word_bundle_service import WordBundleService


@dataclass(frozen=True, slots=True)
class SubjectFieldSpec:
    """One data item needed when a unique-request subject is not in the DB."""

    key: str
    label: str
    required: bool = True
    note: str = ""


_FIELD_SPECS = {
    "full_name": SubjectFieldSpec("full_name", "Фамилия, имя, отчество"),
    "birth_date": SubjectFieldSpec("birth_date", "Дата рождения"),
    "birth_place": SubjectFieldSpec("birth_place", "Место рождения"),
    "registration_address": SubjectFieldSpec(
        "registration_address",
        "Адрес регистрации",
    ),
    "passport": SubjectFieldSpec("passport", "Паспортные данные"),
    "military_unit": SubjectFieldSpec("military_unit", "Войсковая часть"),
    "military_rank": SubjectFieldSpec("military_rank", "Воинское звание"),
    "soch_date": SubjectFieldSpec("soch_date", "Дата СОЧ"),
    "case_type": SubjectFieldSpec("case_type", "Тип дела"),
    "case_number": SubjectFieldSpec(
        "case_number",
        "Номер уголовного дела",
        required=False,
        note="Обязателен только для уголовного дела.",
    ),
    "article": SubjectFieldSpec("article", "Статья и часть УК РФ"),
}


_REQUEST_FIELDS: dict[int, tuple[str, ...]] = {
    1: (
        "full_name", "birth_date", "military_unit", "military_rank",
        "case_type", "case_number", "article",
    ),
    2: (
        "full_name", "birth_date", "birth_place", "passport",
        "military_unit", "military_rank", "case_type", "case_number", "article",
    ),
    3: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "soch_date",
        "case_type", "case_number", "article",
    ),
    4: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "soch_date",
        "case_type", "case_number", "article",
    ),
    5: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "case_type",
        "case_number", "article",
    ),
    6: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "case_type",
        "case_number", "article",
    ),
    7: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "soch_date",
        "case_type", "case_number", "article",
    ),
    8: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "soch_date",
        "case_type", "case_number", "article",
    ),
    9: (
        "full_name", "birth_date", "passport", "military_unit",
        "military_rank", "case_type", "case_number", "article",
    ),
    # МВД is one logical three-page request: local cover letter (10) plus the
    # regional cover letter and the ИЦ/ГИАЦ form (11).  Ask for the union of
    # the fields used by both source templates.
    10: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "case_type", "case_number",
    ),
    11: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "case_type", "case_number",
    ),
    12: (
        "full_name", "birth_date", "registration_address", "military_unit",
        "military_rank", "soch_date", "case_type", "case_number", "article",
    ),
    13: (
        "full_name", "birth_date", "registration_address", "passport",
        "military_unit", "military_rank", "case_type", "case_number", "article",
    ),
    14: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "military_unit", "military_rank", "soch_date", "case_type",
        "case_number", "article",
    ),
    15: (
        "full_name", "birth_date", "birth_place", "registration_address",
        "passport", "military_unit", "military_rank", "case_type",
        "case_number", "article",
    ),
}


class UniqueRequestGenerationService:
    """Generate one selected request without mutating a stored person."""

    def __init__(self, generation_service: GenerationService | None = None) -> None:
        self.generation_service = generation_service or GenerationService()

    @staticmethod
    def required_subject_fields(
        request: RequestTemplate,
    ) -> tuple[SubjectFieldSpec, ...]:
        try:
            keys = _REQUEST_FIELDS[request.number]
        except KeyError as error:
            raise ValueError(f"Неизвестный шаблон запроса: {request.number}") from error
        return tuple(_FIELD_SPECS[key] for key in keys)

    def generate(
        self,
        *,
        person: Person,
        request: RequestTemplate,
        template_dir: Path,
        output_dir: Path,
        organization: Organization | None = None,
        recipient_header: str | None = None,
        registration_mode: RegistrationMode = RegistrationMode.FILLED,
        overrides: Mapping[str, str] | None = None,
    ) -> Path:
        if request.requires_resolved_header and organization is None and not (
            recipient_header and recipient_header.strip()
        ):
            raise ValueError("Для выбранного запроса необходимо указать шапку.")
        if recipient_header is not None and not recipient_header.strip():
            raise ValueError("Шапка уникального запроса не может быть пустой.")

        if request.number == 10:
            return self._generate_mvd_package(
                person=person,
                request=request,
                template_dir=template_dir,
                output_dir=output_dir,
                recipient_header=recipient_header,
                registration_mode=registration_mode,
                overrides=overrides,
            )

        return self.generation_service.generate_request(
            person=person,
            request=request,
            organization=organization,
            template_dir=template_dir,
            output_dir=output_dir,
            overrides=overrides,
            recipient_header_override=recipient_header,
            registration_mode=registration_mode,
        )

    def _generate_mvd_package(
        self,
        *,
        person: Person,
        request: RequestTemplate,
        template_dir: Path,
        output_dir: Path,
        recipient_header: str | None,
        registration_mode: RegistrationMode,
        overrides: Mapping[str, str] | None,
    ) -> Path:
        """Join both МВД cover letters and the ИЦ/ГИАЦ form into one DOCX."""

        regional_request = next(
            item for item in REQUEST_CATALOG if item.number == 11
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="nexusdocs_mvd_",
            dir=output_dir,
        ) as temporary:
            temporary_dir = Path(temporary)
            local_path = self.generation_service.generate_request(
                person=person,
                request=request,
                organization=None,
                template_dir=template_dir,
                output_dir=temporary_dir,
                overrides=overrides,
                recipient_header_override=recipient_header,
                registration_mode=registration_mode,
            )
            regional_path = self.generation_service.generate_request(
                person=person,
                request=regional_request,
                organization=None,
                template_dir=template_dir,
                output_dir=temporary_dir,
                overrides=overrides,
                registration_mode=registration_mode,
            )
            destination = output_dir / local_path.name
            self._combine_documents(
                (local_path, regional_path),
                destination,
            )
        return destination

    @staticmethod
    def _combine_documents(source_paths: tuple[Path, ...], output_path: Path) -> None:
        master = Document(source_paths[0])
        composer = Composer(master)
        for source_path in source_paths[1:]:
            source = Document(source_path)
            section = master.add_section(WD_SECTION.NEW_PAGE)
            WordBundleService._copy_section_layout(
                source.sections[0]._sectPr,
                section._sectPr,
            )
            composer.append(source)
            WordBundleService._copy_section_layout(
                source.sections[-1]._sectPr,
                master.sections[-1]._sectPr,
            )
        composer.save(output_path)
        WordBundleService._restore_section_stories(source_paths, output_path)
