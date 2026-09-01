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


def test_completed_invalid_automatic_snapshot_keeps_polling():
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
            "generating": False,
            "completed": False,
        },
    )

    assert not poll_timer.stopped
    assert not timeout_timer.stopped
    assert dialog.error_message == ""


def test_manual_collection_reports_an_invalid_finished_answer():
    poll_timer = _StopTarget()
    timeout_timer = _StopTarget()
    dialog = SimpleNamespace(
        _last_page_text="",
        _stable_poll_count=0,
        response_parser=lambda text: (_ for _ in ()).throw(
            AliceResponseError("Не распознана девятая шапка.")
        ),
        service=SimpleNamespace(
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
            "text": "[[NEXUSDOCS_BEGIN]]\nответ\n[[NEXUSDOCS_END]]",
            "generating": False,
            "completed": True,
        },
        force=True,
    )

    assert poll_timer.stopped
    assert timeout_timer.stopped
    assert dialog.error_message == "Не распознана девятая шапка."
    assert "пока нельзя безопасно сохранить" in dialog.status_label.text


def test_prompt_markers_do_not_finish_search_while_alice_is_still_working():
    poll_timer = _StopTarget()
    timeout_timer = _StopTarget()
    dialog = SimpleNamespace(
        _last_page_text="",
        _stable_poll_count=0,
        response_parser=lambda text: (_ for _ in ()).throw(
            AliceResponseError("Распознаны разделители: [1, 2, 9].")
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
                "текст запроса [[NEXUSDOCS_BEGIN]] "
                "[[NEXUSDOCS_HEADER_1]] [[NEXUSDOCS_HEADER_2]] "
                "[[NEXUSDOCS_END]]"
            ),
            "generating": True,
            "completed": True,
        },
    )

    assert not poll_timer.stopped
    assert not timeout_timer.stopped
    assert dialog.error_message == ""


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

    assert "1) шапка" in combined["text"]
    assert "оболочка страницы" in combined["candidate_texts"]
    assert combined["completed"] is True


def test_qt_plain_text_payload_is_combined_with_frame_payloads():
    combined = AliceOrganizationSearchDialog._merge_frame_payloads(
        [
            {"text": "", "generating": False},
            "Военному комиссару\n[[NEXUSDOCS_END]]",
        ]
    )

    assert combined["text"] == "Военному комиссару\n[[NEXUSDOCS_END]]"


def test_numbered_frame_payload_is_kept_after_plain_text_copy():
    plain = "Военному комиссару\n[[NEXUSDOCS_END]]"
    numbered = (
        "[[NEXUSDOCS_BEGIN]]\n"
        + "\n".join(f"{number})\nШапка" for number in range(1, 10))
        + "\n[[NEXUSDOCS_END]]"
    )

    combined = AliceOrganizationSearchDialog._merge_frame_payloads(
        [numbered, plain]
    )

    assert combined["text"] == numbered
