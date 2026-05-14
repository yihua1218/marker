# Private Marker Web API 說明

本文件說明 Marker 私有轉換網站使用的 API。

此 hosted service 預期僅供私有、個人、非商業使用。未經額外授權與安全審查，不應公開暴露這些 endpoints。

## 驗證

啟動 server 前設定 `MARKER_WEB_TOKEN`：

```bash
MARKER_WEB_TOKEN=your-private-token .venv/bin/marker_private_web --host 127.0.0.1 --port 8765
```

Client 可用兩種方式驗證：

- Browser cookie：`POST /auth`，form field 為 `token`。
- API token：`Authorization: Bearer <MARKER_WEB_TOKEN>`。

如果沒有設定 `MARKER_WEB_TOKEN`，server 只允許 loopback access。

## 支援輸入格式

支援上傳副檔名：

- `.pdf`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`
- `.pptx`
- `.docx`
- `.xlsx`
- `.html`, `.htm`
- `.epub`

## 支援 Marker 輸出格式

使用 `output_format` form field，值為：

- `markdown`
- `json`
- `html`
- `chunks`

壓縮檔下載格式支援：

- `zip`
- `tar.gz`

## Endpoints

### `GET /auth/status`

回傳目前驗證狀態。

### `POST /auth`

登入 browser session。

```bash
curl -c cookies.txt -F 'token=your-private-token' http://127.0.0.1:8765/auth
```

### `POST /auth/logout`

清除 browser session cookie。

### `POST /jobs`

上傳檔案並建立轉換 job。

```bash
curl \
  -H 'Authorization: Bearer your-private-token' \
  -F 'file=@/path/to/document.pdf' \
  -F 'output_format=markdown' \
  http://127.0.0.1:8765/jobs
```

`output_format` 可為 `markdown`、`json`、`html` 或 `chunks`。

### `GET /jobs`

列出已保留的 jobs。

### `GET /jobs/{job_id}`

取得單一 job 狀態。可輪詢此 endpoint，直到 `status` 為 `complete` 或 `failed`。

### `GET /jobs/{job_id}/download?format=zip`

下載產生的壓縮檔。

`format` 可為：

- `zip`
- `tar.gz`

### `DELETE /jobs/{job_id}`

刪除 completed 或 failed job，並移除上傳檔案、輸出檔案與壓縮檔。

Running jobs 不允許刪除。

## MCP Tool 規劃

未來可以用 MCP server 包裝這些 API：

- `marker_web_auth_status`
  - Input：無，或 `base_url`。
  - Output：驗證狀態。
- `marker_web_create_job`
  - Input：`base_url`、本機檔案路徑、`output_format`。
  - Output：job object。
- `marker_web_get_job`
  - Input：`base_url`、`job_id`。
  - Output：job object。
- `marker_web_list_jobs`
  - Input：`base_url`。
  - Output：已保留 jobs。
- `marker_web_download_job`
  - Input：`base_url`、`job_id`、archive `format`、目的路徑。
  - Output：已儲存 archive 路徑。
- `marker_web_delete_job`
  - Input：`base_url`、`job_id`。
  - Output：刪除結果。

MCP server 應從環境變數讀取 token，例如 `MARKER_WEB_TOKEN`，並用 Bearer token 傳送。

## Skill 規劃

Codex skill 可提供高階工作流：

1. 確認 private Marker server base URL。
2. 確認來源檔案路徑。
3. 選擇 `output_format`：`markdown`、`json`、`html` 或 `chunks`。
4. 透過 `POST /jobs` 上傳檔案。
5. 輪詢 `GET /jobs/{job_id}` 直到完成。
6. 下載指定壓縮格式。
7. 如果使用者要求，刪除已保留 job。

建議 skill 指令：

- 「用 private Marker 把這個檔案轉成 Markdown。」
- 「把這個 PDF 轉成 JSON 並下載 zip。」
- 「列出已保留的 Marker conversion jobs。」
- 「刪除 Marker job `<job_id>`。」
