# 模型服務設定

先依照[快速開始](../README.md)跑通離線示範，再修改 `web_ai_assistant/.env`。模型服務由你另外安裝或取得帳號；助理不會自動安裝 Ollama、部署 LiteLLM 或下載模型。

## 先選擇連線方式

| 使用方式 | `LLM_MODE` | `LLM_BASE_URL` 範例 | 金鑰 |
|---|---|---|---|
| 離線示範 | `mock` | 不會發出模型請求 | 可留白 |
| 本機 Ollama | `openai` | `http://localhost:11434/v1` | 本機服務可填 `ollama` |
| LiteLLM Proxy | `openai` | `http://localhost:4000` | Proxy 管理者提供的金鑰 |
| OpenAI API | `openai` | `https://api.openai.com/v1` | 自己的 OpenAI API 金鑰 |
| 其他相容服務 | `openai` | 供應商提供的 base URL | 供應商要求的金鑰 |

`openai` 是協定名稱，不代表一定呼叫 OpenAI 公司。現在使用的是文字 Chat Completions 串流，不是 Ollama 原生 `/api/chat` 或 Responses API。

`LLM_BASE_URL` 填 **base URL**，不要加上 `/chat/completions`。程式會自動接上這段路徑。是否包含 `/v1` 依服務提供的路由而定，不能一律加上。Ollama 與 OpenAI 的範例包含 `/v1`；LiteLLM 下方使用官方範例的 Proxy 根網址。

## Ollama：直接連接本機模型

### 1. 確認服務與模型

先安裝並啟動 Ollama，再執行：

```bash
ollama list
```

將輸出的完整 `NAME` 填入 `LLM_MODEL`，包括 `:8b` 之類的標籤。下方的 `qwen3:8b` 只是設定範例，不是硬體適用性建議；如果沒有模型，先選擇適合自己記憶體／顯示卡的模型，依 [Ollama 官方說明](https://docs.ollama.com/quickstart)下載。

### 2. 修改助理 `.env`

助理與 Ollama 都直接跑在同一台電腦時：

```dotenv
LLM_MODE=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3:8b
```

本機 Ollama 的相容介面忽略 API key，但目前助理與 SDK 都要求非空值，因此填 `ollama` 即可。這只適用於本機服務；直接使用 Ollama 雲端 API 時仍需要其正式金鑰。[Ollama 官方相容介面](https://docs.ollama.com/api/openai-compatibility)

### 3. Docker 的網址要另行設定

如果只有助理放進 Docker，Ollama 仍執行在主機，請將同一份 `.env` 的網址改為：

```dotenv
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

容器內的 `localhost` 指的是容器自己。內附 Compose 已設定 Linux 的 `host-gateway` 對應，但主機名稱可解析不代表一定可連線：Ollama 預設只監聽 `127.0.0.1:11434`，必須確認容器能到達它的監聽位址與防火牆規則。

必要時，在 **Ollama 所在主機**設定 `OLLAMA_HOST` 並重啟 Ollama；例如 `0.0.0.0:11434` 會監聽所有網路介面，需要用防火牆限制只有助理可存取。本機 API 不會因為填了 `LLM_API_KEY=ollama` 就增加身分驗證。

Windows 桌面版需完全退出 Ollama、修改使用者環境變數後再啟動；Linux systemd 服務需修改該服務的環境變數並重啟。詳細指令見 [Ollama 官方環境變數說明](https://docs.ollama.com/faq#how-do-i-configure-ollama-server)。`OLLAMA_HOST` 不應只寫在助理的 `.env`，那不會改變另一個程序的監聽位址。

若 Ollama 也在 Docker，則依其實際服務名稱與共用網路設定網址，例如 `http://ollama:11434/v1`；本專案的 Compose 沒有提供這個 Ollama 服務。

## LiteLLM：連接既有 Proxy

先取得 Proxy 的 base URL、允許的模型別名與金鑰。在助理 `.env` 設定：

```dotenv
LLM_MODE=openai
LLM_BASE_URL=http://localhost:4000
LLM_API_KEY=replace-with-proxy-key
LLM_MODEL=administrator-approved-model-alias
```

模型名稱填 **Proxy 對外提供的別名**，不一定等於實際供應商模型名稱。助理金鑰使用 Proxy 核發的金鑰；供應商金鑰由 Proxy 管理。本專案沒有內建 LiteLLM，Ollama 也可以直接連線，不必多經過 Proxy。[LiteLLM 官方相容用戶端範例](https://docs.litellm.ai/docs/proxy/user_keys)

若助理在 Docker、Proxy 在主機，上例改成 `http://host.docker.internal:4000`。若 Proxy 有 `/v1` 或其他公開路由前綴，依管理者提供的網址填寫；服務在遠端時用其實際 HTTPS 網址。

## OpenAI 與其他相容服務

OpenAI API 範例：

```dotenv
LLM_MODE=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=replace-with-your-api-key
LLM_MODEL=your-chat-completions-model
```

選擇帳號可用、支援 Chat Completions 串流與目前 system/user/assistant 訊息格式的模型。此系統不會傳入工具、影像、推理參數或供應商特有選項。[OpenAI 官方 Chat Completions 文件](https://developers.openai.com/api/reference/resources/chat)

其他服務同樣替換網址、金鑰與模型即可。相容程度仍需實測：助理會讀取文字 `delta.content`，並要求正常結束的 `finish_reason=stop`；空白回答或不完整串流會顯示錯誤。模型的推理內容不會作為回答顯示。

## 套用設定並確認

1. 將選定的四個 `LLM_*` 欄位寫入 `.env`，不要重複保留多組啟用值。
2. 直接執行 Uvicorn：按 `Ctrl+C` 停止助理，再用原本指令啟動。
3. 使用 Docker：執行 `docker compose up -d --force-recreate`，重新建立容器才會讀到新環境。
4. 開啟 `/widget/`，示範模式提示應消失。送出一個簡短問題，確認文字逐步出現並正常結束。

`/healthz` 成功只代表助理存活；`/api/config` 的 `demo_mode=false` 只代表選擇了相容模式。兩者都不代表模型連線成功，必須實際送出聊天問題。

## 常見問題

| 現象 | 先檢查 |
|---|---|
| 還顯示離線示範 | `.env` 是否在啟動目錄、模式是否為 `openai`、助理是否重啟 |
| 模型不存在 | Ollama 的 `ollama list` 完整名稱，或 Proxy 核發的模型別名 |
| 連線被拒絕 | 模型服務是否啟動、port 是否正確；Docker 不用容器內的 `localhost` 連主機 |
| 401／403 授權問題 | 正式服務或 Proxy 的有效金鑰；本機 Ollama 的占位值不能代替雲端金鑰 |
| 路由 404 | base URL 是否重複了 `/chat/completions`，或 `/v1` 前綴不符 |
| 回覆逾時 | 預設預算為 90 秒；模型首次載入或硬體速度可能超過預算，先確認模型服務狀態 |
| 空白或不完整回覆 | 模型是否產生文字、正常 `stop`，以及代理是否中斷串流 |

介面會隱藏上游原始錯誤，請在受控環境查看模型服務端狀態。回報問題時不要附上金鑰或完整對話。真實 Ollama、LiteLLM、OpenAI 連線尚未在本專案環境實測。
