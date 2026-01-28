import logging
import os
import subprocess
from time import sleep as time_sleep
from datetime import datetime, time, timedelta, timezone

import requests
from mss import mss
from PIL import Image

from sd_pixel_engine.utils import stop_process_by_exe


os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)


class ScreenShot:
    def __init__(self, server_url, user_id, start_time=time(0, 0), 
                 end_time=time(23, 59), times_per_hour=1, 
                 days=[0,1,2,3,4], is_idle_screenshot=False):
        """
        server_url: URL to POST screenshots
        start_time, end_time: datetime.time objects (default 8:00 AM - 5:00 PM)
        times_per_hour: number of screenshots per hour (default 7)
        days: allowed weekdays (0=Mon, ..., 4=Fri by default)
        """
        self.user_id = user_id
        self.start_time = start_time
        self.end_time = end_time
        self.server_url = server_url if server_url else "http://localhost:7600/screenshot/"
        self.times_per_hour = times_per_hour
        self.days = days
        self.is_idle_screenshot = is_idle_screenshot
        self.interval = 3600 / times_per_hour  # seconds between screenshots

    
    def _next_run_datetime(self, now: datetime) -> datetime:
        """
        Always returns the next valid execution datetime,
        correctly handling cross-midnight schedules forever.
        """

        interval = timedelta(seconds=self.interval)

        today_start = datetime.combine(now.date(), self.start_time)
        today_end = datetime.combine(now.date(), self.end_time)

        # Handle cross-midnight window
        if today_end <= today_start:
            today_end += timedelta(days=1)

        # If before start → first slot
        if now < today_start:
            return today_start

        # If within window → next aligned slot
        if today_start <= now <= today_end:
            elapsed = (now - today_start).total_seconds()
            slots_passed = int(elapsed // self.interval) + 1
            return today_start + slots_passed * interval

        # After window → next day's first slot
        next_day = now.date() + timedelta(days=1)
        return datetime.combine(next_day, self.start_time)
    
    def _is_within_time_window(self, now: time) -> bool:
        if self.end_time > self.start_time:
            return self.start_time <= now <= self.end_time
        else:
            # Cross-midnight window
            return now >= self.start_time or now <= self.end_time
    
    def run(self):
        logger.info("Screenshot scheduler started (cross-midnight safe)")

        while True:
            now = datetime.now()

            # Determine which day the schedule belongs to
            schedule_day = now.date()
            if self.end_time <= self.start_time and now.time() <= self.end_time:
                schedule_day -= timedelta(days=1)

            if schedule_day.weekday() not in self.days:
                logger.info("Schedule day not allowed. Sleeping until next day.")
                stop_process_by_exe("sd-pixel-engine.exe")
                break                

            next_run = self._next_run_datetime(now)
            logger.info(f"next run => {next_run}")
            sleep_seconds = (next_run - now).total_seconds()
            
            if sleep_seconds > 0:
                logger.info(f"Next screenshot at {next_run}")
                time_sleep(sleep_seconds)

            self._scheduled_job()

    def _sleep_until_next_day(self):
        tomorrow = datetime.combine(
            datetime.now().date() + timedelta(days=1),
            time(0, 0)
        )
        time_sleep((tomorrow - datetime.now()).total_seconds())
    
    def _take_screenshot(self, screenshot_folder=None):

        if screenshot_folder is None:
            screenshot_folder = os.path.join(os.environ['LOCALAPPDATA'], "Sundial", "Sundial", "Screenshots")

        if not os.path.isdir(screenshot_folder):
            os.makedirs(screenshot_folder)

        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{screenshot_folder}/{self.user_id}_{timestamp}.png"

        # The mss library handles the screenshot capture
        # with mss() as sct:
        #     sct.shot(output=output_file)
        
        with mss() as sct:
            monitor = sct.monitors[0]  # all monitors combined
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            img.save(output_file)

        return output_file
    
    def _scheduled_job(self):
        try:           
            now_time = datetime.now().time().replace(second=0, microsecond=0)
            if not self._is_within_time_window(now_time):
                logger.warning(f"Job triggered outside of schedule time: {now_time}")
                stop_process_by_exe("sd-pixel-engine.exe")
                return
           
            logger.info("Scheduled screenshot triggered")

            screenshot_path = self._take_screenshot()
            capture_time =  datetime.now(timezone.utc)

            payload = {
                'file_location': screenshot_path,
                'is_idle_screenshot': self.is_idle_screenshot,
                'created_at': capture_time.isoformat()
            }          

            response = requests.post(self.server_url, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes
            logger.info(f"Upload response time_specific => {response.json()}")

        except requests.exceptions.RequestException as req_e:
            logger.error(f"Error during API request: {req_e}")
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")


    # Always Option Tracking Interval

    def _sleep_until(self, target: datetime):

        while True:
            now = datetime.now()
            remaining = (target - now).total_seconds()

            if remaining <= 0:
                return
            
            # Sleep in small chunks (max 60s)
            time_sleep(min(60, remaining))

    def _next_anchored_time(self, now: datetime) -> datetime:
        
        interval = timedelta(seconds=3600 / self.times_per_hour)

        today_start = datetime.combine(now.date(), self.start_time)

        # If started before today's start_time
        if now < today_start:
            return today_start

        elapsed = now - today_start
        intervals_passed = int(elapsed.total_seconds() // interval.total_seconds()) + 1

        return today_start + interval * intervals_passed
    
    def run_always(self):
        
        logger.info(
            f"Anchored mode: {self.times_per_hour} screenshots/hour "
            f"(every {int(3600 / self.times_per_hour)} seconds)"
        )

        interval = timedelta(seconds=3600 / self.times_per_hour)
        next_run = self._next_anchored_time(datetime.now())

        logger.info(f"First anchored screenshot at {next_run.strftime('%H:%M:%S')}")

        while True:
            try:
                self._sleep_until(next_run)

                logger.info("Taking anchored screenshot")

                screenshot_path = self._take_screenshot()
                capture_time = datetime.now(timezone.utc)

                payload = {
                    "file_location": screenshot_path,
                    "is_idle_screenshot": self.is_idle_screenshot,
                    "created_at": capture_time.isoformat(),
                }

                response = requests.post(self.server_url, json=payload)
                response.raise_for_status()

                logger.info(f"Upload response => {response.json()}")

                # Move to next slot
                next_run += interval

                # FULL re-anchor if system slept too long
                if next_run < datetime.now() - interval:
                    logger.warning("Detected sleep/hibernate — re-anchoring scheduler")
                    next_run = self._next_anchored_time(datetime.now())

            except requests.exceptions.RequestException as req_e:
                logger.error(f"API error: {req_e}")
                time_sleep(10)

            except Exception as e:
                logger.exception("Anchored scheduler error")
                time_sleep(10)
                