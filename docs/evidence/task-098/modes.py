"""登录页三模式核验（login / register / bootstrap）+ 登出回归。"""
from playwright.sync_api import sync_playwright

EXE = "/home/xuwenzheng/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
fails = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{('  -> ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=EXE)

    # 1) register 模式
    p = b.new_context(viewport={"width": 1200, "height": 800}).new_page()
    p.goto("http://127.0.0.1:8122/login", wait_until="networkidle")
    check("register 模式 h1=登录", p.inner_text("h1") == "登录", p.inner_text("h1"))
    check("register 模式有「没有账户？注册」", "没有账户？注册" in p.inner_text("form"))
    check("register 模式无确认密码字段", p.query_selector('input[name="confirm"]') is None)
    p.click('button:text-is("没有账户？注册")')
    p.wait_for_timeout(300)
    check("切到注册 → h1=注册", p.inner_text("h1") == "注册", p.inner_text("h1"))
    check("注册有确认密码字段", p.query_selector('input[name="confirm"]') is not None)
    check("注册有「已有账户？登录」", "已有账户？登录" in p.inner_text("form"))
    p.screenshot(path="after/after-login-register-desktop.png")
    print("saved after/after-login-register-desktop.png")
    p.close()

    # 2) bootstrap 模式
    p = b.new_context(viewport={"width": 1200, "height": 800}).new_page()
    p.goto("http://127.0.0.1:8123/login", wait_until="networkidle")
    check("bootstrap 模式 h1=初始化账户", p.inner_text("h1") == "初始化账户", p.inner_text("h1"))
    check("bootstrap 提示「首次部署」", "首次部署" in p.inner_text("form"))
    check("bootstrap 无确认密码字段", p.query_selector('input[name="confirm"]') is None)
    p.screenshot(path="after/after-login-bootstrap-desktop.png")
    print("saved after/after-login-bootstrap-desktop.png")
    p.close()

    # 3) 登录失败路径（错误展示）
    p = b.new_context(viewport={"width": 1200, "height": 800}).new_page()
    p.goto("http://127.0.0.1:8120/login", wait_until="networkidle")
    p.fill('input[name="name"]', "owner")
    p.fill('input[name="password"]', "wrong")
    p.click('button[type="submit"]')
    p.wait_for_timeout(800)
    # mock 未实现 login → 404 信封，ErrorBlock 应显示
    check("登录失败显示错误块", p.query_selector(".text-rose-800") is not None,
          (p.query_selector(".text-rose-800").inner_text() if p.query_selector(".text-rose-800") else ""))
    p.close()
    b.close()

print()
print("FAILURES:", fails if fails else "none")
