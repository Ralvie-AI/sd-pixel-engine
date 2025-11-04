
from datetime import time
import requests

from sd_screen_shot.screenshot import ScreenShot
# from screenshot import ScreenShot

def main() -> None:       
    server_url = None
    # res = requests.get("http://localhost:7600/api/0/getallsettings")    
    # print(res.json())    
    screenshot = ScreenShot(server_url, start_time=time(8, 0), end_time=time(17, 0), times_per_hour=12, days=[0,1,2,3,4])
    screenshot.run()


if __name__ == '__main__':
    main()