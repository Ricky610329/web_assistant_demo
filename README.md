# 網站 AI 助理工作區

此儲存庫目前有兩套彼此獨立的實作：

- [`web_ai_assistant/`](web_ai_assistant/) 是新的學校資訊人員參考系統，包含以 iframe 嵌入的元件與 FastAPI 串流後端。請先閱讀該目錄的 README 與部署文件。
- `web_ai_assistant_vanilla/` 是較早期、尚未納入版本控制的原生 JavaScript 原型，只保留作為參考。新服務不會匯入、部署或修改它。

參考系統預設回傳固定的 mock 示範內容。Docker 與真正的 OpenAI 相容服務或 LiteLLM 連線仍須在目標環境驗證；本儲存庫不宣稱已設定真實模型端點。
