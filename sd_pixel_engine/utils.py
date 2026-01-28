
import subprocess
import logging 
import time 


logger = logging.getLogger(__name__)


def stop_process_by_exe(exe_name, time_sleep=0.2):
    logger.info(f"killing start cmd_name {exe_name}")
    subprocess.run(f"taskkill /F /IM {exe_name}", shell=True)
    time.sleep(time_sleep)  # wait 200ms for process cleanup