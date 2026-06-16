import os
import logging
from typing import Optional


import ctypes
import win32gui
import win32api
import win32ui
from PIL import Image, ImageDraw
import cv2
import numpy as np
from mss import mss
# Apply DPI awareness immediately when the script starts
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

logger = logging.getLogger(__name__)

# Constants for DWM to get the real window size (minus shadows)
DWMWA_EXTENDED_FRAME_BOUNDS = 9
BLACK_RATIO_THRESHOLD = 0.05  # 5%
BLACK_PIXEL_THRESHOLD = 10
BOX_THICKNESS = 4
BOX_COLOR = (255, 0, 0)  # Red in RGB

# System window titles to ignore
WINDOW_10_EXCLUDED_OWNERS = ["Date and Time Information", "Cortana", "Action center", "News and interests", 
                             "Meet Now", "Activity Center", "Network Connections", "Volume Control"]
WINDOW_11_EXCLUDED_OWNERS = ["Program Manager", "Start", "", "Settings", "Notification Center", "Search"]
EXCLUDED_OWNERS = WINDOW_10_EXCLUDED_OWNERS + WINDOW_11_EXCLUDED_OWNERS

def is_screen_locked():
    """Returns True if the Windows workstation is locked or on a secure desktop."""
    # Trying to open the input desktop. If it fails, the screen is locked or a UAC prompt is up.
    h_desktop = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100) # DESKTOP_SWITCHDESKTOP
    if h_desktop:
        ctypes.windll.user32.CloseDesktop(h_desktop)
        return False
    return True

def is_likely_fullscreen(win, screen):
    """Check if the window matches or exceeds the screen dimensions."""
    return abs(win["width"] - screen["width"]) < 15 and abs(win["height"] - screen["height"]) < 15

def is_bad_mss_capture(grab, win, screen):
    """Sanity check for the MSS screen grab data."""
    return grab is None or grab.width <= 0 or grab.height <= 0

def get_active_window_info():
    """Return the top-most valid window (based on Z-order) on Windows."""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or not win32gui.IsWindowVisible(hwnd):
        return None

    # Get the window title
    owner = win32gui.GetWindowText(hwnd)
    if owner in EXCLUDED_OWNERS:
        return None

    # Get window placement coordinates
    rect = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top

    # Skip tiny/invisible framework fragments or notifications
    if width < 300 or height < 200:
        return None

    return {
        "id": hwnd,
        "left": int(left),
        "top": int(top),
        "width": int(width),
        "height": int(height),
        "owner": owner,
    }

def get_screen_for_window(win):
    """Return the monitor bounds where the window is located using MSS monitor spaces."""
    with mss() as sct:
        # sct.monitors[0] is the virtual span; index 1+ are individual screens
        for monitor in sct.monitors[1:]:
            s_bounds = {
                "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
            }
            # Check bounding box overlap
            if (win["left"] < s_bounds["left"] + s_bounds["width"] and
                win["left"] + win["width"] > s_bounds["left"] and
                win["top"] < s_bounds["top"] + s_bounds["height"] and
                win["top"] + win["height"] > s_bounds["top"]):
                return s_bounds
    return None

def get_display_info_from_mouse():
    """Return the MSS monitor dictionary containing the current mouse position."""
    x, y = win32api.GetCursorPos()
    with mss() as sct:
        for monitor in sct.monitors[1:]:
            if (monitor["left"] <= x < monitor["left"] + monitor["width"] and
                monitor["top"] <= y < monitor["top"] + monitor["height"]):
                return monitor
        return sct.monitors[1]  # Default Fallback to Primary Monitor

def clamp_region(region, screen):
    """Ensure the capture region stays strictly within monitor bounds."""
    left = max(region["left"], screen["left"])
    top = max(region["top"], screen["top"])
    right = min(region["left"] + region["width"], screen["left"] + screen["width"])
    bottom = min(region["top"] + region["height"], screen["top"] + screen["height"])

    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None

    return {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}

def capture_active_window_direct_with_info(win, output_file):
    """STEP A: Direct native GDI capture of the window handle."""
    hwnd = win["id"]
    try:
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        
        # Create the bitmap object and configure it
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, win["width"], win["height"])
        
        saveDC.SelectObject(saveBitMap)
        
        # Use PrintWindow API to grab the layer graphics
        # PW_RENDERFULLCONTENT = 3 handles modern hardware-accelerated app rendering contexts
        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
        
        if result == 1:
            bmpinfo = saveBitMap.GetInfo()
            bmpbits = saveBitMap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpbits, 'raw', 'BGRX', 0, 1
            )
            img.save(output_file)
            success = True
        else:
            success = False

        # Essential GDI Cleanup
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        return output_file if success else None
    except Exception as e:
        logger.warning(f"Direct native GDI capture failed: {e}")
        return None
    
def capture_active_window_direct_with_info_old(win, output_file):
    """STEP A: Direct native GDI capture of the window handle."""
    hwnd = win["id"]
    try:
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        
        saveBitMap = win32ui.CreateCompatibleBitmap(mfcDC, win["width"], win["height"])
        saveDC.SelectObject(saveBitMap)
        
        # Use PrintWindow API to grab the layer graphics
        # PW_RENDERFULLCONTENT = 3 handles modern hardware-accelerated app rendering contexts
        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
        
        if result == 1:
            bmpinfo = saveBitMap.GetInfo()
            bmpbits = saveBitMap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpbits, 'raw', 'BGRX', 0, 1
            )
            img.save(output_file)
            success = True
        else:
            success = False

        # Essential GDI Cleanup
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        return output_file if success else None
    except Exception as e:
        logger.warning(f"Direct native GDI capture failed: {e}")
        return None

def capture_active_window_screenshot(output_file: str):
    """Capture the active window with multi-step fallback strategy on Windows."""
    if is_screen_locked():
        logger.warning("[SKIP] Screen is locked.")
        return None

    win = get_active_window_info()
    if not win:
        return None

    screen = get_screen_for_window(win)

    # STEP A: Direct GDI Window Capture (only for non-fullscreen)
    if not (screen and is_likely_fullscreen(win, screen)):
        result = capture_active_window_direct_with_info(win, output_file)
        if result:
            return result

    # STEP B: MSS region coordinate crop
    if win["height"] > 100:
        if screen:
            region = clamp_region(win, screen)
            if region:
                try:
                    with mss() as sct:
                        grab = sct.grab(region)
                        if not is_bad_mss_capture(grab, win, screen):
                            img = Image.frombytes("RGB", grab.size, grab.rgb)
                            img.save(output_file)
                            return output_file
                except Exception as e:
                    logger.warning(f"MSS fallback failed: {e}")

    # STEP C: Final fallback (Full display containing mouse cursor)
    try:
        monitor = get_display_info_from_mouse()
        with mss() as sct:
            grab = sct.grab(monitor)
            img = Image.frombytes("RGB", grab.size, grab.rgb)
            img.save(output_file)
            return output_file
    except Exception as e:
        logger.error(f"Step C display fallback failed: {e}")

    return None

def capture_fullscreen(output_file: str, ocr_file: str):
    """Captures the entire virtual workspace and paints a border around the focus target."""
    if is_screen_locked():
        logger.warning("[SKIP] Screen is locked.")
        return None

    try:
        win = get_active_window_info()
        is_normal_window = win and win["height"] > 100

        with mss() as sct:
            monitor_all = sct.monitors[0]  # Spans all connected monitors
            screenshot = sct.grab(monitor_all)

            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            draw = ImageDraw.Draw(img)
            thickness = 5

            # Compute relative bounds inside the large combined image layout
            if is_normal_window:
                left = win["left"] - monitor_all["left"]
                top = win["top"] - monitor_all["top"]
                right = left + win["width"] - 1
                bottom = top + win["height"] - 1
            else:
                monitor = get_display_info_from_mouse()
                left = monitor["left"] - monitor_all["left"]
                top = monitor["top"] - monitor_all["top"]
                right = left + monitor["width"] - 1
                bottom = top + monitor["height"] - 1

            img_w, img_h = img.size
     
            left, top = max(0, left), max(0, top)
            right, bottom = min(img_w - 1, right), min(img_h - 1, bottom)            

            if not os.path.exists(ocr_file):
                ocr_crop = img.crop((left, top, right, bottom))
                ocr_crop.save(ocr_file)

            draw.rectangle(
                [(left, top), (right, bottom)], 
                outline="red", 
                width=thickness
            )
            img.save(output_file)
            return output_file

    except Exception as e:
        logger.error(f"[ERROR] Fullscreen capture failed: {e}")
        return None
   
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
