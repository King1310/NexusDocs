from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
import zipfile

from lxml import etree


_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PARAGRAPH = f"{{{_WORD_NAMESPACE}}}p"
_TEXT = f"{{{_WORD_NAMESPACE}}}t"
_SEPARATORS = {
    f"{{{_WORD_NAMESPACE}}}br",
    f"{{{_WORD_NAMESPACE}}}cr",
    f"{{{_WORD_NAMESPACE}}}tab",
    f"{{{_WORD_NAMESPACE}}}drawing",
    f"{{{_WORD_NAMESPACE}}}pict",
    f"{{{_WORD_NAMESPACE}}}object",
    f"{{{_WORD_NAMESPACE}}}fldChar",
}
_NONBREAKING_SPACE = "\u00a0"

# Keep only a complete article citation together. Other acronyms stay free to
# wrap normally, so this does not bring back the broad short-word rule.
_ARTICLE = re.compile(
    r"(?<!\w)ч\.\s+\d+(?:\.\d+)?\s+ст\.\s+\d+(?:\.\d+)?(?:\s+УК\s+РФ)?",
    re.IGNORECASE,
)
_ARTICLE_ONLY = re.compile(
    r"(?<!\w)ст\.\s+\d+(?:\.\d+)?(?:\s+УК\s+РФ)?",
    re.IGNORECASE,
)
_MILITARY_UNIT = re.compile(
    r"(?<!\w)в/(?:часть|части|ч)\s+(?:№\s*)?\d[\d./-]*",
    re.IGNORECASE,
)
_LOCALITY = re.compile(r"(?<!\w)пос\.(?P<space> +)(?=\S)", re.IGNORECASE)
_NUMBER_SIGN = re.compile(r"№(?P<space> +)(?=\S)")


def _spaces_to_protect(text: str) -> set[int]:
    """Return offsets of ordinary spaces that Word must not wrap at."""

    positions: set[int] = set()
    for pattern in (_ARTICLE, _ARTICLE_ONLY, _MILITARY_UNIT):
        for match in pattern.finditer(text):
            positions.update(
                index for index in range(match.start(), match.end())
                if text[index] == " "
            )
    # Do not attach prepositions or other short words unconditionally. Even
    # when Word would not wrap at that position, NBSP changes justification
    # and can add lines or pages. Restrict this pass to semantic units only.
    for pattern in (_LOCALITY, _NUMBER_SIGN):
        for match in pattern.finditer(text):
            positions.update(range(match.start("space"), match.end("space")))
    return positions


def _protect_paragraph(paragraph: etree._Element) -> bool:
    """Change spaces in-place, preserving every run's formatting and drawings."""

    changed = False
    nodes: list[etree._Element] = []

    def protect_segment() -> None:
        nonlocal changed
        if not nodes:
            return
        combined = "".join(node.text or "" for node in nodes)
        protected = _spaces_to_protect(combined)
        if protected:
            offset = 0
            for node in nodes:
                value = node.text or ""
                local = [index - offset for index in protected
                         if offset <= index < offset + len(value)]
                if local:
                    characters = list(value)
                    for index in local:
                        characters[index] = _NONBREAKING_SPACE
                    node.text = "".join(characters)
                    changed = True
                offset += len(value)
        nodes.clear()

    for element in paragraph.iter():
        if element is not paragraph:
            owner = next(element.iterancestors(_PARAGRAPH), None)
            if owner is not paragraph:
                continue
        if element.tag == _TEXT:
            nodes.append(element)
        elif element.tag in _SEPARATORS:
            protect_segment()
    protect_segment()
    return changed


def _is_document_story(filename: str) -> bool:
    if filename == "word/document.xml":
        return True
    return bool(re.fullmatch(
        r"word/(?:header\d+|footer\d+|footnotes|endnotes)\.xml",
        filename,
    ))


def protect_word_line_breaks(document_path: Path) -> None:
    """Apply nonbreaking spaces to final DOCX stories without flattening runs.

    This is deliberately idempotent. It runs after placeholder substitution so
    dynamic article numbers and military-unit numbers receive the same rules as
    text authored directly in a template.
    """

    descriptor, temporary_name = tempfile.mkstemp(
        suffix=".docx", dir=document_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(document_path, "r") as source, zipfile.ZipFile(
            temporary_path, "w",
        ) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if _is_document_story(item.filename):
                    root = etree.fromstring(data)
                    changed = False
                    for paragraph in root.iter(_PARAGRAPH):
                        changed = _protect_paragraph(paragraph) or changed
                    if changed:
                        data = etree.tostring(
                            root, xml_declaration=True, encoding="UTF-8",
                            standalone=True,
                        )
                target.writestr(item, data)
        os.replace(temporary_path, document_path)
    finally:
        temporary_path.unlink(missing_ok=True)
