"""
run_dragon.py - starts the dragon window AND the voice assistant together.

Run:  .\\voice_env\\Scripts\\python.exe run_dragon.py
Talk to the dragon: double-click it, or press ENTER in this terminal.

Only one dragon runs at a time: starting it again (for example with the Windows
shortcut key) just brings the running dragon back to the screen.
"""
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


def voice_worker(win, talk_event):
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
    while True:
        talk_event.wait()
        talk_event.clear()
        try:
            dragon.listen_and_reply(on_state=emit)
        except Exception:
            traceback.print_exc()
        finally:
            emit("idle")


def enter_listener(talk_event):
    while True:
        try:
            input()
        except EOFError:
            return
        talk_event.set()


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

    talk_event = threading.Event()
    win.talk_requested.connect(talk_event.set)

    threading.Thread(target=voice_worker, args=(win, talk_event), daemon=True).start()
    threading.Thread(target=enter_listener, args=(talk_event,), daemon=True).start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()