
import win32gui
import win32con
import threading
import logging
import time
from datetime import datetime

from sd_pixel_engine.utils import stop_process_by_exe

# Global variable to store time just before sleep
last_sleep_time = None          # datetime when we received PBT_APMSUSPEND
# SLEEP_THRESHOLD = 48 * 3600     # 48 hours in seconds
# SLEEP_THRESHOLD = 24 * 3600     # 48 hours in seconds
SLEEP_THRESHOLD = 1800     # 30 minutes
# SLEEP_THRESHOLD = 900     # 15  minutes

logger = logging.getLogger(__name__)


def is_long_sleep() -> bool:
    """
    Call this function whenever you want to check:
    Returns True if last wake-up was after ≥ 48 hours sleep
    Returns False otherwise (short sleep / no sleep info)
    """
    global last_sleep_time
    if last_sleep_time is None:
        return False

    now = datetime.now()
    slept_seconds = (now - last_sleep_time).total_seconds()

    # Optional: reset after check so repeated calls return False until next sleep
    # last_sleep_time = None

    return slept_seconds >= SLEEP_THRESHOLD


def on_long_sleep_detected():
    logger.info(f"Long sleep detected!")
    stop_process_by_exe("sd-pixel-engine.exe")    


def wnd_proc(hwnd, msg, wparam, lparam):
    global last_sleep_time

    if msg == win32con.WM_POWERBROADCAST:
        ts = datetime.now().strftime("%H:%M:%S")

        if wparam == win32con.PBT_APMSUSPEND:
            last_sleep_time = datetime.now()          # ← key moment
            logger.info(f"System is going to sleep => {last_sleep_time}")
            

        elif wparam == win32con.PBT_APMRESUMEAUTOMATIC:
            logger.info(f"Automatic resume => {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        elif wparam == win32con.PBT_APMRESUMESUSPEND:
            logger.info(f"Resume + user present => {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if is_long_sleep():
                on_long_sleep_detected()

    return 0


def create_hidden_power_listener():
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = wnd_proc
    wc.lpszClassName = "LongSleepDetector"
    win32gui.RegisterClass(wc)

    hwnd = win32gui.CreateWindow(
        wc.lpszClassName, "Long Sleep Detector",
        0, 0, 0, 0, 0, 0, 0, 0, None
    )

    win32gui.PumpMessages()  # runs forever


if __name__ == "__main__":
    print("Long sleep (≥48h) detector running... (Ctrl+C to stop)")

    t = threading.Thread(target=create_hidden_power_listener, daemon=True)
    t.start()

    # Example: you can call is_long_sleep() from anywhere / every minute
    try:
        while True:
            time.sleep(60)
            if is_long_sleep():
                print("→ Called from timer: long sleep detected")
            else:
                print("→ Called from timer: short or no sleep")

    except KeyboardInterrupt:
        print("\nStopped.")