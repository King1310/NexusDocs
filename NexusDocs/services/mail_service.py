from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from services.signed_scan_service import PreparedAttachment


@dataclass(frozen=True, slots=True)
class DraftCreationResult:
    created: tuple[PreparedAttachment, ...]
    skipped_without_email: tuple[PreparedAttachment, ...]


class OutlookDraftService:
    """Create local Outlook drafts without ever sending them."""

    OUTLOOK_MAIL_ITEM = 0
    OUTLOOK_DRAFTS_FOLDER = 16

    def __init__(
        self,
        outlook_factory: Callable[[], object] | None = None,
    ) -> None:
        self.outlook_factory = outlook_factory

    def create_drafts(
        self,
        attachments: tuple[PreparedAttachment, ...],
        *,
        show_drafts_folder: bool = True,
    ) -> DraftCreationResult:
        eligible = tuple(
            attachment
            for attachment in attachments
            if attachment.recipient_email
        )
        skipped = tuple(
            attachment
            for attachment in attachments
            if not attachment.recipient_email
        )
        if not eligible:
            return DraftCreationResult((), skipped)

        pythoncom = None
        outlook = None
        created: list[PreparedAttachment] = []
        try:
            if self.outlook_factory is None:
                import pythoncom as imported_pythoncom
                import win32com.client

                pythoncom = imported_pythoncom
                pythoncom.CoInitialize()
                outlook = win32com.client.Dispatch("Outlook.Application")
            else:
                outlook = self.outlook_factory()

            for attachment in eligible:
                mail = outlook.CreateItem(self.OUTLOOK_MAIL_ITEM)
                mail.To = attachment.recipient_email
                mail.Subject = attachment.subject
                mail.Attachments.Add(str(attachment.path.resolve()))
                mail.Save()
                created.append(attachment)

            if show_drafts_folder:
                namespace = outlook.GetNamespace("MAPI")
                drafts = namespace.GetDefaultFolder(self.OUTLOOK_DRAFTS_FOLDER)
                explorer = outlook.Explorers.Add(drafts)
                explorer.Display()
        except ImportError as error:
            raise RuntimeError(
                "Не найден компонент интеграции с Microsoft Outlook."
            ) from error
        except Exception as error:
            raise RuntimeError(
                "Outlook не смог создать все черновики. "
                f"Успешно создано: {len(created)} из {len(eligible)}."
            ) from error
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()

        return DraftCreationResult(tuple(created), skipped)
