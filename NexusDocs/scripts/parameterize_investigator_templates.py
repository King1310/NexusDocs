"""Replace executor slots while preserving every other DOCX package part."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import shutil

ROOT = Path(__file__).resolve().parents[1]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def replace(nodes, old, new):
    text = "".join(n.text or "" for n in nodes)
    start = text.find(old)
    if start < 0:
        return
    stop = start + len(old)
    offset = 0
    inserted = False
    for node in nodes:
        value = node.text or ""
        end = offset + len(value)
        if offset < stop and end > start:
            left, right = max(0, start - offset), min(len(value), stop - offset)
            node.text = value[:left] + (new if not inserted else "") + value[right:]
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            inserted = True
        offset = end


def patch(path):
    with ZipFile(path) as source:
        parts = {item.filename: source.read(item.filename) for item in source.infolist()}
        infos = source.infolist()
    root = etree.fromstring(parts["word/document.xml"])
    form = False
    for paragraph in root.iter(W + "p"):
        nodes = [n for n in paragraph.iter(W + "t")
                 if next(n.iterancestors(W + "p"), None) is paragraph]
        text = "".join(n.text or "" for n in nodes)
        if path.name.startswith("11_") and text.strip() == "Следователь отдела":
            form = True
        mapping = {
            "Следователь военного следственного отдела": "POSITION_LONG",
            "Следователь отдела": "POSITION_FORM",
            "С.А. Цомартов": "INITIALS_SURNAME",
            "Цомартов С.А.": "SURNAME_INITIALS",
            "лейтенант юстиции": "FORM_RANK" if form else "RANK",
        }
        if text.strip() == "Следователь":
            mapping["Следователь"] = (
                "POSITION_TABLE" if path.name.startswith("09_")
                and list(paragraph.iterancestors(W + "tc")) else "POSITION_SHORT"
            )
        if path.name.startswith("09_") and text.strip() == "Цомартов С.А.":
            mapping["Цомартов С.А."] = "TABLE_NAME"
        if form:
            mapping["(заместитель, следователь)"] = "FORM_ROLE_HINT"
            mapping["(в звании)"] = "FORM_RANK_LABEL"
        for old, slot in mapping.items():
            replace(nodes, old, "{{INVESTIGATOR_" + slot + "}}")
    updated = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if updated == parts["word/document.xml"]:
        return
    backup = ROOT.parent / "tmp" / "executor_feature" / "original_templates" / path.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    with ZipFile(path, "w") as output:
        for info in infos:
            output.writestr(info, updated if info.filename == "word/document.xml" else parts[info.filename])
    with ZipFile(path) as output:
        assert all(output.read(name) == content for name, content in parts.items()
                   if name != "word/document.xml")
    print(path.name)


if __name__ == "__main__":
    for file in sorted((ROOT / "templates" / "requests").glob("*.docx")):
        patch(file)
    patch(ROOT / "templates" / "extensions" / "extension_to_10_days.docx")
