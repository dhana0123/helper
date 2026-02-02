import sys
import markdown
import keyboard
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
                             QLabel, QPushButton, QHBoxLayout, QSizeGrip)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPalette, QFont

from utils import take_screenshot, set_window_affinity
from worker import AnalysisWorker

# Signal bridge for handling hotkey events in the main thread
class HotkeyBridge(QObject):
    triggered = pyqtSignal()

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Coding Assistant")
        
        # Window Flags: Frameless, Always on Top
        # Note: avoid Qt.Tool here because some tool-window styles can interfere
        # with SetWindowDisplayAffinity on certain Windows builds.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                    Qt.WindowType.WindowStaysOnTopHint)
        
        # Transparency/Opacity
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.9)  # Slightly transparent
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Set dark theme style
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                border-radius: 10px;
                border: 1px solid #333;
            }
            QTextEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: none;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 14px;
            }
            QLabel {
                font-weight: bold;
                color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton#closeBtn {
                background-color: #c53030;
            }
            QPushButton#closeBtn:hover {
                background-color: #e53e3e;
            }
        """)

        # Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header_layout = QHBoxLayout()
        self.status_label = QLabel("Ready (Ctrl+Alt+S)")
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close)
        
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_btn)
        self.layout.addLayout(header_layout)
        
        # Content Area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.layout.addWidget(self.text_area)
        
        # Resize Grip (Bottom Right)
        # Note: Frameless windows lose native resizing, so we can add a size grip or implement manual resizing.
        # For simplicity in this script, we'll rely on the user positioning it initially or simple size grip logic.
        # But QSizeGrip usually requires a StatusBar or corner. We'll skip for now or add a simple footer.
        
        # Initial geometry
        self.resize(600, 400)
        self.center_on_screen()

        # Variables for dragging functionality
        self.old_pos = None

    def showEvent(self, event):
        super().showEvent(event)
        # Apply Privacy Mode (Window Affinity) - doing this in showEvent ensures handle exists and is ready
        self.apply_privacy()

    def center_on_screen(self):
        # Basic centering
        screen = QApplication.primaryScreen()
        rect = screen.availableGeometry()
        self.move(rect.width() // 2 - 300, rect.height() // 2 - 200)

    def apply_privacy(self):
        # Get window handle
        hwnd = int(self.winId())
        # First attempt with current window attributes
        # Clear WS_EX_LAYERED if present (Qt may set layered style for translucency)
        from utils import clear_ws_ex_layered, restore_exstyle
        prev_exstyle = clear_ws_ex_layered(hwnd)

        success = set_window_affinity(hwnd, allow_capture=False)
        if success:
            print("Privacy mode enabled: Window excluded from capture.")
            self.status_label.setText("Ready (Privacy On) - Ctrl+Alt+S")
        if success:
            # restore exstyle if we changed it
            try:
                restore_exstyle(hwnd, prev_exstyle)
            except Exception:
                pass
            return

        # If initial attempt failed, it may be due to the window being layered/translucent.
        # Try temporarily disabling translucency and retrying.
        prev_translucent = self.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        prev_opacity = self.windowOpacity()
        try:
            print("Initial privacy enable failed; retrying without translucency/opacities...")
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setWindowOpacity(1.0)

            # Clear again in case Qt re-applied layered style
            prev_exstyle_2 = clear_ws_ex_layered(hwnd)

            success = set_window_affinity(hwnd, allow_capture=False)
            if success:
                print("Privacy mode enabled after disabling translucency/opacities.")
                self.status_label.setText("Ready (Privacy On) - Ctrl+Alt+S")
                # restore exstyle if we changed it
                try:
                    restore_exstyle(hwnd, prev_exstyle_2)
                except Exception:
                    pass
                return
            else:
                print("Failed to enable privacy mode even after retry.")
                self.status_label.setText("Ready (Privacy Fail) - Ctrl+Alt+S")
        finally:
            # Restore previous attributes and any exstyle we saved earlier
            try:
                restore_exstyle(hwnd, prev_exstyle)
            except Exception:
                pass
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, prev_translucent)
            self.setWindowOpacity(prev_opacity)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def start_analysis(self):
        self.status_label.setText("Capturing & Analyzing...")
        self.text_area.setHtml("<i>Processing...</i>")
        
        # 1. Take Screenshot
        # Note: Even with affinity, it's safer to use the dedicated privacy flag.
        # But we capture the screen. The overlay itself won't be in it due to affinity.
        screenshot = take_screenshot()
        
        if not screenshot:
            self.status_label.setText("Screenshot Failed")
            return

        # 2. Start Worker
        self.worker = AnalysisWorker(screenshot)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.error.connect(self.on_analysis_error)
        self.worker.start()

    def on_analysis_finished(self, result_markdown):
        self.status_label.setText("Ready")
        # Convert markdown to basic HTML for display
        html = markdown.markdown(result_markdown, extensions=['fenced_code', 'codehilite'])
        
        # Wrap code blocks in some styling if needed (basic markdown output is often raw)
        # We can add some CSS for code blocks in `setStyleSheet` but `markdown` lib produces <pre><code>
        
        self.text_area.setHtml(html)

    def on_analysis_error(self, error_msg):
        self.status_label.setText("Error")
        self.text_area.setPlainText(f"Error: {error_msg}")

def main():
    app = QApplication(sys.argv)
    
    window = OverlayWindow()
    window.show()

    # Hotkey Handling
    hotkey_bridge = HotkeyBridge()
    hotkey_bridge.triggered.connect(window.start_analysis)

    def hotkey_callback():
        hotkey_bridge.triggered.emit()

    try:
        # Register global hotkey
        keyboard.add_hotkey('ctrl+alt+s', hotkey_callback)
    except Exception as e:
        print(f"Failed to register hotkey: {e}")

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
