import os 

SCREENSHOT_FOLDER_USER = os.path.join(
                    os.path.expanduser("~"),
                    "Library", "Application Support", "Sundial", "Screenshots", '{user_id}')
SCREENSHOT_FOLDER = os.path.join(
                    os.path.expanduser("~"),
                    "Library", "Application Support", "Sundial", "Screenshots")

INTERVAL = 30  # seconds