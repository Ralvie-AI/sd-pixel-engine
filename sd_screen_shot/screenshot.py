import logging
import os
from time import sleep as  time_sleep
import logging
from datetime import datetime, time

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
        self.interval = 3600 / times_per_hour  # seconds between screenshots
        self.is_idle_screenshot = is_idle_screenshot
  
    def _should_take_screenshot(self):
        now = datetime.now()
        current_time = now.time()
        return now.weekday() in self.days and self.start_time <= current_time <= self.end_time

    def _take_screenshot(self, screenshot_folder=None):

        # today = datetime.now().strftime("%Y-%m-%d")
        # if screenshot_folder is None:
        #     screenshot_folder = os.path.join(os.environ['LOCALAPPDATA'], "Sundial", "Sundial", "Screenshots", today)
        if screenshot_folder is None:
            screenshot_folder = os.path.join(os.environ['LOCALAPPDATA'], "Sundial", "Sundial", "Screenshots")

        if not os.path.isdir(screenshot_folder):
            os.makedirs(screenshot_folder)

        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{screenshot_folder}/{self.user_id}_{timestamp}.png"


        with mss() as sct:
            sct.shot(output=output_file)

        return output_file
    
    def run(self):
        logger.info("Screenshot scheduler started")
        while True:
            # print(datetime.now())
            # print("self.interval 1", self.interval)
            try:
                if self._should_take_screenshot():
                    capture_screenshot_data = self._take_screenshot()  
                    payload = {
                        'file_location': capture_screenshot_data,
                        'is_idle_screenshot': self.is_idle_screenshot,
                    }
                    response = requests.post(self.server_url, json=payload)
                    logger.info(f"response => {response.json()}")  
                    time_sleep(self.interval)
                else:
                    time_sleep(10)  # wait before checking again
            except KeyboardInterrupt:
                logger.info("Screenshot stopped by keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Error in screenshot loop: {e}")
                time_sleep(10)
