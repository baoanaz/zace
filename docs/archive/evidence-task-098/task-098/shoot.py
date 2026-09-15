"""TASK-098 截图脚本：登录页（桌面/窄屏）+ 主应用各页（桌面/窄屏）。

用法: python3 shoot.py <port> <mode: cloud|local> <out_dir> <tag>
"""
import sys
import time

from playwright.sync_api import sync_playwright

PORT = sys.argv[1]
MODE = sys.argv[2]
OUT = sys.argv[3]
TAG = sys.argv[4]

BASE = f"http://127.0.0.1:{PORT}"
EXE = "/home/xuwenzheng/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"

DESKTOP = {"width": 1440, "height": 900}
NARROW = {"width": 390, "height": 780}

PAGES = [("/", "dashboard"), ("/history", "history"), ("/keys", "keys")]


def shoot(pw, viewport, name, path, full=False):
    browser = pw.chromium.launch(executable_path=EXE)
    ctx = browser.new_context(viewport=viewport, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(f"{BASE}{path}", wait_until="networkidle")
    page.wait_for_timeout(700)
    out = f"{OUT}/{TAG}-{name}.png"
    page.screenshot(path=out, full_page=full)
    print("saved", out)
    browser.close()


with sync_playwright() as pw:
    if MODE == "cloud":
        # 登录页：桌面 + 窄屏
        shoot(pw, DESKTOP, "login-desktop", "/login")
        shoot(pw, NARROW, "login-narrow", "/login")
    else:
        for path, key in PAGES:
            shoot(pw, DESKTOP, f"{key}-desktop", path, full=True)
        shoot(pw, NARROW, "dashboard-narrow", "/")
        # 窄屏抽屉打开态
        browser = pw.chromium.launch(executable_path=EXE)
        ctx = browser.new_context(viewport=NARROW, device_scale_factor=1)
        page = ctx.new_page()
        page.goto(f"{BASE}/", wait_until="networkidle")
        page.wait_for_timeout(500)
        btn = page.query_selector("header button")
        if btn:
            btn.click()
            page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/{TAG}-drawer-narrow.png")
        print("saved", f"{OUT}/{TAG}-drawer-narrow.png")
        browser.close()
