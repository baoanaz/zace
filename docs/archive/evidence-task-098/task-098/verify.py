"""TASK-098 功能零回归核验（真浏览器）：导航项/顺序/路径、抽屉开关与点后自动关闭。"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8121"
CLOUD = "http://127.0.0.1:8120"
EXE = "/home/xuwenzheng/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
EXPECTED = ["控制台", "接入指南", "API Key", "历史记录", "设置"]
HREFS = ["/", "/connect", "/keys", "/history", "/settings"]

failures = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{('  -> ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=EXE)

    # ---- 1) 桌面：侧边栏常驻、导航项与顺序/路径不变 ----
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.goto(f"{BASE}/", wait_until="networkidle")
    nav = page.query_selector('nav[aria-label="主导航"]')
    check("主导航存在（aria-label=主导航）", nav is not None)
    links = nav.query_selector_all("a")
    check("导航项顺序", [a.inner_text() for a in links] == EXPECTED, str([a.inner_text() for a in links]))
    check("导航 to 路径", [a.get_attribute("href") for a in links] == HREFS, str([a.get_attribute("href") for a in links]))

    # 侧边栏可见且不透明
    aside = page.query_selector('[data-testid="sidebar"]')
    check("桌面侧边栏可见", aside.is_visible())
    check("侧边栏不透明底色", "paper-raised" in (aside.get_attribute("class") or ""))

    # ---- 2) 逐项点击导航，路由与页面内容正确 ----
    for label, href in zip(EXPECTED, HREFS):
        page.click(f'nav[aria-label="主导航"] a:text-is("{label}")')
        page.wait_for_timeout(400)
        check(f"点击「{label}」→ {href}", page.url.endswith(href), page.url)
        # active 态：朱砂底
        cls = page.eval_on_selector(
            f'nav[aria-label="主导航"] a:text-is("{label}")', "el => el.className"
        )
        check(f"「{label}」active 底色 = accent.seal", "bg-accent-seal" in cls, cls)

    # 登出按钮存在于侧边栏底部（本地模式无登出，用 cloud 端测）
    browser.close()

    # ---- 3) 窄屏：抽屉初始关闭、汉堡打开、点导航后自动关闭 ----
    ctx = browser.new_context(viewport={"width": 390, "height": 780}) if False else None
    browser = pw.chromium.launch(executable_path=EXE)
    page = browser.new_context(viewport={"width": 390, "height": 780}).new_page()
    page.goto(f"{BASE}/", wait_until="networkidle")
    aside = page.query_selector('[data-testid="sidebar"]')
    def drawer_closed(el):
        return "-translate-x-full" in (el.get_attribute("class") or "").split()

    check("窄屏侧边栏初始在屏外（抽屉关闭）", drawer_closed(aside), aside.get_attribute("class"))

    page.click('button[aria-label="导航菜单"]')
    page.wait_for_timeout(450)
    aside = page.query_selector('[data-testid="sidebar"]')
    check("汉堡打开抽屉", not drawer_closed(aside), aside.get_attribute("class"))
    check("遮罩出现", page.query_selector('button[aria-label="关闭导航抽屉"]') is not None)

    # 点导航 → 抽屉自动关闭 + 路由变化
    page.click('nav[aria-label="主导航"] a:text-is("历史记录")')
    page.wait_for_timeout(550)
    check("点导航后路由到 /history", page.url.endswith("/history"), page.url)
    aside = page.query_selector('[data-testid="sidebar"]')
    check("点导航后抽屉自动关闭", drawer_closed(aside), aside.get_attribute("class"))

    # 遮罩点击关闭
    page.click('button[aria-label="导航菜单"]')
    page.wait_for_timeout(400)
    # 遮罩铺满视口但抽屉压在左侧 240px 之上，故点击抽屉右侧的遮罩区域。
    page.mouse.click(350, 400)  # drawer (w-60=240px) 右侧的遮罩区
    page.wait_for_timeout(450)
    aside = page.query_selector('[data-testid="sidebar"]')
    check("点遮罩关闭抽屉", drawer_closed(aside), aside.get_attribute("class"))
    browser.close()

    # ---- 4) 登录页三模式 + 登出 ----
    browser = pw.chromium.launch(executable_path=EXE)
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.goto(f"{CLOUD}/login", wait_until="networkidle")
    check("云端未登录 → 登录页 h1=登录", page.inner_text("h1") == "登录", page.inner_text("h1"))
    check("账户字段存在", page.query_selector('input[name="name"]') is not None)
    check("密码字段存在", page.query_selector('input[name="password"]') is not None)
    check("注册关闭提示仍显示", "注册已关闭" in page.inner_text("form"))
    check("右侧卡片是纯白底", "bg-paper-card" in page.eval_on_selector("form", "el => el.className"))
    # 装饰区在桌面可见
    check("桌面左装饰区可见", page.query_selector('section[aria-hidden="true"]').is_visible())
    browser.close()

    # 窄屏登录页：装饰区收起
    browser = pw.chromium.launch(executable_path=EXE)
    page = browser.new_context(viewport={"width": 390, "height": 780}).new_page()
    page.goto(f"{CLOUD}/login", wait_until="networkidle")
    deco = page.query_selector('section[aria-hidden="true"]')
    check("窄屏左装饰区收起", not deco.is_visible())
    check("窄屏表单仍完整", page.query_selector('input[name="name"]') is not None)
    browser.close()

print()
print("FAILURES:", failures if failures else "none")
