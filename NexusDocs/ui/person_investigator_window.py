from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QPushButton, QVBoxLayout

from domain.value_objects.investigator import INVESTIGATORS, investigator_from_key


class PersonInvestigatorWindow(QDialog):
    """First step shared by creation and editing."""

    def __init__(self, form_data, parent=None):
        super().__init__(parent)
        self.form_data = form_data
        self.setWindowTitle("Исполнитель")
        self.resize(610, 220)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите исполнителя для документов этого человека:"))
        self.investigator_combo = QComboBox()
        for profile in INVESTIGATORS:
            self.investigator_combo.addItem(profile.display_name, profile.key)
        self.investigator_combo.setCurrentIndex(
            self.investigator_combo.findData(form_data.investigator.key)
        )
        layout.addWidget(self.investigator_combo)
        layout.addStretch()
        self.next_button = QPushButton("Далее")
        self.next_button.clicked.connect(self.save_form)
        layout.addWidget(self.next_button)
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

    def save_form(self):
        self.form_data.investigator = investigator_from_key(
            self.investigator_combo.currentData()
        )
        self.accept()
