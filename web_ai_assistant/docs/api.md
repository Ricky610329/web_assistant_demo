# HTTP 與串流 API

## 公開路由

| 方法 | 路徑 | 結果 |
|---|---|---|
| `GET` | `/embed.js` | 主頁使用的精簡載入器 |
| `GET` | `/widget/` | 不同來源站的聊天介面 |
| `GET` | `/assets/*` | 有版本管理的介面資源 |
| `GET` | `/api/config` | mock 模式為 `{"demo_mode": true}`，否則為 `false` |
| `GET` | `/healthz` | `{"status":"ok"}`；只代表程序存活，不代表上游模型可用 |
| `POST` | `/api/chat` | Server-sent events 串流 |

## 聊天請求

```json
{
  "messages": [
    {"role": "user", "content": "學校今天幾點放學？"},
    {"role": "assistant", "content": "請以學校正式公告為準。"},
    {"role": "user", "content": "我可以在哪裡確認？"}
  ]
}
```

只接受由 `user` 開始、交替出現並由 `user` 結束的訊息。系統提示詞、模型、上游位址與憑證都由伺服器管理。呼叫上游前會檢查 65,536 bytes 請求上限、10 秒讀取上限、`MAX_MESSAGES`、單筆 4,000 字元及總計 24,000 字元。預設 `MAX_MESSAGES=20`，但因為必須交替且由 user 結束，單次實際最多 19 筆。內附元件另有 4,000 字元回答上限，超過時會停止接收並顯示錯誤。

使用 `curl -N` 避免用戶端緩衝：

```bash
curl -N http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  --data '{"messages":[{"role":"user","content":"你好"}]}'
```

## 串流事件

回應 media type 為 `text/event-stream`，事件內容是 JSON：

```text
event: delta
data: {"text":"你"}

event: delta
data: {"text":"好"}

event: done
data: {}
```

如果串流標頭送出後才發生錯誤，串流會以下列事件結束：

```text
event: error
data: {"code":"upstream_error","message":"暫時無法取得回覆，請稍後再試。"}
```

上游沒有回傳內容，或 finish reason 不是 `stop` 時，會回報 `incomplete_stream`。若驗證、頻率、並行或其他錯誤發生在串流開始前，則回傳對應 HTTP 狀態與 JSON：

```json
{
  "error": {"code": "rate_limited", "message": "請稍後再試。"},
  "request_id": "..."
}
```

串流前的常見狀態包括：瀏覽器來源不允許時回 403；請求內容未在 `BODY_READ_TIMEOUT_SECONDS` 內送完時回 408 與 `request_timeout`；輸入不合法時回 413／422；超過頻率時回 429；並行額滿或服務設定不可用時回 503。429 會附上 `Retry-After`。預設 90 秒的生成預算在串流內執行，逾時會產生代碼為 `timeout` 的 `error` 事件；最多再給 1 秒送出該事件，上游清理則另外限制在 1 秒內。因此整體時間不保證剛好 90 秒。串流開始後已無法變更 HTTP 狀態，用戶端必須處理 `error` 事件。

此 API 是匿名服務。`frame-ancestors` 與 iframe 來源檢查只保護嵌入行為，不能阻止他人直接呼叫 API。若學校規定需要身分驗證或防濫用，應在前端邊緣服務另行處理。
