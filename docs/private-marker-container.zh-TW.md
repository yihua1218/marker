# Private Marker 容器設定

這個服務可以透過 repository 內的 `Dockerfile`、`docker-compose.yml`、`.env`、`.env.example` 使用 Docker Compose 或 `nerdctl compose` 啟動。

## 檔案

- `Dockerfile`：建置 React 前端，並把 private Marker web service 安裝到 Python runtime image。
- `docker-compose.yml`：啟動 web service、對應 port、掛載持久化資料，並設定 health check。
- `.env.example`：會進版本控制的設定範例。
- `.env`：本機執行設定，已被 git 忽略。
- `private-marker-data/`：已被 git 忽略，掛載到容器內 `/app/data` 保存 jobs 與 cache。

## 設定

先複製範例，並在開放服務前更換 token：

```bash
cp .env.example .env
```

重要設定：

- `PORT`：host 與 container 的 web port。預設 `8765`。
- `HOST`：container 內 bind host。容器內請使用 `0.0.0.0`。
- `MARKER_WEB_TOKEN`：private web/API/MCP 共用 token。
- `MARKER_WEB_JOB_DIR`：container 內 job storage 路徑。預設 `/app/data/jobs`。
- `MARKER_WEB_FRONTEND_DIST`：image 內建置完成的前端路徑。
- `HF_HOME`、`TORCH_HOME`、`XDG_CACHE_HOME`：掛載的模型與 runtime cache 路徑。
- `IMAGE_NAME`、`IMAGE_TAG`：compose 使用的本機 image 名稱。

## 建置與啟動

如果你使用 Docker Desktop 或其他 Docker-compatible runtime，執行：

```bash
docker compose up --build
```

如果你使用 Rancher Desktop 搭配 containerd，執行：

```bash
nerdctl compose up --build
```

兩個指令都會在需要時從 `Dockerfile` 建立 image、建立 `private-marker-web` 服務、把 `./private-marker-data` 掛載到 `/app/data`，並用設定的 `PORT` 啟動 web server。

開啟：

```text
http://localhost:8765
```

用 `.env` 裡的 `MARKER_WEB_TOKEN` 登入。

## 只建立 Image

如果只想建立 image，不啟動服務：

```bash
docker build -t localhost/private-marker-web:latest .
```

使用 `nerdctl`：

```bash
nerdctl build -t localhost/private-marker-web:latest .
```

如果你在 `.env` 修改了 `IMAGE_NAME` 或 `IMAGE_TAG`，請用相同值作為 image tag。

## Health Check

```bash
curl -fsS http://localhost:8765/health
```

預期回應：

```json
{
  "ok": true,
  "private_mode": true
}
```

## API Smoke Test

```bash
curl \
  -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  http://localhost:8765/api/info
```

## 上傳 Smoke Test

```bash
curl \
  -H "Authorization: Bearer $MARKER_WEB_TOKEN" \
  -F "file=@/path/to/document.pdf" \
  -F "output_format=markdown" \
  http://localhost:8765/jobs
```

## 停止

使用 Docker Compose：

```bash
docker compose down
```

使用 `nerdctl compose`：

```bash
nerdctl compose down
```

已保留的 jobs 與模型 cache 會留在 `private-marker-data/`。

## 注意事項

- Linux container runtime 內無法使用 macOS 的 MPS/M1 GPU 加速。除非另外設定 Linux GPU runtime，否則這個容器應視為可攜式 CPU service。
- 請保持私有使用。除非已重新審查授權、身份驗證、storage cleanup、upload limits 與 network controls，否則不要公開暴露服務。
