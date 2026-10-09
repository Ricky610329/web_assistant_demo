# 正式環境部署

## 部署方式

助理應與既有學校網站分開部署：

1. 為 `assistant.school.example` 建立 DNS 與 TLS 憑證。
2. 將 `.env.example` 複製成不納入版本控制的 `.env`；把 `PUBLIC_BASE_URL` 設成確切公開 HTTPS 來源站，並設定可嵌入來源站及必要的可信任代理節點。
3. 用 Docker Compose 建置並啟動單一助理服務。
4. 在 `127.0.0.1:8000` 前方配置 HTTPS 反向代理。
5. 檢查 `/healthz`、`/api/config`、元件頁、mock 串流、從真實學校來源站嵌入，以及取消請求。
6. 先在非公開測試路由設定並測試相容模型，通過後才啟用 `LLM_MODE=openai`。
7. 獨立服務通過檢查後，才在原網站加入單一 script 標籤。

Uvicorn 必須維持單一 worker 與單一副本。並行及頻率限制目前只存在單一程序，增加 worker 或副本後會各自計算。水平擴充前，應先把限制狀態移到共用儲存區。

## Nginx 範例

以下是獨立的助理 virtual host。原學校網站的 virtual host 與動態後端不需變更。

```nginx
server {
    listen 443 ssl http2;
    server_name assistant.school.example;

    ssl_certificate     /etc/letsencrypt/live/assistant.school.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/assistant.school.example/privkey.pem;

    client_max_body_size 64k;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;

        # Replace, rather than append to, untrusted incoming forwarding data.
        proxy_set_header X-Forwarded-For $remote_addr;

        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 100s;
        add_header X-Accel-Buffering no always;
    }
}
```

`proxy_read_timeout` 必須大於 `REQUEST_TIMEOUT_SECONDS`，並保留最後事件與清理的時間；範例針對 90 秒生成預算設為 100 秒。`TRUSTED_PROXY_IPS` 應填入實際連到應用程式的精確來源位址，通常是主機代理的 loopback 或明確的容器 gateway。Uvicorn 已停用內建代理標頭判讀，由應用程式執行有限的信任判斷。請勿信任所有節點。

此範例須設定 `PUBLIC_BASE_URL=https://assistant.school.example`。若未設定，Uvicorn 看到的是內部 HTTP 來源站，瀏覽器卻送出外部 HTTPS 來源站，同來源檢查會正確拒絕兩者不符。`PUBLIC_BASE_URL` 只能包含 scheme、host 與選用的 port，不可包含路徑。

## 日常操作

常用檢查：

```bash
docker compose ps
docker compose logs --tail=100 assistant
curl -fsS https://assistant.school.example/healthz
curl -fsS https://assistant.school.example/api/config
curl -N https://assistant.school.example/api/chat \
  -H 'Content-Type: application/json' \
  --data '{"messages":[{"role":"user","content":"連線測試"}]}'
```

`/healthz` 只代表程序存活。正式上線前還應透過選定上游發出受限測試請求，且不得在紀錄中暴露回答或憑證。請確認紀錄只有請求中繼資料。

## 疑難排解

- **按鈕出現但面板被封鎖：** 檢查瀏覽器 CSP 錯誤、元件回應的 `frame-ancestors`、是否重新導向到不同主機名稱，以及 `ALLOWED_FRAME_ORIGINS` JSON 是否完全相符。
- **載入器或樣式被封鎖：** 將助理來源站加入學校網站既有的 `script-src` 與 `frame-src`。現代瀏覽器可保留 `style-src 'self'`；只有使用外部 `assets/embed.css` fallback 的舊瀏覽器，才要把助理來源站加入 `style-src`。三個 directive 不會互相涵蓋，也不需要 `unsafe-inline`。
- **容器無法連到模型：** 主機服務應把 `localhost` 改成 `host.docker.internal`；Linux 保留 Compose 的 `host-gateway`，並檢查模型監聽位址與防火牆只開放必要路徑。
- **OpenAI 模式立即失敗：** 確認 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 都不是空值，且上游支援相容的 `/chat/completions` 串流。
- **串流一次全部出現：** 關閉每一層代理／CDN 的 buffering 與 cache，並使用可逐段讀取串流的用戶端。
- **許多使用者一起遇到 429：** NAT gateway 可能讓多位使用者共用同一位址。請依實測校園流量調整邊緣與應用程式限制。
- **負載時出現 503：** 預設最多四個並行請求，額滿直接拒絕、不排隊。先降低上游延遲；增加副本前須另行設計共用佇列／限制器。
- **生成約 90 秒後逾時：** 修正上游延遲，或同步調整應用程式生成預算與代理讀取 timeout，也要預留最後事件及清理時間。系統刻意不自動重試。
- **串流開始前出現 HTTP 408：** 用戶端未在 `BODY_READ_TIMEOUT_SECONDS` 內送完內容。提高預設 10 秒限制前，先檢查慢速連線或代理 buffering。

## 更新與回復

更新前先記錄目前 image digest，並保留上一個不可變映像。建置新映像、完成 mock 與測試上游檢查後，再替換助理服務。不要把助理更新和原網站應用程式部署綁在一起。

需要回復時，重新部署上一版助理映像，再檢查健康狀態與一筆串流。若要立即移除，只需刪除或停用學校頁面上的單一助理 `<script>`，原頁面其他部分不需更動。接著停止獨立服務：

```bash
docker compose down
```

移除 script 是最快的使用者端回復方式。確認原網站正常後，再清理 DNS、代理或容器。本參考系統沒有對話資料庫；紀錄與產物仍只應依學校既有保存規則處理。
