# Private Marker Unit-Test 覆蓋率報告

這份報告是在 API、MCP、Skill 文件工作的第一輪 unit-test 執行後產生。

## 測試執行資訊

- 日期：2026-05-15
- 環境：專案 `.venv`
- 指令：

```bash
.venv/bin/python -m pytest tests/private_web --cov=marker.scripts.private_web --cov=marker.scripts.private_mcp --cov-report=term-missing --cov-report=json:/private/tmp/private_marker_coverage.json
```

## 結果

- 測試檔案：`tests/private_web/test_private_web_api.py`、`tests/private_web/test_private_mcp.py`、`tests/private_web/test_private_marker_docs.py`
- 測試數量：11
- 通過：11
- 失敗：0
- 執行時間：0.34 秒
- Coverage JSON：`/private/tmp/private_marker_coverage.json`

## 覆蓋率摘要

| 模組                            | Statements | Missed | Coverage |
|---------------------------------|-----------:|-------:|---------:|
| `marker/scripts/private_web.py` |        305 |    139 |      54% |
| `marker/scripts/private_mcp.py` |        104 |     50 |      52% |
| 總計                            |        409 |    189 |      54% |

## 已覆蓋行為

- 繁體中文檔名顯示處理。
- Windows 保留名稱與非法字元處理。
- 透過 `Content-Disposition` 支援 UTF-8 下載檔名。
- 支援格式與無效輸入的上傳驗證。
- 壓縮檔內 Unicode 根目錄與圖片路徑保留。
- Job metadata 持久化與遷移預設值。
- MCP 對 API 行為的 tool registration。
- MCP `initialize`、`tools/list`、成功 `tools/call`、未知工具錯誤處理。
- API、MCP、Skill 文件關鍵段落檢查。

## 已知缺口

- Unit test 尚未涵蓋完整 Marker 轉換流程。
- FastAPI route tests 尚未補上。
- 前端 job retention 與舊工作下載選擇行為尚未有自動化 UI 測試。
- MCP live API calls 尚未納入 unit-test suite。
- Skill 目前驗證文件結構，不等於已由 agent runtime 實際執行。

## 建議下一步

使用 FastAPI `TestClient` 增加 endpoint-level tests，並 monkeypatch conversion runner。這樣可以在不啟動沉重轉換流程的情況下，提高 `/jobs`、`/jobs/{id}`、`/jobs/{id}/download` 與刪除行為的信心。
