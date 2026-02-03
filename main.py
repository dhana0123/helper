import sys
import markdown
import keyboard
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
                             QLabel, QPushButton, QHBoxLayout, QSizeGrip)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPalette, QFont

from utils import take_screenshot, set_window_affinity
from worker import AnalysisWorker

# For syntax highlighting
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False

# Custom QTextEdit that always shows arrow cursor
class ArrowCursorTextEdit(QTextEdit):
    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().enterEvent(event)
    
    def mouseMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)
    
    def cursorRect(self, cursor=None):
        # Return empty rect to prevent cursor rendering
        from PyQt6.QtCore import QRect
        return QRect()
    
    def paintEvent(self, event):
        # Paint but hide the text cursor
        super().paintEvent(event)
        # Force arrow cursor after paint
        self.setCursor(Qt.CursorShape.ArrowCursor)

# Custom QTextEdit for prompt input with Enter to submit
class PromptInputEdit(QTextEdit):
    submit_requested = pyqtSignal(str)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Enter for multiline support
            super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Return:
            # Enter to submit
            text = self.toPlainText().strip()
            if text:
                self.submit_requested.emit(text)
                self.clear()
        else:
            super().keyPressEvent(event)

# Signal bridge for handling hotkey events in the main thread
class HotkeyBridge(QObject):
    triggered = pyqtSignal()

class PromptHotkeyBridge(QObject):
    triggered = pyqtSignal()

class ScreenshotPromptHotkeyBridge(QObject):
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
        # Ensure cursor stays as arrow pointer
        self.setCursor(Qt.CursorShape.ArrowCursor)
        
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
                font-size: 16px;
            }
            QLabel {
                font-weight: bold;
                color: #007acc;
                font-size: 16px;
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
        
        # Custom Prompt Input
        self.prompt_input = PromptInputEdit()
        self.prompt_input.setPlaceholderText("Enter your prompt and press Enter to send...")
        self.prompt_input.setMaximumHeight(60)
        self.prompt_input.setStyleSheet("""
            QTextEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #0e639c;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 14px;
                padding: 5px;
                border-radius: 4px;
            }
        """)
        self.prompt_input.submit_requested.connect(self.on_custom_prompt)
        
        self.layout.addWidget(self.prompt_input)
        
        # Content Area (scrollable)
        from PyQt6.QtWidgets import QScrollArea
        self.text_area = QLabel()
        self.text_area.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text_area.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_area.setStyleSheet("background-color: #252526; color: #d4d4d4; font-family: Consolas, 'Courier New', monospace; font-size: 16px; border: none;")
        self.text_area.setCursor(Qt.CursorShape.ArrowCursor)
        self.text_area.setWordWrap(True)
        self.text_area.setText("")
        self.text_area.setTextFormat(Qt.TextFormat.RichText)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.text_area)
        self.layout.addWidget(self.scroll_area)
        
        # Resize Grip (Bottom Right)
        # Note: Frameless windows lose native resizing, so we can add a size grip or implement manual resizing.
        # For simplicity in this script, we'll rely on the user positioning it initially or simple size grip logic.
        # But QSizeGrip usually requires a StatusBar or corner. We'll skip for now or add a simple footer.
        
        # Initial geometry
        self.resize(600, 600)  # Increased height for prompt input
        self.center_on_screen()

        # Variables for dragging functionality
        self.old_pos = None
        
        # Store the custom prompt for global hotkey
        self.pending_custom_prompt = None

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

    def enterEvent(self, event):
        # When mouse enters the window, ensure cursor is arrow
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        # Always keep cursor as arrow pointer
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def on_custom_prompt(self, prompt_text):
        """Handle custom prompt submission via Enter key or global hotkey."""
        self.status_label.setText("Sending Prompt...")
        self.text_area.setTextFormat(Qt.TextFormat.RichText)
        self.text_area.setText("<i>Processing...</i>")
        
        # Start worker with text-only prompt (no image)
        self.worker = AnalysisWorker(image=None, prompt=prompt_text)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.error.connect(self.on_analysis_error)
        self.worker.start()

    def start_analysis_with_prompt(self):
        """Take screenshot and send it with the prompt text entered in the input field."""
        prompt_text = self.prompt_input.toPlainText().strip()
        
        if not prompt_text:
            self.status_label.setText("Error: Please enter a prompt first")
            self.text_area.setText("Please enter a prompt and try again")
            return
        
        # Bring window to foreground
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except:
            pass
        
        self.status_label.setText("Capturing & Analyzing with Prompt...")
        self.text_area.setTextFormat(Qt.TextFormat.RichText)
        self.text_area.setText("<i>Processing...</i>")
        
        # Take screenshot
        screenshot = take_screenshot()
        
        if not screenshot:
            self.status_label.setText("Screenshot Failed")
            return
        
        # Start worker with both screenshot and prompt
        self.worker = AnalysisWorker(image=screenshot, prompt=prompt_text)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.error.connect(self.on_analysis_error)
        self.worker.start()

    def start_analysis(self):
        # Bring window to foreground
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except:
            pass
        
        self.status_label.setText("Capturing & Analyzing...")
        self.text_area.setTextFormat(Qt.TextFormat.RichText)
        self.text_area.setText("<i>Processing...</i>")
        
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
        
        # Add custom CSS for green code highlighting
        custom_css = """
        <style>
            pre { background-color: #1e1e1e !important; padding: 10px; border-radius: 4px; margin: 10px 0; }
            code { color: #00ff00 !important; font-family: 'Courier New', monospace; background-color: #1e1e1e; padding: 2px 4px; border-radius: 3px; }
            pre code { background-color: #1e1e1e !important; color: #00ff00 !important; }
        </style>
        """
        
        # Convert markdown to HTML without codehilite to avoid conflicts
        html = markdown.markdown(
            result_markdown, 
            extensions=['fenced_code', 'extra', 'tables']
        )
        
        # Replace code block styling
        html = html.replace('<pre><code>', '<pre><code style="color: #00ff00; background-color: #1e1e1e;">')
        html = html.replace('<code>', '<code style="color: #00ff00;">')
        html = custom_css + html
        
        self.text_area.setText("")
        self.text_area.setTextFormat(Qt.TextFormat.RichText)
        self.text_area.setText(html)

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
    
    # Custom prompt hotkey bridge
    prompt_hotkey_bridge = PromptHotkeyBridge()
    
    # Screenshot + Prompt hotkey bridge
    screenshot_prompt_hotkey_bridge = ScreenshotPromptHotkeyBridge()
    
    def on_prompt_hotkey():
        """Handle prompt hotkey in the main thread."""
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        window.show()
        window.raise_()
        window.activateWindow()
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(window.winId()))
        except:
            pass
        window.prompt_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    
    def on_screenshot_prompt_hotkey():
        """Handle screenshot + prompt hotkey in the main thread."""
        window.start_analysis_with_prompt()
    
    prompt_hotkey_bridge.triggered.connect(on_prompt_hotkey)
    screenshot_prompt_hotkey_bridge.triggered.connect(on_screenshot_prompt_hotkey)

    def hotkey_callback():
        hotkey_bridge.triggered.emit()
    
    def prompt_hotkey_callback():
        """Emit signal to focus prompt input from the main thread."""
        prompt_hotkey_bridge.triggered.emit()
    
    def screenshot_prompt_hotkey_callback():
        """Emit signal to take screenshot and send with prompt."""
        screenshot_prompt_hotkey_bridge.triggered.emit()

    try:
        # Register global hotkey for screen analysis (Ctrl+Alt+S)
        keyboard.add_hotkey('ctrl+alt+s', hotkey_callback)
        print("Registered hotkey: Ctrl+Alt+S for screen analysis")
        
        # Register global hotkey for custom prompt (Ctrl+Alt+M)
        keyboard.add_hotkey('ctrl+alt+m', prompt_hotkey_callback)
        print("Registered hotkey: Ctrl+Alt+M for custom prompt")
        
        # Register global hotkey for screenshot + prompt (Ctrl+Alt+T)
        keyboard.add_hotkey('ctrl+alt+t', screenshot_prompt_hotkey_callback)
        print("Registered hotkey: Ctrl+Alt+T for screenshot + prompt")
    except Exception as e:
        print(f"Failed to register hotkey: {e}")

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
