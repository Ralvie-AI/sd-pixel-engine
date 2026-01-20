import logging
import os
import json
import subprocess
import shutil
from pathlib import Path
from time import sleep as time_sleep, perf_counter as time_perf_counter
from datetime import datetime, time, timedelta, timezone
from glob import glob


import requests
from mss import mss
from PIL import Image

from sd_pixel_engine.utils import get_image_name_to_utc, add_second_to_utc
from sd_pixel_engine.const import INTERVAL, SCREENSHOT_FOLDER, SCREENSHOT_FOLDER_USER

os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

logger = logging.getLogger(__name__)


def stop_process_by_exe(exe_name, time_sleep_time=0.2):
    logger.info(f"killing start cmd_name {exe_name}")
    subprocess.run(f"taskkill /F /IM {exe_name}", shell=True)
    time_sleep(time_sleep_time)  # wait 200ms for process cleanup

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
                self._sleep_until_next_day()
                continue

            next_run = self._next_run_datetime(now)
            logger.info(f"next run => {next_run}")

            while True:
                now = datetime.now()

                if now >= next_run:
                    break

                start_time = time_perf_counter()
                self._take_screenshot_30_seconds()
                duration = time_perf_counter() - start_time

                logger.info(f"Screenshot took {duration:.4f} seconds")

                # sleep only remaining time in interval
                # sleep_time = max(0, INTERVAL - duration)
                # logger.info(f"sleep_time INTERVAL {sleep_time} seconds")
                time_sleep(INTERVAL)

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


        if not os.path.isdir(screenshot_folder):
            os.makedirs(screenshot_folder)

        # Generate a timestamp for the filename
        utc_now = datetime.now(timezone.utc)
        timestamp = utc_now.strftime("%Y-%m-%dT%H-%M-%S.%fZ")

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
            logger.info(f"Upload response time_specific => {response.json()}")

        except requests.exceptions.RequestException as req_e:
            logger.error(f"Error during API request: {req_e}")
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")

    def get_image_path_and_event_id(self):
        screenshot_folder_user = SCREENSHOT_FOLDER_USER.format(user_id=self.user_id)
        filename_list = glob(os.path.join(screenshot_folder_user, "*.png"))
        filename_list_tmp = sorted(filename_list, reverse=False)
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

        logger.info(f"payload info => {payload}")
        response = requests.post(self.server_url + "get_event_time_range", json=payload)
        response.raise_for_status() # Raise an exception for bad status codes

        logger.info(f"Upload response time_specific => {response.json()}")
        response_result_tmp = response.json()
        # logger.info(f"response_result 1 => {type(response_result_tmp.get('result'))}")
        response_result = json.loads(response_result_tmp["result"])
        # logger.info(f"response_result => {type(response_result)}")
        logger.info(f"response_result => {response_result}")


        if not os.path.isdir(SCREENSHOT_FOLDER):
            os.makedirs(SCREENSHOT_FOLDER)

        screenshot_to_events = []
        if response_result:
            for tmp_file in filename_list_tmp:
                file_utc_time = get_image_name_to_utc(tmp_file)
                # logger.info(f"file_utc_time => {file_utc_time}")
                
                for row in response_result:
                    start_time, end_time = add_second_to_utc(row.get('timestamp'), row.get('duration'))
                    if start_time <= file_utc_time <= end_time:
                        tmp_dict = {}
                        tmp_dict[tmp_file] = row
                        screenshot_to_events.append(tmp_dict)

            logger.info(f"result => {screenshot_to_events}")            

            max_row = max(screenshot_to_events, key=lambda x: list(x.values())[0]['duration'])
            tmp_file = list(max_row.keys())[0]
            screenshot_path = os.path.join(SCREENSHOT_FOLDER, Path(tmp_file).name)
            shutil.copy2(tmp_file, screenshot_path)

            for tmp_file_data in filename_list:
                os.remove(tmp_file_data)        

            logger.info(f"screenshot_path => {screenshot_path}")
            logger.info(f"event_id => {list(max_row.values())[0].get('id')}")
            return screenshot_path, list(max_row.values())[0].get('id')
        
        else: 
            # it will work for idle time
            # {'start_time': '2026-01-20 01:30:16.221777', 'end_time': '2026-01-20 01:44:51.125691'}
            # when the result of start time and end time are not in the range of screenshot image file name.
            # so screenshot_path will be used the lastest screenshot and
            # event_id will be used from the latest event row.
            
            tmp_file = filename_list_tmp[-1]
            screenshot_path = os.path.join(SCREENSHOT_FOLDER, Path(tmp_file).name)
            shutil.copy2(tmp_file, screenshot_path)

            for tmp_file_data in filename_list:
                os.remove(tmp_file_data) 
            logger.info(f"idle time screenshot_path => {screenshot_path}")
            logger.info(f"idle time event_id => {response_result_tmp.get('event_id')}")
            return screenshot_path, response_result_tmp.get('event_id')

    
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
                while sleep_seconds > 0:
                    self._take_screenshot_30_seconds()
                    # sleep 30s or remaining time (whichever is smaller)
                    sleep_chunk = min(INTERVAL, sleep_seconds)
                    logger.info(f"sleep_chunk => {sleep_chunk}")
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
                logger.info(f"Upload response always => {response.json()}")              

                # Move to next anchored slot
                next_run += timedelta(seconds=3600 / self.times_per_hour)
                logger.info(f"First anchored screenshot at bbb {next_run.strftime('%H:%M:%S')}")
                # Safety re-align (sleep / lag)
                if next_run <= datetime.now():
                    next_run = self._next_anchored_time(datetime.now())

            except requests.exceptions.RequestException as req_e:
                logger.error(f"API error: {req_e}")
                time_sleep(10)

            except Exception as e:
                logger.error(f"Anchored scheduler error: {e}")
                time_sleep(10)
