import subprocess
import os 
import sys

import logging 


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_running_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)

    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base, "../../../sd-pixel-engine/dist/sd-pixel-engine/"))

file_location = get_running_path()
exe_path  = os.path.join(file_location, "sd-pixel-engine")


def start_exe(exec_cmd, process_name=None):
    if not isinstance(exec_cmd, list):
        print("no list")
        exec_cmd = [exec_cmd]        
    else:
        print("list")
                  
    logger.info(f"Starting module {exec_cmd}")
     
    logger.debug("Running: {}".format(exec_cmd))

    # Don't display a console window on Windows
    # See: https://github.com/ActivityWatch/activitywatch/issues/212
    startupinfo = None
    if sys.platform == "win32" or sys.platform == "cygwin":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
   

    # There is a very good reason stdout and stderr is not PIPE here
    # See: https://github.com/ActivityWatch/aw-server/issues/27
    _process = subprocess.Popen(
        exec_cmd, universal_newlines=True, startupinfo=startupinfo
    )


# logger.info(f"starting sd-screen-shot => {file_location}")
# screenshot_exe_file = os.path.join(file_location, "sd-screen-shot.exe")   
screenshot_exe_file = exe_path
logger.info(f"screenshot is file => {os.path.isfile(screenshot_exe_file)}")

CAPTURED_DAYS = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
res_data = {
    "code": "RCI0000",
    "message": "Success",
    "data": {
        "userSetting": None,
        "companySetting": {
            "captureCount": 6,
            "trackingOptions": "always",
            "dayOptions": [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday"
            ],
            "startTime": "00:00",
            "endTime": "23:59",
            "screenshotFunction": True,
            "deleteScreenshot": True,
            "idleScreenshot": True,
            "viewScreenshot": True,
            "userAccessScreenshot": True
        }
    },
    "mid": "9191a94afe814a4dbccf468f3aa73e3c",
    "timestamp": 1767679569226
}


if res_data:

    # user_id = creds.get('userId')
    user_id = "0a07029c9a901fe0819abf69dca12c0d"
    times_per_hour = None
    if res_data.get('data').get('companySetting'):
        logger.info(f"companySetting => {res_data.get('data').get('companySetting')}")
        times_per_hour = res_data.get('data').get('companySetting').get('captureCount')
        start_hour = res_data.get('data').get('companySetting').get('startTime')
        end_hour = res_data.get('data').get('companySetting').get('endTime')
        day_options = res_data.get('data').get('companySetting').get('dayOptions')

        # "screenshotFunction": true,  // If this flag is false means screenshot will not capture for any user
        is_screen_shot_run = res_data.get('data').get('companySetting').get('screenshotFunction')
        is_idle_screen_shot = res_data.get('data').get('companySetting').get('idleScreenshot')
        print("is_idle_screen_shot ", is_idle_screen_shot)
        print(f"is_idle_screen_shot => {str(is_idle_screen_shot)} => type => {type(str(is_idle_screen_shot))}")
        

        days_lst = []
        for day in day_options:                        
            days_lst.append(CAPTURED_DAYS.get(day))

        days_tmp_list = map(str, days_lst)
        days = ",".join(days_tmp_list)    

        command_list = [
            screenshot_exe_file,
            "--server_url", "",
            "--user_id", str(user_id),
            "--start_hour", str(start_hour),
            "--end_hour", str(end_hour),
            "--times_per_hour", str(times_per_hour),
            "--days", days,
            "--is_idle_screenshot", str(is_idle_screen_shot),
            "--tracking_interval", str(1)

        ]


        logger.info(f"command_list => {str(command_list)}")
        logger.info(f"is_screen_shot_run => {is_screen_shot_run}")

        if is_screen_shot_run:
            logger.info(f"command_list => {str(command_list)}")
            start_exe(command_list)