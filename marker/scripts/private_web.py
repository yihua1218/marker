import json
import os
import re
import shutil
import tarfile
import time
import unicodedata
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal, Optional
from urllib.parse import quote

import click
from fastapi import (
    Cookie,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from marker.config.parser import ConfigParser
from marker.converters.pdf import PdfConverter
from marker.logger import get_logger
from marker.models import create_model_dict
from marker.output import convert_if_not_rgb, text_from_rendered
from marker.pipelines.pdf_conversion import DocumentConversionPipeline
from marker.settings import settings


logger = get_logger()
JOB_ROOT = Path(os.environ.get("MARKER_WEB_JOB_DIR", "private_marker_jobs"))
FRONTEND_DIST = Path(os.environ.get("MARKER_WEB_FRONTEND_DIST", "frontend/dist"))
MAX_UPLOAD_BYTES = int(os.environ.get("MARKER_WEB_MAX_UPLOAD_MB", "100")) * 1024 * 1024
AUTO_RESUME_JOBS = os.environ.get("MARKER_WEB_AUTO_RESUME_JOBS", "1").lower() in {"1", "true", "yes"}
SESSION_COOKIE = "marker_web_token"
ALLOWED_ARCHIVE_FORMATS = {"zip", "tar.gz"}
SUPPORTED_OUTPUT_FORMATS = {"markdown", "json", "html", "chunks"}
SUPPORTED_CONVERSION_ENGINES = {"marker", "docling", "auto"}
DOCLING_OUTPUT_FORMATS = {"markdown", "json", "html"}
AUTO_PIPELINE_OUTPUT_FORMATS = {"markdown"}
SUPPORTED_INPUT_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".pptx",
    ".docx",
    ".xlsx",
    ".html",
    ".htm",
    ".epub",
}
executor = ThreadPoolExecutor(max_workers=int(os.environ.get("MARKER_WEB_WORKERS", "1")))


class Job(BaseModel):
    id: str
    original_filename: str
    document_stem: str
    display_stem: str
    output_format: Literal["markdown", "json", "html", "chunks"]
    conversion_engine: Literal["marker", "docling", "auto"] = "marker"
    status: Literal["queued", "running", "complete", "failed"]
    stage: str
    progress: int
    created_at: float
    updated_at: float
    output_dir: Optional[str] = None
    zip_path: Optional[str] = None
    targz_path: Optional[str] = None
    error: Optional[str] = None


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def _job_path(self, job_id: str) -> Path:
        return JOB_ROOT / job_id / "job.json"

    def _persist(self, job: Job):
        job_path = self._job_path(job.id)
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(job.model_dump_json(indent=2), encoding=settings.OUTPUT_ENCODING)

    def load(self):
        with self._lock:
            self._jobs.clear()
            loaded_count = 0
            resumed_count = 0
            for job_path in JOB_ROOT.glob("*/job.json"):
                try:
                    payload = json.loads(job_path.read_text(encoding=settings.OUTPUT_ENCODING))
                    payload.setdefault("output_format", "markdown")
                    payload.setdefault("conversion_engine", "marker")
                    payload.setdefault("display_stem", payload.get("document_stem", "document"))
                    job = Job.model_validate(payload)
                    if job.status in {"queued", "running"}:
                        job = job.model_copy(
                            update={
                                "status": "queued",
                                "stage": "Queued for resume",
                                "progress": min(job.progress, 10),
                                "error": None,
                                "updated_at": time.time(),
                            }
                        )
                        self._persist(job)
                        resumed_count += 1
                        logger.info("Requeued interrupted private web job %s from %s", job.id, job_path)
                    self._jobs[job.id] = job
                    loaded_count += 1
                except Exception:
                    logger.exception("Failed to load private web job metadata from %s", job_path)
                    continue
            logger.info(
                "Loaded %s private web jobs from %s; requeued %s interrupted jobs",
                loaded_count,
                JOB_ROOT,
                resumed_count,
            )

    def add(self, job: Job):
        with self._lock:
            self._jobs[job.id] = job
            self._persist(job)

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            return job.model_copy()

    def list(self) -> list[Job]:
        with self._lock:
            return [
                job.model_copy()
                for job in sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            ]

    def update(self, job_id: str, **changes):
        with self._lock:
            job = self._jobs[job_id].model_copy(update={**changes, "updated_at": time.time()})
            self._jobs[job_id] = job
            self._persist(job)
            return job

    def delete(self, job_id: str):
        with self._lock:
            if job_id not in self._jobs:
                raise HTTPException(status_code=404, detail="Job not found")
            del self._jobs[job_id]
        shutil.rmtree(JOB_ROOT / job_id, ignore_errors=True)


app_data = {"jobs": JobStore()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    jobs: JobStore = app_data["jobs"]
    jobs.load()
    submitted_count = 0
    for job in jobs.list():
        if AUTO_RESUME_JOBS and job.status == "queued":
            submit_job(job)
            submitted_count += 1
    if AUTO_RESUME_JOBS:
        logger.info("Submitted %s queued private web jobs on startup", submitted_count)
    else:
        logger.warning("Automatic private web job resume is disabled; queued jobs require manual retry")
    yield
    executor.shutdown(wait=False, cancel_futures=False)


app = FastAPI(title="Private Marker Web", lifespan=lifespan)

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


def marker_web_token() -> Optional[str]:
    return os.environ.get("MARKER_WEB_TOKEN")


def is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def is_authorized(
    request: Request,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
) -> bool:
    token = marker_web_token()
    if not token:
        return is_loopback(request)

    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()

    return marker_web_token_cookie == token or bearer == token


def require_auth(
    request: Request,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    if not is_authorized(request, marker_web_token_cookie, authorization):
        raise HTTPException(status_code=401, detail="Private access required")


def dist_index() -> Optional[FileResponse]:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return None


def content_disposition(filename: str) -> str:
    ascii_fallback = safe_stem(filename) or "download"
    suffix = "".join(Path(filename).suffixes)
    if suffix and not ascii_fallback.endswith(suffix):
        ascii_fallback = f"{ascii_fallback}{suffix}"
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def display_stem(filename: str) -> str:
    stem = unicodedata.normalize("NFC", Path(filename).stem)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", stem)
    stem = stem.strip(" .-")
    if not stem or stem.upper() in WINDOWS_RESERVED_NAMES:
        return "document"
    return stem[:120]


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_stem).strip(".-")
    if not ascii_stem or ascii_stem.upper() in WINDOWS_RESERVED_NAMES:
        ascii_stem = "document"
    return ascii_stem[:80]


def validate_upload_bytes(filename: str, content: bytes):
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds configured upload limit")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_INPUT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Supported inputs: PDF, images, PPTX, DOCX, XLSX, HTML, and EPUB.",
        )

    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a readable PDF")


def rewrite_image_references(text: str, image_names: list[str]) -> str:
    for image_name in image_names:
        text = text.replace(f"]({image_name})", f"](images/{image_name})")
        text = text.replace(f'src="{image_name}"', f'src="images/{image_name}"')
        text = text.replace(f"src='{image_name}'", f"src='images/{image_name}'")
    return text


def save_private_output(rendered, output_dir: Path, output_stem: str, output_format: str) -> Path:
    text, ext, images = text_from_rendered(rendered)

    images_dir = output_dir / "images"
    if images:
        images_dir.mkdir(parents=True, exist_ok=True)

    image_names = list(images.keys())
    if ext in {"md", "html"}:
        text = rewrite_image_references(text, image_names)
    text = text.encode(settings.OUTPUT_ENCODING, errors="replace").decode(settings.OUTPUT_ENCODING)

    output_path = output_dir / f"{output_stem}.{ext}"
    output_path.write_text(text, encoding=settings.OUTPUT_ENCODING)

    metadata = {
        "marker_metadata": rendered.metadata,
        "generated_at": time.time(),
        "output_format": output_format,
        "output_extension": ext,
        "image_directory": "images",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding=settings.OUTPUT_ENCODING
    )

    for image_name, image in images.items():
        image = convert_if_not_rgb(image)
        image.save(images_dir / image_name, settings.OUTPUT_IMAGE_FORMAT)

    return output_path


def save_docling_output(input_path: Path, output_dir: Path, output_stem: str, output_format: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = DocumentConversionPipeline()
    document = pipeline.convert_with_docling(str(input_path))

    metadata = {
        "conversion_engine": "docling",
        "generated_at": time.time(),
        "output_format": output_format,
    }

    if output_format == "markdown":
        output_path = output_dir / f"{output_stem}.md"
        output_path.write_text(document.export_to_markdown(), encoding=settings.OUTPUT_ENCODING)
        metadata["output_extension"] = "md"
    elif output_format == "html":
        output_path = output_dir / f"{output_stem}.html"
        output_path.write_text(document.export_to_html(), encoding=settings.OUTPUT_ENCODING)
        metadata["output_extension"] = "html"
    elif output_format == "json":
        output_path = output_dir / f"{output_stem}.json"
        document.save_as_json(output_path, indent=2)
        metadata["output_extension"] = "json"
    else:
        raise ValueError("Docling supports markdown, json, and html output formats")

    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding=settings.OUTPUT_ENCODING
    )
    return output_path


def save_auto_pipeline_output(input_path: Path, output_dir: Path, output_stem: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = DocumentConversionPipeline()
    markdown, pipeline_metadata = pipeline.process_pdf(str(input_path))

    output_path = output_dir / f"{output_stem}.md"
    output_path.write_text(markdown, encoding=settings.OUTPUT_ENCODING)

    metadata = {
        "conversion_engine": "auto",
        "generated_at": time.time(),
        "output_format": "markdown",
        "output_extension": "md",
        "pipeline_metadata": pipeline_metadata,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding=settings.OUTPUT_ENCODING
    )
    return output_path


def make_archives(output_dir: Path, archive_dir: Path, storage_stem: str, package_stem: str) -> tuple[Path, Path]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / f"{storage_stem}.zip"
    targz_path = archive_dir / f"{storage_stem}.tar.gz"
    package_root = package_stem

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in output_dir.rglob("*"):
            if path.is_file():
                arcname = (Path(package_root) / path.relative_to(output_dir)).as_posix()
                zf.write(path, arcname)

    with tarfile.open(targz_path, "w:gz") as tf:
        for path in output_dir.rglob("*"):
            if path.is_file():
                tf.add(path, arcname=Path(package_root) / path.relative_to(output_dir))

    return zip_path, targz_path


def job_input_path(job: Job) -> Path:
    suffix = Path(job.original_filename).suffix.lower() or ".pdf"
    return JOB_ROOT / job.id / "input" / f"{job.document_stem}{suffix}"


def submit_job(job: Job):
    input_path = job_input_path(job)
    if not input_path.exists():
        logger.error("Cannot submit private web job %s because input is missing: %s", job.id, input_path)
        app_data["jobs"].update(
            job.id,
            status="failed",
            stage="Failed",
            progress=100,
            error=f"Input file is missing: {input_path}",
        )
        return

    logger.info(
        "Submitting private web job %s for conversion: input=%s output_format=%s",
        job.id,
        input_path,
        job.output_format,
    )
    future = executor.submit(
        run_conversion,
        job.id,
        input_path,
        job.document_stem,
        job.display_stem,
        job.output_format,
        job.conversion_engine,
    )
    future.add_done_callback(lambda done: log_job_future_result(job.id, done))


def log_job_future_result(job_id: str, future):
    try:
        future.result()
    except Exception:
        logger.exception("Private web job %s worker crashed outside conversion error handling", job_id)


def run_conversion(
    job_id: str,
    input_path: Path,
    storage_stem: str,
    package_stem: str,
    output_format: str,
    conversion_engine: str = "marker",
):
    jobs: JobStore = app_data["jobs"]
    job_dir = JOB_ROOT / job_id
    output_dir = job_dir / "output"
    archive_dir = job_dir / "archives"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        started_at = time.time()
        logger.info(
            "Starting private web job %s: input=%s output_format=%s",
            job_id,
            input_path,
            output_format,
        )
        if conversion_engine == "auto":
            jobs.update(job_id, status="running", stage="Running Docling quality gate", progress=20)
            save_auto_pipeline_output(input_path, output_dir, package_stem)
        elif conversion_engine == "docling":
            jobs.update(job_id, status="running", stage="Converting with Docling", progress=20)
            save_docling_output(input_path, output_dir, package_stem, output_format)
        else:
            jobs.update(job_id, status="running", stage="Loading models", progress=10)
            models = create_model_dict()
            logger.info("Private web job %s loaded models", job_id)

            jobs.update(job_id, stage=f"Converting to {output_format}", progress=20)
            config_parser = ConfigParser({"output_format": output_format, "disable_multiprocessing": True})
            converter = PdfConverter(
                config=config_parser.generate_config_dict(),
                artifact_dict=models,
                processor_list=config_parser.get_processors(),
                renderer=config_parser.get_renderer(),
                llm_service=config_parser.get_llm_service(),
            )
            rendered = converter(str(input_path))
            logger.info("Private web job %s conversion finished; saving output", job_id)

            jobs.update(job_id, stage="Normalizing output", progress=85)
            save_private_output(rendered, output_dir, package_stem, output_format)

        jobs.update(job_id, stage="Packaging archives", progress=92)
        zip_path, targz_path = make_archives(output_dir, archive_dir, storage_stem, package_stem)

        jobs.update(
            job_id,
            status="complete",
            stage="Complete",
            progress=100,
            output_dir=str(output_dir),
            zip_path=str(zip_path),
            targz_path=str(targz_path),
        )
        logger.info(
            "Completed private web job %s in %.2fs: zip=%s targz=%s",
            job_id,
            time.time() - started_at,
            zip_path,
            targz_path,
        )
    except Exception as exc:
        logger.exception("Private web job %s failed", job_id)
        jobs.update(job_id, status="failed", stage="Failed", error=str(exc), progress=100)


def html_page() -> str:
    auth_note = (
        "Set MARKER_WEB_TOKEN to require token sign-in. Without it, only loopback access is allowed."
        if not marker_web_token()
        else "Private access is enabled."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Private Marker Converter</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #20242a; }}
    main {{ max-width: 860px; margin: 0 auto; padding: 40px 20px; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; letter-spacing: 0; }}
    p {{ line-height: 1.55; }}
    section {{ background: #fff; border: 1px solid #dde1e7; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
    label {{ display: block; font-weight: 650; margin-bottom: 8px; }}
    input, select, button {{ font: inherit; }}
    input[type="file"], input[type="password"], select {{ width: 100%; box-sizing: border-box; border: 1px solid #c9d0d9; border-radius: 6px; padding: 10px; background: #fff; }}
    button {{ border: 0; border-radius: 6px; background: #1657d2; color: white; padding: 10px 14px; cursor: pointer; font-weight: 650; }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    progress {{ width: 100%; height: 18px; }}
    .row {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: end; }}
    .muted {{ color: #667085; font-size: 14px; }}
    .downloads a {{ display: inline-block; margin-right: 12px; }}
    .error {{ color: #b42318; }}
    footer {{ margin-top: 26px; color: #667085; font-size: 14px; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Private Document Converter</h1>
    <p class="muted">Personal, non-commercial Marker and optional Docling conversion service. {auth_note}</p>
  </header>

  <section id="signin">
    <form id="token-form">
      <label for="token">Private access token</label>
      <div class="row">
        <input id="token" name="token" type="password" autocomplete="current-password" placeholder="Required when MARKER_WEB_TOKEN is set">
        <button type="submit">Sign in</button>
      </div>
    </form>
  </section>

  <section>
    <form id="upload-form">
      <label for="pdf">Document file</label>
      <input id="pdf" name="file" type="file" accept="application/pdf,.pdf,image/*,.png,.jpg,.jpeg,.webp,.tif,.tiff,.pptx,.docx,.xlsx,.html,.htm,.epub" required>
      <p>
        <label for="conversion_engine">Conversion engine</label>
        <select id="conversion_engine" name="conversion_engine">
          <option value="marker">Marker</option>
          <option value="docling">Docling</option>
          <option value="auto">Auto</option>
        </select>
      </p>
      <p>
        <label for="output_format">Output format</label>
        <select id="output_format" name="output_format">
          <option value="markdown">Markdown</option>
          <option value="json">JSON</option>
          <option value="html">HTML</option>
          <option value="chunks">Chunks</option>
        </select>
      </p>
      <p>
        <label for="format">Download format</label>
        <select id="format" name="format">
          <option value="zip">.zip</option>
          <option value="tar.gz">.tar.gz</option>
        </select>
      </p>
      <button id="convert" type="submit">Convert</button>
    </form>
  </section>

  <section>
    <label>Progress</label>
    <progress id="progress" value="0" max="100"></progress>
    <p id="stage" class="muted">Waiting for a document.</p>
    <p id="error" class="error"></p>
    <div id="downloads" class="downloads"></div>
  </section>

  <footer>
    Powered by <a href="https://github.com/VikParuchuri/marker">Marker</a> and optional IBM Docling. This private tool is intended only for the maintainer's personal, non-commercial document conversion use.
  </footer>
</main>
<script>
const tokenForm = document.getElementById("token-form");
const uploadForm = document.getElementById("upload-form");
const progress = document.getElementById("progress");
const stage = document.getElementById("stage");
const errorBox = document.getElementById("error");
const downloads = document.getElementById("downloads");
const format = document.getElementById("format");

tokenForm.addEventListener("submit", async (event) => {{
  event.preventDefault();
  const body = new FormData(tokenForm);
  const response = await fetch("/auth", {{ method: "POST", body }});
  stage.textContent = response.ok ? "Signed in." : "Sign-in failed.";
}});

uploadForm.addEventListener("submit", async (event) => {{
  event.preventDefault();
  errorBox.textContent = "";
  downloads.innerHTML = "";
  progress.value = 5;
  stage.textContent = "Uploading document.";
  const body = new FormData(uploadForm);
  const response = await fetch("/jobs", {{ method: "POST", body }});
  if (!response.ok) {{
    errorBox.textContent = await response.text();
    stage.textContent = "Upload failed.";
    return;
  }}
  const job = await response.json();
  poll(job.id);
}});

async function poll(jobId) {{
  const response = await fetch(`/jobs/${{jobId}}`);
  if (!response.ok) {{
    errorBox.textContent = await response.text();
    return;
  }}
  const job = await response.json();
  progress.value = job.progress;
  stage.textContent = job.stage;
  if (job.status === "failed") {{
    errorBox.textContent = job.error || "Conversion failed.";
    return;
  }}
  if (job.status === "complete") {{
    const selected = format.value;
    downloads.innerHTML = `
      <a href="/jobs/${{jobId}}/download?format=${{encodeURIComponent(selected)}}">Download ${{selected}}</a>
      <a href="/jobs/${{jobId}}/download?format=zip">.zip</a>
      <a href="/jobs/${{jobId}}/download?format=tar.gz">.tar.gz</a>
    `;
    return;
  }}
  setTimeout(() => poll(jobId), 1500);
}}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    dist_response = dist_index()
    if dist_response:
        return dist_response
    return HTMLResponse(html_page())


@app.post("/auth")
async def auth(token: Annotated[str, Form()]):
    expected = marker_web_token()
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="Invalid token")

    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=os.environ.get("MARKER_WEB_SECURE_COOKIE", "0") == "1",
    )
    return response


@app.post("/auth/logout")
async def logout():
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/auth/status")
async def auth_status(
    request: Request,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    return {
        "authenticated": is_authorized(request, marker_web_token_cookie, authorization),
        "token_required": bool(marker_web_token()),
        "loopback_only": not bool(marker_web_token()),
    }


@app.post("/jobs")
async def create_job(
    request: Request,
    file: Annotated[UploadFile, File()],
    output_format: Annotated[str, Form()] = "markdown",
    conversion_engine: Annotated[str, Form()] = "marker",
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported output format")
    if conversion_engine not in SUPPORTED_CONVERSION_ENGINES:
        raise HTTPException(status_code=400, detail="Unsupported conversion engine")
    if conversion_engine == "docling" and output_format not in DOCLING_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail="Docling supports markdown, json, and html output formats")
    if conversion_engine == "auto" and output_format not in AUTO_PIPELINE_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail="Auto pipeline supports markdown output only")

    content = await file.read()
    validate_upload_bytes(file.filename or "document.pdf", content)
    if conversion_engine == "auto" and Path(file.filename or "document.pdf").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Auto pipeline currently supports PDF input only")

    job_id = uuid.uuid4().hex
    original_filename = file.filename or "document.pdf"
    document_stem = f"{safe_stem(original_filename)}-{job_id[:8]}"
    user_display_stem = display_stem(original_filename)
    input_suffix = Path(original_filename).suffix.lower() or ".pdf"
    job_dir = JOB_ROOT / job_id
    input_dir = job_dir / "input"
    if job_dir.exists():
        shutil.rmtree(job_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"{document_stem}{input_suffix}"
    input_path.write_bytes(content)

    job = Job(
        id=job_id,
        original_filename=original_filename,
        document_stem=document_stem,
        display_stem=user_display_stem,
        output_format=output_format,  # type: ignore[arg-type]
        conversion_engine=conversion_engine,  # type: ignore[arg-type]
        status="queued",
        stage="Queued",
        progress=0,
        created_at=time.time(),
        updated_at=time.time(),
    )
    app_data["jobs"].add(job)
    submit_job(job)
    return job


@app.get("/jobs")
async def list_jobs(
    request: Request,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)
    return {"jobs": app_data["jobs"].list()}


@app.get("/jobs/{job_id}")
async def get_job(
    request: Request,
    job_id: str,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)
    return app_data["jobs"].get(job_id)


@app.post("/jobs/{job_id}/retry")
async def retry_job(
    request: Request,
    job_id: str,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)
    jobs: JobStore = app_data["jobs"]
    job = jobs.get(job_id)
    if job.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Job is already running")
    if not job_input_path(job).exists():
        raise HTTPException(status_code=409, detail="Job input file is missing")

    logger.info("Retrying private web job %s", job.id)
    job = jobs.update(
        job.id,
        status="queued",
        stage="Queued",
        progress=0,
        output_dir=None,
        zip_path=None,
        targz_path=None,
        error=None,
    )
    submit_job(job)
    return job


@app.delete("/jobs/{job_id}")
async def delete_job(
    request: Request,
    job_id: str,
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)
    job = app_data["jobs"].get(job_id)
    if job.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Running jobs cannot be deleted")
    app_data["jobs"].delete(job_id)
    return {"deleted": True}


@app.get("/jobs/{job_id}/download")
async def download_job(
    request: Request,
    job_id: str,
    format: str = "zip",
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)
    if format not in ALLOWED_ARCHIVE_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported archive format")

    job = app_data["jobs"].get(job_id)
    if job.status != "complete":
        raise HTTPException(status_code=409, detail="Job is not complete")

    archive_path = Path(job.zip_path if format == "zip" else job.targz_path)
    media_type = "application/zip" if format == "zip" else "application/gzip"
    download_filename = f"{job.display_stem}.{format}"
    return FileResponse(
        archive_path,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition(download_filename)},
    )


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "private_mode": bool(marker_web_token())})


@app.get("/api/info")
async def api_info():
    return {
        "service": "Private Marker Web",
        "authentication": {
            "cookie": SESSION_COOKIE,
            "bearer_token": bool(marker_web_token()),
            "loopback_only_when_token_missing": True,
        },
        "supported_input_extensions": sorted(SUPPORTED_INPUT_EXTENSIONS),
        "supported_output_formats": sorted(SUPPORTED_OUTPUT_FORMATS),
        "supported_conversion_engines": sorted(SUPPORTED_CONVERSION_ENGINES),
        "docling_output_formats": sorted(DOCLING_OUTPUT_FORMATS),
        "auto_pipeline_output_formats": sorted(AUTO_PIPELINE_OUTPUT_FORMATS),
        "supported_archive_formats": sorted(ALLOWED_ARCHIVE_FORMATS),
        "endpoints": {
            "auth_status": "GET /auth/status",
            "auth": "POST /auth",
            "logout": "POST /auth/logout",
            "create_job": "POST /jobs",
            "list_jobs": "GET /jobs",
            "get_job": "GET /jobs/{job_id}",
            "retry_job": "POST /jobs/{job_id}/retry",
            "download_job": "GET /jobs/{job_id}/download?format=zip",
            "delete_job": "DELETE /jobs/{job_id}",
            "openapi": "GET /openapi.json",
        },
    }


@click.command()
@click.option("--port", type=int, default=8765, help="Port to run the private web app on")
@click.option("--host", type=str, default="127.0.0.1", help="Host to run the private web app on")
def private_web_cli(port: int, host: str):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
