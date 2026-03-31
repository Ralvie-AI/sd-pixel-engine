import os 
import sys 
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def start_exe(exec_cmd, timeout_sec=15):
    logger.info(f"Starting module {exec_cmd}")
    if not isinstance(exec_cmd, list):
        exec_cmd = [exec_cmd]

    logger.debug("Running: {}".format(exec_cmd))

    # Don't display a console window on Windows
    # See: https://github.com/ActivityWatch/activitywatch/issues/212
    startupinfo = None
    if sys.platform in ("win32", "cygwin"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        # Use the 'with' statement to ensure underlying handles are cleaned up even if exceptions occur
        with subprocess.Popen(
                exec_cmd,
                universal_newlines=True,
                startupinfo=startupinfo
        ) as proc:

            try:
                # Block and wait, with a timeout mechanism to prevent the process accumulation
                proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                # If the exe hangs, force kill it to prevent processes from piling up!
                logger.error(f"Task execution timed out ({timeout_sec}s)! Force cleaning up...")
                proc.kill()
                proc.wait()
    except Exception as e:
        logger.error(f"Unexpected error occurred while starting the process: {e}")




if __name__ == "__main__":

    cmd = ['C:\\Users\\armat\\AppData\\Local\\Programs\\Sundial\\sd-pixel-engine.exe', '--server_url', '', '--user_id', '8a8783ee93434e01019372d60b950529', '--start_hour', 
    '00:00', '--end_hour', '23:59', '--times_per_hour', '6', '--days', '0,1,2,3,4,5,6', '--is_idle_screenshot', 'True', '--tracking_interval', '1']
    start_exe(cmd)