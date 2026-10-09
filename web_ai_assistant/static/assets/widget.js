(function () {
  "use strict";

  var MAX_MESSAGES = 20;
  var MAX_MESSAGE_CHARS = 4000;
  var MAX_TOTAL_CHARS = 24000;
  var MAX_BODY_BYTES = 65536;
  var API_PATH = "/api/chat";

  var messages = document.getElementById("messages");
  var composer = document.getElementById("composer");
  var input = document.getElementById("message-input");
  var sendButton = document.getElementById("send-button");
  var cancelButton = document.getElementById("cancel-button");
  var clearButton = document.getElementById("clear-button");
  var closeButton = document.getElementById("close-button");
  var liveStatus = document.getElementById("live-status");
  var demoBanner = document.getElementById("demo-banner");
  var title = document.getElementById("assistant-title");

  var history = [];
  var active = null;
  var requestSerial = 0;
  var query = new URLSearchParams(window.location.search);
  var parentOrigin = parseOrigin(query.get("parentOrigin"));

  function parseOrigin(value) {
    if (!value) return null;
    try {
      var url = new URL(value);
      if (url.protocol !== "https:" && url.protocol !== "http:") return null;
      return url.origin;
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

  function characterCount(value) {
    return Array.from(value).length;
  }

  function isPlainRecord(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value) &&
      Object.getPrototypeOf(value) === Object.prototype;
  }

  function postParent(type) {
    if (!parentOrigin || window.parent === window) return;
    window.parent.postMessage({ type: type, version: 1 }, parentOrigin);
  }

  function isNearBottom() {
    return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 88;
  }

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function createMessage(role, text, options) {
    var node = document.createElement("article");
    node.className = "message " + role + (options && options.error ? " error" : "");
    if (options && options.pending) node.classList.add("pending");
    if (options && options.history) node.dataset.history = "true";
    if (role === "user") {
      node.textContent = text;
    } else {
      renderAssistant(node, text);
    }
    messages.appendChild(node);
    if (!options || options.scroll !== false) scrollToBottom();
    return node;
  }

  function renderAssistant(node, text) {
    var stick = isNearBottom();
    if (typeof window.marked !== "object" || typeof window.DOMPurify !== "function") {
      node.textContent = text;
    } else {
      var source = text || "";
      var parsed = window.marked.parse(source, { gfm: true, breaks: true, async: false });
      node.innerHTML = window.DOMPurify.sanitize(parsed, {
        ALLOWED_TAGS: ["p", "br", "strong", "em", "del", "code", "pre", "blockquote", "ul", "ol", "li", "a", "table", "thead", "tbody", "tr", "th", "td", "hr"],
        ALLOWED_ATTR: ["href", "title"],
        FORBID_TAGS: ["style", "svg", "math", "form", "input", "button", "iframe"],
        FORBID_ATTR: ["style", "class", "id"]
      });
      node.querySelectorAll("a[href]").forEach(function (link) {
        link.rel = "noopener noreferrer";
        try {
          var target = new URL(link.href, window.location.href);
          if (target.protocol === "http:" || target.protocol === "https:") link.target = "_blank";
        } catch (_) {
          link.removeAttribute("href");
        }
      });
    }
    if (stick) scrollToBottom();
  }

  function addWelcome() {
    createMessage("assistant", "您好！我是校務 AI 助理，可協助一般問題與文字整理。若涉及校務規定，請以學校正式公告為準。", { scroll: true });
  }

  function setBusy(busy) {
    input.disabled = busy;
    sendButton.hidden = busy;
    sendButton.disabled = busy;
    cancelButton.hidden = !busy;
    clearButton.setAttribute("aria-label", busy ? "停止並清除對話" : "清除對話");
  }

  function resizeInput() {
    input.rows = 1;
    var contentHeight = Math.max(20, input.scrollHeight - 22);
    input.rows = Math.max(1, Math.min(5, Math.ceil(contentHeight / 20)));
  }

  function applyAccent(color) {
    var rule = ":root{--accent:" + color + "}";
    for (var index = 0; index < document.styleSheets.length; index += 1) {
      var sheet = document.styleSheets[index];
      try {
        if (sheet.href && new URL(sheet.href).origin === window.location.origin) {
          sheet.insertRule(rule, sheet.cssRules.length);
          return;
        }
      } catch (_) { /* continue to another same-origin stylesheet */ }
    }
  }

  function removeOldestHistoryPair() {
    history.splice(0, 2);
    var nodes = messages.querySelectorAll('[data-history="true"]');
    if (nodes[0]) nodes[0].remove();
    if (nodes[1]) nodes[1].remove();
  }

  function trimHistoryFor(newText) {
    function totalWithNew() {
      return history.reduce(function (sum, item) { return sum + characterCount(item.content); }, characterCount(newText));
    }
    function requestBytes() {
      var candidate = history.map(function (item) { return { role: item.role, content: item.content }; })
        .concat([{ role: "user", content: newText }]);
      return new TextEncoder().encode(JSON.stringify({ messages: candidate })).byteLength;
    }
    while (history.length >= 2 && (history.length + 1 > MAX_MESSAGES || totalWithNew() > MAX_TOTAL_CHARS || requestBytes() > MAX_BODY_BYTES)) {
      removeOldestHistoryPair();
    }
    return history.map(function (item) { return { role: item.role, content: item.content }; })
      .concat([{ role: "user", content: newText }]);
  }

  function protocolError(message) {
    var error = new Error(message || "回覆格式不正確，請稍後再試。");
    error.name = "ChatProtocolError";
    return error;
  }

  function parseSseFrame(frame) {
    var normalized = frame.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    var eventName = "message";
    var data = [];
    normalized.split("\n").forEach(function (line) {
      if (!line || line.charAt(0) === ":") return;
      var colon = line.indexOf(":");
      var field = colon === -1 ? line : line.slice(0, colon);
      var value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.charAt(0) === " ") value = value.slice(1);
      if (field === "event") eventName = value;
      if (field === "data") data.push(value);
    });
    if (!data.length) return null;
    var payload;
    try {
      payload = JSON.parse(data.join("\n"));
    } catch (_) {
      throw protocolError();
    }
    if (!isPlainRecord(payload)) throw protocolError();
    return { event: eventName, data: payload };
  }

  async function consumeSse(response, signal, onDelta) {
    if (!response.body || typeof response.body.getReader !== "function") throw protocolError("瀏覽器不支援串流回覆。");
    var reader = response.body.getReader();
    var decoder = new TextDecoder("utf-8", { fatal: false });
    var buffer = "";
    var completeText = "";
    var doneSeen = false;

    function consumeFrame(frame) {
      var parsed = parseSseFrame(frame);
      if (!parsed) return;
      if (doneSeen) throw protocolError();
      if (parsed.event === "delta") {
        if (typeof parsed.data.text !== "string") throw protocolError();
        completeText += parsed.data.text;
        if (characterCount(completeText) > MAX_MESSAGE_CHARS) {
          throw protocolError("回覆超過 4,000 字，已停止接收。");
        }
        onDelta(completeText);
      } else if (parsed.event === "done") {
        doneSeen = true;
      } else if (parsed.event === "error") {
        var detail = typeof parsed.data.message === "string" ? parsed.data.message.slice(0, 300) : "產生回覆時發生錯誤。";
        var streamError = new Error(detail);
        streamError.name = "ChatStreamError";
        throw streamError;
      }
    }

    try {
      while (true) {
        if (signal.aborted) throw new DOMException("Aborted", "AbortError");
        var result = await reader.read();
        if (result.done) {
          buffer += decoder.decode();
          break;
        }
        buffer += decoder.decode(result.value, { stream: true });
        var boundary;
        while ((boundary = /\r\n\r\n|\n\n|\r\r/.exec(buffer))) {
          var frame = buffer.slice(0, boundary.index);
          buffer = buffer.slice(boundary.index + boundary[0].length);
          consumeFrame(frame);
        }
      }
      if (buffer.trim()) consumeFrame(buffer);
      if (!doneSeen) throw protocolError("回覆未完整結束，請再試一次。");
      if (!completeText.trim()) throw protocolError("未收到有效回覆，請再試一次。");
      return completeText;
    } finally {
      try { await reader.cancel(); } catch (_) { /* stream already closed */ }
    }
  }

  async function responseError(response) {
    var message = response.status === 429 ? "請求過於頻繁，請稍後再試。" :
      response.status === 503 ? "服務目前忙碌中，請稍後再試。" :
        "目前無法取得回覆，請稍後再試。";
    try {
      var payload = await response.json();
      if (isPlainRecord(payload) && isPlainRecord(payload.error) && typeof payload.error.message === "string") {
        message = payload.error.message.slice(0, 300);
      }
    } catch (_) { /* retain safe status message */ }
    var error = new Error(message);
    error.name = "ChatHttpError";
    return error;
  }

  function markFailure(userNode, assistantNode, message) {
    userNode.classList.add("failed");
    assistantNode.classList.remove("pending");
    assistantNode.classList.add("error");
    assistantNode.textContent = message;
    scrollToBottom();
  }

  function stopActive(clearAll) {
    if (active) {
      var stopped = active;
      requestSerial += 1;
      active = null;
      stopped.controller.abort();
      if (!clearAll) markFailure(stopped.userNode, stopped.assistantNode, "已停止產生回覆。這次訊息未加入對話紀錄。");
    }
    setBusy(false);
    if (clearAll) {
      history = [];
      messages.replaceChildren();
      addWelcome();
      liveStatus.textContent = "已清除對話";
    } else {
      liveStatus.textContent = "已停止產生回覆";
    }
    input.focus();
  }

  async function sendMessage(text) {
    if (active) return;
    if (!text) return;
    if (characterCount(text) > MAX_MESSAGE_CHARS) {
      liveStatus.textContent = "單則訊息最多 4,000 字";
      createMessage("assistant", "單則訊息最多 4,000 字，請縮短後再傳送。", { error: true });
      return;
    }

    var snapshot = trimHistoryFor(text);
    var userNode = createMessage("user", text, { scroll: true });
    var assistantNode = createMessage("assistant", "正在整理回覆…", { pending: true, scroll: true });
    var controller = new AbortController();
    var token = ++requestSerial;
    active = { token: token, controller: controller, userNode: userNode, assistantNode: assistantNode };
    setBusy(true);
    liveStatus.textContent = "正在產生回覆";

    try {
      var response = await fetch(API_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
        body: JSON.stringify({ messages: snapshot }),
        signal: controller.signal,
        credentials: "same-origin"
      });
      if (!response.ok) throw await responseError(response);
      var fullText = await consumeSse(response, controller.signal, function (partial) {
        if (!active || active.token !== token) return;
        assistantNode.classList.remove("pending");
        renderAssistant(assistantNode, partial);
      });
      if (!active || active.token !== token) return;
      assistantNode.classList.remove("pending");
      renderAssistant(assistantNode, fullText);
      userNode.dataset.history = "true";
      assistantNode.dataset.history = "true";
      history.push({ role: "user", content: text }, { role: "assistant", content: fullText });
      liveStatus.textContent = "回覆完成";
    } catch (error) {
      controller.abort();
      if (!active || active.token !== token) return;
      if (error && error.name === "AbortError") return;
      var knownError = error && (error.name === "ChatHttpError" || error.name === "ChatProtocolError" || error.name === "ChatStreamError");
      var message = knownError && typeof error.message === "string" ? error.message : "連線失敗，請檢查網路後再試。";
      markFailure(userNode, assistantNode, message + " 這次訊息未加入對話紀錄。");
      liveStatus.textContent = "回覆失敗";
    } finally {
      if (active && active.token === token) {
        active = null;
        setBusy(false);
        input.focus();
      }
    }
  }

  composer.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text || active) return;
    input.value = "";
    resizeInput();
    sendMessage(text);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });
  input.addEventListener("input", resizeInput);
  cancelButton.addEventListener("click", function () { stopActive(false); });
  clearButton.addEventListener("click", function () { stopActive(true); });
  closeButton.addEventListener("click", function () { postParent("school-ai-assistant:close"); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") postParent("school-ai-assistant:close");
  });

  title.textContent = validName(query.get("name"));
  document.title = title.textContent;
  applyAccent(validColor(query.get("color")));
  addWelcome();
  resizeInput();
  setBusy(false);

  fetch("/api/config", { credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" } })
    .then(function (response) { return response.ok ? response.json() : null; })
    .then(function (config) {
      if (isPlainRecord(config) && config.demo_mode === true) demoBanner.hidden = false;
    })
    .catch(function () { /* mode label is supplementary */ });

  postParent("school-ai-assistant:ready");
  window.setTimeout(function () { input.focus(); }, 0);
}());
