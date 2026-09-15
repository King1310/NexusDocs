from __future__ import annotations

from pathlib import Path

from services.mail_service import OutlookDraftService
from services.signed_scan_service import PreparedAttachment


class FakeAttachments:
    def __init__(self):
        self.paths = []

    def Add(self, path):
        self.paths.append(path)


class FakeMail:
    def __init__(self):
        self.To = ""
        self.Subject = ""
        self.Attachments = FakeAttachments()
        self.saved = False

    def Save(self):
        self.saved = True


class FakeExplorer:
    def __init__(self):
        self.displayed = False

    def Display(self):
        self.displayed = True


class FakeExplorers:
    def __init__(self):
        self.explorer = FakeExplorer()
        self.folder = None

    def Add(self, folder):
        self.folder = folder
        return self.explorer


class FakeNamespace:
    def __init__(self):
        self.requested_folder = None

    def GetDefaultFolder(self, folder_number):
        self.requested_folder = folder_number
        return "drafts"


class FakeOutlook:
    def __init__(self):
        self.mails = []
        self.namespace = FakeNamespace()
        self.Explorers = FakeExplorers()

    def CreateItem(self, item_type):
        mail = FakeMail()
        self.mails.append(mail)
        return mail

    def GetNamespace(self, name):
        assert name == "MAPI"
        return self.namespace


def _attachment(tmp_path, number, email):
    path = tmp_path / f"{number}.pdf"
    path.touch()
    return PreparedAttachment(
        container_number=number,
        abbreviation="нарк",
        path=path,
        recipient_email=email,
        subject="Запрос в отношении Иванова И.И. нарк",
        page_count=1,
    )


def test_outlook_service_saves_drafts_and_skips_missing_email(tmp_path):
    outlook = FakeOutlook()
    ready = _attachment(tmp_path, 5, "narcology@example.ru")
    skipped = _attachment(tmp_path, 4, "")

    result = OutlookDraftService(
        outlook_factory=lambda: outlook
    ).create_drafts((ready, skipped))

    assert result.created == (ready,)
    assert result.skipped_without_email == (skipped,)
    assert len(outlook.mails) == 1
    assert outlook.mails[0].To == "narcology@example.ru"
    assert outlook.mails[0].Subject == ready.subject
    assert outlook.mails[0].Attachments.paths == [str(ready.path.resolve())]
    assert outlook.mails[0].saved
    assert outlook.namespace.requested_folder == 16
    assert outlook.Explorers.explorer.displayed
