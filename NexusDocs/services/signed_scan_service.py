from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from pypdf import PdfReader, PdfWriter

from domain.entities.person import Person
from utils.declension import decline_full_name


@dataclass(frozen=True, slots=True)
class DispatchRule:
    container_number: int
    abbreviation: str


@dataclass(frozen=True, slots=True)
class PreparedAttachment:
    container_number: int
    abbreviation: str
    path: Path
    recipient_email: str
    subject: str
    page_count: int
    outgoing_number: str = ""
    duplicate_index: int = 0

    @property
    def display_outgoing_number(self) -> str:
        number = self.outgoing_number.strip()
        if not number:
            number = f".{self.container_number}"
        if self.duplicate_index:
            number += f".{self.duplicate_index}"
        return number


@dataclass(frozen=True, slots=True)
class RecognizedScanRequest:
    container_number: int
    first_page_index: int
    page_count: int
    recipient_email: str
    outgoing_number: str = ""
    outgoing_date: date | None = None
    duplicate_index: int = 0


@dataclass(frozen=True, slots=True)
class ScanPreparationResult:
    output_directory: Path
    manifest_path: Path
    attachments: tuple[PreparedAttachment, ...]

    @property
    def missing_email_attachments(self) -> tuple[PreparedAttachment, ...]:
        return tuple(
            attachment
            for attachment in self.attachments
            if not attachment.recipient_email
        )


DISPATCH_RULES = (
    DispatchRule(3, "комиссариат"),
    DispatchRule(4, "комендатура"),
    DispatchRule(5, "нарк"),
    DispatchRule(6, "псих"),
    DispatchRule(7, "црб"),
    DispatchRule(8, "тфомс"),
    DispatchRule(12, "администрация"),
    DispatchRule(13, "повск"),
    DispatchRule(14, "фку"),
    DispatchRule(15, "тик"),
)
DISPATCH_ABBREVIATIONS = {
    rule.container_number: rule.abbreviation for rule in DISPATCH_RULES
}


class DispatchPackageStore:
    """Write and read a portable package for the Outlook stage."""

    MANIFEST_FILENAME = "пакет_отправки.nexusdocs.json"
    LAUNCHER_FILENAME = "Создать черновики Outlook.cmd"
    POWERSHELL_FILENAME = "create_outlook_drafts.ps1"
    PACKAGE_FORMAT = "nexusdocs.dispatch"
    PACKAGE_VERSION = 1

    def write(
        self,
        output_directory: Path,
        attachments: tuple[PreparedAttachment, ...],
    ) -> Path:
        manifest_path = output_directory / self.MANIFEST_FILENAME
        payload = {
            "format": self.PACKAGE_FORMAT,
            "version": self.PACKAGE_VERSION,
            "created_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "attachments": [
                {
                    "container_number": attachment.container_number,
                    "abbreviation": attachment.abbreviation,
                    "outgoing_number": attachment.outgoing_number,
                    "duplicate_index": attachment.duplicate_index,
                    "filename": attachment.path.name,
                    "recipient_email": attachment.recipient_email,
                    "subject": attachment.subject,
                    "page_count": attachment.page_count,
                    "sha256": self._sha256(attachment.path),
                }
                for attachment in attachments
            ],
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_portable_outlook_launcher(output_directory)
        return manifest_path

    def load(self, manifest_path: Path) -> ScanPreparationResult:
        manifest_path = manifest_path.resolve()
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"Не найден пакет отправки NexusDocs:\n{manifest_path}"
            )

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Файл пакета отправки повреждён.") from error

        if (
            payload.get("format") != self.PACKAGE_FORMAT
            or payload.get("version") != self.PACKAGE_VERSION
        ):
            raise ValueError("Это не поддерживаемый пакет отправки NexusDocs.")

        records = payload.get("attachments")
        if (
            not isinstance(records, list)
            or not records
            or len(records) > 200
        ):
            raise ValueError(
                "В пакете должен быть хотя бы один запрос (не более 200)."
            )

        root = manifest_path.parent.resolve()
        attachments: list[PreparedAttachment] = []
        seen_filenames: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("В пакете обнаружена некорректная запись.")

            container_number = record.get("container_number")
            abbreviation = record.get("abbreviation")
            if (
                not isinstance(container_number, int)
                or isinstance(container_number, bool)
                or container_number < 0
                or container_number > 999
            ):
                raise ValueError("В пакете указан некорректный номер запроса.")
            expected_abbreviation = (
                DISPATCH_ABBREVIATIONS.get(container_number, "")
                if container_number
                else ""
            )
            if abbreviation != expected_abbreviation:
                raise ValueError(
                    "Аббревиатура запроса в пакете не соответствует его "
                    f"исходящему номеру .{container_number}."
                )

            outgoing_number = record.get("outgoing_number", "")
            duplicate_index = record.get("duplicate_index", 0)
            if not isinstance(outgoing_number, str):
                raise ValueError("В пакете указан некорректный исходящий номер.")
            outgoing_number = outgoing_number.strip()
            if outgoing_number and not re.fullmatch(
                r"\d{3,}(?:\.\d{1,3})?",
                outgoing_number,
            ):
                raise ValueError("В пакете указан некорректный исходящий номер.")
            if (
                not isinstance(duplicate_index, int)
                or isinstance(duplicate_index, bool)
                or duplicate_index < 0
                or duplicate_index > 199
            ):
                raise ValueError("В пакете указан некорректный номер повтора.")

            filename = record.get("filename")
            if (
                not isinstance(filename, str)
                or not filename
                or Path(filename).name != filename
                or Path(filename).suffix.casefold() != ".pdf"
            ):
                raise ValueError("В пакете указано некорректное имя PDF.")
            if filename.casefold() in seen_filenames:
                raise ValueError(f"Имя PDF повторяется в пакете: {filename}")
            seen_filenames.add(filename.casefold())
            attachment_path = (root / filename).resolve()
            if attachment_path.parent != root or not attachment_path.is_file():
                raise FileNotFoundError(
                    f"В папке пакета отсутствует файл:\n{filename}"
                )

            page_count = record.get("page_count")
            subject = record.get("subject")
            recipient_email = record.get("recipient_email")
            checksum = record.get("sha256")
            if not isinstance(page_count, int) or page_count < 1:
                raise ValueError(f"Некорректно число страниц файла {filename}.")
            if not isinstance(subject, str) or not subject.strip():
                raise ValueError(f"Не указана тема письма для файла {filename}.")
            if not isinstance(recipient_email, str):
                raise ValueError(f"Некорректно указана почта для файла {filename}.")
            if not isinstance(checksum, str) or checksum != self._sha256(
                attachment_path
            ):
                raise ValueError(
                    f"Файл {filename} изменён или повреждён после разбиения."
                )
            if len(PdfReader(attachment_path).pages) != page_count:
                raise ValueError(
                    f"Число страниц файла {filename} не совпадает с пакетом."
                )

            attachments.append(
                PreparedAttachment(
                    container_number=container_number,
                    abbreviation=expected_abbreviation,
                    path=attachment_path,
                    recipient_email=recipient_email.strip(),
                    subject=subject.strip(),
                    page_count=page_count,
                    outgoing_number=outgoing_number,
                    duplicate_index=duplicate_index,
                )
            )

        return ScanPreparationResult(
            output_directory=root,
            manifest_path=manifest_path,
            attachments=tuple(attachments),
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_portable_outlook_launcher(self, output_directory: Path) -> None:
        launcher_path = output_directory / self.LAUNCHER_FILENAME
        launcher_path.write_text(
            "\r\n".join(
                (
                    "@echo off",
                    "setlocal",
                    "set \"POWERSHELL_EXE=%SystemRoot%\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe\"",
                    "if not exist \"%POWERSHELL_EXE%\" set \"POWERSHELL_EXE=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\"",
                    f'"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0{self.POWERSHELL_FILENAME}"',
                    "if errorlevel 1 pause",
                    "endlocal",
                    "",
                )
            ),
            encoding="ascii",
        )

        powershell_path = output_directory / self.POWERSHELL_FILENAME
        powershell_path.write_text(
            self._powershell_launcher_source(),
            encoding="utf-8-sig",
        )

    def _powershell_launcher_source(self) -> str:
        return f'''$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

function Show-NexusDocsError([string]$Message) {{
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "NexusDocs - ошибка",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}}

try {{
    $packageRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
    $manifestPath = Join-Path $packageRoot "{self.MANIFEST_FILENAME}"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {{
        throw "В папке не найден файл {self.MANIFEST_FILENAME}."
    }}

    $package = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 |
        ConvertFrom-Json
    if ($package.format -ne "{self.PACKAGE_FORMAT}" -or
        $package.version -ne {self.PACKAGE_VERSION}) {{
        throw "Файл пакета отправки имеет неподдерживаемый формат."
    }}

    $attachments = @($package.attachments)
    if ($attachments.Count -lt 1 -or $attachments.Count -gt 200) {{
        throw "В пакете должен быть хотя бы один запрос (не более 200)."
    }}

    $validated = @()
    $packagePrefix = $packageRoot.TrimEnd("\\") + "\\"
    foreach ($item in $attachments) {{
        $filename = [string]$item.filename
        if ([string]::IsNullOrWhiteSpace($filename) -or
            [System.IO.Path]::GetFileName($filename) -ne $filename -or
            [System.IO.Path]::GetExtension($filename).ToLowerInvariant() -ne ".pdf") {{
            throw "В пакете указано некорректное имя PDF."
        }}

        $attachmentPath = [System.IO.Path]::GetFullPath(
            (Join-Path $packageRoot $filename)
        )
        if (-not $attachmentPath.StartsWith(
            $packagePrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {{
            throw "PDF находится за пределами папки пакета: $filename"
        }}
        if (-not (Test-Path -LiteralPath $attachmentPath -PathType Leaf)) {{
            throw "В папке отсутствует файл: $filename"
        }}

        $actualHash = (Get-FileHash -LiteralPath $attachmentPath -Algorithm SHA256).Hash
        if ($actualHash.ToLowerInvariant() -ne ([string]$item.sha256).ToLowerInvariant()) {{
            throw "Файл изменён или повреждён после разбиения: $filename"
        }}
        $validated += [PSCustomObject]@{{
            Item = $item
            Path = $attachmentPath
        }}
    }}

    $outlook = New-Object -ComObject Outlook.Application
    $created = 0
    $skipped = @()
    foreach ($entry in $validated) {{
        $email = ([string]$entry.Item.recipient_email).Trim()
        if ([string]::IsNullOrWhiteSpace($email)) {{
            $numberLabel = ([string]$entry.Item.outgoing_number).Trim()
            $duplicateIndex = [int]$entry.Item.duplicate_index
            if (-not [string]::IsNullOrWhiteSpace($numberLabel) -and
                $duplicateIndex -gt 0) {{
                $numberLabel += "." + [string]$duplicateIndex
            }}
            $label = ([string]$entry.Item.abbreviation).Trim()
            if (-not [string]::IsNullOrWhiteSpace($label) -and
                -not [string]::IsNullOrWhiteSpace($numberLabel)) {{
                $label += " (" + $numberLabel + ")"
            }}
            elseif ([string]::IsNullOrWhiteSpace($label)) {{
                $label = $numberLabel
            }}
            if ([string]::IsNullOrWhiteSpace($label)) {{
                $label = "." + [string]$entry.Item.container_number
            }}
            $skipped += $label
            continue
        }}

        $mail = $outlook.CreateItem(0)
        $mail.To = $email
        $mail.Subject = ([string]$entry.Item.subject).Trim()
        $displayName = [System.IO.Path]::GetFileName($entry.Path)
        $mail.Attachments.Add(
            $entry.Path,
            1,
            1,
            $displayName
        ) | Out-Null
        $mail.Save()
        $created++
    }}

    $namespace = $outlook.GetNamespace("MAPI")
    $drafts = $namespace.GetDefaultFolder(16)
    $explorer = $outlook.Explorers.Add($drafts, 0)
    $explorer.Display()

    $message = "Создано черновиков Outlook: $created.`nПисьма не отправлялись."
    if ($skipped.Count -gt 0) {{
        $message += "`n`nБез электронной почты: " + ($skipped -join ", ")
    }}
    [System.Windows.Forms.MessageBox]::Show(
        $message,
        "NexusDocs - черновики готовы",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}}
catch {{
    Show-NexusDocsError $_.Exception.Message
    exit 1
}}
'''


class WordBundlePageMap:
    """Read request page counts from the bookmarks in the final Word bundle."""

    BOOKMARK_PREFIX = "NEXUSDOCS_REQUEST_"
    WORD_PAGE_NUMBER = 3
    WORD_PDF_FORMAT = 17

    def request_page_counts(self, bundle_path: Path) -> dict[int, int]:
        if not bundle_path.is_file():
            raise FileNotFoundError(f"Не найден общий Word-файл:\n{bundle_path}")

        try:
            import pythoncom
            import win32com.client
        except ImportError as error:
            raise RuntimeError(
                "Для определения страниц нужен установленный Microsoft Word."
            ) from error

        with tempfile.TemporaryDirectory(prefix="nexusdocs_page_map_") as temp_dir:
            pagination_pdf = Path(temp_dir) / "pagination.pdf"
            pythoncom.CoInitialize()
            application = None
            document = None
            try:
                application = win32com.client.DispatchEx("Word.Application")
                application.Visible = False
                application.DisplayAlerts = 0
                document = application.Documents.Open(
                    str(bundle_path.resolve()),
                    ConfirmConversions=False,
                    ReadOnly=True,
                    AddToRecentFiles=False,
                    Visible=False,
                )
                document.Repaginate()
                document.ExportAsFixedFormat(
                    str(pagination_pdf),
                    self.WORD_PDF_FORMAT,
                )
                with pagination_pdf.open("rb") as stream:
                    total_pages = len(PdfReader(stream).pages)
                starts = {
                    request_number: int(
                        document.Bookmarks(
                            f"{self.BOOKMARK_PREFIX}{request_number:02d}"
                        ).Range.Information(self.WORD_PAGE_NUMBER)
                    )
                    for request_number in range(1, 16)
                }
            except Exception as error:
                raise RuntimeError(
                    "Не удалось определить границы запросов в Word. "
                    "Сохраните общий Word-файл и попробуйте снова."
                ) from error
            finally:
                if document is not None:
                    document.Close(False)
                if application is not None:
                    application.Quit()
                document = None
                application = None
                gc.collect()
                pythoncom.CoUninitialize()

        return self._page_counts_from_starts(starts, total_pages)

    @staticmethod
    def _page_counts_from_starts(
        starts: dict[int, int],
        total_pages: int,
    ) -> dict[int, int]:
        expected = set(range(1, 16))
        if set(starts) != expected:
            missing = ", ".join(str(number) for number in sorted(expected - set(starts)))
            raise ValueError(f"В Word отсутствуют закладки контейнеров: {missing}")
        if total_pages < 15:
            raise ValueError("В общем Word обнаружено слишком мало страниц.")

        counts: dict[int, int] = {}
        for request_number in range(1, 16):
            start = starts[request_number]
            end = (
                starts[request_number + 1] - 1
                if request_number < 15
                else total_pages
            )
            if start < 1 or end < start:
                raise ValueError(
                    "Закладки контейнеров в Word расположены некорректно."
                )
            counts[request_number] = end - start + 1
        return counts


class WordBundleHeaderEmails:
    """Extract only e-mail values explicitly printed in request headers."""

    BOOKMARK_PREFIX = "NEXUSDOCS_REQUEST_"
    EMAIL_PATTERN = re.compile(
        r"(?:эл(?:ектронная)?\.?\s*почта|e-?mail)\s*:\s*"
        r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-ZА-Я]{2,})",
        re.IGNORECASE,
    )

    def emails_by_request(self, bundle_path: Path) -> dict[int, str]:
        if not bundle_path.is_file():
            raise FileNotFoundError(f"Не найден общий Word-файл:\n{bundle_path}")

        with ZipFile(bundle_path) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))

        body = root.find(qn("w:body"))
        if body is None:
            raise ValueError("В общем Word не найдено содержимое документа.")

        section_text: dict[int, list[str]] = {}
        request_sections: dict[int, int] = {}
        section_index = 0
        for child in body:
            bookmark_names = [
                node.get(qn("w:name"), "")
                for node in child.iter(qn("w:bookmarkStart"))
            ]
            request_bookmarks = [
                name
                for name in bookmark_names
                if name.startswith(self.BOOKMARK_PREFIX)
            ]
            if request_bookmarks:
                request_number = int(request_bookmarks[0][-2:])
                request_sections[request_number] = section_index
            text = "".join(
                node.text or "" for node in child.iter(qn("w:t"))
            )
            if text.strip():
                section_text.setdefault(section_index, []).append(text)
            if child.find(f".//{qn('w:sectPr')}") is not None:
                section_index += 1

        request_text: dict[int, list[str]] = {}
        ordered_requests = sorted(
            request_sections,
            key=request_sections.__getitem__,
        )
        for position, request_number in enumerate(ordered_requests):
            first_section = request_sections[request_number]
            last_section = (
                request_sections[ordered_requests[position + 1]]
                if position + 1 < len(ordered_requests)
                else section_index + 1
            )
            request_text[request_number] = [
                block
                for index in range(first_section, last_section)
                for block in section_text.get(index, ())
            ]

        document = Document(bundle_path)
        header_text: dict[int, str] = {}
        for request_number, index in request_sections.items():
            if index >= len(document.sections):
                continue
            section = document.sections[index]
            stories = (
                section.header,
                section.first_page_header,
                section.even_page_header,
            )
            header_text[request_number] = "\n".join(
                "".join(
                    node.text or ""
                    for node in story._element.iter(qn("w:t"))
                )
                for story in stories
            )

        result: dict[int, str] = {}
        for request_number, blocks in request_text.items():
            searchable = "\n".join(
                (header_text.get(request_number, ""), *blocks)
            )
            match = self.EMAIL_PATTERN.search(searchable)
            result[request_number] = match.group(1) if match else ""
        return result


class WindowsPdfOcrTextExtractor:
    """Recognize every PDF page with the OCR engine built into Windows."""

    POWERSHELL_SCRIPT = r'''
param(
    [Parameter(Mandatory = $true)]
    [string]$PdfPath,
    [string]$LanguageTag = "ru"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $OutputEncoding
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq "AsTask" -and
        $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1 -and
        $_.ToString().Contains('(Windows.Foundation.IAsyncOperation`1')
    } |
    Select-Object -First 1
$asTaskAction = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq "AsTask" -and
        -not $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1 -and
        $_.ToString().Contains("(Windows.Foundation.IAsyncAction)")
    } |
    Select-Object -First 1

function Wait-WinRtOperation($Operation, [Type]$ResultType) {
    $task = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke(
        $null,
        @($Operation)
    )
    $task.Wait()
    return $task.Result
}

function Wait-WinRtAction($Action) {
    $task = $asTaskAction.Invoke($null, @($Action))
    $task.Wait()
}

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType = WindowsRuntime]

$resolvedPath = [System.IO.Path]::GetFullPath($PdfPath)
$file = Wait-WinRtOperation (
    [Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPath)
) ([Windows.Storage.StorageFile])
$document = Wait-WinRtOperation (
    [Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)
) ([Windows.Data.Pdf.PdfDocument])
$language = New-Object Windows.Globalization.Language($LanguageTag)
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) {
    throw "OCR language is not installed: $LanguageTag"
}

$pages = @()
for ($index = 0; $index -lt $document.PageCount; $index++) {
    $page = $document.GetPage($index)
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    try {
        $longestSide = [Math]::Max(
            [double]$page.Dimensions.Width,
            [double]$page.Dimensions.Height
        )
        $scale = [Math]::Min(
            3.0,
            ([double][Windows.Media.Ocr.OcrEngine]::MaxImageDimension - 4.0) /
                $longestSide
        )
        $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
        $options.DestinationWidth = [uint32][Math]::Round(
            [double]$page.Dimensions.Width * $scale
        )
        $options.DestinationHeight = [uint32][Math]::Round(
            [double]$page.Dimensions.Height * $scale
        )
        Wait-WinRtAction ($page.RenderToStreamAsync($stream, $options))
        $stream.Seek(0)
        $decoder = Wait-WinRtOperation (
            [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
        ) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Wait-WinRtOperation (
            $decoder.GetSoftwareBitmapAsync()
        ) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result = Wait-WinRtOperation (
                $engine.RecognizeAsync($bitmap)
            ) ([Windows.Media.Ocr.OcrResult])
            $pages += [pscustomobject]@{
                page = $index + 1
                text = $result.Text
            }
        }
        finally {
            if ($null -ne $bitmap) { $bitmap.Dispose() }
        }
    }
    finally {
        $stream.Dispose()
        $page.Dispose()
    }
}

@($pages) | ConvertTo-Json -Depth 3 -Compress
'''

    def page_texts(self, pdf_path: Path) -> tuple[str, ...]:
        powershell = self._powershell_path()
        with tempfile.TemporaryDirectory(prefix="nexusdocs_ocr_") as temp_dir:
            script_path = Path(temp_dir) / "read_pdf.ps1"
            script_path.write_text(
                self.POWERSHELL_SCRIPT,
                encoding="utf-8-sig",
            )
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            completed = subprocess.run(
                (
                    str(powershell),
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-PdfPath",
                    str(pdf_path.resolve()),
                ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                creationflags=creation_flags,
                check=False,
            )

        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as error:
            details = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                "Windows не смог распознать текст подписанного PDF. "
                "Проверьте, что в Windows установлен русский язык "
                "распознавания текста."
                + (f"\n\n{details}" if details else "")
            ) from error

        records = payload if isinstance(payload, list) else [payload]
        expected_pages = len(PdfReader(pdf_path).pages)
        texts = [""] * expected_pages
        for record in records:
            if not isinstance(record, dict):
                raise RuntimeError("Некорректный результат распознавания PDF.")
            page_number = record.get("page")
            text = record.get("text")
            if (
                not isinstance(page_number, int)
                or not 1 <= page_number <= expected_pages
                or not isinstance(text, str)
            ):
                raise RuntimeError("Некорректный результат распознавания PDF.")
            texts[page_number - 1] = text
        if any(not text.strip() for text in texts):
            empty_pages = ", ".join(
                str(index + 1)
                for index, text in enumerate(texts)
                if not text.strip()
            )
            raise ValueError(
                "Не удалось прочитать текст на страницах: "
                f"{empty_pages}. Проверьте качество скана."
            )
        return tuple(texts)

    @staticmethod
    def _powershell_path() -> Path:
        windows_directory = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        candidates = (
            windows_directory
            / "Sysnative"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe",
            windows_directory
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise RuntimeError(
            "Не найден системный компонент Windows PowerShell для OCR."
        )


@dataclass(frozen=True, slots=True)
class _PageOutgoingMarker:
    outgoing_number: str
    container_number: int
    outgoing_date: date | None
    is_header_marker: bool


class ScanRequestRecognizer:
    """Find request boundaries from outgoing numbers, regardless of order."""

    EMAIL_PATTERN = re.compile(
        r"(?:эл(?:ектронная)?\.?\s*почта|e-?mail)\s*:\s*"
        r"([A-Z0-9._%+\-]+(?:\s+[A-Z0-9._%+\-]+)?)\s*@\s*"
        r"([A-Z0-9.\-]+)\s*\.\s*([A-ZА-Я]{2,})",
        re.IGNORECASE,
    )
    HEADER_SCAN_LIMIT = 360
    HEADER_DATE_PATTERN = re.compile(
        r"(?<!\d)(\d{1,2})\s*[./,]\s*(\d{1,2})\s*[./,]\s*"
        r"(20\d{2})(?!\d)"
    )
    FIRST_PAGE_PHRASES = (
        "в производстве военного следственного отдела",
        "в военном следственном отделе",
        "в целях осуществления предварительного следствия",
        "в целях осуществления доследственной проверки",
    )

    def __init__(self, ocr_extractor=None) -> None:
        self.ocr_extractor = ocr_extractor or WindowsPdfOcrTextExtractor()

    def recognize(
        self,
        scan_path: Path,
        outgoing_number: str,
    ) -> tuple[RecognizedScanRequest, ...]:
        reader = PdfReader(scan_path)
        native_texts = tuple(page.extract_text() or "" for page in reader.pages)
        if native_texts and all(text.strip() for text in native_texts):
            page_texts = native_texts
        else:
            ocr_texts = self.ocr_extractor.page_texts(scan_path)
            page_texts = tuple(
                "\n".join(part for part in pair if part.strip())
                for pair in zip(native_texts, ocr_texts, strict=True)
            )
        return self.requests_from_page_texts(page_texts, outgoing_number)

    @classmethod
    def requests_from_page_texts(
        cls,
        page_texts: tuple[str, ...],
        outgoing_number: str,
    ) -> tuple[RecognizedScanRequest, ...]:
        if not page_texts:
            raise ValueError("В подписанном PDF нет страниц.")

        base_number = cls._base_number(outgoing_number)
        selected_number_pattern = re.compile(
            rf"(?<!\d){re.escape(base_number)}\s*[./,\\]\s*"
            r"(\d{1,3})(?!\d)"
        )
        starts: list[tuple[int, _PageOutgoingMarker, int]] = []
        active_outgoing_number: str | None = None
        occurrence_counts: dict[str, int] = {}
        for page_index, text in enumerate(page_texts):
            number_text = text.translate(
                str.maketrans({"О": "0", "O": "0", "о": "0", "o": "0"})
            )
            marker = cls._page_outgoing_marker(
                number_text,
                base_number,
                selected_number_pattern,
            )
            if marker is None:
                continue

            is_new_request = marker.outgoing_number != active_outgoing_number
            if not is_new_request and (
                marker.is_header_marker
                or cls._looks_like_request_first_page(number_text)
            ):
                is_new_request = True
            if not is_new_request:
                continue

            duplicate_index = occurrence_counts.get(marker.outgoing_number, 0)
            occurrence_counts[marker.outgoing_number] = duplicate_index + 1
            starts.append((page_index, marker, duplicate_index))
            active_outgoing_number = marker.outgoing_number

        if not starts:
            raise ValueError(
                "Не найден ни один исходящий номер. Проверьте выбранного "
                f"человека (ожидался номер {base_number}) и качество скана."
            )
        if starts[0][0] != 0:
            starts[0] = (0, starts[0][1], starts[0][2])

        requests: list[RecognizedScanRequest] = []
        for index, (first_page, marker, duplicate_index) in enumerate(starts):
            next_page = (
                starts[index + 1][0]
                if index + 1 < len(starts)
                else len(page_texts)
            )
            requests.append(
                RecognizedScanRequest(
                    container_number=marker.container_number,
                    first_page_index=first_page,
                    page_count=next_page - first_page,
                    recipient_email=cls._recipient_email(
                        page_texts[first_page]
                    ),
                    outgoing_number=marker.outgoing_number,
                    outgoing_date=marker.outgoing_date,
                    duplicate_index=duplicate_index,
                )
            )
        return tuple(requests)

    @classmethod
    def _page_outgoing_marker(
        cls,
        text: str,
        selected_base_number: str,
        selected_number_pattern: re.Pattern[str],
    ) -> _PageOutgoingMarker | None:
        header_marker = cls._header_outgoing_marker(
            text,
            selected_base_number,
        )
        selected_matches = tuple(selected_number_pattern.finditer(text))
        containers = {
            int(match.group(1))
            for match in selected_matches
            if 1 <= int(match.group(1)) <= 999
        }
        if len(containers) > 1:
            visible = ", ".join(f".{number}" for number in sorted(containers))
            raise ValueError(
                "На одной странице распознано несколько исходящих номеров: "
                f"{visible}. Проверьте скан."
            )

        if containers:
            container_number = containers.pop()
            outgoing_number = f"{selected_base_number}.{container_number}"
            matching_header = (
                header_marker
                if header_marker is not None
                and header_marker.outgoing_number == outgoing_number
                else None
            )
            if (
                header_marker is not None
                and matching_header is None
                and min(match.start() for match in selected_matches)
                > cls.HEADER_SCAN_LIMIT
            ):
                return header_marker
            return _PageOutgoingMarker(
                outgoing_number=outgoing_number,
                container_number=container_number,
                outgoing_date=(
                    matching_header.outgoing_date
                    if matching_header is not None
                    else None
                ),
                is_header_marker=matching_header is not None,
            )

        return header_marker

    @classmethod
    def _header_outgoing_marker(
        cls,
        text: str,
        selected_base_number: str,
    ) -> _PageOutgoingMarker | None:
        header = text[: cls.HEADER_SCAN_LIMIT]
        for date_match in cls.HEADER_DATE_PATTERN.finditer(header):
            if int(date_match.group(3)) < 2020:
                continue
            outgoing_match = re.search(
                r"\D{0,12}(\d{4,}(?:\s*[./,\\]\s*\d{1,3})?)",
                header[date_match.end() : date_match.end() + 64],
            )
            if outgoing_match is None:
                continue

            raw_number = outgoing_match.group(1)
            interpreted = cls._interpret_header_number(
                raw_number,
                selected_base_number,
            )
            if interpreted is None:
                continue
            outgoing_number, container_number = interpreted
            try:
                outgoing_date = date(
                    int(date_match.group(3)),
                    int(date_match.group(2)),
                    int(date_match.group(1)),
                )
            except ValueError:
                outgoing_date = None
            return _PageOutgoingMarker(
                outgoing_number=outgoing_number,
                container_number=container_number,
                outgoing_date=outgoing_date,
                is_header_marker=True,
            )
        return None

    @staticmethod
    def _interpret_header_number(
        raw_number: str,
        selected_base_number: str,
    ) -> tuple[str, int] | None:
        compact = re.sub(r"\s+", "", raw_number)
        separated = re.fullmatch(r"(\d{3,})[./,\\](\d{1,3})", compact)
        if separated:
            base, suffix = separated.groups()
            suffix_number = int(suffix)
            if base == selected_base_number and 1 <= suffix_number <= 999:
                return f"{base}.{suffix_number}", suffix_number
            return f"{base}.{suffix_number}", 0

        if not compact.isdigit() or len(compact) < 3:
            return None
        if compact == selected_base_number:
            return None
        if compact.startswith(selected_base_number):
            suffix = compact[len(selected_base_number) :]
            if suffix and len(suffix) <= 3:
                suffix_number = int(suffix)
                if 1 <= suffix_number <= 999:
                    return (
                        f"{selected_base_number}.{suffix_number}",
                        suffix_number,
                    )
        if len(compact) <= 5:
            return compact, 0
        return None

    @classmethod
    def _looks_like_request_first_page(cls, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text).casefold()
        return any(phrase in normalized for phrase in cls.FIRST_PAGE_PHRASES)

    @staticmethod
    def _base_number(outgoing_number: str) -> str:
        groups = re.findall(r"\d+", outgoing_number)
        if not groups:
            raise ValueError("Исходящий номер человека не содержит цифр.")
        return max(groups, key=len)

    @classmethod
    def _recipient_email(cls, text: str) -> str:
        match = cls.EMAIL_PATTERN.search(text)
        if not match:
            return ""
        local_part = re.sub(r"\s+", "_", match.group(1))
        domain = re.sub(r"\s+", "", match.group(2))
        return f"{local_part}@{domain}.{match.group(3)}"


class SignedScanService:
    """Split a signed scan by the outgoing number printed on each request."""

    def __init__(
        self,
        request_recognizer: ScanRequestRecognizer | None = None,
        header_emails: WordBundleHeaderEmails | None = None,
        package_store: DispatchPackageStore | None = None,
    ) -> None:
        self.request_recognizer = request_recognizer or ScanRequestRecognizer()
        self.header_emails = header_emails or WordBundleHeaderEmails()
        self.package_store = package_store or DispatchPackageStore()

    def prepare(
        self,
        *,
        person: Person,
        bundle_path: Path | None,
        scan_path: Path,
        output_directory: Path,
    ) -> ScanPreparationResult:
        if not scan_path.is_file():
            raise FileNotFoundError(f"Не найден PDF со сканом:\n{scan_path}")
        if scan_path.suffix.casefold() != ".pdf":
            raise ValueError("Для обработки нужен один файл в формате PDF.")

        reader = PdfReader(scan_path)
        recognized_requests = self.request_recognizer.recognize(
            scan_path,
            person.document_info.outgoing_number,
        )

        emails = self._header_emails_if_available(bundle_path)
        output_directory.mkdir(parents=True, exist_ok=False)
        surname_genitive = decline_full_name(
            person.full_name
        ).last_name_genitive
        initials = (
            f"{person.full_name.first_name[:1]}."
            f"{person.full_name.middle_name[:1]}."
        )

        attachments: list[PreparedAttachment] = []
        for request in recognized_requests:
            abbreviation = DISPATCH_ABBREVIATIONS.get(
                request.container_number,
                "",
            )
            writer = PdfWriter()
            for page in reader.pages[
                request.first_page_index :
                request.first_page_index + request.page_count
            ]:
                writer.add_page(page)

            filename = self.attachment_filename(
                person,
                request.container_number,
                abbreviation,
                outgoing_number=request.outgoing_number,
                outgoing_date=request.outgoing_date,
                duplicate_index=request.duplicate_index,
            )
            output_path = output_directory / filename
            with output_path.open("wb") as stream:
                writer.write(stream)

            subject_parts = (
                "Запрос в отношении",
                surname_genitive,
                initials,
                abbreviation,
            )

            attachments.append(
                PreparedAttachment(
                    container_number=request.container_number,
                    abbreviation=abbreviation,
                    path=output_path,
                    recipient_email=(
                        request.recipient_email
                        or (
                            emails.get(request.container_number, "")
                            if request.container_number
                            and request.duplicate_index == 0
                            else ""
                        )
                    ),
                    subject=" ".join(part for part in subject_parts if part),
                    page_count=request.page_count,
                    outgoing_number=(
                        request.outgoing_number
                        or self._standard_outgoing_number(
                            person,
                            request.container_number,
                        )
                    ),
                    duplicate_index=request.duplicate_index,
                )
            )

        self._validate_outputs(attachments)
        attachments_tuple = tuple(attachments)
        manifest_path = self.package_store.write(
            output_directory,
            attachments_tuple,
        )
        return ScanPreparationResult(
            output_directory=output_directory,
            manifest_path=manifest_path,
            attachments=attachments_tuple,
        )

    def _header_emails_if_available(
        self,
        bundle_path: Path | None,
    ) -> dict[int, str]:
        if bundle_path is None or not bundle_path.is_file():
            return {}
        try:
            return self.header_emails.emails_by_request(bundle_path)
        except Exception:
            # The Word bundle is only a precision fallback for e-mail values.
            # Splitting must still work for an arbitrary standalone PDF.
            return {}

    @staticmethod
    def attachment_filename(
        person: Person,
        container_number: int,
        abbreviation: str,
        *,
        outgoing_number: str = "",
        outgoing_date: date | None = None,
        duplicate_index: int = 0,
    ) -> str:
        actual_outgoing_number = (
            outgoing_number.strip()
            or SignedScanService._standard_outgoing_number(
                person,
                container_number,
            )
        )
        actual_outgoing_number = re.sub(
            r'[<>:"/\\|?*]',
            "-",
            actual_outgoing_number,
        )
        if duplicate_index:
            actual_outgoing_number += f".{duplicate_index}"
        date_text = (
            outgoing_date or person.document_info.outgoing_date
        ).strftime("%d.%m.%Y")
        filename = f"исх. № {actual_outgoing_number} от {date_text}"
        if abbreviation:
            filename += f" {abbreviation}"
        return f"{filename}.pdf"

    @staticmethod
    def _standard_outgoing_number(
        person: Person,
        container_number: int,
    ) -> str:
        base_number = ScanRequestRecognizer._base_number(
            person.document_info.outgoing_number
        )
        return f"{base_number}.{container_number}"

    @staticmethod
    def unique_output_directory(parent: Path, scan_stem: str) -> Path:
        safe_stem = re.sub(r'[<>:"/\\|?*]', "_", scan_stem).strip(" .")
        candidate = parent / (safe_stem or "подписанный_скан")
        index = 2
        while candidate.exists():
            candidate = parent / f"{safe_stem}_{index}"
            index += 1
        return candidate

    @staticmethod
    def _validate_outputs(attachments: list[PreparedAttachment]) -> None:
        for attachment in attachments:
            written = PdfReader(attachment.path)
            if len(written.pages) != attachment.page_count:
                raise RuntimeError(
                    f"Не удалось проверить файл {attachment.path.name}."
                )
