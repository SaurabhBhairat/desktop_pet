"""
run_dragon.py - starts the dragon window AND the voice assistant together.

Run:  .\\voice_env\\Scripts\\python.exe run_dragon.py
Talk to the dragon: double-click it, or press ENTER in this terminal.

Only one dragon runs at a time: starting it again (for example with the Windows
shortcut key) just brings the running dragon back to the screen.
"""
import queue
import sys
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

MODEL = ROOT / "assets" / "models" / "baby_dragon_idle.glb"
SERVER_NAME = "BabyDragonSingleInstance"


def already_running():
    """If a dragon is already running, ask it to show itself and report True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def init_com():
    """Windows speech (pyttsx3/SAPI) needs COM started in any non-main thread."""
    for name in ("pythoncom", "comtypes"):
        try:
            getattr(__import__(name), "CoInitialize")()
            return
        except Exception:
            pass


def voice_worker(win, jobs):
    from voice.assistant_voice import BabyDragonVoice      # heavy imports happen here, in the background
    init_com()
    emit = win.state_requested.emit
    try:
        dragon = BabyDragonVoice()
    except Exception:
        traceback.print_exc()
        print("Could not start the voice assistant; the dragon will just wander.")
        return

    print("Dragon is ready. Double-click it, or press ENTER here, to talk.")
    from voice import dragon_settings
    say = win.say_requested.emit

    def voice_on():                              # read live, so the settings panel applies at once
        return dragon_settings.answer_voice(win._prefs)

    def bubble_on():
        return dragon_settings.answer_bubble(win._prefs)

    while True:
        kind, text = jobs.get()                  # ("voice", None) or ("text", "the question")
        try:
            if kind == "text":
                dragon.reply_to_text(text, on_state=emit, on_text=say, voice_on=voice_on, bubble_on=bubble_on)
            else:
                dragon.listen_and_reply(on_state=emit, on_text=say, voice_on=voice_on, bubble_on=bubble_on)
        except Exception:
            traceback.print_exc()
        finally:
            emit("idle")


def enter_listener(jobs):
    while True:
        try:
            input()
        except EOFError:
            return
        if jobs.empty():
            jobs.put(("voice", None))


def main():
    app = QApplication(sys.argv)
    if already_running():
        return                                   # the running dragon was asked to show itself

    from voice.dragon_window import DragonWindow
    win = DragonWindow(str(MODEL))
    win.show()

    QLocalServer.removeServer(SERVER_NAME)       # clear any leftover from a crash
    server = QLocalServer()
    server.listen(SERVER_NAME)

    def on_connection():
        conn = server.nextPendingConnection()
        conn.readyRead.connect(lambda: (conn.readAll(), win.show_dragon()))
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)

    jobs = queue.Queue()                         # questions waiting for the assistant

    def ask_by_voice():
        if jobs.empty():
            jobs.put(("voice", None))

    def ask_by_text(text):
        if jobs.empty():
            jobs.put(("text", text))

    win.talk_requested.connect(ask_by_voice)
    win.text_submitted.connect(ask_by_text)

    threading.Thread(target=voice_worker, args=(win, jobs), daemon=True).start()
    threading.Thread(target=enter_listener, args=(jobs,), daemon=True).start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()