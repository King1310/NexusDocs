from types import SimpleNamespace

from services.alice_organization_search_service import AliceResponseError
from ui.alice_organization_search_dialog import AliceOrganizationSearchDialog


class _StopTarget:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _StatusLabel:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


def test_completed_answer_is_accepted_even_if_page_is_still_dynamic():
    outcome = object()
    poll_timer = _StopTarget()
    timeout_timer = _StopTarget()
    accepted = []
    dialog = SimpleNamespace(
        _last_page_text="предыдущий снимок страницы",
        _stable_poll_count=0,
        response_parser=lambda text: outcome,
        service=SimpleNamespace(
            has_completed_answer=lambda text: "[[NEXUSDOCS_END]]" in text,
        ),
        outcome=None,
        error_message="",
        poll_timer=poll_timer,
        timeout_timer=timeout_timer,
        status_label=_StatusLabel(),
        accept=lambda: accepted.append(True),
    )

    AliceOrganizationSearchDialog._inspect_page_text(
        dialog,
        {
            "text": "новый снимок страницы\n[[NEXUSDOCS_END]]",
            "generating": True,
            "completed": False,
        },
    )

    assert dialog.outcome is outcome
    assert poll_timer.stopped
    assert timeout_timer.stopped
    assert dialog.status_label.text == "Результат Алисы получен и разобран."
    assert accepted == [True]


def test_completed_invalid_answer_reports_error_without_waiting():
    poll_timer = _StopTarget()
    timeout_timer = _StopTarget()
    dialog = SimpleNamespace(
        _last_page_text="предыдущий снимок страницы",
        _stable_poll_count=0,
        response_parser=lambda text: (_ for _ in ()).throw(
            AliceResponseError("Не распознана девятая шапка.")
        ),
        service=SimpleNamespace(
            BEGIN_MARKER="[[NEXUSDOCS_BEGIN]]",
            END_MARKER="[[NEXUSDOCS_END]]",
            has_completed_answer=lambda text: "[[NEXUSDOCS_END]]" in text,
        ),
        outcome=None,
        error_message="",
        poll_timer=poll_timer,
        timeout_timer=timeout_timer,
        status_label=_StatusLabel(),
        accept=lambda: None,
    )

    AliceOrganizationSearchDialog._inspect_page_text(
        dialog,
        {
            "text": (
                "текст запроса [[NEXUSDOCS_END]]\n"
                "[[NEXUSDOCS_BEGIN]]\nответ\n[[NEXUSDOCS_END]]"
            ),
            "generating": True,
            "completed": False,
        },
    )

    assert poll_timer.stopped
    assert timeout_timer.stopped
    assert dialog.error_message == "Не распознана девятая шапка."
    assert "нельзя безопасно сохранить" in dialog.status_label.text


def test_frame_payloads_are_combined_for_nested_alice_content():
    combined = AliceOrganizationSearchDialog._merge_frame_payloads(
        [
            {"text": "оболочка страницы", "generating": False},
            {
                "text": "1) шапка\n[[NEXUSDOCS_END]]",
                "generating": False,
                "completed": True,
            },
        ]
    )

    assert "оболочка страницы" in combined["text"]
    assert "1) шапка" in combined["text"]
    assert combined["completed"] is True


def test_qt_plain_text_payload_is_combined_with_frame_payloads():
    combined = AliceOrganizationSearchDialog._merge_frame_payloads(
        [
            {"text": "", "generating": False},
            "Военному комиссару\n[[NEXUSDOCS_END]]",
        ]
    )

    assert combined["text"] == "Военному комиссару\n[[NEXUSDOCS_END]]"
