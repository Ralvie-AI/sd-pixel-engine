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
    
def capture_screenshots(filename: str, ocr_filename: str):
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        logger.warning("No active window found.")
        return

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

        # Fix for Windows 11 hidden top border / scaled overlays
        safe_top = max(cy1, 0) + (BOX_THICKNESS // 2)
        safe_left = max(cx1, 0) + (BOX_THICKNESS // 2)
        safe_right = min(cx2, canvas.width) - (BOX_THICKNESS // 2)
        safe_bottom = min(cy2, canvas.height) - (BOX_THICKNESS // 2)

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
        
        canvas.save(filename)
   
def crop_black_background(image_path: str, 
                          output_path: Optional[str] = None, 
                          threshold: int = BLACK_PIXEL_THRESHOLD):
    """
    Detects and crops black background from an image.
    """
    # Load image
    img = cv2.imread(image_path)
    
    # Check if image exists to avoid crashes
    if img is None:
        logger.warning(f"Could not read image: {image_path}")
        return

    # Check if black background exists
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    black_pixels = np.sum(gray <= threshold)
    total_pixels = gray.size
    black_ratio = black_pixels / total_pixels
        
    if black_ratio > BLACK_RATIO_THRESHOLD: 
        logger.info("Black background detected!")
    else:
        logger.info("No significant black background found.")
        return

    # Create a mask of non-black pixels
    mask = gray > threshold

    # Find bounding box of non-black content
    coords = np.argwhere(mask)
    if len(coords) == 0:
        return # Empty image
        
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    # Crop the image
    cropped = img[y_min:y_max+1, x_min:x_max+1]
    
    # Convert BGR (OpenCV) → RGB (PIL)
    cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    result = Image.fromarray(cropped_rgb)

    # Save if output path provided
    if output_path:
        result.save(output_path)
        if os.path.exists(image_path):
            os.remove(image_path) # Clean up original


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting automated screen capture script with timestamping. Press Ctrl+C to exit.")
    
    folder = datetime.today().strftime("%Y-%m-%d")
    if not os.path.exists(folder):
        os.mkdir(folder)

    while True:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            output_image = f"{folder}/{timestamp}.png"
            ocr_image = f"{folder}/{timestamp}_ocr.png"
            final_output = f"{folder}/{timestamp}_black_crop.png"
            
            # Execute captures
            capture_screenshots(output_image, ocr_image)
            
            # Run background crop if the base file exists
            if os.path.exists(ocr_image):
                # Run the crop only on the OCR-cropped image to prevent background skewing
                crop_black_background(ocr_image, final_output)
            
            # Wait 30 seconds before repeating
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Error occurred during capture iteration: {e}")
            time.sleep(30)