import logging
import os
import json
import shutil
from pathlib import Path
from glob import glob
from time import sleep as time_sleep
from datetime import datetime, time, timedelta, timezone

import requests
from PIL import Image

from sd_pixel_engine.utils import get_image_name_to_utc, add_second_to_utc, stop_process_by_exe
from sd_pixel_engine.const import INTERVAL, SCREENSHOT_FOLDER, SCREENSHOT_FOLDER_USER
from sd_pixel_engine.capture_window import capture_screenshots, crop_black_background

os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

logger = logging.getLogger(__name__)

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

            # Determine schedule day (cross-midnight safe)
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

            while sleep_seconds > 0:
                self._take_screenshot_30_seconds()
                # sleep 30s or remaining time (whichever is smaller)
                sleep_chunk = min(INTERVAL, sleep_seconds)                
                time_sleep(sleep_chunk)
                sleep_seconds -= sleep_chunk                

            self._scheduled_job()   

    def _sleep_until_next_day(self):
        tomorrow = datetime.combine(
            datetime.now().date() + timedelta(days=1),
            time(0, 0)
        )
        time_sleep((tomorrow - datetime.now()).total_seconds())
    
    # 2026-01-13 06:58:16.823000+00:00 UTC Time
    # 2026-01-13T06-58-16.823000Z.png
    def _take_screenshot_30_seconds(self, screenshot_folder=None):
        
        if screenshot_folder is None:
            screenshot_folder = SCREENSHOT_FOLDER_USER.format(user_id=self.user_id)

        os.makedirs(screenshot_folder, exist_ok=True)

        try:
            utc_now = datetime.now(timezone.utc)
            timestamp = utc_now.strftime("%Y-%m-%dT%H-%M-%S.%fZ")
            output_file = os.path.join(
                screenshot_folder,
                f"{self.user_id}_{timestamp}.png"
            )

            output_file_ocr = os.path.join(
                screenshot_folder,
                f"{self.user_id}_{timestamp}_ocr.png"
            )           
            capture_screenshots(output_file, output_file_ocr)

        except Exception as e:
            logger.error(f"MSS screenshot capture failed: {e}")

           
    def _scheduled_job(self):
        try:           
            now_time = datetime.now().time().replace(second=0, microsecond=0)
            if not self._is_within_time_window(now_time):
                logger.warning(f"Job triggered outside of schedule time: {now_time}")
                stop_process_by_exe("sd-pixel-engine.exe")
                return
           
            logger.info("Scheduled screenshot triggered")
            capture_time =  datetime.now(timezone.utc)

            screenshot_path, event_id = self.get_image_path_and_event_id()
            payload = {
                'file_location': screenshot_path,
                'is_idle_screenshot': self.is_idle_screenshot,
                'created_at': capture_time.isoformat(),
                'event_id': event_id
            }          

            response = requests.post(self.server_url, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes

        except requests.exceptions.RequestException as req_e:
            logger.error(f"Error during API request: {req_e}")
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")


    def get_image_path_and_event_id(self):
        screenshot_folder_user = SCREENSHOT_FOLDER_USER.format(user_id=self.user_id)
        filename_list = glob(os.path.join(screenshot_folder_user, "*.png"))

        filtered_files = [f for f in filename_list if not f.endswith("_ocr.png")]

        filename_list_tmp = sorted(filtered_files, reverse=False)
        if len(filename_list_tmp) == 1: 
            start_time = get_image_name_to_utc(filename_list_tmp[0])
            end_time = get_image_name_to_utc(filename_list_tmp[0])
        else:
            start_time = get_image_name_to_utc(filename_list_tmp[0])
            end_time = get_image_name_to_utc(filename_list_tmp[-1])

        payload = {
            'start_time': start_time,
            'end_time': end_time,               
        }

        logger.info(f"screenshot time range => {payload}")
        response = requests.post(self.server_url + "get_event_time_range", json=payload)
        response.raise_for_status() # Raise an exception for bad status codes
        
        response_result_tmp = response.json()      
        response_result = json.loads(response_result_tmp["result"])
      
        if not os.path.isdir(SCREENSHOT_FOLDER):
            os.makedirs(SCREENSHOT_FOLDER)

        screenshot_to_events = []
        if response_result and len(response_result) > 1:
            for tmp_file in filename_list_tmp:
                file_utc_time = get_image_name_to_utc(tmp_file)
                
                for row in response_result:
                    start_time, end_time = add_second_to_utc(row.get('timestamp'), row.get('duration'))
                    if start_time <= file_utc_time <= end_time:
                        tmp_dict = {}
                        tmp_dict[tmp_file] = row
                        screenshot_to_events.append(tmp_dict)

            event_id = 0
            if screenshot_to_events:
                max_row = max(reversed(screenshot_to_events), key=lambda x: list(x.values())[0]['duration'])
                tmp_file = list(max_row.keys())[0]
                event_id = list(max_row.values())[0].get('id')

                # logger.info(f"tmp_file => {tmp_file}")
                logger.info(f"event_id => {event_id}")
            else:
                # Get the maximum duration if there is no mapped between events time and 
                # screenshot capture time.
                # Get the latest screenshot if there are more than one screenshots.

                max_row = max(response_result, key=lambda x: x['duration'])
                event_id = max_row.get('id')
        
                if len(filename_list_tmp) > 1:
                    tmp_file = filename_list_tmp[-1]
                else:
                    tmp_file = filename_list_tmp[0]
                
                logger.info(f"event_id => {event_id}")            

            screenshot_path = self.move_image_file(tmp_file)         

            for tmp_file_data in filename_list:
                os.remove(tmp_file_data)

            return screenshot_path, event_id
        
        else: 
            # it will work for idle time
            # {'start_time': '2026-01-20 01:30:16.221777', 'end_time': '2026-01-20 01:44:51.125691'}
            # when the result of start time and end time are not in the range of screenshot image file name.
            # so screenshot_path will be used the lastest screenshot and
            # event_id will be used from the latest event row.
            
            tmp_file = filename_list_tmp[-1]            

            screenshot_path = self.move_image_file(tmp_file)

            for tmp_file_data in filename_list:
                os.remove(tmp_file_data)             

            if response_result:
                event_id = response_result[0].get('id')
                logger.info(f"idle time event_id => {event_id}")
            else:
                if isinstance(response_result_tmp, dict):
                    event_id = response_result_tmp.get('event_id')
                    logger.info(f"idle time event_id => {event_id}")
            return screenshot_path, event_id
        
    def get_readable_file_size(self, file_path):
        size_bytes = os.path.getsize(file_path)
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024

    def aggressive_compress_png(self, input_path, output_path):                   
            
        with Image.open(input_path) as img:
            # 1. Convert to RGB if necessary
            if img.mode != "RGB":
                img = img.convert("RGB")
                
            # 2. Resize the image (PNGs at 4K or 1080p are rarely under 500kb)
            # We will scale it down to a max width of 1280px to save space
            width, height = img.size
            if width > 1280:
                ratio = 1280 / width
                new_size = (1280, int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                print(f"Resized to {new_size[0]}x{new_size[1]}")

            # 3. Apply Quantization (The most important step for PNG size)
            # We reduce the image to a 256-color palette
            print("Applying color quantization...")
            img = img.convert("P", palette=Image.ADAPTIVE, colors=256)

            os.remove(input_path)
            
            # 4. Save with optimization
            img.save(output_path, "PNG", optimize=True)
    
    def move_image_file(self, tmp_file):
        # logger.info(f"tmp_file => {tmp_file}")
        full_screen_img = Path(tmp_file).name
        tmp_ocr, ocr_ext = os.path.splitext(full_screen_img)
        ocr_img = tmp_ocr + "_ocr.png"
        screenshot_path = os.path.join(SCREENSHOT_FOLDER, full_screen_img)
        screenshot_ocr_path = os.path.join(SCREENSHOT_FOLDER, ocr_img)
        
        tmp_ocr_full_path, ocr_tmp_ext = os.path.splitext(tmp_file)
        ocr_tmp_file = tmp_ocr_full_path + "_ocr.png"

        shutil.copy2(tmp_file, screenshot_path)
        shutil.copy2(ocr_tmp_file, screenshot_ocr_path)

        crop_black_background(screenshot_path, screenshot_path)

        if os.path.getsize(screenshot_path) > 1024 * 1024:
            file_size = self.get_readable_file_size(screenshot_path)
            logger.info(f"File size => {file_size}")
            self.aggressive_compress_png(screenshot_path, screenshot_path)

        return screenshot_path


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

        next_run = self._next_anchored_time(datetime.now())

        logger.info(f"First anchored screenshot at {next_run.strftime('%H:%M:%S')}")

        while True:
            try:
                now = datetime.now()

                sleep_seconds = (next_run - now).total_seconds()
                while sleep_seconds > 0:
                    self._take_screenshot_30_seconds()
                    # sleep 30s or remaining time (whichever is smaller)
                    sleep_chunk = min(INTERVAL, sleep_seconds)
                    time_sleep(sleep_chunk)
                    sleep_seconds -= sleep_chunk
                    
                logger.info("Taking anchored screenshot")

                capture_time =  datetime.now(timezone.utc)

                screenshot_path, event_id = self.get_image_path_and_event_id()
                payload = {
                    'file_location': screenshot_path,
                    'is_idle_screenshot': self.is_idle_screenshot,
                    'created_at': capture_time.isoformat(),
                    'event_id': event_id
                }          

                response = requests.post(self.server_url, json=payload)
                response.raise_for_status() # Raise an exception for bad status codes
                # logger.info(f"Upload response always => {response.json()}")              

                # Move to next anchored slot
                next_run += timedelta(seconds=3600 / self.times_per_hour)
                logger.info(f"Second anchored screenshot at {next_run.strftime('%H:%M:%S')}")
                # Safety re-align (sleep / lag)
                if next_run <= datetime.now():
                    next_run = self._next_anchored_time(datetime.now())

            except requests.exceptions.RequestException as req_e:
                logger.error(f"API error: {req_e}")
                time_sleep(10)

            except Exception as e:
                logger.exception("Anchored scheduler error")
                time_sleep(10)
