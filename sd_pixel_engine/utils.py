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

    # Just the filename, not the path.
    filename = os.path.basename(filename)

    # delete _active
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

    # split _active 
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

# ------------------------------
# Constants
# ------------------------------

# System-level processes that should be ignored
EXCLUDED_OWNERS = {
    "Window Server",
    "Dock",
    "Control Center",
    "Notification Center",
    "Spotlight",
    "TextInputMenuAgent"
}


# ------------------------------
# Helper Functions
# ------------------------------

def is_screen_locked():
    """Return True if macOS screen is locked."""
    session_info = Quartz.CGSessionCopyCurrentDictionary()
    if session_info:
        return session_info.get("CGSSessionScreenIsLocked", False)
    return False


def get_active_window_info():
    """
    Return the top-most valid window (based on Z-order).
    
    Filtering strategy:
    - Skip system processes
    - Skip very small windows (notifications, toolbars)
    - Do NOT rely on layer (important for fullscreen support)
    """
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID
    )

    for win in window_list:

        if not win.get("kCGWindowIsOnscreen"):
            continue

        owner = win.get("kCGWindowOwnerName", "")
        bounds = win.get("kCGWindowBounds")

        if not bounds:
            continue

        # Skip system UI
        if owner in EXCLUDED_OWNERS:
            continue

        # Skip small windows (likely notifications / fragments)
        if bounds["Width"] < 300 or bounds["Height"] < 200:
            continue

        return {
            "id": win.get("kCGWindowNumber"),
            "left": int(bounds["X"]),
            "top": int(bounds["Y"]),
            "width": int(bounds["Width"]),
            "height": int(bounds["Height"]),
            "owner": owner,
        }

    return None


def get_screen_for_window(win):
    """Return the screen bounds where the window is located."""
    for screen in NSScreen.screens():
        frame = screen.frame()
        s_bounds = {
            "left": int(frame.origin.x),
            "top": int(frame.origin.y),
            "width": int(frame.size.width),
            "height": int(frame.size.height),
        }

        # Check overlap between window and screen
        if (win["left"] < s_bounds["left"] + s_bounds["width"] and
            win["left"] + win["width"] > s_bounds["left"] and
            win["top"] < s_bounds["top"] + s_bounds["height"] and
            win["top"] + win["height"] > s_bounds["top"]):
            return s_bounds

    return None


def get_display_id_from_mouse():
    """
    Return display ID based on current mouse position.
    Used for fullscreen fallback when window detection is unreliable.
    """
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
    """
    Ensure the capture region stays within screen bounds.
    Prevents invalid or out-of-range capture areas.
    """
    left = max(region["left"], screen["left"])
    top = max(region["top"], screen["top"])
    right = min(region["left"] + region["width"], screen["left"] + screen["width"])
    bottom = min(region["top"] + region["height"], screen["top"] + screen["height"])

    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None

    return {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}


def is_bad_mss_capture(img, win, screen):
    """
    Detect failed MSS captures.
    
    Common failure cases:
    - Very small image (capture failed)
    - Fullscreen app but captured image is too small
    """
    if img.height < screen["height"] * 0.25:
        return True

    if (win and win["width"] >= screen["width"] * 0.95 and
        win["height"] >= screen["height"] * 0.95 and
        img.height < screen["height"] * 0.9):
        return True

    return False


def is_likely_fullscreen(win, screen):
    """Heuristic check if window is fullscreen."""
    if not win or not screen:
        return False

    return (
        win["width"] >= screen["width"] * 0.95 and
        win["height"] >= screen["height"] * 0.95
    )


def capture_active_window_direct_with_info(win, output_file: str):
    """
    Capture a single window directly using Quartz.
    
    Pros:
    - Clean (no overlay / no obstruction)
    
    Cons:
    - May fail for fullscreen / system-layer windows
    """
    if not win:
        return None

    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        win["id"],
        Quartz.kCGWindowImageBoundsIgnoreFraming
    )

    if not image:
        return None

    url = Quartz.CFURLCreateWithFileSystemPath(
        None, output_file,
        Quartz.kCFURLPOSIXPathStyle,
        False
    )

    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, image, None)
    Quartz.CGImageDestinationFinalize(dest)

    return output_file


# ------------------------------
# Main Capture Functions
# ------------------------------

def capture_active_window_screenshot(output_file: str):
    """
    Capture the active window with multi-step fallback strategy:

    STEP A:
    - Try direct window capture (best quality)
    - Skip if fullscreen

    STEP B:
    - Use MSS region crop

    STEP C:
    - Fallback to full display capture
    """

    if is_screen_locked():
        logger.warning("[SKIP] Screen is locked.")
        return None

    win = get_active_window_info()
    if not win:
        return None

    screen = get_screen_for_window(win)

    # STEP A: Direct capture (only for non-fullscreen)
    if not (screen and is_likely_fullscreen(win, screen)):
        result = capture_active_window_direct_with_info(win, output_file)
        if result:
            return result

    # STEP B: MSS region capture
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

    # STEP C: Final fallback (full display)
    display_id = get_display_id_from_mouse()

    image = Quartz.CGDisplayCreateImage(display_id)
    if image:
        url = Quartz.CFURLCreateWithFileSystemPath(None, output_file, Quartz.kCFURLPOSIXPathStyle, False)
        dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
        Quartz.CGImageDestinationAddImage(dest, image, None)
        Quartz.CGImageDestinationFinalize(dest)

    return output_file


def capture_fullscreen(output_file: str):
    """
    Capture full screen and highlight active window with a red border.
    
    Cases:
    - Normal window → draw border around window
    - Fullscreen / unknown → highlight entire active display
    """

    if is_screen_locked():
        logger.warning("[SKIP] Screen is locked.")
        return None

    try:
        win = get_active_window_info()
        is_normal_window = win and win["height"] > 100

        with mss() as sct:
            monitor_all = sct.monitors[0]
            screenshot = sct.grab(monitor_all)

            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            draw = ImageDraw.Draw(img)
            thickness = 3

            if is_normal_window:
                # Draw border around detected window
                left = win["left"] - monitor_all["left"]
                top = win["top"] - monitor_all["top"]
                right = left + win["width"]
                bottom = top + win["height"]
            else:
                # Fullscreen fallback → highlight entire display
                display_id = get_display_id_from_mouse()
                d_bounds = Quartz.CGDisplayBounds(display_id)

                left = int(d_bounds.origin.x) - monitor_all["left"]
                top = int(d_bounds.origin.y) - monitor_all["top"]
                right = left + int(d_bounds.size.width)
                bottom = top + int(d_bounds.size.height)

            for i in range(thickness):
                draw.rectangle(
                    [left - i, top - i, right + i, bottom + i],
                    outline="red"
                )

            img.save(output_file)
            return output_file

    except Exception as e:
        logger.error(f"[ERROR] Fullscreen capture failed: {e}")
        return None


if __name__ == '__main__':
    # add_second_to_utc("2026-01-14 06:49:15.373000+00:00", 2.015)
    a, b = add_second_to_utc("2026-01-14 06:49:18.394000+00:00", 5.04)

    t = get_image_name_to_utc("2c8ea4a694971ac90194b1d4988b02b6_2026-01-14T06-49-22.409657Z.png")
    if a <= t <= b:
        print(f"yes => {t}")
    else:
        print("no")

