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

## Job 恢復與 Log

Job metadata 與上傳的 input file 會保留在 `MARKER_WEB_JOB_DIR`。Server 啟動時，原本是 `queued` 或 `running` 的 jobs 會被移回 `queued`，並且預設重新送進 worker pool。只有在你想手動檢查或手動 retry 時，才設定 `MARKER_WEB_AUTO_RESUME_JOBS=0`。

Server 會透過 Marker logger 記錄 job 載入、重新排隊、送進 executor、開始轉換、完成轉換、建立 archive、input 缺失、retry 與失敗事件。Log 會包含 job id 與除錯需要的路徑。

## 支援輸入格式

支援上傳副檔名：

- `.pdf`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`
- `.pptx`
- `.docx`
- `.xlsx`
- `.html`, `.htm`
- `.epub`

## 轉換引擎與輸出格式

使用 `conversion_engine` form field 選擇轉換引擎：

- `marker`：預設，使用此專案原本的 Marker pipeline。
- `docling`：使用 IBM Docling `DocumentConverter`。Docling 是 optional dependency，需先安裝 `marker-pdf[docling]` 或 `marker-pdf[full]`。
- `auto`：PDF-to-Markdown routing pipeline。先用啟用 OCR 的 Docling 快速轉換並做品質檢查，不通過時才 fallback 到 Marker。

Docling 官方文件目前建議的 Python 用法是 `DocumentConverter().convert(source).document`，再用 `export_to_markdown()` 等方法輸出；本專案依這個 API 包裝。

使用 `output_format` form field，Marker 可用值為：

- `markdown`
- `json`
- `html`
- `chunks`

Docling 可用值為：

- `markdown`
- `json`
- `html`

Auto 可用值為：

- `markdown`

壓縮檔下載格式支援：

- `zip`
- `tar.gz`

## 檔名處理

服務會將檔名分成三種：

- `original_filename`：瀏覽器提供的原始檔名，用於顯示。
- `display_stem`：Unicode NFC 正規化後、Windows-safe 的顯示名稱。繁體中文檔名會保留在這裡。
- `document_stem`：內部儲存用的 ASCII slug，並附加 job id 前綴以避免撞名。

下載時會使用 RFC 5987 `Content-Disposition` header，同時提供 `filename` 與 `filename*`，讓 Windows 上的現代瀏覽器能正確取得繁體中文檔名。

壓縮檔內容會使用 `display_stem` 作為 package root 與輸出檔名。例如上傳 `測試文件.pdf` 並選擇 Markdown，壓縮檔內會類似：

```text
測試文件/
  測試文件.md
  metadata.json
  images/
```

Windows 不允許的字元 (`<>:"/\\|?*` 與控制字元) 會被替換成 `-`，保留裝置名稱則 fallback 成 `document`。

## Endpoints

### `GET /api/info`

回傳機器可讀的 API metadata，包含支援輸入副檔名、輸出格式、壓縮格式與 endpoint 名稱。

### `GET /openapi.json`

回傳此 private web service 的 FastAPI OpenAPI schema。

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
  -F 'conversion_engine=auto' \
  -F 'output_format=markdown' \
  http://127.0.0.1:8765/jobs
```

`conversion_engine` 可為 `marker`、`docling` 或 `auto`。`output_format` 在 Marker 可為 `markdown`、`json`、`html` 或 `chunks`；在 Docling 可為 `markdown`、`json` 或 `html`；在 Auto 只支援 `markdown`。

### `GET /jobs`

列出已保留的 jobs。

### `GET /jobs/{job_id}`

取得單一 job 狀態。可輪詢此 endpoint，直到 `status` 為 `complete` 或 `failed`。

### `POST /jobs/{job_id}/retry`

使用保留的 input file 重新排入 completed 或 failed job。已經是 `queued` 或 `running` 的 job 會回傳 `409`。

### `GET /jobs/{job_id}/download?format=zip`

下載產生的壓縮檔。

`format` 可為：

- `zip`
- `tar.gz`

### `DELETE /jobs/{job_id}`

刪除 completed 或 failed job，並移除上傳檔案、輸出檔案與壓縮檔。

Running jobs 不允許刪除。

## MCP Tool 規劃

已實作的 stdio MCP server 會用以下 tools 包裝這些 API：

- `marker_web_auth_status`
  - Input：無，或 `base_url`。
  - Output：驗證狀態。
- `marker_web_create_job`
  - Input：`base_url`、本機檔案路徑、`output_format`、`conversion_engine`。
  - Output：job object。
- `marker_web_get_job`
  - Input：`base_url`、`job_id`。
  - Output：job object。
- `marker_web_list_jobs`
  - Input：`base_url`。
  - Output：已保留 jobs。
- `marker_web_retry_job`
  - Input：`base_url`、`job_id`。
  - Output：重新排入的 job object。
- `marker_web_download_job`
  - Input：`base_url`、`job_id`、archive `format`、目的路徑。
  - Output：已儲存 archive 路徑。
- `marker_web_delete_job`
  - Input：`base_url`、`job_id`。
  - Output：刪除結果。

MCP server 應從環境變數讀取 token，例如 `MARKER_WEB_TOKEN`，並用 Bearer token 傳送。

啟動方式與 JSON-RPC 範例請見 [private-marker-mcp.md](./private-marker-mcp.md)。

## Skill 規劃

Codex skill 可提供高階工作流：

1. 確認 private Marker server base URL。
2. 確認來源檔案路徑。
3. 選擇 `conversion_engine`：`marker`、`docling` 或 `auto`。
4. 選擇 `output_format`：`markdown`、`json`、`html` 或 `chunks`。Docling 不支援 `chunks`；Auto 只支援 Markdown。
5. 透過 `POST /jobs` 上傳檔案。
6. 輪詢 `GET /jobs/{job_id}` 直到完成。
7. 下載指定壓縮格式。
8. 如果使用者要求，刪除已保留 job。

建議 skill 指令：

- 「用 private Marker 把這個檔案轉成 Markdown。」
- 「用 Docling 把這個 PDF 轉成 Markdown。」
- 「用 Auto mode 轉這個 PDF；Docling 品質不夠時自動 fallback Marker。」
- 「把這個 PDF 轉成 JSON 並下載 zip。」
- 「列出已保留的 Marker conversion jobs。」
- 「刪除 Marker job `<job_id>`。」

Skill 說明與範例請見 [private-marker-skill.md](./private-marker-skill.md) 和 [skills/private-marker-web/SKILL.md](./skills/private-marker-web/SKILL.md)。
