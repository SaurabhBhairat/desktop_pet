"""
dragon_bubble.py - the dragon's speech bubble and the little box you type into.

The bubble is its own transparent window next to the dragon, so the dragon window does not have to grow.
Long answers scroll (mouse wheel or the scrollbar); the bubble stays open while your mouse is on it.
Buttons: Copy (the whole answer to the clipboard) and Close. Answers can use markdown (lists, code, bold).
"""
TAIL = 12                  # height of the little pointer toward the dragon
TEXT_WIDTH = 320           # widest the text area gets
MAX_TEXT_HEIGHT = 340      # taller answers scroll
BUTTON_ROW = 26
MAX_CHARS = 8000


def show_seconds(text):
    """How long to keep the bubble up (the clock restarts while your mouse is on it)."""
    return max(8.0, min(60.0, 4.0 + len(text) / 12.0))


def place(bw, bh, dragon, screen):
    """Where to put a bubble of size bw x bh next to the dragon.
    dragon, screen: (left, top, right, bottom).  Returns (x, y, tail_down).
    Above the dragon's head if there is room, otherwise below; always kept on screen."""
    dl, dt, dr, db = dragon
    sl, st, sr, sb = screen
    x = (dl + dr) // 2 - bw // 2
    x = max(sl + 4, min(x, sr - bw - 4))
    y = dt + 14 - bh                       # the dragon's head is a little below its window top
    tail_down = True
    if y < st + 4:
        y = db - 14                        # not enough room above: hang below the dragon
        tail_down = False
    y = max(st + 4, min(y, sb - bh - 4))
    return x, y, tail_down


def text_height_limit(screen_height):
    """Tallest text area allowed: never more than about 45% of the screen."""
    return max(120, min(MAX_TEXT_HEIGHT, int(screen_height * 0.45)))


class BubbleWindow:
    """Created lazily by the dragon window. Needs PySide6, imported inside so the helpers above stay testable."""

    def __new__(cls, get_dragon_rect):
        from PySide6.QtCore import QPointF, Qt, QTimer
        from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen, QPolygonF
        from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QTextBrowser, QWidget

        button_style = ("QPushButton { background:#e6d5ff; color:#3a1f70; border:1px solid #b890ff;"
                        " border-radius:8px; font-size:11px; padding:0 8px; }"
                        "QPushButton:hover { background:#d4b8ff; }")

        class _Bubble(QWidget):
            def __init__(self):
                super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                                 | Qt.WindowDoesNotAcceptFocus)
                self.setAttribute(Qt.WA_TranslucentBackground, True)
                self.setAttribute(Qt.WA_ShowWithoutActivating, True)
                self._tail_down = True
                self._text = ""
                self._body = (100, 60)
                self._hide_ms = 8000

                self._view = QTextBrowser(self)
                self._view.setFrameShape(QFrame.NoFrame)
                self._view.setOpenLinks(False)
                self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self._view.setStyleSheet(
                    "QTextBrowser { background:transparent; color:#2a1650; font-size:13px; border:none; }"
                    "QScrollBar:vertical { width:8px; background:transparent; margin:0; }"
                    "QScrollBar::handle:vertical { background:#b890ff; border-radius:4px; min-height:24px; }"
                    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }")

                self._copy = QPushButton("Copy", self)
                self._copy.setStyleSheet(button_style)
                self._copy.clicked.connect(self._copy_text)
                self._close = QPushButton("Close", self)
                self._close.setStyleSheet(button_style)
                self._close.clicked.connect(self.hide)

                self._hide_timer = QTimer(self)
                self._hide_timer.setSingleShot(True)
                self._hide_timer.timeout.connect(self.hide)
                self._follow = QTimer(self)                 # stays next to the dragon while it moves
                self._follow.timeout.connect(self._tick)

            # ---------------------------------------------------------- showing
            def show_text(self, text):
                text = str(text).strip()
                if len(text) > MAX_CHARS:
                    text = text[:MAX_CHARS].rstrip() + "\n\n... (cut off)"
                growing = self.isVisible() and bool(self._text) and text.startswith(self._text)
                bar = self._view.verticalScrollBar()
                old_pos, at_bottom = bar.value(), bar.value() >= bar.maximum() - 4
                self._text = text
                self._view.setMarkdown(text)
                d = get_dragon_rect()
                scr = QGuiApplication.screenAt(d.center()) or QGuiApplication.primaryScreen()
                max_h = text_height_limit(scr.availableGeometry().height())

                doc = self._view.document()
                doc.setTextWidth(TEXT_WIDTH - 14)             # measure at full width first...
                width = max(120, min(TEXT_WIDTH, int(doc.idealWidth()) + 22))
                doc.setTextWidth(width - 14)                  # ...then at the width we really use
                height = max(30, min(int(doc.size().height()) + 8, max_h))
                self._view.setFixedSize(width, height)

                bw = width + 20
                bh = 8 + height + 4 + BUTTON_ROW + 6
                self._body = (bw, bh)
                self.setFixedSize(bw, bh + TAIL)
                if growing:        # the answer is still being written: stay at the bottom, or where you scrolled to
                    QTimer.singleShot(0, lambda: bar.setValue(bar.maximum() if at_bottom else old_pos))
                else:
                    bar.setValue(0)
                self._copy.setText("Copy")
                self._layout_children()
                self._reposition()
                self.show()
                self.raise_()
                self._hide_ms = int(show_seconds(text) * 1000)
                self._hide_timer.start(self._hide_ms)
                self._follow.start(50)

            def _layout_children(self):
                bw, bh = self._body
                off = 0 if self._tail_down else TAIL
                self._view.move(10, 8 + off)
                y = 8 + self._view.height() + 4 + off
                self._close.setGeometry(bw - 10 - 56, y, 56, BUTTON_ROW - 4)
                self._copy.setGeometry(bw - 10 - 56 - 6 - 56, y, 56, BUTTON_ROW - 4)

            def _reposition(self):
                d = get_dragon_rect()
                scr = QGuiApplication.screenAt(d.center()) or QGuiApplication.primaryScreen()
                s = scr.availableGeometry()
                x, y, tail_down = place(self.width(), self.height(),
                                        (d.left(), d.top(), d.right(), d.bottom()),
                                        (s.left(), s.top(), s.right(), s.bottom()))
                if tail_down != self._tail_down:
                    self._tail_down = tail_down
                    self._layout_children()
                    self.update()
                self.move(x, y)

            def _tick(self):
                self._reposition()
                if self.frameGeometry().contains(QCursor.pos()):   # reading or scrolling: keep it open
                    self._hide_timer.start(self._hide_ms)

            def hide(self):
                self._follow.stop()
                self._hide_timer.stop()
                super().hide()

            def _copy_text(self):
                QApplication.clipboard().setText(self._text)
                self._copy.setText("Copied!")
                QTimer.singleShot(1500, lambda: self._copy.setText("Copy"))

            # ---------------------------------------------------------- drawing
            def paintEvent(self, event):
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing, True)
                bw, bh = self._body
                top = 0 if self._tail_down else TAIL
                fill, edge = QColor("#f6edff"), QColor("#a070ff")
                path = QPainterPath()
                path.addRoundedRect(1, top + 1, bw - 2, bh - 2, 14, 14)
                p.setPen(QPen(edge, 2))
                p.setBrush(fill)
                p.drawPath(path)
                cx = bw // 2
                if self._tail_down:
                    tri = QPolygonF([QPointF(cx - 9, bh - 1), QPointF(cx + 9, bh - 1), QPointF(cx, bh + TAIL - 1)])
                else:
                    tri = QPolygonF([QPointF(cx - 9, top + 1), QPointF(cx + 9, top + 1), QPointF(cx, 1)])
                p.setPen(QPen(edge, 2))
                p.drawPolygon(tri)
                p.setPen(Qt.NoPen)                       # hide the bubble border where the pointer joins it
                p.setBrush(fill)
                if self._tail_down:
                    p.drawRect(cx - 8, bh - 3, 16, 4)
                else:
                    p.drawRect(cx - 8, top - 1, 16, 4)
                p.drawPolygon(tri)

        return _Bubble()


class TypeBox:
    """A tiny box to type a question to the dragon. Enter sends, Esc (or clicking elsewhere) closes it."""

    def __new__(cls, get_dragon_rect, on_submit):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

        class _Box(QWidget):
            def __init__(self):
                super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                self.setStyleSheet("QWidget { background:#2c2045; border:2px solid #a070ff; border-radius:12px; }"
                                   "QLineEdit { background:#f6edff; color:#2a1650; border-radius:8px;"
                                   " padding:6px 10px; font-size:14px; border:none; }")
                self._edit = QLineEdit(self)
                self._edit.setMaxLength(4000)                # long pasted questions are fine
                self._edit.setPlaceholderText("Type to the dragon, then press Enter...")
                self._edit.returnPressed.connect(self._send)
                lay = QHBoxLayout(self)
                lay.setContentsMargins(8, 8, 8, 8)
                lay.addWidget(self._edit)
                self.setFixedSize(330, 52)

            def open(self):
                d = get_dragon_rect()
                scr = QGuiApplication.screenAt(d.center()) or QGuiApplication.primaryScreen()
                s = scr.availableGeometry()
                x, y, _ = place(self.width(), self.height(),
                                (d.left(), d.top(), d.right(), d.bottom()),
                                (s.left(), s.top(), s.right(), s.bottom()))
                self.move(x, y)
                self._edit.clear()
                self.show()
                self.raise_()
                self.activateWindow()
                self._edit.setFocus()

            def _send(self):
                text = self._edit.text()
                self.hide()
                on_submit(text)

            def keyPressEvent(self, event):
                if event.key() == Qt.Key_Escape:
                    self.hide()
                else:
                    super().keyPressEvent(event)

            def event(self, e):
                if e.type() == QEvent.WindowDeactivate:      # clicked somewhere else
                    self.hide()
                return super().event(e)

        return _Box()
