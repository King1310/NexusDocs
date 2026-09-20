"""Generate review-only bundles for all three executors, without changing the DB."""
from dataclasses import replace
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from domain.entities.organization import Organization
from domain.enums.organization_type import OrganizationType
from domain.value_objects.investigator import INVESTIGATORS
from services.generation_service import GenerationService
from services.extension_generation_service import ExtensionGenerationService
from services.document_signature_service import DocumentSignatureService
from services.word_bundle_service import WordBundleService
from tests.factories.person_factory import PersonFactory


def main():
    output = ROOT.parent / "tmp/executor_feature/qa"
    headers = (
        "Военному комиссару\nВоенного комиссариата\nгорода Балашиха",
        "Военному коменданту\nВоенной комендатуры\nМосковского гарнизона",
        "Главному врачу\nГБУЗ Московской области\n«Балашихинская больница»\nНаркологическое отделение",
        "Главному врачу\nГБУЗ Московской области\n«Балашихинская больница»\nПсихиатрическое отделение",
        "Главному врачу\nГБУЗ Московской области\n«Балашихинская больница»",
        "Директору\nТерриториального фонда\nобязательного медицинского страхования\nМосковской области",
        "Главе\nгородского округа Балашиха Московской области",
        "Начальнику\nПункта отбора\nна военную службу по контракту\nМосковской области",
        "Председателю\nТерриториальной избирательной комиссии\nгорода Балашиха",
    )
    organizations = [Organization(
        i, kind, header, "143900, Московская область,\nг. Балашиха, ул. Советская, д. 1",
        ("+7 (495) 000-00-00",), "" if kind in {
            OrganizationType.MILITARY_COMMISSARIAT,
            OrganizationType.MILITARY_COMMANDANT,
            OrganizationType.CONTRACT_SERVICE_POINT,
        } else "qa@example.invalid",
    ) for i, (kind, header) in enumerate(zip(OrganizationType, headers), 1)]
    for profile in INVESTIGATORS:
        person = replace(PersonFactory.create(), investigator=profile)
        person.soch_case = replace(person.soch_case, article="ч. 5 ст. 337 УК РФ")
        person.document_info = replace(person.document_info, outgoing_date=date(2026, 9, 7))
        directory = output / profile.key
        directory.mkdir(parents=True, exist_ok=True)
        paths = GenerationService().generate_bundle(person, organizations, ROOT / "templates/requests", directory / "individual")
        assembled = directory / "assembled.docx"
        WordBundleService().create_editable_bundle(paths, assembled)
        signatures = DocumentSignatureService()
        signatures.create_unsigned_copy(assembled, directory / "unsigned.docx")
        count = signatures.create_signed_copy(assembled, directory / "signed.docx", profile)
        assert count == 18, (profile.key, count)
        ExtensionGenerationService().generate(person, ROOT / "templates/extensions/extension_to_10_days.docx", directory)
        print(profile.key, "signatures:", count, flush=True)


if __name__ == "__main__":
    main()
