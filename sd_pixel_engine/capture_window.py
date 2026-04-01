import time
import os
import win32gui
import win32ui
from ctypes import windll, byref, Structure, c_long
from PIL import Image
from datetime import datetime

from mss import mss


class RECT(Structure):
    _fields_ = [
        ('left', c_long),
        ('top', c_long),
        ('right', c_long),
        ('bottom', c_long)
    ]


class WindowCapture:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.update_window_rect()

    def update_window_rect(self):
        rect = RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        windll.dwmapi.DwmGetWindowAttribute(
            self.hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            byref(rect),
            16
        )
        self.left = rect.left
        self.top = rect.top
        self.right = rect.right
        self.bottom = rect.bottom
        self.width = self.right - self.left
        self.height = self.bottom - self.top

    def capture(self):
        hwndDC = win32gui.GetWindowDC(self.hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, self.width, self.height)
        saveDC.SelectObject(saveBitMap)

        windll.user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 3)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)

        img = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1
        )

        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, hwndDC)

        return img


def capture_active_window(filename):    
    hwnd = win32gui.GetForegroundWindow()
    wc = WindowCapture(hwnd)
    img = wc.capture()    
    img.save(filename)
    # return filename
    
def capture_full_screen(filename):
     with mss() as sct:
        monitor = sct.monitors[0]  # all monitors combined
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        img.save(filename)

if __name__ == "__main__":
    capture_active_window()