import time
import logging
from datetime import datetime, timedelta

from sd_main.sd_desktop.monitor import stop_process, get_running_process_id

logger = logging.getLogger(__name__)

SLEEP_THRESHOLD = timedelta(minutes=15)
CHECK_INTERVAL = 5  # seconds

last_tick_time = None
already_killed = False


def on_long_sleep_detected(gap: timedelta):
    logger.warning(f"Long sleep detected (gap={gap})")
    pid = get_running_process_id("sd-pixel-engine")
    stop_process(pid)


def sleep_wake_monitor_loop():
    global last_tick_time, already_killed

    logger.info("Starting macOS sleep detector loop")

    last_tick_time = datetime.now()

    while True:
        time.sleep(CHECK_INTERVAL)

        now = datetime.now()
        gap = now - last_tick_time

        # check when wake
        if gap >= SLEEP_THRESHOLD:
            if not already_killed:
                on_long_sleep_detected(gap)
                already_killed = True
            return 

        last_tick_time = now