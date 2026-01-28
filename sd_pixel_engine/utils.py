
import re
import argparse
import Quartz
from AppKit import NSScreen
from mss import mss
from PIL import Image

from datetime import datetime, timezone, timedelta, time


# filename: "0a07029c9a901fe0819abf69dca12c0d_2026-01-14T00-55-52.905552Z.png"
# '2026-01-14 00:55:52.905552'
def get_image_name_to_utc(filename : str) -> str:
    ts_part = re.sub(r"^[^_]+_|\.png$", "", filename)
    dt_utc = datetime.strptime(ts_part, "%Y-%m-%dT%H-%M-%S.%fZ").replace(tzinfo=timezone.utc)

    result = dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")

    return result 

def get_image_name_to_utc_dt(filename: str) -> datetime:
    ts_part = re.sub(r"^[^_]+_|\.png$", "", filename)
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
    
def get_main_screen_bounds():
    """
    Return main screen bounds as MSS-compatible dict
    """
    screen = NSScreen.mainScreen().frame()
    return {
        "left": int(screen.origin.x),
        "top": int(screen.origin.y),
        "width": int(screen.size.width),
        "height": int(screen.size.height),
    }


def clamp_region(region, screen):
    """
    Clamp window bounds to screen bounds.
    Return None if the window does not overlap the screen at all.
    """
    left = max(region["left"], screen["left"])
    top = max(region["top"], screen["top"])

    right = min(
        region["left"] + region["width"],
        screen["left"] + screen["width"],
    )
    bottom = min(
        region["top"] + region["height"],
        screen["top"] + screen["height"],
    )

    width = right - left
    height = bottom - top

    if width <= 0 or height <= 0:
        return None

    return {
        "left": int(left),
        "top": int(top),
        "width": int(width),
        "height": int(height),
    }


def get_active_window_bounds():
    """
    Get the current active on-screen window bounds using Quartz.
    Return None if no active window exists (empty desktop).
    """
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID
    )

    for win in window_list:
        if not win.get("kCGWindowIsOnscreen"):
            continue
        if win.get("kCGWindowLayer") != 0:
            continue

        bounds = win.get("kCGWindowBounds")
        if not bounds:
            continue

        return {
            "left": int(bounds["X"]),
            "top": int(bounds["Y"]),
            "width": int(bounds["Width"]),
            "height": int(bounds["Height"]),
            "owner": win.get("kCGWindowOwnerName", "unknown"),
        }

    return None

def is_bad_mss_capture(img, win, screen):
    """
    Detect broken MSS captures on macOS fullscreen apps
    """
    if img.height < screen["height"] * 0.25:
        return True

    if (
        win
        and win["width"] >= screen["width"] * 0.95
        and win["height"] >= screen["height"] * 0.95
        and img.height < screen["height"] * 0.9
    ):
        return True

    return False


def capture_active_window_screenshot(output_file: str):
    """
    Smart screenshot:
    1) Active window (MSS)
    2) Fullscreen app fallback
    3) Empty desktop
    """
    screen = get_main_screen_bounds()
    win = get_active_window_bounds()

    # -------------------------------------------------
    # Case 3: Empty desktop
    # -------------------------------------------------
    if not win:
        image = Quartz.CGDisplayCreateImage(Quartz.CGMainDisplayID())
        if image:
            url = Quartz.CFURLCreateWithFileSystemPath(
                None, output_file, Quartz.kCFURLPOSIXPathStyle, False
            )
            dest = Quartz.CGImageDestinationCreateWithURL(
                url, "public.png", 1, None
            )
            Quartz.CGImageDestinationAddImage(dest, image, None)
            Quartz.CGImageDestinationFinalize(dest)
        return

    # -------------------------------------------------
    # Case 1: Active window (MSS)
    # -------------------------------------------------
    region = clamp_region(win, screen)

    if region:
        try:
            with mss() as sct:
                grab = sct.grab(region)

                if is_bad_mss_capture(grab, win, screen):
                    raise RuntimeError("Bad MSS capture")

                img = Image.frombytes("RGB", grab.size, grab.rgb)
                img.save(output_file)
                return
        except Exception:
            pass

    # -------------------------------------------------
    # Case 2: Fullscreen fallback
    # -------------------------------------------------
    image = Quartz.CGDisplayCreateImage(Quartz.CGMainDisplayID())
    if image:
        url = Quartz.CFURLCreateWithFileSystemPath(
            None, output_file, Quartz.kCFURLPOSIXPathStyle, False
        )
        dest = Quartz.CGImageDestinationCreateWithURL(
            url, "public.png", 1, None
        )
        Quartz.CGImageDestinationAddImage(dest, image, None)
        Quartz.CGImageDestinationFinalize(dest)


if __name__ == '__main__':
    # add_second_to_utc("2026-01-14 06:49:15.373000+00:00", 2.015)
    a, b = add_second_to_utc("2026-01-14 06:49:18.394000+00:00", 5.04)

    t = get_image_name_to_utc("2c8ea4a694971ac90194b1d4988b02b6_2026-01-14T06-49-22.409657Z.png")
    if a <= t <= b:
        print(f"yes => {t}")
    else:
        print("no")

