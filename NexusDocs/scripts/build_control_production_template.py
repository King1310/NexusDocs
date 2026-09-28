"""Prepare the KP template without rebuilding the user's Word package."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
from zipfile import ZipFile

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"w": W[1:-1]}


def prepare(source: Path, destination: Path) -> None:
    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
        count = 0
        for paragraph in root.findall(".//" + W + "p"):
            children = list(paragraph)
            index = 0
            while index < len(children):
                begin = children[index].find(W + "fldChar")
                if begin is None or begin.get(W + "fldCharType") != "begin":
                    index += 1
                    continue
                end = index + 1
                while end < len(children):
                    marker = children[end].find(W + "fldChar")
                    if marker is not None and marker.get(W + "fldCharType") == "end":
                        break
                    end += 1
                if end == len(children):
                    raise ValueError("Незавершённое поле Word.")
                runs = children[index:end + 1]
                instruction = "".join(node.text or "" for run in runs
                                      for node in run.findall(W + "instrText"))
                match = re.search(r'MERGEFIELD\s+"?([^"\s\\]+)', instruction)
                if not match:
                    raise ValueError(f"Неизвестное поле: {instruction}")
                result = next((run for run in runs if run.find(W + "t") is not None), runs[0])
                replacement = etree.Element(W + "r")
                properties = result.find(W + "rPr")
                if properties is not None:
                    replacement.append(deepcopy(properties))
                text = etree.SubElement(replacement, W + "t")
                text.text = "{{" + match.group(1) + "}}"
                paragraph.insert(paragraph.index(runs[0]), replacement)
                for run in runs:
                    paragraph.remove(run)
                count += 1
                index = end + 1
        if count != 171 or root.findall(".//" + W + "fldSimple"):
            raise ValueError(f"Изменился исходный набор полей ({count}/171).")

        pk = root.xpath(".//w:p[w:r/w:t[contains(., '{{ПК}}')]]", namespaces=NS)
        if len(pk) != 1:
            raise ValueError("Не найдена единственная строка ПК.")
        for node in list(pk[0]):
            if node.tag != W + "pPr":
                pk[0].remove(node)

        candidates = []
        for row in root.findall(".//" + W + "tr"):
            text = "".join(row.xpath(".//w:t/text()", namespaces=NS))
            if re.search(r"Представить\s+уголовное\s+дело\s+на\s+изучение", text):
                candidates.append(row)
        if len(candidates) != 1:
            raise ValueError("Строка обмена сроков не найдена однозначно.")
        swapped = 0
        for text in candidates[0].findall(".//" + W + "t"):
            if text.text == "{{ДатаВудКПМес}}":
                text.text = "{{ДатаВуд20}}"
                swapped += 1
            elif text.text == "{{ДатаВуд20}}":
                text.text = "{{ДатаВудКПМес}}"
                swapped += 1
        if swapped != 2:
            raise ValueError("Строка обмена сроков изменилась.")
        replacements = {"word/document.xml": etree.tostring(root, xml_declaration=True,
                        encoding="UTF-8", standalone=True)}
        settings = etree.fromstring(package.read("word/settings.xml"))
        for tag in ("mailMerge", "updateFields"):
            for node in settings.findall(W + tag):
                settings.remove(node)
        replacements["word/settings.xml"] = etree.tostring(settings, xml_declaration=True,
                                                            encoding="UTF-8", standalone=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, "w") as output:
            for item in package.infolist():
                output.writestr(item, replacements.get(item.filename, package.read(item.filename)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.destination)
