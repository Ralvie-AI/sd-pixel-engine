import logging
import os
from time import sleep as time_sleep
from datetime import datetime, time, timedelta, timezone

import schedule
import requests
from mss import mss

os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

class ScreenShot:
    def __init__(self, server_url, user_id, start_time=time(8, 0), 
                 end_time=time(17, 0), times_per_hour=7, 
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

    def _generate_daily_times(self):
        """
        Returns a list of 'HH:MM' strings for a continuous schedule 
        between two times, anchored strictly at the start time.
        """
        today = datetime.now().date()

        interval_minutes = 60 / self.times_per_hour
        interval = timedelta(minutes=interval_minutes)
        
    
        current_dt = datetime.combine(today, self.start_time)
        end_dt = datetime.combine(today, self.end_time)
        
        # Handle schedules that cross midnight (optional, but good practice)
        if end_dt < current_dt:
            end_dt += timedelta(days=1)

        schedule_times = []

 
        while current_dt <= end_dt:
            # Add the current time string to the list
            schedule_times.append(current_dt.strftime("%H:%M"))
            
            # Advance to the next time slot
            current_dt += interval

        return schedule_times    

    def run(self):
        logger.info("Screenshot scheduler started using schedule module")

        last_scheduled_date = None  # track day to avoid duplicate registrations

        while True:
            now = datetime.now()

            # register schedule ONCE per day
            if now.date() != last_scheduled_date:
                last_scheduled_date = now.date()

                if now.weekday() not in self.days:
                    logger.info("Today is not allowed. Waiting 1 hour...")
                    time_sleep(3600)
                    continue

                # RESET schedule for new day
                schedule.clear()

                times = self._generate_daily_times()
                logger.info("Generated today's scheduled screenshot times:")
                logger.info(f"Times => {times}")
                for t in times:
                    schedule.every().day.at(t).do(self._scheduled_job)

            # run jobs
            schedule.run_pending()
            # time_sleep(1)  
    
    def _take_screenshot(self, screenshot_folder=None):

        if screenshot_folder is None:
            screenshot_folder = os.path.join(os.environ['LOCALAPPDATA'], "Sundial", "Sundial", "Screenshots")

        if not os.path.isdir(screenshot_folder):
            os.makedirs(screenshot_folder)

        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{screenshot_folder}/{self.user_id}_{timestamp}.png"

        # The mss library handles the screenshot capture
        with mss() as sct:
            sct.shot(output=output_file)

        return output_file
    
    def _scheduled_job(self):
        try:           
            now_time = datetime.now().time().replace(second=0, microsecond=0)
            if not (self.start_time <= now_time <= self.end_time):               
                logger.warning(f"Job triggered outside of schedule time: {now_time}")
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

            except requests.exceptions.RequestException as req_e:
                logger.error(f"API error: {req_e}")
                time_sleep(10)

            except Exception as e:
                logger.error(f"Anchored scheduler error: {e}")
                time_sleep(10)

    