import logging
import os
import platform
from time import sleep as  time_sleep
import logging

from datetime import datetime, time

from mss import mss
import requests

PROTOCOL = "http"
# HOST = "localhost:3323"
HOST = "182.66.219.114:9010"

HOST_TO_UPLOAD_SHOT_GET = f"{PROTOCOL}://{HOST}/web/events/screenshot?fileFormat=jpg"  

MAX_RETRIES = 3
DELAY_SECONDS = 3  # wait before retry

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)


class ScreenShot:
    def __init__(self, server_url, start_time=time(8, 0), end_time=time(17, 0), times_per_hour=7, days=[0,1,2,3,4]):
        """
        server_url: URL to POST screenshots
        start_time, end_time: datetime.time objects (default 8:00 AM - 5:00 PM)
        times_per_hour: number of screenshots per hour (default 7)
        days: allowed weekdays (0=Mon, ..., 4=Fri by default)
        """
        self.start_time = start_time
        self.end_time = end_time
        self.server_url = server_url if server_url else "http://localhost:7600/screenshot/"
        self.times_per_hour = times_per_hour
        self.days = days
        self.interval = 3600 / times_per_hour  # seconds between screenshots

    def _should_take_screenshot(self):
        now = datetime.now()
        current_time = now.time()
        return now.weekday() in self.days and self.start_time <= current_time <= self.end_time

    def _take_screenshot(self, screenshot_folder=None):

        today = datetime.now().strftime("%Y-%m-%d")
        if screenshot_folder is None:
            screenshot_folder = os.path.join(os.environ['LOCALAPPDATA'], "Sundial", "Sundial", "Screenshots", today)

        if not os.path.isdir(screenshot_folder):
            os.makedirs(screenshot_folder)

        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = f"{screenshot_folder}/screenshot_{timestamp}.png"

        print("output_file ", output_file)

        with mss() as sct:
            sct.shot(output=output_file)

        print("is file", output_file, "=>" ,os.path.isfile(output_file))
        return output_file
    
    def get_pre_signed_url(self):
        result = None 
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                res = requests.get(HOST_TO_UPLOAD_SHOT_GET)
                data = res.json()
                result = data.get('data').get("preSignedUrl"), data.get('data').get("objectKey")
                break
            except Exception as e:
                logging.error("[ERROR]: %s", e)
                if attempt == MAX_RETRIES:
                    logging.info("Failed after retries.")
                else:
                    time_sleep(DELAY_SECONDS)
        return result 
       
    def update_object_key_file(self, url_path):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                res = requests.put(url_path)
                data = res.json()
                print("data", data)
                logging.info(f"Upload failed with status code: {data.get('code')}")
                logging.info(f"Url to download: {data.get('data').get('url')}")
                break
            except Exception as e:
                logging.error("[ERROR]: %s", e)
                if attempt == MAX_RETRIES:
                    logging.info("Failed after retries.")
                else:
                    time_sleep(DELAY_SECONDS)

    def upload_screenshot(self, file_path, presigned_url):

        try:
            # Open the file in binary mode
            with open(file_path, 'rb') as file_obj:
                # Perform HTTP PUT request to upload file
                response = requests.put(presigned_url, data=file_obj)    
            # Check response code (200 or 204 usually means success for S3)
            if response.status_code in [200, 204]:
                return {
                    "status": "SUCCESS",
                    "message": None
                }
            else:
                logging.info(f"Upload failed with status code: {response.status_code}")
                return {
                    "status": "ERROR",
                    "message": f"Upload failed with status code: {response.status_code}"
                }    
        except Exception as e:
            logging.info(f"Exception during upload: {str(e)}")
            return {
                "status": "ERROR",
                "message": str(e)
            }


    def run(self):
        logger.info("Screenshot scheduler started")
        while True:
            try:
                if self._should_take_screenshot():
                    capture_screenshot_data = self._take_screenshot()
                    pre_signed_url, object_key = self.get_pre_signed_url()
                    # print("object_key ", object_key)
                    res = self.upload_screenshot(capture_screenshot_data, pre_signed_url)
                    if res.get('status') == "SUCCESS":
                        payload = {
                            'object_key': object_key,
                            'file_location': capture_screenshot_data
                        }
                        response = requests.post(self.server_url, json=payload)
                        print("response ", response.json())
                        logger.info(f"response => {response.json()}")  
                        logger.info(f"result url => {object_key}")  
                    time_sleep(self.interval)
                else:
                    time_sleep(10)  # wait before checking again
            except KeyboardInterrupt:
                logger.info("Screenshot stopped by keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Error in screenshot loop: {e}")
                time_sleep(10)

