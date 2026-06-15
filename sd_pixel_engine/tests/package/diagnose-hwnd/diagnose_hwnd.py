import os
import logging
from typing import Tuple, Optional
import time
from datetime import datetime

import mss
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw
import cv2
import numpy as np
import winreg


# ─────────────────────────────────────────────
#  Apply DPI awareness FIRST — before anything
# ─────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def get_windows_edition() -> Tuple[str, int]:
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
        edition_id = winreg.QueryValueEx(key, "EditionID")[0]
        build = int(winreg.QueryValueEx(key, "CurrentBuild")[0])
    return edition_id, build

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────
DWMWA_EXTENDED_FRAME_BOUNDS = 9
BLACK_RATIO_THRESHOLD = 0.05   # 5%
BLACK_PIXEL_THRESHOLD = 10
BOX_THICKNESS = 4
BOX_COLOR = (255, 0, 0)        # Red in RGB
MIN_WINDOW_SIZE = 10           # px — anything smaller is a shell/invisible window

# Window classes that DWM lies about — fall back to GetWindowRect for these
UNRELIABLE_DWM_CLASSES = {
    "Windows.UI.Core.CoreWindow",        # Notification Center, Action Center
    "ApplicationManager_DesktopShellWindow",  # Desktop shell (returns 0,0,0,0)
    "WorkerW",                           # Desktop background worker window
    "Progman",                           # Program Manager / desktop
}

# ─────────────────────────────────────────────
#  Logging setup
# ─────────────────────────────────────────────

def setup_logging(folder: str) -> logging.Logger:
    logger = logging.getLogger("ScreenCapture")
    logger.setLevel(logging.DEBUG)

    fmt_file = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - "
        "%(filename)s:%(lineno)d - %(funcName)s() - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fmt_console = logging.Formatter(
        "%(asctime)s - %(levelname)s - "
        "%(filename)s:%(lineno)d - %(message)s",
        datefmt="%H:%M:%S",
    )

    fh = logging.FileHandler(
        os.path.join(folder, "capture_log.txt"),
        encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt_file)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_console)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


# Bootstrap logger early so helpers can use it
_boot_folder = datetime.today().strftime("%Y-%m-%d")
os.makedirs(_boot_folder, exist_ok=True)
logger = setup_logging(_boot_folder)

edition_id, build = get_windows_edition()
logger.info(f"Windows build={build}  edition={edition_id}")

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def get_windows_edition() -> Tuple[str, int]:
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
        edition_id = winreg.QueryValueEx(key, "EditionID")[0]
        build = int(winreg.QueryValueEx(key, "CurrentBuild")[0])
    return edition_id, build


def get_dpi_scale_for_monitor(hwnd: int) -> float:
    """
    Return the DPI scale factor (e.g. 1.25 for 125%) for the monitor
    that contains the given window.  Falls back to the primary monitor.
    """
    try:
        hmonitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        ctypes.windll.shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        return dpi_x.value / 96.0
    except Exception:
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return dpi / 96.0
        except Exception:
            return 1.0


def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 255)
    return buf.value


def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 255)
    return buf.value


def get_true_window_rect(hwnd: int, window_class: str) -> Optional[Tuple[int, int, int, int]]:
    """
    Return the window's physical-pixel bounding rect.

    Strategy:
      - Classes in UNRELIABLE_DWM_CLASSES → use GetWindowRect
        (DWM returns wrong/zero coords for these system surfaces)
      - Everything else → DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)
        which strips the invisible shadow border correctly
    """
    use_get_window_rect = any(cls in window_class for cls in UNRELIABLE_DWM_CLASSES)

    if use_get_window_rect:
        try:
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
            logger.info(f"Using GetWindowRect for class '{window_class}'")
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception as e:
            logger.warning(f"GetWindowRect failed: {e}")
            return None
    else:
        try:
            rect = wintypes.RECT()
            ctypes.windll.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            logger.info(f"Using DwmGetWindowAttribute for class '{window_class}'")
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception as e:
            logger.warning(f"DwmGetWindowAttribute failed: {e}")
            return None


def get_virtual_screen_physical_origin() -> Tuple[int, int]:
    """
    Returns the physical-pixel origin of the virtual screen.
    GetSystemMetrics is DPI-aware when SetProcessDpiAwareness(2) is active,
    so this correctly handles multi-monitor setups with mixed scaling.
    """
    try:
        vx = ctypes.windll.user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = ctypes.windll.user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        return vx, vy
    except Exception:
        return 0, 0


# ─────────────────────────────────────────────
#  Logging setup
# ─────────────────────────────────────────────

def setup_logging(folder: str) -> logging.Logger:
    logger = logging.getLogger("ScreenCapture")
    logger.setLevel(logging.DEBUG)

    fmt_file = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_console = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    fh = logging.FileHandler(os.path.join(folder, "capture_log.txt"), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt_file)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_console)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

# ─────────────────────────────────────────────
#  Core capture
# ─────────────────────────────────────────────

def capture_screenshots(filename: str, ocr_filename: str) -> None:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        logger.warning("No active window found.")
        return

    window_title = get_window_title(hwnd)
    window_class = get_window_class(hwnd)
    logger.info(f"Capturing: '{window_title}'  (Class: {window_class})")

    # --- Get physical-pixel rect using the right method for this window class ---
    rect = get_true_window_rect(hwnd, window_class)
    if not rect:
        logger.warning("Could not get window rect — skipping.")
        return

    wx1, wy1, wx2, wy2 = rect
    win_w, win_h = wx2 - wx1, wy2 - wy1
    logger.info(f"Window physical rect  wx1={wx1} wy1={wy1} wx2={wx2} wy2={wy2}  (w={win_w} h={win_h})")

    # --- Guard: skip degenerate / invisible windows ---
    if win_w < MIN_WINDOW_SIZE or win_h < MIN_WINDOW_SIZE:
        logger.warning(
            f"Window rect too small ({win_w}×{win_h}) — "
            "likely a system shell or minimised window. Skipping."
        )
        return

    # --- Physical-pixel origin of the virtual screen ---
    vx1, vy1 = get_virtual_screen_physical_origin()
    logger.info(f"Virtual screen physical origin  vx1={vx1}  vy1={vy1}")

    with mss.mss() as sct:
        monitor_all = sct.monitors[0]
        shot = sct.grab(monitor_all)
        canvas = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        logger.info(f"Canvas size  w={canvas.width}  h={canvas.height}")

        # Convert physical window coords → canvas-relative coords
        cx1 = wx1 - vx1
        cy1 = wy1 - vy1
        cx2 = wx2 - vx1
        cy2 = wy2 - vy1

        logger.info(f"Canvas crop  cx1={cx1} cy1={cy1} cx2={cx2} cy2={cy2}")

        # Clamp to canvas bounds
        cx1c = max(cx1, 0)
        cy1c = max(cy1, 0)
        cx2c = min(cx2, canvas.width)
        cy2c = min(cy2, canvas.height)

        # Guard: after clamping, ensure crop area is still valid
        if cx2c <= cx1c or cy2c <= cy1c:
            logger.warning(
                f"Clamped crop is empty ({cx1c},{cy1c})→({cx2c},{cy2c}) — "
                "window may be off-screen. Skipping."
            )
            return

        # 1. Clean OCR crop (no border drawn)
        ocr_crop = canvas.crop((cx1c, cy1c, cx2c, cy2c))
        ocr_crop.save(ocr_filename)
        logger.info(f"OCR image saved: {ocr_filename}")

        # 2. Draw the red border on the full canvas (inset by half thickness)
        half = BOX_THICKNESS // 2
        box_left   = cx1c + half
        box_top    = cy1c + half
        box_right  = cx2c - half
        box_bottom = cy2c - half

        logger.info(
            f"Border rect  left={box_left} top={box_top} "
            f"right={box_right} bottom={box_bottom}"
        )

        draw = ImageDraw.Draw(canvas)
        draw.rectangle(
            [box_left, box_top, box_right, box_bottom],
            outline=BOX_COLOR,
            width=BOX_THICKNESS,
        )
        canvas.save(filename)
        logger.info(f"Annotated image saved: {filename}")


# ─────────────────────────────────────────────
#  Black-background crop
# ─────────────────────────────────────────────

def crop_black_background(
    image_path: str,
    output_path: Optional[str] = None,
    threshold: int = BLACK_PIXEL_THRESHOLD,
) -> None:
    img = cv2.imread(image_path)
    if img is None:
        logger.warning(f"Could not read image: {image_path}")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    black_pixels = np.sum(gray <= threshold)
    black_ratio = black_pixels / gray.size

    if black_ratio <= BLACK_RATIO_THRESHOLD:
        logger.info("No significant black background — skipping crop.")
        return

    logger.info(f"Black background detected ({black_ratio:.1%}) — cropping.")

    mask = gray > threshold
    coords = np.argwhere(mask)
    if len(coords) == 0:
        logger.warning("Image is entirely black — skipping.")
        return

    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    cropped = img[y_min : y_max + 1, x_min : x_max + 1]
    result = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))

    if output_path:
        result.save(output_path)
        logger.info(f"Cropped image saved: {output_path}")
        if os.path.exists(image_path):
            os.remove(image_path)


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

def get_window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 255)
    return buf.value

def get_window_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 255)
    return buf.value

def get_dwm_rect(hwnd):
    try:
        rect = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect), ctypes.sizeof(rect))
        return rect.left, rect.top, rect.right, rect.bottom
    except:
        return None

def get_winrect(hwnd):
    try:
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom
    except:
        return None

def get_client_rect(hwnd):
    try:
        rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom
    except:
        return None

def is_cloaked(hwnd):
    try:
        val = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), wintypes.DWORD(DWMWA_CLOAKED),
            ctypes.byref(val), ctypes.sizeof(val))
        return val.value != 0
    except:
        return False

def enum_children(hwnd, depth=0, max_depth=3):
    if depth > max_depth:
        return
    children = []
    def cb(child_hwnd, _):
        children.append(child_hwnd)
        return True
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    ctypes.windll.user32.EnumChildWindows(hwnd, EnumWindowsProc(cb), 0)
    
    for child in children[:10]:  # limit output
        cls = get_window_class(child)
        title = get_window_title(child)
        wr = get_winrect(child)
        cloaked = is_cloaked(child)
        if wr and (wr[2]-wr[0]) > 50 and (wr[3]-wr[1]) > 50:
            print(f"{'  '*depth}Child hwnd={child} class='{cls}' title='{title[:30]}' cloaked={cloaked}")
            print(f"{'  '*depth}  GetWindowRect: {wr}  (w={wr[2]-wr[0]} h={wr[3]-wr[1]})")

# ─────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────

def main() -> None:
    folder = datetime.today().strftime("%Y-%m-%d")
    os.makedirs(folder, exist_ok=True)

    logger.info("Capture loop started. Press Ctrl+C to stop.")

    while True:
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_image = f"{folder}/{ts}.png"
            ocr_image    = f"{folder}/{ts}_ocr.png"
            final_output = f"{folder}/{ts}_black_crop.png"

            capture_screenshots(output_image, ocr_image)

            if os.path.exists(ocr_image):
                crop_black_background(ocr_image, final_output)


            hwnd = ctypes.windll.user32.GetForegroundWindow()
            cls = get_window_class(hwnd)
            title = get_window_title(hwnd)
            cloaked = is_cloaked(hwnd)

            logger.info(f"\n=== Foreground Window ===")
            logger.info(f"hwnd={hwnd}  class='{cls}'  title='{title}'  cloaked={cloaked}")
            logger.info(f"GetWindowRect:              {get_winrect(hwnd)}")
            logger.info(f"DwmExtendedFrameBounds:     {get_dwm_rect(hwnd)}")
            logger.info(f"GetClientRect (local):      {get_client_rect(hwnd)}")

            logger.info(f"\n=== Children (w/h > 50px, depth<=3) ===")
            enum_children(hwnd, depth=0)

            logger.info("\nDone.")

            time.sleep(5)

        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error in capture loop: {e}", exc_info=True)
            time.sleep(30)


if __name__ == "__main__":
    main()