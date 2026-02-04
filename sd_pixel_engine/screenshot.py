import logging
import os
from time import sleep as  time_sleep
import logging
import platform
import signal

from datetime import datetime, time, timedelta, timezone

from mss import mss
from PIL import Image
import requests
import subprocess

from sd_main.sd_desktop.monitor import stop_process, get_running_process_id


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
    
    def _log_today_schedule(self, now: datetime):
        slots = []

        current = datetime.combine(now.date(), self.start_time)
        today_end = datetime.combine(now.date(), self.end_time)

        # cross-midnight
        if self.end_time <= self.start_time:
            today_end += timedelta(days=1)

        interval = timedelta(seconds=self.interval)

        while current <= today_end:
            slots.append(current.strftime("%H:%M:%S"))
            current += interval

        logger.info(f"Times => {slots}")

    
    def run(self):
        logger.info("Screenshot scheduler started (cross-midnight safe)")
        last_logged_date = None

        while True:
            now = datetime.now()
            # Determine which day the schedule belongs to
            schedule_day = now.date()

            if now.date() != last_logged_date:
                last_logged_date = now.date()
                self._log_today_schedule(now)

            if self.end_time <= self.start_time and now.time() <= self.end_time:
                schedule_day -= timedelta(days=1)

            if schedule_day.weekday() not in self.days:
                logger.info("Schedule day not allowed. Sleeping until next day.")
                screenshot_pid = get_running_process_id("sd-pixel-engine")
                stop_process(screenshot_pid)
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
        system = platform.system()

        if screenshot_folder is None:
            if system == "Darwin":
                screenshot_folder = os.path.join(
                    os.path.expanduser("~"),
                    "Library", "Application Support", "Sundial", "Screenshots"
                )

        if not os.path.isdir(screenshot_folder):
            os.makedirs(screenshot_folder)

        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = f"{screenshot_folder}/screenshot_{timestamp}.png"

        with mss() as sct:
            # for i, m in enumerate(sct.monitors):
            #     logger.info(f"Monitor {i}: {m}")
            # sct.shot(output=output_file)
            monitor = sct.monitors[0]  # all monitors combined
            screenshot = sct.grab(monitor)

            img = Image.frombytes(
                "RGB",
                screenshot.size,
                screenshot.rgb
            )
            img.save(output_file)

        return output_file

    def _scheduled_job(self):
        try:           
            now_time = datetime.now().replace(microsecond=0).time()
            logger.info(f"now_time {now_time}")
            if not self._is_within_time_window(now_time):               
                logger.warning(f"Job triggered outside of schedule time: {now_time}")
                screenshot_pid = get_running_process_id("sd-pixel-engine")
                stop_process(screenshot_pid)
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

        next_run = self._next_anchored_time(datetime.now())
        logger.info(f"First anchored screenshot at {next_run.strftime('%H:%M:%S')}")

        while True:
            try:  
                now = datetime.now()

                sleep_seconds = (next_run - now).total_seconds()
                if sleep_seconds > 0:
                    time_sleep(sleep_seconds)

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

                # Move to next anchored slot
                next_run += timedelta(seconds=3600 / self.times_per_hour)

                # Safety re-align (sleep / lag)
                if next_run <= datetime.now():
                    next_run = self._next_anchored_time(datetime.now())
                    
                # shot_time = datetime.now()
                # next_run = shot_time + timedelta(seconds=3600 / self.times_per_hour)

            except requests.exceptions.RequestException as req_e:
                logger.error(f"API error: {req_e}")
                time_sleep(10)
            except Exception as e:
                logger.error(f"Anchored scheduler error: {e}")
                time_sleep(10)


