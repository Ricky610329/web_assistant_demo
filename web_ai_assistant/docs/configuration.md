# 設定參考

本頁列出助理的 `.env` 設定。第一次啟動時複製 `.env.example`；已有設定時直接編輯，不要覆蓋。`.env` 已被 Git 忽略，範本只包含示範值。

## 三種網址不要混淆

| 用途 | 欄位 | 範例 |
|---|---|---|
| 助理後端連到模型的網址 | `LLM_BASE_URL` | `http://localhost:11434/v1` |
| 瀏覽器看到的助理公開來源 | `PUBLIC_BASE_URL` | `https://assistant.school.example` |
| 可以嵌入助理的主網站來源 | `ALLOWED_FRAME_ORIGINS` | `["https://www.school.example"]` |

「來源」是協定、主機名稱及 port 的組合，不包含頁面路徑。`http://localhost:8080` 與 `http://127.0.0.1:8080` 是不同來源；HTTP 與 HTTPS 也不同。

## 模型設定

| 欄位 | 預設值 | 說明 |
|---|---|---|
| `LLM_MODE` | `mock` | `mock` 為離線示範；`openai` 使用相容 Chat Completions 串流 |
| `LLM_BASE_URL` | `http://localhost:4000/v1` | 模型服務的 base URL；範本值是占位值，不會啟動 LiteLLM |
| `LLM_API_KEY` | 空白 | `openai` 模式必須有非空值；本機 Ollama 可填 `ollama` |
| `LLM_MODEL` | 空白 | 相容模式必填，使用實際模型名稱或 Proxy 別名 |
| `SYSTEM_PROMPT` | 空白時使用內建提示詞 | 內建提示詞要求繁體中文、清楚誠實及說明不確定性；自訂上限 8,000 字元 |

各服務可直接使用的範例見[模型服務設定](model-services.md)。系統提示詞只影響回答方式，不會讓模型讀取網站或取得校務資料。

## 網站與代理設定

| 欄位 | 預設值 | 說明 |
|---|---|---|
| `PUBLIC_BASE_URL` | 空白 | 直接本機 HTTP 使用時留白；HTTPS 反向代理部署時填入瀏覽器看到的助理來源 |
| `ALLOWED_FRAME_ORIGINS` | `["http://localhost:8080","http://127.0.0.1:8080"]` | 精確來源的 JSON 清單，不可使用 `*`；不等於 API 身分驗證 |
| `TRUSTED_PROXY_IPS` | `[]` | 精確代理 IP 的 JSON 清單；只有來自這些 IP 的連線才採用 `X-Forwarded-For` |
| `ASSISTANT_BIND_ADDRESS` | `127.0.0.1` | 僅由 Compose 決定主機發布 port 的監聽位址，不是 FastAPI 設定 |

`PUBLIC_BASE_URL` 不能填主網站網址、模型網址或 `/widget/` 路徑。代理與 CSP 的部署範例見[部署文件](deployment.md)及[嵌入說明](embedding.md)。

## 資源限制

| 欄位 | 預設值 | 單位／行為 |
|---|---|---|
| `MAX_CONCURRENT_REQUESTS` | `4` | 同時進行的聊天請求；額滿回 503，不排隊 |
| `REQUESTS_PER_MINUTE` | `20` | 每個可見用戶端 IP、滾動 60 秒；超額回 429 |
| `REQUEST_TIMEOUT_SECONDS` | `90` | 秒，生成預算；可設定上限為 600 秒 |
| `BODY_READ_TIMEOUT_SECONDS` | `10` | 秒，讀取請求內容的預算；超過回 408 |
| `MAX_BODY_BYTES` | `65536` | 整個 JSON 請求的 bytes 上限 |
| `MAX_MESSAGES` | `20` | 訊息筆數上限；因角色交替並以 user 結束，預設實際最多 19 筆 |
| `MAX_MESSAGE_CHARS` | `4000` | 單筆內容的字元上限 |
| `MAX_TOTAL_CHARS` | `24000` | 請求中所有對話訊息的字元總和上限 |

內附前端也有固定的訊息／歷史紀錄限制與 4,000 字元回答上限。只提高後端值，不會同步提高前端限制。字元與 bytes 不同，中文字的 JSON 請求可能先碰到 bytes 上限。

90 秒不是整個請求的硬性總時間；最後事件傳送與上游清理還有受限的寬限時間。詳見 [API 的逾時行為](api.md)。流量限制保存在單一程序記憶體，重啟後重設，因此目前維持 **單一 worker、單一副本**。

## 修改後怎麼套用

- 直接執行：停止 Uvicorn，再用原指令啟動。
- Docker：在專案目錄執行 `docker compose up -d --force-recreate`。
- 若變更 `ALLOWED_FRAME_ORIGINS` 或網站 CSP，重啟後重新整理主網站再檢查。

程序環境變數會優先於 `.env`；若修改檔案仍無效，檢查啟動方式是否另外設定同名變數。金鑰只放在助理伺服器，不能放進嵌入 script、網址或瀏覽器程式碼。
