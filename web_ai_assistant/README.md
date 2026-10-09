# 學校網站 AI 助理參考系統

這是一套可獨立部署的小型聊天元件，供學校網站資訊人員參考。精簡的 `embed.js` 會建立 Shadow DOM 隔離的按鈕，使用者開啟時才載入助理來源站的 iframe。FastAPI 同時提供元件檔案與串流聊天 API。

預設 `LLM_MODE=mock`，只顯示固定示範回覆，不會呼叫模型。改成 `LLM_MODE=openai` 後，伺服器才會連到管理者指定、支援 `/chat/completions` 的 OpenAI 相容端點。瀏覽器無法指定模型、上游網址、API 金鑰或系統提示詞。

本參考系統刻意不包含登入、資料庫、檢索增強生成（RAG）、頁面內容擷取、對話保存或瀏覽器工具。請勿把它當成學校政策的正式資訊來源；若日後加入校務資料，須先設計適當的資料審查與授權方式。

## 本機啟動

參考執行環境為 Python 3.14。

Windows PowerShell：

```powershell
cd web_ai_assistant
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Linux：

```bash
cd web_ai_assistant
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

接著檢查 [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)，並開啟 [http://127.0.0.1:8000/widget/](http://127.0.0.1:8000/widget/)。設定只會從目前工作目錄載入 `.env`，因此請在本目錄執行指令。

若要測試跨來源嵌入，請執行 `python -m http.server 8080 --directory static/examples`，再開啟 `http://127.0.0.1:8080/embed.html?assistant=http://127.0.0.1:8000/`。也可用相同查詢參數開啟 `portal.html`，確認元件不會破壞原頁面的表單與樣式。主網站來源必須列在 `ALLOWED_FRAME_ORIGINS`。完整設定請見[嵌入說明](docs/embedding.md)。

## 使用 Docker

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/healthz
```

映像使用 `python:3.14-slim`，只安裝執行期套件並複製 `app/` 與 `static/`，服務以非 root 使用者執行。Compose 預設只發布在 `127.0.0.1`，限制為 1 GiB、2 顆 CPU，並固定單一 worker，因為流量限制目前只存在單一程序記憶體中。

若相容模型服務執行在 Docker 主機上，請設定 `LLM_BASE_URL=http://host.docker.internal:4000/v1`。Compose 已加入 Linux 的 `host-gateway` 對應。容器內的 `localhost` 是助理容器本身；模型服務必須監聽容器可到達的位址，並避免直接暴露給不受信任的網路。

## 連接模型服務

在伺服器端 `.env` 設定：

```dotenv
LLM_MODE=openai
LLM_BASE_URL=http://host.docker.internal:4000/v1
LLM_API_KEY=replace-with-a-real-secret
LLM_MODEL=administrator-approved-model
PUBLIC_BASE_URL=https://assistant.school.example
```

OpenAI 模式要求 base URL、模型與金鑰都不是空值。若受信任的內部服務確實不檢查身分，可由管理者明確填入非機密的占位值。請勿把金鑰放進 HTML、`embed.js`、查詢參數或版本控制。

本機直接用 HTTP 存取 Uvicorn 時，請將 `PUBLIC_BASE_URL` 留白。正式環境由反向代理終止 HTTPS 時，請填入瀏覽器實際看到的完整來源站，讓同來源檢查能正確比對 `Origin`，不必全面信任代理標頭。

LiteLLM 可作為上游相容服務，但不是必要元件，也沒有包含在此部署中。除非另外完成設定與測試，請勿宣稱已整合真正的 LiteLLM 或模型。`SYSTEM_PROMPT` 留白時會使用內建的繁體中文提示詞；填入非空值才會在啟動時取代它。

## 已完成的驗證

- 後端共 45 項測試通過。
- 以本機真實 HTTP 連線與 OpenAI 相容 SDK gateway 驗證 3 種情境；這不是對真正 LiteLLM 或付費模型的測試。
- 使用已安裝的 Microsoft Edge 做無頭瀏覽器測試：兩個不同主網站版型、跨來源嵌入、桌面 1440 像素與手機 390 像素、取消、清除、錯誤狀態及安全的歷史紀錄處理皆通過，沒有 JavaScript 例外或非預期 console 錯誤。
- 本機 vendor 套件稽核結果為 0 個已知弱點。
- 本機沒有 Docker，因此尚未實際建置映像或執行 Compose。

瀏覽器驗證可用下列指令重跑；需先安裝開發套件，且電腦上已有 Microsoft Edge：

```bash
python -m pip install -r requirements-dev.txt
python tests/browser_smoke.py
```

腳本會自行啟動並停止本機測試伺服器。畫面與診斷檔寫入已忽略的 `.artifacts/`，不應提交至版本控制。

## 文件

- [架構與信任邊界](docs/architecture.md)
- [嵌入學校網站](docs/embedding.md)
- [HTTP 與串流 API](docs/api.md)
- [正式部署、代理、疑難排解與回復](docs/deployment.md)

若只要執行開發測試，安裝 `requirements-dev.txt` 後執行 `python -m pytest`。正式環境仍須自行驗證 Docker 建置與實際上游連線。
