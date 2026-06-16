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
#  Helpers
# ─────────────────────────────────────────────

def get_windows_edition() -> Tuple[str, int]:
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
        edition_id = winreg.QueryValueEx(key, "EditionID")[0]
        build = int(winreg.QueryValueEx(key, "CurrentBuild")[0])
    return edition_id, build



def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 255)
    return buf.value


def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 255)
    return buf.value


def get_true_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """
    Get the true window bounds excluding DWM shadows (Windows only).
    """
    try:
        rect = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect)
        )
        return rect.left, rect.top, rect.right, rect.bottom
    except Exception as e:
        logger.info(f"Failed to get window rect via DWM: {e}")
        return None


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


# Bootstrap logger early so helpers can use it
_boot_folder = datetime.today().strftime("%Y-%m-%d")
os.makedirs(_boot_folder, exist_ok=True)
logger = setup_logging(_boot_folder)

edition_id, build = get_windows_edition()
logger.info(f"Windows build={build}  edition={edition_id}")


# ─────────────────────────────────────────────
#  Core capture
# ─────────────────────────────────────────────

def capture_screenshots(filename: str, ocr_filename: str):
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    
    if not hwnd:
        logger.warning("No active window found.")
        return
    
    window_title = get_window_title(hwnd)
    window_class = get_window_class(hwnd)
    logger.info(f"Capturing: '{window_title}'  (Class: {window_class})")

    # rect = get_true_window_rect(hwnd)
    rect = None
    if window_class == "Windows.UI.Core.CoreWindow":
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        rect = rect.left, rect.top, rect.right, rect.bottom
    else:
        rect = get_true_window_rect(hwnd)

    if not rect: 
        return
    
    wx1, wy1, wx2, wy2 = rect

    with mss.mss() as sct:
        monitor_all = sct.monitors[0]
        shot = sct.grab(monitor_all)
        canvas = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        # Virtual screen offsets
        vx1, vy1 = monitor_all["left"], monitor_all["top"]

        # Calculate relative crop coordinates
        cx1, cy1 = wx1 - vx1, wy1 - vy1
        cx2, cy2 = wx2 - vx1, wy2 - vy1

        win_w, win_h = wx2 - wx1, wy2 - wy1
        logger.info(f"Window physical rect  cx1={cx1} cy1={cy1} cx2={cx2} cy2={cy2}  (w={win_w} h={win_h})")

        # Fix for Windows 11 hidden top border / scaled overlays
        safe_top = max(cy1, 0) + (BOX_THICKNESS // 2)
        safe_left = max(cx1, 0) + (BOX_THICKNESS // 2)
        safe_right = min(cx2, canvas.width) - (BOX_THICKNESS // 2)
        safe_bottom = min(cy2, canvas.height) - (BOX_THICKNESS // 2)

        if window_title not in ["Notification Center", "Search"]:

            # 1. Save CLEAN crop for OCR (Using original coords)
            active_window_crop = canvas.crop((cx1, cy1, cx2, cy2))
            active_window_crop.save(ocr_filename)

            # 2. Draw the Box on the context shot using SAFE coordinates
            draw = ImageDraw.Draw(canvas)
            draw.rectangle(
                [safe_left, safe_top, safe_right, safe_bottom],
                outline=BOX_COLOR,
                width=BOX_THICKNESS
            )
        else:
            canvas.save(ocr_filename)    
        
        canvas.save(filename)
   
def crop_black_background(image_path: str, 
                          output_path: Optional[str] = None, 
                          threshold: int = BLACK_PIXEL_THRESHOLD):
    """
    Detects and crops black background from an image.
    
    Args:
        image_path: Path to input image
        output_path: Path to save cropped image (optional)
        threshold: Pixel value threshold to consider as "black" (0-255)    
    """
    # Load image
    img = cv2.imread(image_path)
    
    # --- Step 1: Check if black background exists ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    black_pixels = np.sum(gray <= threshold)
    total_pixels = gray.size
    black_ratio = black_pixels / total_pixels
        
    if black_ratio > BLACK_RATIO_THRESHOLD:  # More than 5% black pixels
        logger.info("Black background detected!")
    else:
        logger.info("No significant black background found.")
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    # --- Step 2: Create a mask of non-black pixels ---
    mask = gray > threshold  # True where pixels are NOT black

    # --- Step 3: Find bounding box of non-black content ---
    coords = np.argwhere(mask)          # All non-black pixel coordinates
    y_min, x_min = coords.min(axis=0)  # Top-left corner
    y_max, x_max = coords.max(axis=0)  # Bottom-right corner
    
    # print(f"Content bounding box: ({x_min}, {y_min}) → ({x_max}, {y_max})")

    # --- Step 4: Crop the image ---
    cropped = img[y_min:y_max+1, x_min:x_max+1]
    
    # Convert BGR (OpenCV) → RGB (PIL)
    cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    result = Image.fromarray(cropped_rgb)

    # --- Step 5: Save if output path provided ---
    if output_path:
        os.remove(image_path)
        result.save(output_path)


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
            logger.info(f"output_image => {output_image}")
            logger.info(f"ocr_image => {ocr_image}")
            logger.info(f"final_output => {final_output}")

            if os.path.exists(ocr_image):
                crop_black_background(ocr_image, final_output)
                
            logger.info("\n")

            time.sleep(3)

        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error in capture loop: {e}", exc_info=True)
            time.sleep(30)


if __name__ == "__main__":
    main()