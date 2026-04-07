import logging
import re
import argparse
import Quartz
import os
from AppKit import NSScreen
from mss import mss
from PIL import Image, ImageDraw

from datetime import datetime, timezone, timedelta, time


logger = logging.getLogger(__name__)


# filename: "0a07029c9a901fe0819abf69dca12c0d_2026-01-14T00-55-52.905552Z.png"
# '2026-01-14 00:55:52.905552'
def get_image_name_to_utc(filename: str) -> str:
    import re
    from datetime import datetime, timezone

    # เอาแค่ชื่อไฟล์ ไม่เอา path
    filename = os.path.basename(filename)

    # ลบ _active
    filename = filename.replace("_active", "")

    match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d+Z", filename)

    if not match:
        raise ValueError(f"Invalid filename format: {filename}")

    ts_part = match.group(0)

    dt_utc = datetime.strptime(ts_part, "%Y-%m-%dT%H-%M-%S.%fZ").replace(tzinfo=timezone.utc)

    return dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")

def get_image_name_to_utc_dt(filename: str) -> datetime:
    import os
    import re

    filename = os.path.basename(filename)
    # logger.error(f"[DEBUG PARSE INPUT] filename => {filename}") 

    # ตัด _active ออกเสมอ
    filename = filename.replace("_active", "")

    match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d+Z", filename)

    if not match:
        raise ValueError(f"Invalid filename format: {filename}")

    ts_part = match.group(0)

    return datetime.strptime(
        ts_part,
        "%Y-%m-%dT%H-%M-%S.%fZ"
    ).replace(tzinfo=timezone.utc)


def add_second_to_utc(date_time, seconds):

    # 1. Define your starting timestamp string
    timestamp_str = date_time

    # 2. Parse the string into a datetime object
    # .fromisoformat() handles the timezone (+00:00) automatically
    dt = datetime.fromisoformat(timestamp_str)

    # 3. Add 9.095 seconds using timedelta
    new_dt = dt + timedelta(seconds=seconds)

    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    added_duration_timestamp = new_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    return timestamp, added_duration_timestamp

def parse_time(value: str) -> time:
    try:
        hour, minute = map(int, value.split(":"))
        return time(hour, minute)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid time format: '{value}'. Use HH:MM (e.g., 09:00)"
        )

def parse_days(value):
    try:
        return [int(v) for v in value.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("Days must be comma-separated integers (e.g. 0,1,2,3,4)")
    
def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected (true/false).")

# รายชื่อ Process ระบบที่ควรข้ามในการหา Active Window
EXCLUDED_OWNERS = {
    "Window Server",
    "Dock",
    "Control Center",
    "Notification Center",
    "Spotlight",
    "TextInputMenuAgent"
}

# --- Helper Functions: Window & Screen Management ---

def get_active_window_bounds():
    """ดึงพิกัดของหน้าต่างที่กำลัง Active อยู่ โดยกรองเอาเฉพาะแอปที่ผู้ใช้ใช้งานจริง"""
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID
    )

    for win in window_list:
        if not win.get("kCGWindowIsOnscreen"):
            continue

        owner = win.get("kCGWindowOwnerName", "")
        layer = win.get("kCGWindowLayer")
        bounds = win.get("kCGWindowBounds")

        # Log เพื่อการตรวจสอบ (สามารถปิดได้ถ้าใช้งานจริง)
        # logger.info(f"Checking Window: {owner} | Layer: {layer} | Bounds: {bounds}")

        if layer != 0:
            continue
        if owner in EXCLUDED_OWNERS:
            continue
        if not bounds:
            continue

        return {
            "left": int(bounds["X"]),
            "top": int(bounds["Y"]),
            "width": int(bounds["Width"]),
            "height": int(bounds["Height"]),
            "owner": owner,
        }
    return None

def get_screen_for_window(win):
    """ตรวจสอบว่าหน้าต่างที่ระบุ วางอยู่บนหน้าจอ (Monitor) ไหน"""
    for screen in NSScreen.screens():
        frame = screen.frame()
        s_bounds = {
            "left": int(frame.origin.x),
            "top": int(frame.origin.y),
            "width": int(frame.size.width),
            "height": int(frame.size.height),
        }
        # Check overlap
        if (win["left"] < s_bounds["left"] + s_bounds["width"] and
            win["left"] + win["width"] > s_bounds["left"] and
            win["top"] < s_bounds["top"] + s_bounds["height"] and
            win["top"] + win["height"] > s_bounds["top"]):
            return s_bounds
    return None

def get_display_id_from_mouse():
    """หา Display ID ของหน้าจอที่เมาส์วางอยู่ปัจจุบัน (ใช้สำหรับ Fullscreen Fallback)"""
    mouse_event = Quartz.CGEventCreate(None)
    mouse_loc = Quartz.CGEventGetLocation(mouse_event)
    
    max_displays = 16
    err, active_displays, display_count = Quartz.CGGetActiveDisplayList(max_displays, None, None)
    
    for i in range(display_count):
        display_id = active_displays[i]
        bounds = Quartz.CGDisplayBounds(display_id)
        if (bounds.origin.x <= mouse_loc.x < bounds.origin.x + bounds.size.width and
            bounds.origin.y <= mouse_loc.y < bounds.origin.y + bounds.size.height):
            return display_id
    return Quartz.CGMainDisplayID()

def clamp_region(region, screen):
    """ตัดขอบพิกัดหน้าต่างให้ไม่เกินขอบเขตของหน้าจอจริง"""
    left = max(region["left"], screen["left"])
    top = max(region["top"], screen["top"])
    right = min(region["left"] + region["width"], screen["left"] + screen["width"])
    bottom = min(region["top"] + region["height"], screen["top"] + screen["height"])

    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None

    return {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}

def is_bad_mss_capture(img, win, screen):
    """ตรวจสอบว่า MSS จับภาพพลาดหรือไม่ (มักเกิดกับ Fullscreen Apps)"""
    if img.height < screen["height"] * 0.25:
        return True
    if (win and win["width"] >= screen["width"] * 0.95 and 
        win["height"] >= screen["height"] * 0.95 and 
        img.height < screen["height"] * 0.9):
        return True
    return False

# --- Main Screenshot Functions ---

def capture_active_window_screenshot(output_file: str):
    """
    ฟังก์ชันหลักในการจับภาพหน้าต่างที่ Active:
    1. ถ้าเป็นหน้าต่างปกติ จะพยายาม Crop เฉพาะตัวแอป (MSS)
    2. ถ้าเป็น Fullscreen หรือหาพิกัดไม่ได้ จะถ่ายทั้งหน้าจอที่เมาส์อยู่ (Quartz)
    """
    win = get_active_window_bounds()
    
    # ตรวจสอบว่าเป็นหน้าต่างแอปปกติหรือไม่ (ถ้าสูงน้อยกว่า 100 มักจะเป็นแค่ Title Bar ลวง)
    is_normal_window = win and win["height"] > 100

    if is_normal_window:
        # logger.info(f"[CASE 1] Capturing Window: {win['owner']}")
        screen = get_screen_for_window(win)
        if screen:
            region = clamp_region(win, screen)
            if region:
                try:
                    with mss() as sct:
                        grab = sct.grab(region)
                        if not is_bad_mss_capture(grab, win, screen):
                            img = Image.frombytes("RGB", grab.size, grab.rgb)
                            img.save(output_file)
                            return # สำเร็จ: ออกจากฟังก์ชันทันที
                except Exception as e:
                    logger.warning(f"MSS Capture failed, falling back: {e}")

    # Fallback Case: ใช้สำหรับ Fullscreen หรือกรณีที่ MSS ทำงานผิดพลาด
    # logger.info("[CASE 2] Smart Fallback -> Capturing full display via Quartz")
    display_id = get_display_id_from_mouse()
    
    image = Quartz.CGDisplayCreateImage(display_id)
    if image:
        url = Quartz.CFURLCreateWithFileSystemPath(None, output_file, Quartz.kCFURLPOSIXPathStyle, False)
        dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
        Quartz.CGImageDestinationAddImage(dest, image, None)
        Quartz.CGImageDestinationFinalize(dest)

def capture_fullscreen(output_file: str):
    """จับภาพหน้าจอทั้งหมด พร้อมวาดเส้นแดงล้อมรอบสิ่งที่กำลัง Active (Window หรือ Fullscreen)"""
    win = get_active_window_bounds()
    
    # เช็คว่าเป็นหน้าต่างปกติหรือไม่ (ความสูงเกิน 100)
    is_normal_window = win and win["height"] > 100

    with mss() as sct:
        # 1. จับภาพพื้นที่ Virtual Desktop ทั้งหมด (ทุกจอมัดรวมกัน)
        monitor_all = sct.monitors[0] 
        screenshot = sct.grab(monitor_all)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        draw = ImageDraw.Draw(img)
        thickness = 3

        # 2. ส่วนการวาดกรอบ (Decision Logic)
        if is_normal_window:
            # --- CASE ปกติ: วาดรอบหน้าต่างแอป ---
            left = win["left"] - monitor_all["left"]
            top = win["top"] - monitor_all["top"]
            right, bottom = left + win["width"], top + win["height"]
            # logger.info(f"[BORDER] Drawing around Window: {win['owner']}")
        else:
            # --- CASE Fullscreen: วาดรอบหน้าจอที่เมาส์อยู่ ---
            display_id = get_display_id_from_mouse()
            d_bounds = Quartz.CGDisplayBounds(display_id)
            
            left = int(d_bounds.origin.x) - monitor_all["left"]
            top = int(d_bounds.origin.y) - monitor_all["top"]
            right = left + int(d_bounds.size.width)
            bottom = top + int(d_bounds.size.height)
            # logger.info("[BORDER] Drawing around Full Screen (Mouse Position)")

        # 3. ลงมือวาดเส้นตามพิกัดที่เลือกมา
        for i in range(thickness):
            draw.rectangle([left - i, top - i, right + i, bottom + i], outline="red")

        img.save(output_file)
    return output_file




if __name__ == '__main__':
    # add_second_to_utc("2026-01-14 06:49:15.373000+00:00", 2.015)
    a, b = add_second_to_utc("2026-01-14 06:49:18.394000+00:00", 5.04)

    t = get_image_name_to_utc("2c8ea4a694971ac90194b1d4988b02b6_2026-01-14T06-49-22.409657Z.png")
    if a <= t <= b:
        print(f"yes => {t}")
    else:
        print("no")

