#!/usr/bin/env python
"""在临时数据库和独立端口中验证网页与 worker，不修改使用者的数据或账号。"""
import argparse
import io
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def check_pages(base_url, executable, artifacts, password):
    from playwright.sync_api import sync_playwright

    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        # 故意使用美国时区：图表仍应与北京时间的网页快照表一致。
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="America/New_York")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base_url + "/")
        assert "/accounts/login/" in page.url, "匿名访问应重定向到登录页"
        page.get_by_label("用户名").fill("browser-check")
        page.get_by_label("密码").fill("incorrect-password")
        page.get_by_role("button", name="登录", exact=True).click()
        page.locator(".errorlist").wait_for()
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        page.wait_for_url(base_url + "/")
        page.get_by_role("heading", name="商品分析", exact=True).wait_for()
        print("PASS 登录保护、错误密码与正常登录", flush=True)

        page.get_by_role("link", name="演示 · 便携咖啡杯", exact=True).click()
        page.wait_for_function("window.echarts && echarts.getInstanceByDom(document.getElementById('price-chart'))")
        options = page.evaluate("echarts.getInstanceByDom(document.getElementById('price-chart')).getOption()")
        assert len(options["series"][0]["data"]) == 7
        assert "08:00:00" in options["xAxis"][0]["data"][0], "图表应使用网页时区，不受浏览器时区影响"
        if artifacts:
            page.screenshot(path=str(artifacts / "detail.png"), full_page=True)
        print("PASS 历史图表、7 个观测点与跨时区一致性", flush=True)

        page.get_by_role("link", name="商品分析", exact=True).click()
        page.get_by_role("link", name="＋ 添加商品", exact=True).click()
        page.get_by_label("商品名称", exact=False).fill("浏览器验证商品")
        page.get_by_label("商品链接", exact=False).fill("https://example.com/browser-check")
        page.get_by_label("平台", exact=False).fill("Other")
        page.get_by_role("button", name="保存商品", exact=True).click()
        page.get_by_role("heading", name="浏览器验证商品", exact=True).wait_for()
        page.get_by_role("link", name="编辑商品", exact=True).click()
        page.get_by_label("商品名称", exact=False).fill("浏览器验证商品 · 已编辑")
        page.get_by_role("button", name="保存商品", exact=True).click()
        page.get_by_role("heading", name="浏览器验证商品 · 已编辑", exact=True).wait_for()
        page.get_by_role("button", name="采集最新价格", exact=True).click()
        page.locator("#job-poll").wait_for(state="detached", timeout=15000)
        page.locator(".badge.failed").wait_for(timeout=15000)
        assert "仅支持" in page.locator("main").inner_text()
        print("PASS 商品新增、编辑、真实 worker 执行与失败反馈", flush=True)

        page.get_by_role("link", name="导入数据", exact=True).click()
        upload = page.get_by_label("CSV 文件（UTF-8，最大 2 MB）", exact=False)
        upload.set_input_files({"name": "invalid.csv", "mimeType": "text/csv", "buffer": b'"unterminated\n'})
        page.get_by_role("button", name="校验并导入", exact=True).click()
        page.get_by_text("CSV 格式错误", exact=False).wait_for()
        upload.set_input_files({"name": "duplicate.csv", "mimeType": "text/csv", "buffer": b'title,url,price,price,currency,observed_at\n'})
        page.get_by_role("button", name="校验并导入", exact=True).click()
        page.get_by_text("CSV 表头不能有重复", exact=False).wait_for()
        for _ in range(2):
            page.get_by_label("CSV 文件（UTF-8，最大 2 MB）", exact=False).set_input_files(str(ROOT / "examples/products.csv"))
            page.get_by_role("button", name="校验并导入", exact=True).click()
            page.wait_for_url(base_url + "/")
            page.get_by_role("link", name="演示 · CSV 示例商品", exact=True).wait_for()
            if _ == 0:
                page.get_by_role("link", name="导入数据", exact=True).click()
        assert "新增 0 条快照，更新 2 条已有快照" in page.locator("main").inner_text()
        with page.expect_download() as download_info:
            page.get_by_role("link", name="导出筛选商品历史", exact=True).click()
        assert download_info.value.suggested_filename == "shophot-snapshots.csv"
        print("PASS 损坏 CSV 错误提示、重复表头拒绝、导入幂等性与导出", flush=True)

        page.get_by_role("link", name="利润工具", exact=True).click()
        inputs = [("售价（结算币种）", "20"), ("1 单位结算币种对应人民币", "7"),
                  ("采购成本（人民币）", "50"), ("运费（人民币）", "20"),
                  ("平台费率（%）", "10"), ("其他成本（人民币）", "6")]
        for label, value in inputs:
            page.get_by_label(label, exact=False).fill(value)
        page.get_by_role("button", name="计算利润", exact=True).click()
        page.locator("#profit-result .profit").wait_for()
        assert "50.00" in page.locator("#profit-result .profit").inner_text()
        page.get_by_label("1 单位结算币种对应人民币", exact=False).fill("0")
        page.locator("form[hx-post]").evaluate("form => {form.noValidate = true; form.requestSubmit();}")
        page.get_by_text("输入无效，请检查以下字段。", exact=False).wait_for()
        print("PASS HTMX 利润计算与输入错误反馈", flush=True)

        page.get_by_role("link", name="商品分析", exact=True).click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "手机布局横向溢出"
        if artifacts:
            page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
        page.get_by_role("button", name="退出 browser-check", exact=True).click()
        page.wait_for_url(base_url + "/accounts/login/")
        assert not errors, "JavaScript 页面错误：" + repr(errors)
        print("PASS 手机布局、退出登录及无 JavaScript 页面错误", flush=True)
        browser.close()


def run(executable, artifacts):
    password = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="shophot-selfcheck-") as temporary:
        temp = Path(temporary)
        # 使用测试专属配置，数据库、日志和运行进程均与现有网站隔离。
        (temp / "smoke_settings.py").write_text(
            "from config.settings import *\n"
            f"DATABASES['default']['NAME'] = {str(temp / 'smoke.sqlite3')!r}\n"
            f"LOGGING['handlers']['file']['filename'] = {str(temp / 'smoke.log')!r}\n"
            "DEBUG = True\nALLOWED_HOSTS = ['127.0.0.1', 'localhost']\n"
            "SESSION_COOKIE_SECURE = False\nCSRF_COOKIE_SECURE = False\nSECURE_SSL_REDIRECT = False\n",
            encoding="utf-8",
        )
        sys.path[:0] = [str(temp), str(ROOT)]
        environment = os.environ.copy()
        environment.update({"DJANGO_SETTINGS_MODULE": "smoke_settings", "SHOPHOT_DEBUG": "1",
                            "PYTHONPATH": os.pathsep.join([str(temp), str(ROOT), os.getenv("PYTHONPATH", "")]), "PYTHONUNBUFFERED": "1"})
        subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=ROOT,
                       env=environment, check=True, stdout=subprocess.DEVNULL)
        os.environ["DJANGO_SETTINGS_MODULE"] = "smoke_settings"
        os.environ["SHOPHOT_DEBUG"] = "1"
        import django
        django.setup()
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        get_user_model().objects.create_user("browser-check", password=password)
        call_command("seed_demo", stdout=io.StringIO())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        processes = []
        with (temp / "processes.log").open("w") as output:
            try:
                for command in [["runserver", f"127.0.0.1:{port}", "--noreload"], ["collect_worker"]]:
                    processes.append(subprocess.Popen([sys.executable, "manage.py", *command], cwd=ROOT,
                                                       env=environment, stdout=output, stderr=output))
                # 禁用代理仅用于本机就绪请求，外网采集仍保留平台的网络代理。
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline = time.monotonic() + 30
                while True:
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError("测试服务提前退出，请检查浏览器自检运行环境。")
                    try:
                        with opener.open(base_url + "/accounts/login/", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("测试服务未在 30 秒内就绪。")
                    time.sleep(0.2)
                check_pages(base_url, executable, artifacts, password)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                from django.db import connections
                connections.close_all()
    print("浏览器自检完成：临时数据库、账号和服务已清理。", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default=shutil.which("chromium"), help="可选：系统 Chromium 可执行文件路径")
    parser.add_argument("--artifacts", type=Path, help="可选：保存页面截图的目录")
    args = parser.parse_args()
    if args.artifacts:
        args.artifacts.mkdir(parents=True, exist_ok=True)
    run(args.chromium, args.artifacts)
