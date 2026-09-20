from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import is_zipfile

from pypdf import PdfReader

from services.signed_scan_service import (
    DispatchPackageStore,
    RecognizedScanRequest,
    ScanPreparationResult,
    SignedScanService,
)


# A separate COM instance opens only a snapshot of the saved document. In
# particular, no active Word instance, open editor document or database is used.
WORD_EXPORT_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$application = $null
$document = $null
try {
    $previousWordIds = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    $application = New-Object -ComObject Word.Application
    $application.Visible = $false
    $application.DisplayAlerts = 0
    $application.AutomationSecurity = 3
    $application.Options.UpdateLinksAtOpen = $false

    # Read-only snapshot; do not add it to the user's recent documents.
    # Password-protected input is rejected before COM is invoked.
    $document = $application.Documents.Open(
        $env:NEXUSDOCS_WORD_SOURCE, $false, $true, $false
    )
    # Word.Application has no Hwnd; the document window owns the handle.
    # Record a PID only after verifying it did not exist before this export.
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NexusWordProcess {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
    [uint32]$wordProcessId = 0
    [NexusWordProcess]::GetWindowThreadProcessId(
        [IntPtr]$document.Windows.Item(1).Hwnd, [ref]$wordProcessId
    ) | Out-Null
    if ($wordProcessId -and $wordProcessId -notin $previousWordIds) {
        $wordProcess = Get-Process -Id $wordProcessId
        @{
            id = $wordProcessId
            started = $wordProcess.StartTime.ToUniversalTime().Ticks.ToString()
        } | ConvertTo-Json | Set-Content -LiteralPath $env:NEXUSDOCS_WORD_PROCESS -Encoding UTF8
    }
    $document.Repaginate()
    $document.ExportAsFixedFormat($env:NEXUSDOCS_WORD_PDF, 17)
    $bookmarks = @()
    foreach ($bookmark in $document.Bookmarks) {
        if ($bookmark.Name -match '^NEXUSDOCS_REQUEST_(\d+)$') {
            $bookmarks += [PSCustomObject]@{
                number = [int]$Matches[1]
                start = [int]$bookmark.Range.Start
                page = [int]$bookmark.Range.Information(3)
            }
        }
    }
    $bookmarks = @($bookmarks | Sort-Object start)
    $records = @()
    for ($index = 0; $index -lt $bookmarks.Count; $index++) {
        $entry = $bookmarks[$index]
        $end = [int]$document.Content.End
        if ($index + 1 -lt $bookmarks.Count) { $end = $bookmarks[$index + 1].start }
        $range = $document.Range($entry.start, $end)
        $section = $range.Sections.Item(1)
        $headers = @()
        $footers = @()
        # TextFrame content is not included in Word Range.Text. Several of
        # our recipient headers use floating text boxes, not paragraphs.
        foreach ($shape in $document.Shapes) {
            if ($shape.Anchor.Information(3) -eq $entry.page) {
                try {
                    if ($shape.TextFrame.HasText) { $headers += [string]$shape.TextFrame.TextRange.Text }
                } catch {}
            }
        }
        # Legacy positioned Word frames may precede their bookmark in the
        # story order even though they render on this request's first page.
        foreach ($frame in $document.Frames) {
            if ($frame.Range.Information(3) -eq $entry.page) {
                $headers += [string]$frame.Range.Text
            }
        }
        for ($kind = 1; $kind -le 3; $kind++) {
            if ($section.Headers.Item($kind).Exists) {
                $headers += [string]$section.Headers.Item($kind).Range.Text
                foreach ($shape in $section.Headers.Item($kind).Shapes) {
                    try {
                        if ($shape.TextFrame.HasText) { $headers += [string]$shape.TextFrame.TextRange.Text }
                    } catch {}
                }
            }
            if ($section.Footers.Item($kind).Exists) {
                $footers += [string]$section.Footers.Item($kind).Range.Text
            }
        }
        $records += @{
            number = $entry.number
            page = $entry.page
            text = [string]$range.Text
            header = $headers -join "`n"
            footer = $footers -join "`n"
        }
    }
    @{ requests = @($records) } | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $env:NEXUSDOCS_WORD_METADATA -Encoding UTF8
}
catch {
    [System.IO.File]::WriteAllText($env:NEXUSDOCS_WORD_ERROR, ($_.Exception.Message + "`n" + $_.InvocationInfo.PositionMessage))
    exit 1
}
finally {
    if ($null -ne $document) {
        try { $document.Close(0) } catch {}
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $application) {
        try { $application.Quit(0) } catch {}
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
'''


@dataclass(frozen=True, slots=True)
class WordExportResult:
    pdf_path: Path
    requests: tuple[RecognizedScanRequest, ...]


class ReviewedWordConverter:
    """Export a saved Word bundle and read its freshly paginated bookmarks."""

    def __init__(self, timeout_seconds: int = 180) -> None:
        self.timeout_seconds = timeout_seconds

    def convert(self, docx_path: Path, work_directory: Path) -> WordExportResult:
        pdf_path = work_directory / "проверенный_комплект.pdf"
        metadata_path = work_directory / "word_metadata.json"
        process_path = work_directory / "word_process.json"
        error_path = work_directory / "word_error.txt"
        executable = self._powershell()
        env = dict(os.environ)
        env.update({
            "NEXUSDOCS_WORD_SOURCE": str(docx_path.resolve()),
            "NEXUSDOCS_WORD_PDF": str(pdf_path.resolve()),
            "NEXUSDOCS_WORD_METADATA": str(metadata_path.resolve()),
            "NEXUSDOCS_WORD_PROCESS": str(process_path.resolve()),
            "NEXUSDOCS_WORD_ERROR": str(error_path.resolve()),
        })
        try:
            result = self._run_powershell(
                executable, WORD_EXPORT_SCRIPT, env, self.timeout_seconds
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "Microsoft Word не завершил преобразование за отведённое время. "
                "Сохраните правки, проверьте, открывается ли выбранный файл "
                "в Word без дополнительных окон, и повторите подготовку PDF."
            ) from error
        finally:
            # Word can retain a background COM server after Quit even when
            # PowerShell has exited. Never terminate the user's older instance.
            self._stop_own_word(executable, process_path)
        if result.returncode or not pdf_path.is_file() or not metadata_path.is_file():
            detail = error_path.read_text(encoding="utf-8-sig") if error_path.is_file() else ""
            raise RuntimeError(
                "Не удалось преобразовать выбранный Word в PDF. "
                "Для этой операции нужен установленный Microsoft Word."
                + (f"\n{detail}" if detail else "")
            )
        payload = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        requests = self.requests_from_metadata(payload, len(PdfReader(pdf_path).pages))
        return WordExportResult(pdf_path, requests)

    @staticmethod
    def _powershell() -> str:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
        if not executable.is_file():
            raise RuntimeError("Не найден Windows PowerShell для преобразования Word.")
        return str(executable)

    @staticmethod
    def _run_powershell(executable, script, env, timeout):
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            env=env, capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @classmethod
    def _stop_own_word(cls, executable: str, process_path: Path) -> None:
        # Both PID and creation time must match the instance started above.
        if not process_path.is_file():
            return
        env = dict(os.environ, NEXUSDOCS_WORD_PROCESS=str(process_path.resolve()))
        script = r'''
$record = Get-Content -LiteralPath $env:NEXUSDOCS_WORD_PROCESS -Raw | ConvertFrom-Json
$process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
if ($process -and $process.ProcessName -eq 'WINWORD' -and
    $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started) {
    Stop-Process -Id $process.Id -Force
}
'''
        try:
            cls._run_powershell(executable, script, env, 15)
        except (OSError, subprocess.TimeoutExpired):
            pass

    @classmethod
    def requests_from_metadata(cls, payload: dict, total_pages: int):
        records = payload.get("requests", [])
        if not isinstance(records, list) or Counter(record.get("number") for record in records) != Counter(range(1, 16)):
            raise ValueError(
                "В выбранном Word отсутствуют или повреждены границы запросов. "
                "Сохраните его в PDF через Word и выберите полученный PDF "
                "для обычного разделения."
            )
        starts = [int(record["page"]) - 1 for record in records]
        if not starts or starts[0] != 0 or any(
            start < 0 or end <= start
            for start, end in zip(starts, starts[1:] + [total_pages])
        ):
            raise ValueError(
                "После редактирования некоторые запросы начинаются на одной "
                "странице. Добавьте разрыв страницы перед каждым запросом."
            )
        requests = []
        occurrences: Counter[str] = Counter()
        for record, start, end in zip(records, starts, starts[1:] + [total_pages]):
            header = str(record.get("header", ""))
            body = str(record.get("text", ""))
            footer = str(record.get("footer", ""))
            address_block = cls._address_block(header, body)
            outgoing_number, outgoing_date = cls._outgoing_details(address_block, footer)
            duplicate_index = occurrences[outgoing_number]
            occurrences[outgoing_number] += 1
            requests.append(RecognizedScanRequest(
                container_number=int(record["number"]),
                first_page_index=start,
                page_count=end - start,
                recipient_email=cls._recipient_email(address_block),
                outgoing_number=outgoing_number,
                outgoing_date=outgoing_date,
                duplicate_index=duplicate_index,
            ))
        return tuple(requests)

    @staticmethod
    def _address_block(header: str, body: str) -> str:
        body_start = re.search(
            r"(?:уважаем\w*\s|в\s+производстве\s|в\s+военном\s+следственном\s|"
            r"в\s+целях\s|руководствуясь\s|на\s+основании\s|прошу\s|"
            r"в\s+соответствии\s)", body, re.IGNORECASE,
        )
        before_body = body[:body_start.start()] if body_start else body[:2000]
        return header + "\n" + before_body

    @staticmethod
    def _recipient_email(text: str) -> str:
        match = re.search(
            r"(?:эл(?:ектронная)?\.?\s*почта|e-?mail)\s*:\s*"
            r"([A-Z0-9._%+\-]+\s*@\s*[A-Z0-9.\-]+\.[A-ZА-Я]{2,})",
            text, re.IGNORECASE,
        )
        return re.sub(r"\s+", "", match.group(1)) if match else ""

    @staticmethod
    def _outgoing_details(header: str, footer: str) -> tuple[str, date]:
        # The template's outgoing stamp is in the footer; the top letterhead
        # can contain the same details and takes precedence if manually edited.
        number_pattern = re.compile(r"№\s*(?:Исх\.?[-\s]*)?(\d{3,})(?:\s*[./]\s*(\d{1,3}))?", re.IGNORECASE)
        date_pattern = re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(20\d{2})(?!\d)")
        for text in (header, footer):
            number = number_pattern.search(text)
            dates = list(date_pattern.finditer(text))
            if number and dates:
                # Dates closest to the outgoing number are less likely to be
                # unrelated identifiers in the organisation's name/address.
                match = min(dates, key=lambda item: abs(item.start() - number.start()))
                try:
                    actual_date = date(int(match[3]), int(match[2]), int(match[1]))
                except ValueError:
                    continue
                actual_number = number[1] + (f".{int(number[2])}" if number[2] else "")
                return actual_number, actual_date
        raise ValueError(
            "В одном из запросов выбранного Word не удалось прочитать "
            "исходящий номер и дату. Проверьте их в сохранённом файле."
        )


class _ExportedRequestRecognizer:
    def __init__(self, requests):
        self.requests = requests

    def recognize(self, scan_path, outgoing_number):
        return self.requests


class WordDispatchService:
    """Prepare PDFs only when the user explicitly selects their reviewed DOCX."""

    def __init__(self, *, converter=None, package_store=None) -> None:
        self.converter = converter or ReviewedWordConverter()
        self.package_store = package_store or DispatchPackageStore()

    def prepare(self, *, person, docx_path: Path, output_directory: Path) -> ScanPreparationResult:
        docx_path = docx_path.resolve()
        if not docx_path.is_file() or docx_path.suffix.casefold() != ".docx":
            raise ValueError("Выберите сохранённый Word-файл в формате DOCX.")
        if not is_zipfile(docx_path):
            raise ValueError("Word-файл повреждён или защищён паролем. Сохраните незашифрованную копию DOCX.")
        if output_directory.exists():
            raise ValueError("Папка результата уже существует. Выберите новую папку.")
        with tempfile.TemporaryDirectory(prefix="nexusdocs_reviewed_word_") as temporary:
            workspace = Path(temporary)
            snapshot = workspace / docx_path.name
            shutil.copy2(docx_path, snapshot)
            exported = self.converter.convert(snapshot, workspace)
            # No fallback to old generated files: deleted e-mails must stay
            # deleted, and manual edits in this snapshot are authoritative.
            return SignedScanService(
                request_recognizer=_ExportedRequestRecognizer(exported.requests),
                package_store=self.package_store,
            ).prepare(
                person=person, bundle_path=None, scan_path=exported.pdf_path,
                output_directory=output_directory,
            )
