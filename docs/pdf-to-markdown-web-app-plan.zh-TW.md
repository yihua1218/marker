# PDF 轉 Markdown 網站規劃

狀態說明：這是規劃與實作歷史文件。若要查看目前的啟動、API、容器與整合方式，請先看 [docs/README.md](./README.md)。

## 目標

建立一個小型私有網站，讓使用者上傳 PDF，透過 Marker 轉換成 Markdown，轉換期間顯示進度條，並在完成後把 Markdown 與抽出的圖片一起打包下載。

此應用程式的原始碼可以公開，但實際執行中的轉換服務應保持私有、有存取控制，並限制為維護者個人非商業使用。

預設輸出結構應該把抽出的圖片放在 `images/` 目錄，Markdown 檔案則放在匯出套件的根目錄。

範例匯出結構：

```text
converted-document/
  document.md
  metadata.json
  images/
    page_0_picture_0.jpeg
    page_1_table_0.jpeg
```

## 使用者體驗

MVP 的第一個畫面應該直接是可用的轉換器，而不是 landing page。

核心流程：

1. 維護者先透過私有存取入口登入。
2. 維護者上傳一個 PDF。
3. 網站驗證檔案類型、大小，以及基本 PDF 可讀性。
4. 維護者開始轉換。
5. 進度條顯示目前階段與可取得的百分比。
6. 網站顯示完成狀態、警告與輸出摘要。
7. 維護者選擇下載 `.zip`、`.tar.gz` 或其他支援的壓縮格式。

必要 UI 元素：

- 私有登入或 VPN-only 存取入口。
- PDF 上傳控制項。
- 帶有合理預設值的轉換設定區。
- 進度條，階段標籤可包含 `Queued`、`Loading models`、`Detecting layout`、`Recognizing text`、`Recognizing tables`、`Packaging output`、`Complete`。
- 下載格式選擇器。
- 下載按鈕。
- 轉換失敗時的錯誤面板。
- Footer 或授權說明區，顯示 `Powered by Marker`，並連結到 Marker GitHub repository：<https://github.com/VikParuchuri/marker>。

## 部署範圍

此專案應以私有個人工具的方式實作：

- 原始碼可以發布在公開 repository。
- 實際執行中的網站服務不得允許匿名使用者、公開註冊或第三方轉換存取。
- 存取應限制為維護者本人，可使用 VPN、IP allowlist、單一使用者登入、magic link，或其他等效的私有存取控制。
- 服務用途僅限維護者個人、非商業文件轉換。
- 上傳的 PDF、產生的 Markdown、抽出的圖片、壓縮檔、secrets、API keys、model caches，以及本機 job data 不得 commit 到公開原始碼 repository。
- 未來若要讓朋友、同事、客戶、公開訪客或自動化外部 clients 使用此 hosted conversion service，必須重新進行授權審查。

建議專案說明文字：

```text
This private tool is powered by Marker and is intended only for the maintainer's personal, non-commercial document conversion use.
```

## 輸出與壓縮格式

預設選項：

- Markdown 檔名：`document.md`，安全時可由上傳 PDF 檔名衍生。
- 圖片目錄：`images/`。
- Metadata 檔案：`metadata.json`。
- 預設壓縮格式：`.zip`。

MVP 支援的壓縮格式：

- `.zip`
- `.tar.gz`

後續可考慮的格式：

- `.tar`
- `.7z`，僅在伺服器環境有可靠且授權清楚的實作時啟用。

網站在打包前應正規化路徑，避免不安全檔名、路徑穿越或意外覆寫。

## 最小 MVP 執行路徑

1. 在任何 upload 或 job endpoint 可被存取前，先加入私有存取控制。
2. 建立 PDF 上傳用的 web server endpoint。
3. 將每個上傳 PDF 存在個別 job 的暫存目錄。
4. 建立轉換 job 紀錄，包含狀態、進度、時間戳、輸入檔名、輸出路徑與錯誤詳情。
5. 啟動背景 worker process 或 task 執行轉換。
6. 對上傳的 PDF 執行 Marker 轉換。
7. 複製或重寫產生的圖片引用，讓 Markdown 指向 `images/<filename>`。
8. 將抽出的圖片移到該 job 的 `images/` 目錄。
9. 建立 `metadata.json`，記錄轉換設定、耗時、Marker 版本與警告。
10. 依照使用者選擇的格式，從正規化後的輸出目錄建立壓縮檔。
11. 提供 progress polling 或 server-sent events，讓瀏覽器更新進度條。
12. 顯示完成畫面與下載連結。
13. 在保留期限後清理暫存檔案。

## 進度回報策略

Marker CLI 目前主要透過 logs 和 progress bars 輸出進度。MVP 可先採用務實的分階段進度模型：

- `0%`：job 建立。
- `5%`：上傳驗證完成。
- `10%`：worker 啟動並載入模型。
- `20%`：Marker 轉換開始。
- `35%`：偵測或估算 layout detection 階段。
- `55%`：偵測或估算 text recognition 階段。
- `75%`：偵測或估算 table recognition 或 image extraction 階段。
- `90%`：輸出正規化與壓縮打包。
- `100%`：壓縮檔可下載。

實作選項：

- 優先考慮直接使用 Python API，以便更好控制輸出路徑與 metadata。
- 若 MVP 先使用 CLI，則捕捉 subprocess 輸出，將已知 log/progress 訊息對應到粗略進度階段。
- 進度文案應保持誠實：無法取得精確百分比時，使用 `Working` 或 `Estimated progress` 這類標籤。

## 架構

建議 MVP 技術堆疊：

- Backend：FastAPI。
- Worker：MVP 先用本機 background task；只有在並行 jobs 需求出現後才導入 Celery/RQ/Arq。
- Frontend：簡單 server-rendered page 或輕量 SPA。
- Storage：使用可設定的本機 job 目錄。
- Packaging：Python 標準函式庫 `zipfile` 與 `tarfile`。
- Container runtime：使用 `nerdctl compose`、Python runtime image，以及掛載的持久化資料目錄。

Job 目錄結構：

```text
jobs/
  <job-id>/
    input/
      original.pdf
    output/
      document.md
      metadata.json
      images/
    archives/
      document.zip
      document.tar.gz
```

容器化部署檔案：

- `Dockerfile`：建置前端，並打包 private Marker web service。
- `docker-compose.yml`：用 `nerdctl compose` 啟動服務、對應設定的 port，並持久化 `/app/data`。
- `.env.example`：記錄 `PORT`、`MARKER_WEB_TOKEN`、`MARKER_WEB_JOB_DIR`、cache paths、image name、image tag 等 runtime settings。
- `.env`：本機使用且被 git 忽略的 runtime configuration。

建置、啟動、health check 與 smoke test 指令請見 [private-marker-container.zh-TW.md](./private-marker-container.zh-TW.md)。

## 安全性與可靠性

- 在提供轉換器之前，要求 authentication 或 VPN/IP allowlist。
- 停用公開註冊與匿名存取。
- 限制上傳大小。
- 只接受 PDF MIME type，並驗證檔案 header。
- 由伺服器產生 job ID；不要信任使用者提供的路徑。
- 清理壓縮檔內的 entry name。
- 每個 job 使用獨立轉換目錄。
- 加入轉換 timeout 控制。
- 顯示部分警告，但不要暴露伺服器 stack trace。
- 定期清理舊 jobs。
- 除非產品明確承諾保留，否則不要永久保存文件。
- 避免將上傳 PDF、輸出、壓縮檔、model caches 與 secrets 放進公開 repository。

## Marker 標示與授權規劃

Marker repository 在 `pyproject.toml` 宣告程式碼授權為 `GPL-3.0-or-later`。Repository 也包含 GPL v3 的 `LICENSE`，而 `README.md` 說明模型權重使用修改版 AI Pubs OpenRAIL-M license。

網站應謹慎處理授權：

- 在 UI 顯示 `Powered by Marker`，並提供清楚可見的連結到 <https://github.com/VikParuchuri/marker>。
- 提供 `Licenses` 頁面或 modal，連結 Marker、GPL 授權文字，以及部署服務使用的模型授權文字。
- 說明 hosted service 是私有、有存取控制，且僅供維護者個人非商業使用。
- 保留 Marker 的 copyright、license 與 attribution notices。
- 如果此網站修改 Marker 程式碼，或散布包含 Marker 的組合式應用，應準備遵守 GPL 義務，包含在必要時以相容條款提供對應原始碼。
- 公開此網站的原始碼可作為專案目標，但 repository 不得包含私人文件、產生輸出、secrets、model caches，或任何不打算再散布的檔案。
- 如果網站只是把 Marker 作為維護者私有的伺服器端工具執行，仍應清楚標示 attribution，並在散布任何 bundled application、container image 或修改版 Marker 程式碼前審視 GPL 義務。
- 不要暗示 Marker、Datalab、Broadcom 或任何上游授權方背書此網站。
- 遵守模型授權限制。此 repository 內的 `MODEL_LICENSE` 包含使用限制與 attribution 要求，README 也說明更廣泛商業使用或移除 GPL 要求需向 Datalab 取得商業授權。
- 未重新進行授權審查前，不得允許第三方使用 hosted conversion service。
- 對於 public access、商業 self-hosting、企業使用、同事、客戶，或任何超出個人非商業使用的情境，正式上線前應諮詢法律顧問並檢視 Datalab 的商業授權頁面。

本文件是實作規劃筆記，不是法律意見。

## MVP Checklist

- [ ] 建立 `docs/` 內的產品、架構與授權規劃文件。
- [ ] 將 hosted service 定義為私有、個人、非商業使用。
- [ ] 建立單頁 PDF 上傳 UI。
- [ ] 加入 authentication、VPN-only routing、IP allowlist 或等效存取控制。
- [ ] 停用匿名存取與公開註冊。
- [ ] 加入 `Powered by Marker` 與 GitHub 連結。
- [ ] 加入 `Licenses` 連結或 modal。
- [ ] 實作 PDF 上傳 endpoint。
- [ ] 加入上傳大小與 PDF 驗證。
- [ ] 建立 job 目錄與 job status model。
- [ ] 在背景 worker 執行 Marker 轉換。
- [ ] 追蹤分階段進度並顯示在 progress bar。
- [ ] 將 Markdown 圖片引用正規化為 `images/`。
- [ ] 將抽出的圖片移到 `images/`。
- [ ] 寫入 `metadata.json`。
- [ ] 打包輸出為 `.zip`。
- [ ] 打包輸出為 `.tar.gz`。
- [ ] 加入壓縮格式選擇器。
- [ ] 加入下載 endpoint。
- [ ] 加入失敗狀態與可讀錯誤訊息。
- [ ] 加入 job 清理政策。
- [ ] 確保上傳 PDF、輸出、壓縮檔、secrets 與 model caches 都被 git ignore。
- [ ] 加入 private web service 的 container image build。
- [ ] 加入 `nerdctl compose` runtime configuration。
- [ ] 文件化 container build、run、health check 與 smoke-test 步驟。
- [ ] 在散布前驗證 GPL 與模型授權合規。
- [ ] 記錄 public access、第三方使用、工作用途、客戶使用或付費部署都需要重新授權審查。

## 後續增強

- 多 PDF 批次轉換。
- WebSocket 或 server-sent event 進度更新。
- Active jobs queue dashboard。
- 逐頁預覽。
- Markdown 預覽。
- 可選的 `use_llm` 轉換模式，並清楚處理 API key。
- 管理員保留期限控制。
- 企業部署用下載 audit logs。
