# 嵌入聊天元件

正式環境應使用獨立的 HTTPS 來源站，例如 `https://assistant.school.example`。在既有學校頁面加入一個延後載入的 script：

```html
<script
  defer
  src="https://assistant.school.example/embed.js"
  data-assistant-url="https://assistant.school.example"
  data-name="校園 AI 助理"
  data-color="#155e75"></script>
```

明確填寫 `data-assistant-url`，可避免複製或快取的載入器推斷出錯誤來源站。名稱與顏色只用於外觀。請勿把機密、提示詞、模型名稱、使用者識別資訊或供應商設定放進 data attributes。

在助理服務的 `ALLOWED_FRAME_ORIGINS` 填入可以嵌入 `/widget/` 的精確學校來源站：

```dotenv
ALLOWED_FRAME_ORIGINS=["https://www.school.example","https://school.example"]
```

若既有學校網站有 Content Security Policy，也必須允許助理來源站。請把來源站合併到原本的 directive，不要再加一個互相衝突的標頭：

```text
script-src 'self' https://assistant.school.example;
frame-src 'self' https://assistant.school.example;
style-src 'self';
```

現代瀏覽器使用 constructable stylesheet；實際 Edge 跨來源測試已確認主頁維持 `style-src 'self'` 時，按鈕樣式、自訂強調色與 iframe 都能正常運作，且沒有 CSP 錯誤。較舊、不支援此功能的瀏覽器會改載入助理來源站的 `assets/embed.css`，這時才須把 `https://assistant.school.example` 加入主頁的 `style-src`；fallback 按鈕使用預設強調色，iframe 內仍會使用設定的自訂顏色。兩種方式都不需要 `unsafe-inline`。助理端的 frame 允許清單不能覆蓋主頁更嚴格的 CSP；同樣地，主頁允許 iframe 也不能覆蓋助理的 `frame-ancestors` 清單。正式測試時要同時檢查學校主要網址與重新導向後的網址。

本機跨來源測試時，將主頁範例放在 HTTP 8080 port，助理維持在 `127.0.0.1:8000`，並把兩種本機主機名稱都放入 `ALLOWED_FRAME_ORIGINS`。在 `web_ai_assistant` 執行：

```bash
python -m http.server 8080 --directory static/examples
```

請開啟 `http://127.0.0.1:8080/embed.html?assistant=http://127.0.0.1:8000/`，不要直接開 HTML 檔。`file://` 頁面的來源站不透明，因此不在預設允許清單中。

內附的[最小嵌入範例](../static/examples/embed.html)會從 `assistant` 查詢參數建立相同 script，讓模擬主頁與助理在開發時維持不同來源站。[入口網站共存範例](../static/examples/portal.html)則包含獨立樣式與可操作表單，可用來確認載入或開啟元件不會破壞主頁版面與互動。

目前 iframe 只會送出 `ready` 與 `close` 事件，不接收父頁訊息。主頁收到事件時會檢查助理來源站、訊息是否來自該 iframe window，以及事件資料結構是否完全符合預期。若日後增加傳入 iframe 的訊息，也必須檢查父頁來源站、`window.parent` 與資料結構。
