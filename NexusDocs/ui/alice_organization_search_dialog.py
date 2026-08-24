from __future__ import annotations

import json
from pathlib import Path

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
from services.alice_organization_search_service import (
    AliceOrganizationSearchService,
    AliceSearchRequest,
    AliceResponseError,
)


class AliceOrganizationSearchDialog(QDialog):
    """Run the strict nine-header request in Alice's free web interface."""

    SEARCH_TIMEOUT_MS = 180_000
    POLL_INTERVAL_MS = 1_500

    def __init__(
        self,
        address: Address,
        parent=None,
        *,
        request: AliceSearchRequest | None = None,
        response_parser=None,
        result_description: str = "все девять шапок",
    ):
        super().__init__(parent)
        self.service = AliceOrganizationSearchService()
        self.request = request or self.service.build_request(address)
        self.response_parser = response_parser or self.service.parse_response
        self.result_description = result_description
        self.outcome = None
        self.error_message = ""
        self._prompt_filled = False
        self._sent = False
        self._last_page_text = ""
        self._stable_poll_count = 0

        self.setWindowTitle("Поиск девяти шапок через Алису AI")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)

        layout = QVBoxLayout(self)
        self.status_label = QLabel(
            "Открываю Алису AI. Если Яндекс попросит войти или показать, "
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
        self.cancel_button = QPushButton("Отмена")
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.retry_button)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.copy_button.clicked.connect(self._copy_prompt)
        self.retry_button.clicked.connect(self._retry)
        self.cancel_button.clicked.connect(self.reject)
        self.web_view.loadFinished.connect(self._on_load_finished)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_page)

        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        self.timeout_timer.start(self.SEARCH_TIMEOUT_MS)

        self.web_view.setUrl(QUrl("https://alice.yandex.ru/"))

    def _persistent_profile(self) -> QWebEngineProfile:
        profile = QWebEngineProfile("NexusDocsAlice", self)
        app_data = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
        )
        profile_dir = app_data / "alice_browser_profile"
        cache_dir = app_data / "alice_browser_cache"
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
                "Страница Алисы не загрузилась. Проверьте интернет и нажмите "
                "«Отправить заново»."
            )
            return
        if not self._sent:
            QTimer.singleShot(1_000, self._fill_prompt)

    def _fill_prompt(self) -> None:
        if self._sent:
            return
        prompt_json = json.dumps(self.request.prompt, ensure_ascii=False)
        script = f"""
        (() => {{
            const input = document.querySelector(
                'textarea[placeholder="Спросите о чём угодно"]'
            );
            if (!input) return false;
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            setter.call(input, {prompt_json});
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
            input.focus();
            return true;
        }})()
        """
        self.page.runJavaScript(script, self._after_prompt_filled)

    def _after_prompt_filled(self, filled) -> None:
        if not filled:
            self.status_label.setText(
                "Ожидаю поле ввода Алисы. При необходимости войдите в "
                "Яндекс ID, затем нажмите «Отправить заново»."
            )
            return
        self._prompt_filled = True
        self.status_label.setText(
            "Строгий запрос подготовлен. Отправляю его Алисе AI…"
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
                return label === 'отправить' || label.includes('отправить запрос');
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
                "Алиса пока не готова принять запрос. Проверьте окно ниже "
                "и нажмите «Отправить заново»."
            )
            return
        self._sent = True
        self.status_label.setText(
            f"Алиса выполняет поиск. Жду {self.result_description}…"
        )
        self.poll_timer.start()

    def _poll_page(self) -> None:
        self.page.runJavaScript(
            """
            (() => {
                if (!document.body) return '';
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('ol').forEach(list => {
                    let nextNumber = Number(list.getAttribute('start') || 1);
                    Array.from(list.children).forEach(item => {
                        if (item.tagName !== 'LI') return;
                        const valueAttribute = item.getAttribute('value');
                        const explicit = valueAttribute === null
                            ? Number.NaN
                            : Number(valueAttribute);
                        const number = Number.isFinite(explicit)
                            ? explicit
                            : nextNumber;
                        const marker = document.createElement('span');
                        marker.textContent = `${number})\n`;
                        item.prepend(marker);
                        nextNumber = number + 1;
                    });
                });
                const generating = Array.from(
                    document.querySelectorAll('button')
                ).some(button => {
                    const label = (
                        button.getAttribute('aria-label') ||
                        button.getAttribute('title') ||
                        button.innerText || ''
                    ).trim().toLowerCase();
                    return label.includes('остановить');
                });
                return {text: clone.innerText, generating};
            })()
            """,
            self._inspect_page_text,
        )

    def _inspect_page_text(self, payload) -> None:
        if isinstance(payload, dict):
            page_text = payload.get("text", "")
            generating = bool(payload.get("generating"))
        else:
            page_text = payload
            generating = False
        if not isinstance(page_text, str) or not page_text:
            return
        if page_text == self._last_page_text:
            self._stable_poll_count += 1
        else:
            self._last_page_text = page_text
            self._stable_poll_count = 0
        if generating or self._stable_poll_count < 1:
            return
        normalized = page_text.casefold().replace("ё", "е")
        if "подтвердите, что вы не робот" in normalized or "captcha" in normalized:
            self.status_label.setText(
                "Яндекс запросил проверку. Пройдите её в окне Алисы; после "
                "этого поиск продолжится."
            )
            return
        try:
            outcome = self.response_parser(page_text)
        except AliceResponseError as error:
            begin = page_text.rfind(self.service.BEGIN_MARKER)
            end = page_text.find(
                self.service.END_MARKER,
                begin + len(self.service.BEGIN_MARKER),
            )
            if begin >= 0 and end > begin:
                self.poll_timer.stop()
                self.error_message = str(error)
                self.status_label.setText(
                    "Алиса закончила ответ, но его нельзя безопасно "
                    f"сохранить: {error} Нажмите «Отправить заново»."
                )
            return

        self.outcome = outcome
        self.poll_timer.stop()
        self.timeout_timer.stop()
        self.status_label.setText("Результат Алисы получен и разобран.")
        self.accept()

    def _retry(self) -> None:
        self.poll_timer.stop()
        self._prompt_filled = False
        self._sent = False
        self._last_page_text = ""
        self._stable_poll_count = 0
        self.error_message = ""
        self.timeout_timer.start(self.SEARCH_TIMEOUT_MS)
        current = self.web_view.url().toString()
        if "alice.yandex" not in current:
            self.web_view.setUrl(QUrl("https://alice.yandex.ru/"))
        else:
            self._fill_prompt()

    def _copy_prompt(self) -> None:
        QGuiApplication.clipboard().setText(self.request.prompt)
        self.status_label.setText(
            "Строгий запрос скопирован. Его можно вставить в поле Алисы вручную."
        )

    def _on_timeout(self) -> None:
        self.poll_timer.stop()
        self.error_message = (
            f"Алиса не вернула {self.result_description} за три минуты."
        )
        QMessageBox.warning(
            self,
            "Поиск Алисы не завершён",
            self.error_message
            + "\n\nМожно нажать «Отправить заново» или закрыть окно.",
        )

    def reject(self) -> None:
        self.poll_timer.stop()
        self.timeout_timer.stop()
        super().reject()
