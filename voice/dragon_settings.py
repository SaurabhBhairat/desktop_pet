"""
dragon_settings.py - the dragon's own settings (saved in voice\\dragon_prefs.json).

    mode          "talk" | "type" | "both"   how you and the dragon communicate
    cursor_look   True/False                 turns toward your mouse, reacts to hovering
    cursor_chase  True/False                 walks after your mouse (off by default)
    quiet_on      True/False                 quiet hours: the dragon never speaks first
    quiet_from    0-23                       quiet hours start (hour)
    quiet_to      0-23                       quiet hours end (hour)
    speak_first   "never" | "rarely" | "sometimes" | "often"   how much it starts chats

This file never touches shared\\settings.json.
"""
import datetime
import json
from pathlib import Path

PREFS_PATH = Path(__file__).resolve().parent / "dragon_prefs.json"

DEFAULTS = {
    "mode": "both",
    "cursor_look": True,
    "cursor_chase": False,
    "quiet_on": True,
    "quiet_from": 22,
    "quiet_to": 8,
    "speak_first": "sometimes",
}
MODES = ("talk", "type", "both")
FREQUENCIES = ("never", "rarely", "sometimes", "often")
# minutes the dragon waits between messages it starts itself
SPEAK_GAP_MINUTES = {"never": None, "rarely": 90, "sometimes": 40, "often": 15}


def load_prefs(path=PREFS_PATH):
    prefs = dict(DEFAULTS)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            prefs.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:
        pass
    if prefs["mode"] not in MODES:
        prefs["mode"] = DEFAULTS["mode"]
    if prefs["speak_first"] not in FREQUENCIES:
        prefs["speak_first"] = DEFAULTS["speak_first"]
    for k in ("quiet_from", "quiet_to"):
        try:
            prefs[k] = max(0, min(23, int(prefs[k])))
        except Exception:
            prefs[k] = DEFAULTS[k]
    for k in ("cursor_look", "cursor_chase", "quiet_on"):
        prefs[k] = bool(prefs[k])
    return prefs


def save_prefs(prefs, path=PREFS_PATH):
    clean = {k: prefs.get(k, DEFAULTS[k]) for k in DEFAULTS}
    try:
        Path(path).write_text(json.dumps(clean, indent=2), encoding="utf-8")
        return True
    except Exception as exc:
        print("Could not save dragon settings:", exc)
        return False


def in_quiet_hours(prefs, hour=None):
    """True when the dragon should not start a conversation."""
    if not prefs.get("quiet_on"):
        return False
    h = datetime.datetime.now().hour if hour is None else hour
    a, b = prefs["quiet_from"], prefs["quiet_to"]
    if a == b:
        return False
    return (a <= h < b) if a < b else (h >= a or h < b)


def may_speak_first(prefs, hour=None):
    return SPEAK_GAP_MINUTES[prefs["speak_first"]] is not None and not in_quiet_hours(prefs, hour)


# ---------------------------------------------------------------- the panel
def make_dialog(prefs, on_change, parent=None):
    """Builds the settings window. on_change(new_prefs) is called after every change."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
                                   QHBoxLayout, QLabel, QRadioButton, QSpinBox, QVBoxLayout)

    dlg = QDialog(parent)
    dlg.setWindowTitle("Baby Dragon - Settings")
    dlg.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
    dlg.setMinimumWidth(340)
    dlg.setStyleSheet("""
        QDialog { background:#1d1530; }
        QLabel, QCheckBox, QRadioButton, QGroupBox { color:#eadcff; font-size:13px; }
        QGroupBox { border:1px solid #5b3f99; border-radius:8px; margin-top:12px; padding:10px 8px 6px 8px; }
        QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px; color:#c9a8ff; }
        QSpinBox, QComboBox { background:#2c2045; color:#fff; border:1px solid #5b3f99; padding:2px 6px; }
    """)
    state = dict(prefs)

    def changed():
        on_change(dict(state))

    root = QVBoxLayout(dlg)

    # --- talk / type / both
    box = QGroupBox("How do we talk?")
    row = QHBoxLayout(box)
    radios = {}
    for key, label in (("talk", "Talk (voice)"), ("type", "Type (text)"), ("both", "Both")):
        rb = QRadioButton(label)
        rb.setChecked(state["mode"] == key)
        rb.toggled.connect(lambda on, k=key: on and (state.__setitem__("mode", k), changed()))
        radios[key] = rb
        row.addWidget(rb)
    root.addWidget(box)

    # --- cursor
    box = QGroupBox("Your mouse")
    col = QVBoxLayout(box)
    look = QCheckBox("Look at my mouse and react when I hover on it")
    look.setChecked(state["cursor_look"])
    look.toggled.connect(lambda on: (state.__setitem__("cursor_look", bool(on)), changed()))
    chase = QCheckBox("Chase my mouse along the screen (can be annoying)")
    chase.setChecked(state["cursor_chase"])
    chase.toggled.connect(lambda on: (state.__setitem__("cursor_chase", bool(on)), changed()))
    col.addWidget(look)
    col.addWidget(chase)
    root.addWidget(box)

    # --- speaking first
    box = QGroupBox("Dragon starts chats")
    form = QFormLayout(box)
    freq = QComboBox()
    for f in FREQUENCIES:
        freq.addItem(f.capitalize(), f)
    freq.setCurrentIndex(FREQUENCIES.index(state["speak_first"]))
    freq.currentIndexChanged.connect(
        lambda i: (state.__setitem__("speak_first", FREQUENCIES[i]), changed()))
    form.addRow(QLabel("How often:"), freq)
    quiet = QCheckBox("Quiet hours (it will not speak first)")
    quiet.setChecked(state["quiet_on"])
    quiet.toggled.connect(lambda on: (state.__setitem__("quiet_on", bool(on)), changed()))
    form.addRow(quiet)
    qf, qt = QSpinBox(), QSpinBox()
    for sp, key in ((qf, "quiet_from"), (qt, "quiet_to")):
        sp.setRange(0, 23)
        sp.setSuffix(":00")
        sp.setValue(state[key])
        sp.valueChanged.connect(lambda v, k=key: (state.__setitem__(k, int(v)), changed()))
    form.addRow(QLabel("From:"), qf)
    form.addRow(QLabel("Until:"), qt)
    root.addWidget(box)

    note = QLabel("Changes are saved instantly.")
    note.setStyleSheet("color:#a58bd6; font-size:11px;")
    root.addWidget(note)
    return dlg
