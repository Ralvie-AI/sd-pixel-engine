import os 

import mss
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw
import cv2
import numpy as np


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


def crop_black_background(image_path, output_path=None, threshold=10):
    """
    Detects and crops black background from an image.
    
    Args:
        image_path: Path to input image
        output_path: Path to save cropped image (optional)
        threshold: Pixel value threshold to consider as "black" (0-255)
    
    Returns:
        Cropped PIL Image
    """
    # Load image
    img = cv2.imread(image_path)
    
    # --- Step 1: Check if black background exists ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    black_pixels = np.sum(gray <= threshold)
    total_pixels = gray.size
    black_ratio = black_pixels / total_pixels
    
    print(f"Black pixel ratio: {black_ratio:.2%}")
    
    if black_ratio > 0.05:  # More than 5% black pixels
        print("✅ Black background detected!")
    else:
        print("❌ No significant black background found.")
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
