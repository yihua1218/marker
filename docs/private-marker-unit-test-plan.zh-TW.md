# Private Marker Unit Test 驗證計畫

這份計畫定義 private Marker 網站 API、MCP server，以及 Skill 套件的第一階段 unit-test 路徑。目標是在不必每次都執行完整 OCR/model 轉換的情況下，先保護私有轉換流程裡最關鍵、最容易回歸的行為。

## 範圍

- API 模組：`marker/scripts/private_web.py`
- MCP 模組：`marker/scripts/private_mcp.py`
- 根目錄 MCP 啟動器：`private_marker_mcp.py`
- API 文件：`docs/private-web-api.md`
- MCP 文件：`docs/private-marker-mcp.md`
- Skill 文件與範例：`docs/private-marker-skill.md`、`docs/skills/private-marker-web/SKILL.md`

## 第一階段 MVP 測試路徑

- 驗證繁體中文檔名與 Windows 敏感檔名的處理。
- 驗證支援格式與拒絕格式的上傳檢查。
- 驗證壓縮檔建立，包含 Unicode 根目錄與圖片路徑。
- 驗證 job metadata 的持久化，以及舊版 `job.json` 的遷移。
- 驗證 MCP tool schema 是否涵蓋所有對應 API 的工具。
- 驗證 MCP JSON-RPC 的初始化、工具列表、工具呼叫序列化，以及未知工具錯誤。
- 驗證 API、MCP、Skill 文件是否包含必要的操作說明。

## Unit-Test Checklist

- [x] API 檔名 helper 保留顯示名稱，並提供 ASCII-safe fallback。
- [x] API 下載 `Content-Disposition` 支援 RFC 5987 `filename*` UTF-8 檔名。
- [x] API 上傳驗證接受宣告支援的格式。
- [x] API 上傳驗證拒絕不支援的副檔名與無效 PDF header。
- [x] API 壓縮檔建立時，在 `.zip` 內保留繁體中文名稱。
- [x] API job store 能持久化並重新載入完成的工作。
- [x] API job store 能為舊 metadata 補上預設輸出格式與顯示名稱。
- [x] MCP tool schema 包含 auth、API info、list、get、create、download、delete tools。
- [x] MCP server 能回應 `initialize`。
- [x] MCP server 能回應 `tools/list`。
- [x] MCP server 能序列化成功的 `tools/call` 結果。
- [x] MCP server 對未知工具回傳結構化錯誤。
- [x] Skill 與 API 文件包含必要 workflow、privacy、format、boundary 說明。

## 第一次測試指令

從專案根目錄使用 `.venv` 執行：

```bash
.venv/bin/python -m pytest tests/private_web --cov=marker.scripts.private_web --cov=marker.scripts.private_mcp --cov-report=term-missing --cov-report=json:/private/tmp/private_marker_coverage.json
```

## 目前刻意排除的範圍

- Unit test 不執行完整 Marker OCR/model 轉換，因為速度慢且受硬體環境影響。
- 尚未涵蓋瀏覽器與 UI 流程，後續應使用 Vitest 或 Playwright 補上。
- MCP 對實際 API server 的 live upload/download 尚未放入 unit-test suite。
- Skill 目前驗證文件與工作流程覆蓋，不當作已安裝的 runtime integration 測試。

## 下一階段覆蓋目標

- 使用 FastAPI `TestClient` 增加 endpoint tests，並 monkeypatch `run_conversion`。
- 增加 `GET /jobs/{id}/download` 下載舊完成工作項目的測試。
- 增加前端保留 job selection 與 output-format submission 的測試。
- 加上需要明確 opt-in marker 的 MCP integration smoke tests。
- endpoint tests 提升覆蓋率後，再設定 coverage threshold。
