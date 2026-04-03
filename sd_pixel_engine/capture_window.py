import mss
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw

# Constants for DWM to get the real window size (minus shadows)
DWMWA_EXTENDED_FRAME_BOUNDS = 9

def get_true_window_rect(hwnd):
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect)
    )
    return rect.left, rect.top, rect.right, rect.bottom

def capture_screenshots(filename, ocr_filename):
    # Ensure DPI awareness is set before any coordinate calls
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # Process_Per_Monitor_DPI_Aware
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        print("No active window found.")
        return

    # Get the "Clean" coordinates (no shadows)
    wx1, wy1, wx2, wy2 = get_true_window_rect(hwnd)

    with mss.mss() as sct:
        # sct.monitors[0] is the virtual desktop covering ALL monitors
        monitor_all = sct.monitors[0]
        
        # Capture the entire virtual desktop at once
        # This is more reliable than stitching individual monitors manually
        shot = sct.grab(monitor_all)
        canvas = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        vx1, vy1 = monitor_all["left"], monitor_all["top"]

        # Calculate relative crop coordinates
        crop_x1 = wx1 - vx1
        crop_y1 = wy1 - vy1
        crop_x2 = wx2 - vx1
        crop_y2 = wy2 - vy1

        # 1. Save the clean crop for OCR
        active_window_crop = canvas.crop((crop_x1, crop_y1, crop_x2, crop_y2))
        active_window_crop.save(ocr_filename)

        # 2. Draw the red box on the full canvas for the "context" shot
        draw = ImageDraw.Draw(canvas)
        for t in range(4): # Thickness
            draw.rectangle(
                [crop_x1 - t, crop_y1 - t, crop_x2 + t, crop_y2 + t],
                outline=(255, 0, 0)
            )
        
        canvas.save(filename)
        # print(f"✓ Saved context: {filename}")
        # print(f"✓ Saved OCR crop: {ocr_filename}")

# Usage
# capture_screenshots("full_desktop.png", "ocr_target.png")