import os
import logging
from typing import Tuple, Optional

import mss
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Constants for DWM to get the real window size (minus shadows)
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DPI_AWARENESS_LEVEL = 2  # Process_Per_Monitor_DPI_Aware
BLACK_RATIO_THRESHOLD = 0.05  # 5%
BLACK_PIXEL_THRESHOLD = 10
BOX_THICKNESS = 4
BOX_COLOR = (255, 0, 0)  # Red in RGB

def get_true_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """
    Get the true window bounds excluding DWM shadows (Windows only).
    
    Args:
        hwnd: Window handle
    
    Returns:
        Tuple of (left, top, right, bottom) or None if DWM call fails
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

def capture_screenshots(filename, ocr_filename):
    # Ensure DPI awareness is set before any coordinate calls
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(DPI_AWARENESS_LEVEL) # Process_Per_Monitor_DPI_Aware
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
        draw.rectangle(
                [crop_x1, crop_y1, crop_x2, crop_y2],
                outline=BOX_COLOR,
                width=BOX_THICKNESS
            )        
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
