# 可嵌入網站的 LLM 助理

這是一套教學與開發參考系統：在既有網站加入一個 `<script>`，就能開啟獨立的聊天介面。後端透過 OpenAI 相容的 Chat Completions 介面連接模型，可設定 Ollama、LiteLLM 或其他相容服務。

預設使用離線示範，不需要 API 金鑰，也不會呼叫模型。先依照[快速開始](web_ai_assistant/README.md)操作，再接上自己的模型服務。

| 想做的事 | 閱讀文件 |
|---|---|
| 在本機啟動並試聊 | [快速開始](web_ai_assistant/README.md) |
| 設定 Ollama、LiteLLM 或 OpenAI | [模型服務設定](web_ai_assistant/docs/model-services.md) |
| 查詢 `.env` 欄位 | [設定參考](web_ai_assistant/docs/configuration.md) |
| 插入自己的網站 | [嵌入說明](web_ai_assistant/docs/embedding.md) |
| 部署到伺服器 | [部署與維運](web_ai_assistant/docs/deployment.md) |
| 理解程式或串接 API | [架構](web_ai_assistant/docs/architecture.md)、[API](web_ai_assistant/docs/api.md) |

## 儲存庫內容

公開內容集中在 `web_ai_assistant/`：包含後端、聊天介面、兩個嵌入範例、測試、Docker 範本及繁體中文文件。舊版 vanilla 已移除。

`.env`、本機金鑰、虛擬環境、快取、日誌及瀏覽器測試產物不納入版本控制。只提交不含真實金鑰的 `.env.example`。介面使用的第三方程式庫及其授權聲明保留在 [web_ai_assistant/static/assets/vendor/](web_ai_assistant/static/assets/vendor/)，不需執行時連到外部 CDN。

實作階段已通過 45 項後端測試及 12 項 Edge 瀏覽器驗收。真實 Ollama／LiteLLM／OpenAI 連線與 Docker 建置仍需在使用者的環境驗證。
