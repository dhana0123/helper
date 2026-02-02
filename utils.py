import ctypes
from ctypes import windll, wintypes
from PIL import ImageGrab
import platform

# Additional WinAPI helpers
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000

# Constants for SetWindowDisplayAffinity
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # This is the key constant for hiding from capture

def take_screenshot():
    """
    Captures the entire screen and returns the PIL Image object.
    """
    try:
        # Capture the entire screen
        screenshot = ImageGrab.grab(all_screens=True)
        return screenshot
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return None

def set_window_affinity(hwnd, allow_capture=True):
    """
    Sets the window display affinity to exclude it from screen capture.
    
    Args:
        hwnd: The window handle (integer).
        allow_capture: Boolean. If False, the window will be hidden from captures.
    """
    if platform.system() != "Windows":
        print("SetWindowDisplayAffinity is only supported on Windows.")
        return False

    try:
        # Define arg/return types for clearer ctypes usage
        try:
            windll.user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
            windll.user32.SetWindowDisplayAffinity.argtypes = (wintypes.HWND, wintypes.DWORD)
        except Exception:
            # Older ctypes may not allow setting these, ignore silently
            pass

        affinity = WDA_NONE if allow_capture else WDA_EXCLUDEFROMCAPTURE
        result = windll.user32.SetWindowDisplayAffinity(hwnd, affinity)

        if result == 0:
            # Retrieve last error for diagnostics
            try:
                windll.kernel32.GetLastError.restype = wintypes.DWORD
                error_code = windll.kernel32.GetLastError()
            except Exception:
                error_code = None

            print(f"Failed to set display affinity (code={error_code}).")

            # If we attempted the newer exclude-from-capture flag, try the older monitor flag as fallback
            if not allow_capture:
                print("Attempting fallback to WDA_MONITOR...")
                result = windll.user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
                if result == 0:
                    try:
                        error_code = windll.kernel32.GetLastError()
                    except Exception:
                        error_code = None
                    print(f"Failed to set WDA_MONITOR (code={error_code}).")
                    return False
                print("Fallback to WDA_MONITOR successful.")
                return True

            return False

        return True
    except Exception as e:
        print(f"Error setting window affinity: {e}")
        return False


def _get_set_window_long_functions():
    """Return the appropriate Get/SetWindowLong functions for the platform (32/64-bit)."""
    try:
        # Prefer the "Ptr" variants on 64-bit
        GetWindowLong = windll.user32.GetWindowLongPtrW
        SetWindowLong = windll.user32.SetWindowLongPtrW
    except AttributeError:
        GetWindowLong = windll.user32.GetWindowLongW
        SetWindowLong = windll.user32.SetWindowLongW

    # Set arg/return types when possible
    try:
        GetWindowLong.restype = wintypes.LONG
        GetWindowLong.argtypes = (wintypes.HWND, wintypes.INT)
        SetWindowLong.restype = wintypes.LONG
        SetWindowLong.argtypes = (wintypes.HWND, wintypes.INT, wintypes.LONG)
    except Exception:
        pass

    return GetWindowLong, SetWindowLong


def clear_ws_ex_layered(hwnd):
    """If the window has WS_EX_LAYERED, clear it and return the previous exstyle.

    This helps SetWindowDisplayAffinity succeed on windows that would otherwise
    be layered (translucent) by Qt.
    """
    try:
        GetWindowLong, SetWindowLong = _get_set_window_long_functions()
        prev = GetWindowLong(hwnd, GWL_EXSTYLE)
        if prev & WS_EX_LAYERED:
            new = prev & ~WS_EX_LAYERED
            SetWindowLong(hwnd, GWL_EXSTYLE, new)
            # Trigger a frame change so styles take effect (best-effort)
            try:
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
            except Exception:
                pass
            return prev
        return prev
    except Exception as e:
        print(f"Error clearing WS_EX_LAYERED: {e}")
        return None


def restore_exstyle(hwnd, prev_exstyle):
    """Restore a previously saved exstyle (if provided)."""
    try:
        if prev_exstyle is None:
            return False
        _, SetWindowLong = _get_set_window_long_functions()
        SetWindowLong(hwnd, GWL_EXSTYLE, prev_exstyle)
        try:
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"Error restoring exstyle: {e}")
        return False
