from datetime import datetime, timezone
import re

# filename: "0a07029c9a901fe0819abf69dca12c0d_2026-01-14T00-55-52.905552Z.png"
# '2026-01-14 00:55:52.905552'
def get_image_name_to_utc(filename : str) -> str:
    ts_part = re.sub(r"^[^_]+_|\.png$", "", filename)
    dt_utc = datetime.strptime(ts_part, "%Y-%m-%dT%H-%M-%S.%fZ").replace(tzinfo=timezone.utc)

    result = dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")

    return result 


def add_second_to_utc(date_time, seconds):
    from datetime import datetime, timedelta

    # 1. Define your starting timestamp string
    timestamp_str = date_time

    # 2. Parse the string into a datetime object
    # .fromisoformat() handles the timezone (+00:00) automatically
    dt = datetime.fromisoformat(timestamp_str)

    # 3. Add 9.095 seconds using timedelta
    new_dt = dt + timedelta(seconds=seconds)

    print(f"Original: {dt}")
    print(f"New Time: {new_dt}")
    a = dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    b = new_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    print(type(a), a)
    print(type(b), b)
    return a, b


if __name__ == '__main__':
    # add_second_to_utc("2026-01-14 06:49:15.373000+00:00", 2.015)
    a, b = add_second_to_utc("2026-01-14 06:49:18.394000+00:00", 5.04)

    t = get_image_name_to_utc("2c8ea4a694971ac90194b1d4988b02b6_2026-01-14T06-49-22.409657Z.png")
    if a <= t <= b:
        print(f"yes => {t}")
    else:
        print("no")
