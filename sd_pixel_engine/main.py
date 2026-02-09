import os 
import argparse
import shutil
import logging 
from datetime import time

from sd_core.log import setup_logging
from sd_pixel_engine.screenshot import ScreenShot
from sd_pixel_engine.const import SCREENSHOT_FOLDER_USER
from sd_pixel_engine.utils import parse_time, parse_days, str2bool
from sd_pixel_engine.detect_sleep import sleep_wake_monitor_loop

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Screenshot uploader")
    parser.add_argument("--server_url", required=True, help="URL to upload screenshots")
    parser.add_argument("--user_id", required=True, help="User ID for identification")
    parser.add_argument("--start_hour", type=parse_time, default=time(8, 0),
                    help="Start time (HH:MM)")
    parser.add_argument("--end_hour", type=parse_time, default=time(17, 0),
                    help="End time (HH:MM)")
    parser.add_argument("--times_per_hour", type=int, default=7, help="Screenshots per hour")
    parser.add_argument("--days", type=parse_days, default=[0,1,2,3,4], help="Allowed weekdays (0=Mon ... 6=Sun)")
    parser.add_argument("--is_idle_screenshot", type=str2bool, nargs="?", const=True, default=False,
                        help="Enable idle screenshots (true/false, default=False)")
    parser.add_argument("--tracking_interval", type=int, default=0, help="Tracking Intervalr")
 
    args = parser.parse_args()
 
    # Set up logging
    setup_logging(
        "sd-pixel-engine",
        log_stderr=True,
        log_file=True,
    )
 
    screenshot = ScreenShot(
        server_url=args.server_url,
        user_id=args.user_id,
        start_time=args.start_hour,
        end_time=args.end_hour,
        # times_per_hour= 20 ,
        times_per_hour=args.times_per_hour,
        days=args.days,
        is_idle_screenshot=args.is_idle_screenshot
    )
    if args.tracking_interval == 0:
        screenshot.run_always()
    else:
        screenshot.run()
 
 
if __name__ == '__main__':
    detect_sleep_thread = threading.Thread(target=sleep_wake_monitor_loop,daemon=True)
    detect_sleep_thread.start()
    main()