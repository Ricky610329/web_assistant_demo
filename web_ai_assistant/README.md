# 快速開始

本系統供教學與開發參考。主網站只需加入一個 script；聊天介面與模型請求由獨立的助理服務處理。

建議順序：**先跑離線示範 → 試嵌入 → 接上模型 → 正式部署**。以下指令都在儲存庫根目錄開始操作。實作驗證環境為 Python 3.14。

## 1. 啟動離線示範

選擇自己的作業系統。這些指令不需要啟用虛擬環境，直接使用其中的 Python。

Windows PowerShell：

```powershell
cd web_ai_assistant
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Linux：

```bash
cd web_ai_assistant
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

保留這個終端視窗。開啟[聊天頁面](http://127.0.0.1:8000/widget/)，應看到「示範模式」，傳送訊息後會收到離線示範回覆。這代表介面與串流可用，還沒有接上語言模型。

設定從目前工作目錄的 `.env` 載入，因此必須在 `web_ai_assistant/` 啟動。已經有 `.env` 時，不要用範本覆蓋自己的設定。

## 2. 試嵌入另一個網站

開啟第二個終端，切換到 `web_ai_assistant/`，啟動範例網站：

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m http.server 8080 --directory static/examples
```

Linux：

```bash
.venv/bin/python -m http.server 8080 --directory static/examples
```

開啟：

- [最小嵌入範例](http://127.0.0.1:8080/embed.html?assistant=http://127.0.0.1:8000/)
- [含表單的入口網站範例](http://127.0.0.1:8080/portal.html?assistant=http://127.0.0.1:8000/)

右下角會出現聊天按鈕，點擊後才載入助理。主網站在 8080 port，助理在 8000 port，兩者是不同來源。請透過這些 HTTP 網址測試，不要直接開啟 HTML 檔案。

要放到自己的網站，照[嵌入說明](docs/embedding.md)設定允許來源並加入 script。

## 3. 接上模型

在 `.env` 設定模式、服務網址、模型名稱與金鑰，再重啟助理。`LLM_MODE=openai` 表示使用 **OpenAI 相容協定**，所以 Ollama 也使用這個模式。

例如助理與 Ollama 都直接執行在同一台電腦：

```dotenv
LLM_MODE=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3:8b
```

模型名稱須改成你實際已安裝的模型。Docker 的網址不同，請先閱讀[模型服務設定](docs/model-services.md)，其中也有 LiteLLM 與 OpenAI 範例。完整欄位見[設定參考](docs/configuration.md)。

## 4. 使用 Docker 或正式部署

若已安裝 Docker 與 Docker Compose，在 `web_ai_assistant/` 執行：

```bash
docker compose up --build -d
docker compose ps
```

第一次使用先複製 `.env.example` 成 `.env`；若只跑示範，也可使用 Compose 的無 `.env` 預設模式。服務網址是 `http://127.0.0.1:8000/widget/`。

修改 `.env` 後用 `docker compose up -d --force-recreate` 套用，單純 `restart` 不會更新容器環境變數。停止服務用 `docker compose down`。

映像只包含執行程式與靜態資源，以非 root 使用者執行。範本限制為 1 GiB 記憶體、2 顆 CPU，並固定單一 worker。公開部署需要 HTTPS、允許嵌入的網站來源與正確的代理設定，請依照[部署與維運](docs/deployment.md)操作。本機尚未安裝 Docker，範本未經實際建置驗證。

## 範圍與驗證

目前支援文字聊天、串流、取消、清除、訊息限制、頻率限制與逾時。瀏覽器不能指定上游服務、模型、系統提示詞或金鑰；這些都由後端管理。

本系統沒有登入、資料庫、對話保存、RAG、校務資料檢索、檔案上傳或頁面擷取。聊天內容保留在目前頁面的記憶體中，清除或重新整理後不會還原。模型不會自動知道你網站或學校的資訊。

實作階段的結果：

| 驗證 | 結果 |
|---|---|
| 後端測試 | 45 項通過，含本機真實 HTTP 的相容 gateway 測試 |
| Edge 瀏覽器驗收 | 12 項通過，含桌面、手機、跨來源、取消、錯誤及 CSP |
| 真正的模型服務 | 尚未實測 Ollama、LiteLLM 或 OpenAI |
| Docker | 尚未建置或執行 |

開發者可用建立的虛擬環境重跑：

| 操作 | Windows PowerShell | Linux |
|---|---|---|
| 安裝開發套件 | `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` | `.venv/bin/python -m pip install -r requirements-dev.txt` |
| 後端測試 | `.\.venv\Scripts\python.exe -m pytest` | `.venv/bin/python -m pytest` |
| 瀏覽器驗收 | `.\.venv\Scripts\python.exe tests/browser_smoke.py` | `.venv/bin/python tests/browser_smoke.py` |

瀏覽器驗收需已有 Microsoft Edge；它會自行啟停測試伺服器，產物寫入不追蹤的 `.artifacts/`。

## 進一步閱讀

- [模型服務設定](docs/model-services.md)：Ollama、LiteLLM、OpenAI、連線排錯。
- [設定參考](docs/configuration.md)：所有 `.env` 欄位及重啟方式。
- [嵌入說明](docs/embedding.md)：script、外觀、網站允許清單與 CSP。
- [部署與維運](docs/deployment.md)：HTTPS、代理、更新與回復。
- [架構](docs/architecture.md)與 [API](docs/api.md)：開發者參考。
