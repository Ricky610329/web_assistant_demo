"""Run real Edge UI checks: python tests/browser_smoke.py (dev dependencies).

Local HTTP servers are owned by this process and are stopped on exit. No model
credentials, external requests, or browser downloads are needed.
"""

from pathlib import Path
import json
import sys
from urllib.parse import quote

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright, expect

from app.main import create_app
from app.settings import Settings
from test_live_http import serve


def main():
    artifacts = PROJECT / ".artifacts"
    artifacts.mkdir(exist_ok=True)
    school = FastAPI()
    school.mount("/", StaticFiles(directory=PROJECT / "static" / "examples"), name="school")
    checks = []
    console_errors = []
    page_errors = []
    requests = []

    with serve(school) as school_url:
        assistant = create_app(Settings(_env_file=None, allowed_frame_origins=[school_url],
                                        requests_per_minute=100))
        with serve(assistant) as assistant_url, sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("console", lambda message: console_errors.append({
                "text": message.text, "url": message.location.get("url", "")
            }) if message.type == "error" else None)
            page.on("request", lambda request: requests.append(json.loads(request.post_data))
                    if request.url == assistant_url + "/api/chat" and request.post_data else None)
            query = "?assistant=" + quote(assistant_url + "/", safe="")
            page.goto(school_url + "/embed.html" + query)
            expect(page.locator("#school-ai-assistant-embed")).to_have_count(1)
            expect(page.locator("iframe")).to_have_count(0)
            page.add_script_tag(url=assistant_url + "/embed.js")
            expect(page.locator("#school-ai-assistant-embed")).to_have_count(1)
            checks.append("lazy iframe and duplicate-loader protection")

            page.get_by_role("button", name="開啟校務 AI 助理", exact=True).click()
            frame = page.frame_locator("iframe")
            expect(frame.locator("#demo-banner")).to_be_visible()
            expect(frame.locator("#assistant-title")).to_have_text("校務 AI 助理")
            page.evaluate("window.postMessage({type:'school-ai-assistant:close',version:1}, '*')")
            expect(page.locator(".panel")).to_be_visible()
            frame.locator("#message-input").fill("你好，請示範串流。")
            frame.locator("#message-input").press("Enter")
            expect(frame.locator("[data-history=true]")).to_have_count(2)
            expect(frame.locator(".message.assistant").last).to_contain_text("離線示範回覆")
            expect(frame.locator("#send-button")).to_be_visible()
            expect(frame.locator("#cancel-button")).to_be_hidden()

            malicious = '<img src=x onerror="window.__injected=1"> [危險連結](javascript:alert(1))'
            frame.locator("#message-input").fill(malicious)
            frame.locator("#message-input").press("Enter")
            expect(frame.locator("[data-history=true]")).to_have_count(4)
            assert frame.locator("#messages img, #messages script, #messages [onerror], #messages a[href^='javascript:']").count() == 0
            assert requests[-1]["messages"][0]["content"] == "你好，請示範串流。"
            assert requests[-1]["messages"][-1]["content"] == malicious
            checks.append("Chinese streaming, paired history and sanitized Markdown")

            frame.locator("#message-input").fill("要停止的訊息" * 50)
            frame.locator("#message-input").press("Enter")
            expect(frame.locator("#cancel-button")).to_be_visible()
            frame.locator("#cancel-button").click()
            expect(frame.locator(".message.error").last).to_contain_text("已停止")
            frame.locator("#message-input").fill("停止後重新傳送")
            frame.locator("#message-input").press("Enter")
            expect(frame.locator("[data-history=true]")).to_have_count(6)
            assert not any("要停止的訊息" in entry["content"] for entry in requests[-1]["messages"])

            frame.locator("#message-input").fill("清除中的訊息" * 50)
            frame.locator("#message-input").press("Enter")
            expect(frame.locator("#cancel-button")).to_be_visible()
            frame.locator("#clear-button").click()
            expect(frame.locator(".message")).to_have_count(1)
            expect(frame.locator("#send-button")).to_be_visible()
            frame.locator("#message-input").fill("全新對話")
            frame.locator("#message-input").press("Enter")
            expect(frame.locator("[data-history=true]")).to_have_count(2)
            assert requests[-1]["messages"] == [{"role": "user", "content": "全新對話"}]
            checks.append("cancel/clear exclude incomplete turns and prevent stale updates")

            frame.locator("#close-button").click()
            expect(page.locator(".panel")).to_be_hidden()
            assert page.get_by_role("button", name="開啟校務 AI 助理", exact=True).evaluate("el => el.matches(':focus')")
            page.get_by_role("button", name="開啟校務 AI 助理", exact=True).click()
            expect(frame.locator("#message-input")).to_be_visible()
            page.wait_for_timeout(200)  # Let the reopened cross-origin frame composite.
            page.screenshot(path=str(artifacts / "desktop.png"))
            checks.append("verified close message and focus recovery")

            page.goto(school_url + "/portal.html" + query)
            page.locator("#reference-email").fill("reference@example.com")
            page.locator("#reference-submit").click()
            expect(page.locator("#reference-result")).to_contain_text("1")
            page.get_by_role("button", name="開啟", exact=False).last.click()
            portal_frame = page.frame_locator("iframe")
            expect(portal_frame.locator("#message-input")).to_be_visible()
            portal_frame.locator("#close-button").click()
            page.locator("#reference-submit").click()
            expect(page.locator("#reference-result")).to_contain_text("2")
            checks.append("second host design and original form unaffected")

            page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_role("button", name="開啟", exact=False).last.click()
            expect(portal_frame.locator("#message-input")).to_be_visible()
            expect(page.locator(".launcher")).to_be_hidden()
            expect(portal_frame.locator("#send-button")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            actual_frame = page.frames[-1]
            assert actual_frame.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.wait_for_timeout(200)  # Wait for mobile layout/iframe paint, not network work.
            page.screenshot(path=str(artifacts / "mobile.png"))
            checks.append("390px mobile viewport without page or widget horizontal overflow")

            # Force one-byte UTF-8 chunks, CRLF frames, and a final frame without newline.
            # The real widget code consumes this browser-local stream unchanged.
            actual_frame.evaluate("""() => {
                window.originalFetch = window.fetch;
                window.fetch = (url, options) => {
                    if (url !== '/api/chat') return window.originalFetch(url, options);
                    const bytes = new TextEncoder().encode(
                        'event: delta\\r\\ndata: {"text":"多位元文字測試"}\\r\\n\\r\\nevent: done\\ndata: {}');
                    return Promise.resolve(new Response(new ReadableStream({start(controller) {
                        for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
                        controller.close();
                    }}), {headers:{'Content-Type':'text/event-stream'}}));
                };
            }""")
            portal_frame.locator("#message-input").fill("分段測試")
            portal_frame.locator("#message-input").press("Enter")
            expect(portal_frame.locator("[data-history=true]")).to_have_count(2)
            expect(portal_frame.locator(".message.assistant").last).to_have_text("多位元文字測試")
            actual_frame.evaluate("() => { window.fetch = window.originalFetch; delete window.originalFetch; }")
            portal_frame.locator("#clear-button").click()
            checks.append("one-byte UTF-8, CRLF and final unterminated SSE frame")

            for body in ('event: done\\ndata: {}\\n\\n',
                         'event: delta\\ndata: {"text":"未完成"}\\n\\n',
                         'event: delta\\ndata: invalid-json\\n\\n'):
                body = body.replace('\\n', '\n')
                page.route(assistant_url + "/api/chat", lambda route, _request, body=body: route.fulfill(
                    status=200, content_type="text/event-stream", body=body))
                portal_frame.locator("#message-input").fill("不完整回覆測試")
                portal_frame.locator("#message-input").press("Enter")
                expect(portal_frame.locator(".message.error").last).to_be_visible()
                expect(portal_frame.locator("#send-button")).to_be_visible()
                expect(portal_frame.locator("[data-history=true]")).to_have_count(0)
                page.unroute(assistant_url + "/api/chat")
            checks.append("empty, truncated and malformed streams never enter history")

            # A transport failure gives a local error and leaves the school form usable.
            page.route(assistant_url + "/api/chat", lambda route: route.abort("failed"))
            portal_frame.locator("#message-input").fill("故障測試")
            portal_frame.locator("#message-input").press("Enter")
            expect(portal_frame.locator(".message.error").last).to_contain_text("連線失敗")
            portal_frame.locator("#close-button").click()
            page.locator("#reference-submit").click()
            expect(page.locator("#reference-result")).to_contain_text("3")
            checks.append("network failure remains isolated from host operations")
            page.unroute(assistant_url + "/api/chat")

            page.goto(school_url + "/portal.html" + query)
            page.route(assistant_url + "/widget/**", lambda route: route.abort("failed"))
            page.clock.install()
            page.get_by_role("button", name="開啟", exact=False).last.click()
            page.clock.fast_forward(11000)
            expect(page.get_by_text("助理暫時無法載入", exact=True)).to_be_visible()
            page.get_by_role("button", name="關閉", exact=False).last.click()
            page.locator("#reference-email").fill("reference@example.com")
            page.locator("#reference-submit").click()
            expect(page.locator("#reference-result")).to_contain_text("1")
            checks.append("iframe load failure degrades locally and leaves host form usable")
            context.close()
            browser.close()

    # Route-aborted fetch is an expected browser console failure in the last scenario.
    unexpected = [value for value in console_errors
                  if "net::ERR_FAILED" not in value["text"] and not value["url"].endswith("/favicon.ico")]
    assert not page_errors, page_errors
    assert not unexpected, unexpected
    report = {"browser": "headless Microsoft Edge", "checks": checks,
              "javascript_errors": page_errors, "unexpected_console_errors": unexpected}
    (artifacts / "browser-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
