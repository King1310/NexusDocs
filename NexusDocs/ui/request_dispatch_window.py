from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from database.repositories.person_repository import PersonRepository
from services.mail_service import OutlookDraftService
from services.signed_scan_service import DispatchPackageStore, SignedScanService
from services.word_bundle_service import WordBundleService
from services.word_dispatch_service import WordDispatchService


class _SplitScanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        scan_service,
        person,
        bundle_path: Path | None,
        scan_path: Path,
        output_directory: Path,
    ) -> None:
        super().__init__()
        self.scan_service = scan_service
        self.person = person
        self.bundle_path = bundle_path
        self.scan_path = scan_path
        self.output_directory = output_directory

    @Slot()
    def run(self) -> None:
        try:
            result = self.scan_service.prepare(
                person=self.person,
                bundle_path=self.bundle_path,
                scan_path=self.scan_path,
                output_directory=self.output_directory,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(result)


class _CreateDraftsWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, *, package_store, draft_service, manifest_path: Path):
        super().__init__()
        self.package_store = package_store
        self.draft_service = draft_service
        self.manifest_path = manifest_path

    @Slot()
    def run(self) -> None:
        try:
            package = self.package_store.load(self.manifest_path)
            drafts = self.draft_service.create_drafts(package.attachments)
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(package, drafts)


class _PrepareWordWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, *, word_service, person, docx_path, output_directory):
        super().__init__()
        self.word_service = word_service
        self.person = person
        self.docx_path = docx_path
        self.output_directory = output_directory

    @Slot()
    def run(self) -> None:
        try:
            result = self.word_service.prepare(
                person=self.person,
                docx_path=self.docx_path,
                output_directory=self.output_directory,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(result)


class RequestDispatchWindow(QDialog):
    """Prepare a reviewed Word or scan, then create Outlook drafts separately."""

    def __init__(
        self,
        repository: PersonRepository,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.word_bundle_service = WordBundleService()
        self.package_store = DispatchPackageStore()
        self.signed_scan_service = SignedScanService(
            package_store=self.package_store
        )
        self.word_dispatch_service = WordDispatchService(package_store=self.package_store)
        self.outlook_draft_service = OutlookDraftService()
        self._people_by_id = {}
        self._work_thread = None
        self._worker = None
        self._progress_dialog = None
        self._active_button = None

        self.setWindowTitle("Отправка запросов")
        self.resize(820, 420)
        self.setMinimumSize(700, 360)
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)

        self._setup_ui()
        self._load_people()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Отправка запросов")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        explanation = QLabel(
            "Сначала просмотрите Word-комплект, внесите правки и сохраните его. "
            "Затем выберите этот Word или готовый PDF и нажмите кнопку подготовки. "
            "Word будет преобразован в PDF и разбит целиком. "
            "Количество, повторы и порядок контейнеров не важны; запросы "
            "с другими исходящими номерами тоже будут разделены. После "
            "разбиения можно перенести всю созданную папку на компьютер "
            "с Outlook; устанавливать туда NexusDocs не обязательно."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        split_title = QLabel("1. Подготовить отдельные PDF")
        split_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(split_title)

        split_form = QFormLayout()
        self.person_combo = QComboBox()
        split_form.addRow("Человек:", self.person_combo)

        self.scan_input = QLineEdit()
        self.scan_input.setReadOnly(True)
        self.scan_input.setPlaceholderText(
            "Выберите проверенный и сохранённый Word или общий PDF"
        )
        self.scan_input.textChanged.connect(self._source_changed)
        scan_row = QHBoxLayout()
        scan_row.addWidget(self.scan_input)
        self.choose_scan_button = QPushButton("Выбрать Word / PDF")
        self.choose_scan_button.clicked.connect(self.choose_scan)
        scan_row.addWidget(self.choose_scan_button)
        split_form.addRow("Проверенный файл:", scan_row)
        layout.addLayout(split_form)

        self.split_button = QPushButton("1. Разбить PDF")
        self.split_button.clicked.connect(self.split_scan)
        layout.addWidget(self.split_button)

        review_note = QLabel(
            "Для Word используются последние сохранённые изменения выбранного файла. "
            "После создания комплекта преобразование само не запускается."
        )
        review_note.setWordWrap(True)
        layout.addWidget(review_note)

        drafts_title = QLabel("2. Создать письма на компьютере с Outlook")
        drafts_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(drafts_title)

        package_row = QHBoxLayout()
        self.package_input = QLineEdit()
        self.package_input.setReadOnly(True)
        self.package_input.setPlaceholderText(
            "Выберите файл пакет_отправки.nexusdocs.json"
        )
        package_row.addWidget(self.package_input)
        self.choose_package_button = QPushButton("Выбрать пакет")
        self.choose_package_button.clicked.connect(self.choose_package)
        package_row.addWidget(self.choose_package_button)
        layout.addLayout(package_row)

        self.create_drafts_button = QPushButton(
            "2. Создать черновики Outlook"
        )
        self.create_drafts_button.clicked.connect(self.create_drafts)
        layout.addWidget(self.create_drafts_button)

        note = QLabel(
            "NexusDocs только сохраняет письма в «Черновики» и ничего "
            "не отправляет автоматически."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def _load_people(self) -> None:
        self.person_combo.clear()
        self._people_by_id = {
            person.id: person
            for person in self.repository.get_all()
            if person.id is not None
        }
        for person in self._people_by_id.values():
            self.person_combo.addItem(
                f"{person.id} — {person.full_name.full}",
                person.id,
            )
        self.split_button.setEnabled(bool(self._people_by_id))

    def choose_scan(self) -> None:
        start_directory = self._selected_person_output_directory()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите проверенный Word или общий PDF с запросами",
            str(start_directory),
            "Word и PDF (*.docx *.pdf);;Word (*.docx);;PDF (*.pdf)",
        )
        if selected:
            self.scan_input.setText(selected)

    def _source_changed(self, value: str) -> None:
        is_word = Path(value).suffix.casefold() == ".docx"
        self.split_button.setText(
            "1. Преобразовать Word и разбить PDF" if is_word else "1. Разбить PDF"
        )

    def choose_package(self) -> None:
        current = Path(self.package_input.text().strip())
        start_directory = (
            current.parent
            if current.parent.is_dir()
            else self._project_directory() / "output"
        )
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите пакет отправки NexusDocs",
            str(start_directory),
            "Пакет NexusDocs (*.nexusdocs.json);;JSON (*.json)",
        )
        if selected:
            self.package_input.setText(selected)

    def split_scan(self) -> None:
        if self._work_thread is not None:
            self._show_busy_message()
            return

        person = self._selected_person()
        if person is None:
            QMessageBox.warning(
                self,
                "Не выбран человек",
                "Выберите человека, для которого подготовлен комплект.",
            )
            return

        scan_path = Path(self.scan_input.text().strip())
        if not scan_path.is_file():
            self.choose_scan()
            scan_path = Path(self.scan_input.text().strip())
            if not scan_path.is_file():
                return

        person_output = self._selected_person_output_directory()
        output_directory = self.signed_scan_service.unique_output_directory(
            person_output / "К отправке", scan_path.stem,
        )
        if scan_path.suffix.casefold() == ".docx":
            worker = _PrepareWordWorker(
                word_service=self.word_dispatch_service,
                person=person,
                docx_path=scan_path,
                output_directory=output_directory,
            )
            self._start_worker(
                worker,
                completed=self._split_completed,
                progress_text="Преобразую сохранённый Word в PDF и разделяю запросы…",
                active_button=self.split_button,
            )
            return

        bundle_path = person_output / self.word_bundle_service.bundle_filename(
            person
        )
        if not bundle_path.is_file():
            bundle_path = None

        worker = _SplitScanWorker(
            scan_service=self.signed_scan_service,
            person=person,
            bundle_path=bundle_path,
            scan_path=scan_path,
            output_directory=output_directory,
        )
        self._start_worker(
            worker,
            completed=self._split_completed,
            progress_text=(
                "Распознаю исходящие номера и разбиваю общий PDF…"
            ),
            active_button=self.split_button,
        )

    def create_drafts(self) -> None:
        if self._work_thread is not None:
            self._show_busy_message()
            return

        manifest_path = Path(self.package_input.text().strip())
        if not manifest_path.is_file():
            self.choose_package()
            manifest_path = Path(self.package_input.text().strip())
            if not manifest_path.is_file():
                return

        worker = _CreateDraftsWorker(
            package_store=self.package_store,
            draft_service=self.outlook_draft_service,
            manifest_path=manifest_path,
        )
        self._start_worker(
            worker,
            completed=self._drafts_completed,
            progress_text="Создаю черновики Outlook…",
            active_button=self.create_drafts_button,
        )

    def _start_worker(
        self,
        worker: QObject,
        *,
        completed,
        progress_text: str,
        active_button: QPushButton,
    ) -> None:
        self._progress_dialog = QProgressDialog(
            progress_text,
            "",
            0,
            0,
            self,
        )
        self._progress_dialog.setCancelButton(None)
        self._progress_dialog.setWindowModality(
            Qt.WindowModality.WindowModal
        )
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.show()

        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(completed)
        worker.failed.connect(self._operation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._worker_cleanup)

        active_button.setEnabled(False)
        self._active_button = active_button
        self._work_thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _split_completed(self, preparation) -> None:
        self._close_progress()
        self.package_input.setText(str(preparation.manifest_path))

        message = (
            f"Создано отдельных PDF: {len(preparation.attachments)}\n\n"
            f"Папка пакета:\n{preparation.output_directory}\n\n"
            "Если Outlook находится на другом компьютере, перенесите туда "
            "всю эту папку целиком и дважды нажмите файл "
            f"«{self.package_store.LAUNCHER_FILENAME}». Устанавливать "
            "NexusDocs на тот компьютер не нужно."
        )
        if preparation.missing_email_attachments:
            missing = ", ".join(
                (
                    f"{attachment.abbreviation} "
                    f"({attachment.display_outgoing_number})"
                    if attachment.abbreviation
                    else attachment.display_outgoing_number
                )
                for attachment in preparation.missing_email_attachments
            )
            message += (
                "\n\nPDF без электронной почты тоже созданы; черновики "
                f"для них будут пропущены: {missing}."
            )
        QMessageBox.information(self, "PDF разделён", message)
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(preparation.output_directory))
        )

    @Slot(object, object)
    def _drafts_completed(self, package, drafts) -> None:
        self._close_progress()
        message = (
            f"Создано черновиков Outlook: {len(drafts.created)}.\n"
            "Письма сохранены в папке «Черновики». "
            "NexusDocs ничего не отправлял."
        )
        if drafts.skipped_without_email:
            skipped = ", ".join(
                (
                    f"{attachment.abbreviation} "
                    f"({attachment.display_outgoing_number})"
                    if attachment.abbreviation
                    else attachment.display_outgoing_number
                )
                for attachment in drafts.skipped_without_email
            )
            message += (
                "\n\nБез черновика — в шапке не указана почта: "
                + skipped
            )
        QMessageBox.information(self, "Черновики готовы", message)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self._close_progress()
        QMessageBox.warning(self, "Операция остановлена", message)

    @Slot()
    def _worker_cleanup(self) -> None:
        if self._active_button is not None:
            self._active_button.setEnabled(True)
        self._active_button = None
        self._work_thread = None
        self._worker = None
        self._progress_dialog = None

    def _close_progress(self) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()

    def _selected_person(self):
        person_id = self.person_combo.currentData()
        return self._people_by_id.get(person_id)

    def _selected_person_output_directory(self) -> Path:
        person_id = self.person_combo.currentData()
        if person_id is None:
            return self._project_directory() / "output"
        return self._project_directory() / "output" / str(person_id)

    @staticmethod
    def _project_directory() -> Path:
        return Path(__file__).resolve().parents[1]

    def _show_busy_message(self) -> None:
        QMessageBox.information(
            self,
            "Обработка уже идёт",
            "Дождитесь завершения текущей операции.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._work_thread is not None:
            self._show_busy_message()
            event.ignore()
            return
        super().closeEvent(event)
