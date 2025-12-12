import logging
import os
from time import sleep as time_sleep
from datetime import datetime, time, timedelta

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
            time_sleep(1)  
    
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
            now_time = datetime.now().time()
            if not (self.start_time <= now_time <= self.end_time):               
                logger.warning(f"Job triggered outside of schedule time: {now_time}")
                return

            logger.info("Scheduled screenshot triggered")

            screenshot_path = self._take_screenshot()

            payload = {
                'file_location': screenshot_path,
                'is_idle_screenshot': self.is_idle_screenshot,
            }          

            response = requests.post(self.server_url, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes
            logger.info(f"Upload response => {response.json()}")

        except requests.exceptions.RequestException as req_e:
            logger.error(f"Error during API request: {req_e}")
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")
            