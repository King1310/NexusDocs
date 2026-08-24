from collections.abc import Sequence

from PySide6.QtWidgets import QDialog


BACK_DIALOG_CODE = 2


def run_form_sequence(
    parent,
    form_data,
    dialog_types: Sequence[type[QDialog]],
) -> bool:
    """Run form dialogs with working Back navigation."""

    step_index = 0
    while step_index < len(dialog_types):
        dialog = dialog_types[step_index](
            form_data=form_data,
            parent=parent,
        )
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            step_index += 1
            continue
        if result == BACK_DIALOG_CODE and step_index > 0:
            step_index -= 1
            continue
        return False

    return True
