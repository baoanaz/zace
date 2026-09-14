"""登出回归：云端已登录 → 侧边栏底部有账户名与登出按钮 → 点击后回登录页。"""
from playwright.sync_api import sync_playwright
EXE = "/home/xuwenzheng/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
fails = []
def check(l, ok, d=""):
    print(f"{'PASS' if ok else 'FAIL'}  {l}{('  -> ' + d) if d else ''}")
    if not ok: fails.append(l)
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=EXE)
    p = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    p.goto("http://127.0.0.1:8124/", wait_until="networkidle")
    check("云端已登录直接进控制台", "控制台" in p.inner_text("body"))
    aside = p.query_selector('[data-testid="sidebar"]')
    check("侧边栏底部显示账户名", "xuwenzheng" in aside.inner_text(), aside.inner_text().replace("\n", " | "))
    check("侧边栏底部有登出按钮", p.query_selector('button:text-is("登出")') is not None)
    p.screenshot(path="after/after-dashboard-signedin-desktop.png")
    print("saved after/after-dashboard-signedin-desktop.png")
    p.click('button:text-is("登出")')
    p.wait_for_timeout(1200)
    check("登出后回到登录页", p.url.endswith("/login") and p.inner_text("h1") == "登录", f"{p.url} h1={p.inner_text('h1')}")
    b.close()
print()
print("FAILURES:", fails if fails else "none")
