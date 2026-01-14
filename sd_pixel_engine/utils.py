from datetime import datetime, timezone
import re

# filename: "0a07029c9a901fe0819abf69dca12c0d_2026-01-14T00-55-52.905552Z.png"
# '2026-01-14 00:55:52.905552'
def get_image_name_to_utc(filename : str) -> str:
    ts_part = re.sub(r"^[^_]+_|\.png$", "", filename)
    dt_utc = datetime.strptime(ts_part, "%Y-%m-%dT%H-%M-%S.%fZ").replace(tzinfo=timezone.utc)

    result = dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")

    return result 
