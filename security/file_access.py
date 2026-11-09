
from pathlib import Path
import json
import tkinter as tk
from tkinter import filedialog


# Project settings location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "shared" / "settings.json"


def load_settings():
    """Load local settings safely."""
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def get_approved_folder():
    """Return the approved folder only when access is enabled."""
    settings = load_settings()

    if settings.get("privacy_lock", False):
        return None

    if settings.get("file_access") != "Approved folder":
        return None

    folder = settings.get("approved_folder")

    if not folder:
        return None

    try:
        approved_path = Path(folder).resolve()

        if approved_path.is_dir():
            return approved_path

    except (OSError, RuntimeError, ValueError):
        pass

    return None


def is_path_approved(file_path):
    """Check whether a file is inside the approved folder."""
    approved_folder = get_approved_folder()

    if approved_folder is None:
        return False

    try:
        candidate = Path(file_path).resolve(strict=True)

        if not candidate.is_file():
            return False

        return candidate.is_relative_to(approved_folder)

    except (OSError, RuntimeError, ValueError):
        return False


def read_approved_file(file_path):
    """Read a file only after checking its approval."""
    if not is_path_approved(file_path):
        raise PermissionError(
            "This file is outside the approved folder or access is disabled."
        )

    return Path(file_path).read_text(encoding="utf-8")


def choose_file():
    """Let the user explicitly select an approved file."""
    approved_folder = get_approved_folder()

    if approved_folder is None:
        raise PermissionError(
            "File access is disabled. Check Privacy Lock and folder approval."
        )

    root = tk.Tk()
    root.withdraw()

    try:
        selected_file = filedialog.askopenfilename(
            title="Choose a file for Baby Dragon",
            initialdir=str(approved_folder),
            filetypes=[
                ("Text files", "*.txt"),
                ("Python files", "*.py"),
                ("All files", "*.*")
            ]
        )
    finally:
        root.destroy()

    if not selected_file:
        return None

    if not is_path_approved(selected_file):
        raise PermissionError(
            "This file is outside the approved folder."
        )

    return selected_file
