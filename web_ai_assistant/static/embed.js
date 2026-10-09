(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var ROOT_ID = "school-ai-assistant-embed";
  if (document.getElementById(ROOT_ID)) return;

  function validBase(value) {
    if (!value || !String(value).trim()) return null;
    try {
      var url = new URL(value, script.src);
      if (url.protocol !== "https:" && url.protocol !== "http:") return null;
      if (url.username || url.password) return null;
      if (!url.pathname.endsWith("/")) url.pathname += "/";
      url.search = "";
      url.hash = "";
      return url;
    } catch (_) {
      return null;
    }
  }

  function validName(value) {
    var name = String(value || "").replace(/[\u0000-\u001f\u007f]/g, "").trim();
    return name && name.length <= 40 ? name : "校務 AI 助理";
  }

  function validColor(value) {
    var color = String(value || "").trim();
    return /^#[0-9a-fA-F]{6}$/.test(color) ? color : "#4f46e5";
  }

  var fallbackBase = validBase(new URL(".", script.src).href);
  var base = validBase(script.getAttribute("data-assistant-url")) || fallbackBase;
  if (!base) return;

  var assistantName = validName(script.getAttribute("data-name"));
  var accent = validColor(script.getAttribute("data-color"));
  var widgetUrl = new URL("widget/", base);
  widgetUrl.searchParams.set("parentOrigin", window.location.origin);
  widgetUrl.searchParams.set("name", assistantName);
  widgetUrl.searchParams.set("color", accent);

  function mount() {
    if (!document.body || document.getElementById(ROOT_ID)) return;

    var host = document.createElement("div");
    host.id = ROOT_ID;
    host.setAttribute("data-school-ai-assistant", "");
    var shadow = host.attachShadow({ mode: "open" });
    var open = false;
    var frame = null;
    var readyTimer = null;

    shadow.innerHTML = [
      "<style>",
      ":host{all:initial}",
      ".root{position:fixed;right:20px;bottom:20px;z-index:2147483000;font-family:system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;color:#111827}",
      ".launcher{width:58px;height:58px;border:0;border-radius:999px;background:", accent, ";color:#fff;display:grid;place-items:center;cursor:pointer;box-shadow:0 12px 30px rgba(15,23,42,.28);transition:transform .16s ease,box-shadow .16s ease}",
      ".launcher:hover{transform:translateY(-2px);box-shadow:0 16px 36px rgba(15,23,42,.34)}",
      ".launcher:focus-visible,.fallback a:focus-visible,.fallback button:focus-visible{outline:3px solid #fff;outline-offset:3px;box-shadow:0 0 0 6px ", accent, "}",
      ".launcher svg{width:27px;height:27px}",
      ".panel{position:absolute;right:0;bottom:72px;width:min(390px,calc(100vw - 24px));height:min(680px,calc(100vh - 108px));overflow:hidden;border:1px solid rgba(15,23,42,.14);border-radius:20px;background:#fff;box-shadow:0 24px 70px rgba(15,23,42,.28)}",
      ".panel[hidden]{display:none}",
      "iframe{display:block;width:100%;height:100%;border:0;background:#fff}",
      ".fallback{height:100%;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:28px;text-align:center;background:#f8fafc}",
      ".fallback strong{font-size:17px}.fallback p{margin:0;color:#475569;font-size:14px;line-height:1.6}",
      ".fallback a,.fallback button{box-sizing:border-box;border-radius:10px;padding:10px 14px;font:600 14px/1 system-ui,-apple-system,sans-serif;cursor:pointer}",
      ".fallback a{color:#fff;background:", accent, ";text-decoration:none}.fallback button{color:#334155;background:#fff;border:1px solid #cbd5e1}",
      "@media(max-width:520px){.root{right:12px;bottom:12px}.panel{position:fixed;inset:0;width:100vw;height:100dvh;border:0;border-radius:0}.launcher{width:54px;height:54px}.launcher[aria-expanded=true]{visibility:hidden;pointer-events:none}}",
      "@media(prefers-reduced-motion:reduce){.launcher{transition:none}}",
      "</style>",
      '<div class="root">',
      '<section class="panel" hidden aria-label="', assistantName.replace(/[&<>"']/g, ""), '"></section>',
      '<button class="launcher" type="button" aria-label="開啟', assistantName.replace(/[&<>"']/g, ""), '" aria-expanded="false">',
      '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8M8 13h5"/></svg>',
      "</button></div>"
    ].join("");

    var panel = shadow.querySelector(".panel");
    var launcher = shadow.querySelector(".launcher");

    function exactMessage(data, type) {
      if (!data || Object.getPrototypeOf(data) !== Object.prototype) return false;
      var keys = Object.keys(data).sort();
      return keys.length === 2 && keys[0] === "type" && keys[1] === "version" &&
        data.type === type && data.version === 1;
    }

    function renderFallback() {
      if (readyTimer) window.clearTimeout(readyTimer);
      readyTimer = null;
      frame = null;
      panel.replaceChildren();
      var box = document.createElement("div");
      box.className = "fallback";
      var title = document.createElement("strong");
      title.textContent = "助理暫時無法載入";
      var copy = document.createElement("p");
      copy.textContent = "您可以稍後重試，或改在新頁面開啟助理。";
      var link = document.createElement("a");
      link.href = widgetUrl.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "在新頁面開啟";
      var retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "重新載入";
      retry.addEventListener("click", function () {
        panel.replaceChildren();
        createFrame();
      });
      var close = document.createElement("button");
      close.type = "button";
      close.textContent = "關閉助理";
      close.addEventListener("click", closePanel);
      box.append(title, copy, link, retry, close);
      panel.appendChild(box);
    }

    function createFrame() {
      if (frame) return;
      frame = document.createElement("iframe");
      frame.title = assistantName;
      frame.src = widgetUrl.href;
      frame.loading = "eager";
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      frame.setAttribute("sandbox", "allow-scripts allow-forms allow-same-origin");
      frame.addEventListener("error", renderFallback, { once: true });
      panel.appendChild(frame);
      readyTimer = window.setTimeout(renderFallback, 10000);
    }

    function closePanel() {
      open = false;
      panel.hidden = true;
      launcher.setAttribute("aria-expanded", "false");
      launcher.setAttribute("aria-label", "開啟" + assistantName);
      launcher.focus();
    }

    function openPanel() {
      open = true;
      panel.hidden = false;
      launcher.setAttribute("aria-expanded", "true");
      launcher.setAttribute("aria-label", "關閉" + assistantName);
      createFrame();
      if (frame && frame.contentWindow) frame.contentWindow.focus();
    }

    launcher.addEventListener("click", function () {
      if (open) closePanel(); else openPanel();
    });

    window.addEventListener("message", function (event) {
      if (!frame || event.origin !== base.origin || event.source !== frame.contentWindow) return;
      if (exactMessage(event.data, "school-ai-assistant:ready")) {
        if (readyTimer) window.clearTimeout(readyTimer);
        readyTimer = null;
        if (open) frame.contentWindow.focus();
      } else if (exactMessage(event.data, "school-ai-assistant:close")) {
        closePanel();
      }
    });

    document.body.appendChild(host);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }
}());
