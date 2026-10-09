# 架構與信任邊界

## 請求路徑

```text
school page (origin A)
  -> https://assistant.school.example/embed.js
  -> lazy iframe https://assistant.school.example/widget/ (origin B)
       -> same-origin POST /api/chat
            -> FastAPI/Uvicorn, one process
                 -> mock responder, or administrator-selected compatible API
```

`embed.js` 只負責啟動按鈕與 iframe 外框。Shadow DOM 可減少它和原學校網站 CSS 互相影響。完整聊天介面位於不同來源站的 iframe，因此原頁面的 JavaScript 無法透過一般 DOM 存取對話內容。所有 `postMessage` 通訊都必須同時檢查 `event.origin` 與 `event.source`，而且主頁與元件只傳送必要的少量介面事件。

後端提供 `/embed.js`、`/widget/`、`/assets/*`、`/api/config`、`/healthz` 與 `/api/chat`。元件以同來源方式呼叫 API。允許嵌入只是在控制哪些頁面可顯示介面，不是 API 身分驗證，也不會把匿名公開端點變成私人服務。

## 資料流與範圍

用戶端只能傳送有長度限制、依序交替的 `user` 與 `assistant` 訊息，最後一筆必須是新的使用者訊息。伺服器自行加入系統提示詞並選用已設定的模型；用戶端不能提供 system 角色、模型、上游網址或憑證。本參考系統不會讀取嵌入頁面、擷取網頁內容、查詢資料庫、呼叫工具或檢索校務文件。

在 OpenAI 模式中，伺服器會把受限的對話送到已設定的相容端點，再串流傳回文字。瀏覽器中斷連線時，伺服器會盡力取消上游請求，但無法保證供應商一定停止運算或計費。

紀錄只應包含 request ID、耗時與結果／狀態。請勿記錄提示詞、回答、授權標頭、上游金鑰或原始請求內容。

## 資源與流量限制

伺服器最多等候 10 秒讀取聊天請求，內容上限為 65,536 bytes。呼叫上游前，會檢查訊息筆數、單筆 4,000 字元及總計 24,000 字元的限制。元件收到超過 4,000 字元的回答時也會停止接收。程序內的併發限制會直接用 503 拒絕超額請求，不會排隊；程序內的頻率限制則回傳 429 與 `Retry-After`。

模型生成預設最多 90 秒，而且不自動重試供應商。時間到後，回應層最多再給 1 秒送出最後的 timeout 事件；上游串流清理則另外以 1 秒為限並採盡力處理。因此 90 秒是生成預算，不是整個 HTTP 請求的硬性總時間。

這些限制只存在記憶體中，重啟服務就會重設。位於同一個 NAT 後方的使用者也可能共用可見位址。在改用共用限制儲存區前，Uvicorn 必須維持單一 worker 與單一服務副本。請依學校實際流量與隱私需求調整頻率。

`TRUSTED_PROXY_IPS` 是精確的 JSON 清單。只有來自清單內節點的連線，才能透過 `X-Forwarded-For` 影響用戶端位址判定。請只信任實際部署觀察到的 loopback 代理或確切容器／gateway 位址，不能填 `0.0.0.0/0` 或寬廣的校園網段。

## 與原網站分離

助理使用獨立程序／容器，並應配置自己的子網域與反向代理路由。這樣能降低相互影響，也能單獨回復版本。不過，只要兩套系統共用作業系統、虛擬化平台、網路、代理、儲存空間或資源上限，就無法保證完全隔離。請在部署層設定 CPU、記憶體、程序、網路與存取限制，並獨立監控原網站。
