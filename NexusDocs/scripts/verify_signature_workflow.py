"""Build a review fixture and exercise the real Word export without sending mail."""

import argparse
from pathlib import Path
import sys
from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.repositories.person_repository import PersonRepository
from database.repositories.territory_repository import TerritoryRepository
from services.document_signature_service import DocumentSignatureService
from services.generation_service import GenerationService
from services.territory_service import TerritoryService
from services.word_bundle_service import WordBundleService
from services.word_dispatch_service import ReviewedWordConverter, WordDispatchService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--person", type=int, default=36)
    parser.add_argument("--export", action="store_true", help="Test real Word conversion and splitting without Outlook")
    args = parser.parse_args()
    person = PersonRepository().get_by_id(args.person)
    if person is None:
        raise ValueError("Не найден выбранный человек.")
    resolution = TerritoryService(TerritoryRepository()).resolve_headers(
        person.registration_address
    )
    paths = GenerationService().generate_bundle(
        person, resolution.organizations, Path("templates/requests"),
        args.output / "individual",
    )
    signed = args.output / WordBundleService.bundle_filename(person)
    assembled = args.output / "assembled.docx"
    WordBundleService().create_editable_bundle(paths, assembled)
    count = DocumentSignatureService().create_signed_copy(assembled, signed, person.investigator)
    print(f"Created one signed Word file; signatures: {count}", flush=True)
    print(signed.resolve(), flush=True)
    if args.export:
        work = args.output / ("export_" + signed.stem)
        work.mkdir(exist_ok=True)
        exported = ReviewedWordConverter().convert(signed, work)
        # Simulate a saved manual correction in the generated document.
        reviewed = args.output / "reviewed.docx"
        document = Document(signed)
        changed = 0
        for node in document.element.body.iter(qn("w:t")):
            if "oktbol@amurzdrav.ru" in (node.text or ""):
                node.text = node.text.replace("oktbol@amurzdrav.ru", "review-test@example.invalid")
                changed += 1
        assert changed, "QA fixture has no expected editable header"
        document.save(reviewed)
        saved_bytes = reviewed.read_bytes()
        package = WordDispatchService().prepare(
            person=person, docx_path=reviewed, output_directory=args.output / "package",
        )
        assert reviewed.read_bytes() == saved_bytes, "Conversion modified user's saved file"
        assert len(package.attachments) == 15
        assert sum(item.page_count for item in package.attachments) == len(PdfReader(exported.pdf_path).pages)
        for number in (5, 6, 7):
            attachment = next(item for item in package.attachments if item.container_number == number)
            assert attachment.recipient_email == "review-test@example.invalid", number
            pdf_text = "".join(page.extract_text() for page in PdfReader(attachment.path).pages)
            assert "review-test@example.invalid" in pdf_text, number
        assert all(item.recipient_email != "vso-2402@vso.rsnet.ru" for item in package.attachments)
        print("Verified: one reviewed Word, 15 PDFs, saved edits and recipient-only emails; no Outlook", flush=True)


if __name__ == "__main__":
    main()
