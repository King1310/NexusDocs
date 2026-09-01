from __future__ import annotations

import json
from pathlib import Path
import re

from PySide6.QtCore import QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain.value_objects.address import Address
from services.google_organization_search_service import (
    GoogleOrganizationSearchService,
    GoogleSearchRequest,
    GoogleResponseError,
)


class GoogleOrganizationSearchDialog(QDialog):
    """Run the strict nine-header request in Google AI Mode."""

    SEARCH_TIMEOUT_MS = 180_000
    POLL_INTERVAL_MS = 1_500
    GOOGLE_AI_URL = (
        "https://www.google.com/search?sourceid=chrome&ie=UTF-8&amc=1"
        "&udm=50&aep=48&cud=0&source=chrome.crn.obic&atvm=2&hl=ru"
    )

    def __init__(
        self,
        address: Address,
        parent=None,
        *,
        request: GoogleSearchRequest | None = None,
        response_parser=None,
        result_description: str = "все девять шапок",
    ):
        super().__init__(parent)
        self.service = GoogleOrganizationSearchService()
        self.request = request or self.service.build_request(address)
        self.response_parser = response_parser or self.service.parse_response
        self.result_description = result_description
        self.outcome = None
        self.error_message = ""
        self._prompt_filled = False
        self._sent = False
        self._last_page_text = ""
        self._stable_poll_count = 0
        self._tagged_blocks: dict[int, str] = {}

        self.setWindowTitle("Поиск девяти шапок через Google AI")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)

        layout = QVBoxLayout(self)
        self.status_label = QLabel(
            "Открываю режим ИИ Google. Если Google попросит войти или показать, "
            "что вы не робот, выполните это прямо в окне ниже."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.web_view = QWebEngineView(self)
        self.profile = self._persistent_profile()
        self.page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(self.page)
        layout.addWidget(self.web_view, 1)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Скопировать строгий запрос")
        self.retry_button = QPushButton("Отправить заново")
        self.collect_button = QPushButton("Забрать готовые шапки")
        self.cancel_button = QPushButton("Отмена")
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.retry_button)
        buttons.addWidget(self.collect_button)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.copy_button.clicked.connect(self._copy_prompt)
        self.retry_button.clicked.connect(self._retry)
        self.collect_button.clicked.connect(
            lambda _checked=False: self._poll_page(force=True)
        )
        self.cancel_button.clicked.connect(self.reject)
        self.web_view.loadFinished.connect(self._on_load_finished)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_page)

        self.fill_timer = QTimer(self)
        self.fill_timer.setInterval(1_000)
        self.fill_timer.timeout.connect(self._fill_prompt)
        self.fill_timer.start()

        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        self.timeout_timer.start(self.SEARCH_TIMEOUT_MS)

        self.web_view.setUrl(QUrl(self.GOOGLE_AI_URL))

    def _persistent_profile(self) -> QWebEngineProfile:
        profile = QWebEngineProfile("NexusDocsGoogleAI", self)
        app_data = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
        )
        profile_dir = app_data / "google_ai_browser_profile"
        cache_dir = app_data / "google_ai_browser_cache"
        profile_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        profile.setPersistentStoragePath(str(profile_dir))
        profile.setCachePath(str(cache_dir))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        return profile

    def _on_load_finished(self, succeeded: bool) -> None:
        if not succeeded:
            self.status_label.setText(
                "Страница Google AI не загрузилась. Проверьте интернет и нажмите "
                "«Отправить заново»."
            )
            return
        if not self._sent:
            self.fill_timer.start()
            QTimer.singleShot(500, self._fill_prompt)

    def _fill_prompt(self) -> None:
        if self._sent:
            return
        prompt_json = json.dumps(self.request.prompt, ensure_ascii=False)
        script = f"""
        (() => {{
            const buttons = Array.from(document.querySelectorAll('button'));
            const consent = buttons.find(button => {{
                const label = (
                    button.getAttribute('aria-label') ||
                    button.innerText || ''
                ).trim().toLowerCase();
                return label === 'отклонить все'
                    || label === 'reject all'
                    || label === 'alles afwijzen'
                    || label === 'alle ablehnen';
            }});
            if (consent) {{
                consent.click();
                return 'consent';
            }}
            const input = document.querySelector(
                'textarea[placeholder="Задайте вопрос"], '
                + 'textarea[placeholder="Ask anything"], '
                + 'textarea[name="q"], textarea[maxlength="8192"]'
            );
            if (!input) return 'missing';
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            setter.call(input, {prompt_json});
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
            input.focus();
            return 'filled';
        }})()
        """
        self.page.runJavaScript(script, self._after_prompt_filled)

    def _after_prompt_filled(self, filled) -> None:
        if filled == "consent":
            self.status_label.setText(
                "Google показал окно cookies. Закрываю его и продолжаю поиск…"
            )
            return
        if filled not in (True, "filled"):
            self.status_label.setText(
                "Ожидаю поле ввода Google AI. При необходимости войдите в "
                "аккаунт Google, затем нажмите «Отправить заново»."
            )
            return
        self._prompt_filled = True
        self.fill_timer.stop()
        self.status_label.setText(
            "Строгий запрос подготовлен. Отправляю его в Google AI…"
        )
        QTimer.singleShot(500, self._click_send)

    def _click_send(self) -> None:
        if self._sent or not self._prompt_filled:
            return
        script = """
        (() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const send = buttons.find(button => {
                const label = (
                    button.getAttribute('aria-label') ||
                    button.getAttribute('title') ||
                    button.innerText || ''
                ).trim().toLowerCase();
                return label === 'отправить'
                    || label.includes('отправить запрос')
                    || label === 'send'
                    || label.includes('send prompt');
            });
            if (!send || send.disabled) return false;
            send.click();
            return true;
        })()
        """
        self.page.runJavaScript(script, self._after_send)

    def _after_send(self, sent) -> None:
        if not sent:
            self.status_label.setText(
                "Google AI пока не готов принять запрос. Проверьте окно ниже "
                "и нажмите «Отправить заново»."
            )
            return
        self._sent = True
        self.fill_timer.stop()
        self.status_label.setText(
            f"Google AI выполняет поиск. Жду {self.result_description}…"
        )
        self.poll_timer.start()

    def _poll_page(self, force: bool = False) -> None:
        if force:
            self.status_label.setText("Считываю готовый ответ Google AI…")
        script = """
            (() => {
                if (!document.body) {
                    return {text: '', generating: false, completed: false,
                        error: 'document.body отсутствует'};
                }
                try {
                    const rawText = document.body.innerText
                        || document.body.textContent || '';
                    const buttons = Array.from(
                        document.querySelectorAll('button')
                    );
                    const buttonLabel = button => (
                        button.getAttribute('aria-label') ||
                        button.getAttribute('title') ||
                        button.innerText || ''
                    ).trim().toLowerCase();
                    const isVisible = element => {
                        const style = window.getComputedStyle(element);
                        return element.getClientRects().length > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    };
                    const generating = buttons.some(button => {
                        const style = window.getComputedStyle(button);
                        const visible = button.getClientRects().length > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                        if (!visible) return false;
                        const label = buttonLabel(button);
                        return label.includes('остановить')
                            || label === 'стоп'
                            || label === 'stop';
                    });
                    const copyButtons = buttons.filter(button => {
                        if (!isVisible(button)) return false;
                        const label = buttonLabel(button);
                        return label === 'скопировать текст'
                            || label === 'copy text';
                    });
                    const answerCandidates = [];
                    copyButtons.forEach(button => {
                        let element = button;
                        for (let level = 0; level < 10 && element; level += 1) {
                            const text = element.innerText
                                || element.textContent || '';
                            if (text.includes('[[NEXUSDOCS_END]]')) {
                                answerCandidates.push(text);
                            }
                            element = element.parentElement;
                        }
                    });
                    answerCandidates.sort((left, right) => {
                        const leftComplete = left.includes('[[NEXUSDOCS_BEGIN]]')
                            && left.includes('[[NEXUSDOCS_HEADER_9]]');
                        const rightComplete = right.includes('[[NEXUSDOCS_BEGIN]]')
                            && right.includes('[[NEXUSDOCS_HEADER_9]]');
                        if (leftComplete !== rightComplete) {
                            return leftComplete ? -1 : 1;
                        }
                        return left.length - right.length;
                    });
                    const text = answerCandidates[0] || rawText;
                    const completed = copyButtons.length > 0
                        && text.includes('[[NEXUSDOCS_END]]');
                    return {
                        text,
                        candidateTexts: answerCandidates,
                        generating,
                        completed,
                        error: '',
                    };
                } catch (error) {
                    return {
                        text: document.body.innerText
                            || document.body.textContent || '',
                        generating: false,
                        completed: false,
                        error: String(error),
                    };
                }
            })()
            """

        frames = []
        try:
            def append_frame(frame) -> None:
                if not frame.isValid():
                    return
                frames.append(frame)
                for child in frame.children():
                    append_frame(child)

            append_frame(self.page.mainFrame())
        except (AttributeError, RuntimeError):
            frames = []

        if not frames:
            self.page.runJavaScript(
                script,
                lambda payload: self._inspect_page_text(payload, force=force),
            )
            return

        state = {
            "remaining": len(frames) + 1,
            "payloads": [None] * (len(frames) + 1),
        }

        def receive_frame_payload(index: int, payload) -> None:
            state["payloads"][index] = payload
            state["remaining"] -= 1
            if state["remaining"] != 0:
                return
            combined = self._merge_frame_payloads(state["payloads"])
            if force:
                clipboard_text = QGuiApplication.clipboard().text().strip()
                if (
                    clipboard_text
                    and self.service.has_completed_answer(clipboard_text)
                ):
                    combined["text"] = "\n".join(
                        part
                        for part in (combined["text"], clipboard_text)
                        if part
                    )
                    combined["completed"] = True
            self._inspect_page_text(combined, force=force)

        for index, frame in enumerate(frames):
            frame.runJavaScript(
                script,
                lambda payload, frame_index=index: receive_frame_payload(
                    frame_index,
                    payload,
                ),
            )
        self.page.toPlainText(
            lambda text: receive_frame_payload(len(frames), text)
        )

    @staticmethod
    def _merge_frame_payloads(payloads) -> dict:
        """Combine visible text collected from the Google AI page."""

        texts: list[str] = []
        errors: list[str] = []
        generating = False
        completed = False
        for payload in payloads:
            if isinstance(payload, dict):
                text = payload.get("text", "")
                payload_candidates = payload.get("candidateTexts") or []
                generating = generating or bool(payload.get("generating"))
                completed = completed or bool(payload.get("completed"))
                error = str(payload.get("error") or "").strip()
                if error:
                    errors.append(error)
            else:
                text = payload
                payload_candidates = []
            for candidate in payload_candidates:
                if (
                    isinstance(candidate, str)
                    and candidate.strip()
                    and candidate not in texts
                ):
                    texts.append(candidate)
            if isinstance(text, str) and text.strip() and text not in texts:
                texts.append(text)
        texts.sort(key=GoogleOrganizationSearchDialog._payload_text_score)
        return {
            "text": texts[-1] if texts else "",
            "candidate_texts": texts,
            "generating": generating,
            "completed": completed,
            "error": "; ".join(errors) if not texts else "",
        }

    @staticmethod
    def _payload_text_score(value: str) -> tuple[int, int, int, int, int]:
        numbers = {
            int(match.group(1))
            for match in re.finditer(
                r"(?m)^\s*([1-9])\s*[).:]\s*",
                value,
            )
        }
        header_markers = {
            int(number)
            for number in re.findall(
                r"\[\[\s*NEXUSDOCS_HEADER_([1-9])\s*\]\]",
                value,
                flags=re.IGNORECASE,
            )
        }
        return (
            int(GoogleOrganizationSearchService.has_completed_answer(value)),
            int(header_markers == set(range(1, 10))),
            len(header_markers),
            int(numbers == set(range(1, 10))),
            -len(value),
        )

    def _inspect_page_text(self, payload, *, force: bool = False) -> None:
        if isinstance(payload, dict):
            page_text = payload.get("text", "")
            candidate_texts = payload.get("candidate_texts") or [page_text]
            generating = bool(payload.get("generating"))
            completed = bool(payload.get("completed"))
            polling_error = str(payload.get("error") or "").strip()
        else:
            page_text = payload
            candidate_texts = [page_text]
            generating = False
            completed = False
            polling_error = ""
        if polling_error:
            self.status_label.setText(
                "Не удалось автоматически считать ответ Google AI: "
                f"{polling_error}. Нажмите «Забрать готовые шапки»."
            )
        if not isinstance(page_text, str) or not page_text:
            if force and not polling_error:
                self.status_label.setText(
                    "Google AI не разрешил приложению прочитать страницу. "
                    "Нажмите «Скопировать текст» под ответом, затем снова "
                    "нажмите «Забрать готовые шапки»."
                )
            return
        if hasattr(self.service, "extract_complete_tagged_blocks"):
            tagged_blocks = getattr(self, "_tagged_blocks", None)
            if tagged_blocks is None:
                tagged_blocks = {}
                self._tagged_blocks = tagged_blocks
            for candidate in candidate_texts:
                if not isinstance(candidate, str):
                    continue
                current_prompt = candidate.rfind("ВАЖНО ДЛЯ ФОРМАТА")
                if current_prompt >= 0:
                    candidate = candidate[current_prompt:]
                tagged_blocks.update(
                    self.service.extract_complete_tagged_blocks(candidate)
                )
            if set(tagged_blocks) == set(range(1, 10)):
                page_text = self.service.assemble_tagged_blocks(tagged_blocks)
                completed = True
        completed = completed or self.service.has_completed_answer(page_text)
        if page_text == self._last_page_text:
            self._stable_poll_count += 1
        else:
            self._last_page_text = page_text
            self._stable_poll_count = 0
        normalized = page_text.casefold().replace("ё", "е")
        if "подтвердите, что вы не робот" in normalized or "captcha" in normalized:
            self.status_label.setText(
                "Google запросил проверку. Пройдите её в окне Google AI; после "
                "этого поиск продолжится."
            )
            return
        try:
            outcome = self.response_parser(page_text)
        except GoogleResponseError as error:
            # The user's prompt itself contains the complete protocol and may
            # be visible on the page while Google AI is still writing.
            # Therefore an invalid automatic snapshot is never authoritative:
            # keep polling until a complete response parses successfully.  A
            # manual collection is explicit and may report the parse error.
            if not force:
                return
            self.poll_timer.stop()
            self.timeout_timer.stop()
            self.error_message = str(error)
            self.status_label.setText(
                "Готовый ответ Google AI пока нельзя безопасно сохранить: "
                f"{error} Дождитесь конца ответа и нажмите кнопку ещё раз."
            )
            return

        self.outcome = outcome
        self.poll_timer.stop()
        self.fill_timer.stop()
        self.timeout_timer.stop()
        self.status_label.setText("Результат Google AI получен и разобран.")
        self.accept()

    def _retry(self) -> None:
        self.poll_timer.stop()
        self.fill_timer.start()
        self._prompt_filled = False
        self._sent = False
        self._last_page_text = ""
        self._stable_poll_count = 0
        self._tagged_blocks.clear()
        self.error_message = ""
        self.timeout_timer.start(self.SEARCH_TIMEOUT_MS)
        current = self.web_view.url().toString()
        if "google.com/search" not in current or "udm=50" not in current:
            self.web_view.setUrl(QUrl(self.GOOGLE_AI_URL))
        else:
            self.web_view.setUrl(QUrl(self.GOOGLE_AI_URL))

    def _copy_prompt(self) -> None:
        QGuiApplication.clipboard().setText(self.request.prompt)
        self.status_label.setText(
            "Строгий запрос скопирован. Его можно вставить в Google AI вручную."
        )

    def _on_timeout(self) -> None:
        self.poll_timer.stop()
        self.fill_timer.stop()
        self.error_message = (
            f"Google AI не вернул {self.result_description} за три минуты."
        )
        QMessageBox.warning(
            self,
            "Поиск Google AI не завершён",
            self.error_message
            + "\n\nМожно нажать «Отправить заново» или закрыть окно.",
        )

    def reject(self) -> None:
        self.poll_timer.stop()
        self.fill_timer.stop()
        self.timeout_timer.stop()
        super().reject()


# Backward-compatible import for extensions written for NexusDocs 1.0.
AliceOrganizationSearchDialog = GoogleOrganizationSearchDialog
