import json
import os
import re
import shutil
import tarfile
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal, Optional

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
from marker.models import create_model_dict
from marker.output import convert_if_not_rgb, text_from_rendered
from marker.settings import settings


JOB_ROOT = Path(os.environ.get("MARKER_WEB_JOB_DIR", "private_marker_jobs"))
FRONTEND_DIST = Path(os.environ.get("MARKER_WEB_FRONTEND_DIST", "frontend/dist"))
MAX_UPLOAD_BYTES = int(os.environ.get("MARKER_WEB_MAX_UPLOAD_MB", "100")) * 1024 * 1024
SESSION_COOKIE = "marker_web_token"
ALLOWED_ARCHIVE_FORMATS = {"zip", "tar.gz"}
executor = ThreadPoolExecutor(max_workers=int(os.environ.get("MARKER_WEB_WORKERS", "1")))


class Job(BaseModel):
    id: str
    original_filename: str
    document_stem: str
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
            for job_path in JOB_ROOT.glob("*/job.json"):
                try:
                    job = Job.model_validate_json(job_path.read_text(encoding=settings.OUTPUT_ENCODING))
                    if job.status in {"queued", "running"}:
                        job = job.model_copy(
                            update={
                                "status": "failed",
                                "stage": "Interrupted",
                                "error": "The server stopped before this conversion finished.",
                                "updated_at": time.time(),
                            }
                        )
                        self._persist(job)
                    self._jobs[job.id] = job
                except Exception:
                    continue

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
    app_data["jobs"].load()
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


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return stem or "document"


def validate_pdf_bytes(content: bytes):
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds configured upload limit")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a readable PDF")


def rewrite_image_references(markdown: str, image_names: list[str]) -> str:
    for image_name in image_names:
        markdown = markdown.replace(f"]({image_name})", f"](images/{image_name})")
        markdown = markdown.replace(f'src="{image_name}"', f'src="images/{image_name}"')
        markdown = markdown.replace(f"src='{image_name}'", f"src='images/{image_name}'")
    return markdown


def save_private_output(rendered, output_dir: Path, document_stem: str) -> Path:
    text, ext, images = text_from_rendered(rendered)
    if ext != "md":
        raise ValueError("Private web converter currently expects markdown output")

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    image_names = list(images.keys())
    text = rewrite_image_references(text, image_names)
    text = text.encode(settings.OUTPUT_ENCODING, errors="replace").decode(settings.OUTPUT_ENCODING)

    markdown_path = output_dir / f"{document_stem}.md"
    markdown_path.write_text(text, encoding=settings.OUTPUT_ENCODING)

    metadata = {
        "marker_metadata": rendered.metadata,
        "generated_at": time.time(),
        "output_format": "markdown",
        "image_directory": "images",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding=settings.OUTPUT_ENCODING
    )

    for image_name, image in images.items():
        image = convert_if_not_rgb(image)
        image.save(images_dir / image_name, settings.OUTPUT_IMAGE_FORMAT)

    return markdown_path


def make_archives(output_dir: Path, archive_dir: Path, document_stem: str) -> tuple[Path, Path]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / f"{document_stem}.zip"
    targz_path = archive_dir / f"{document_stem}.tar.gz"
    package_root = document_stem

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in output_dir.rglob("*"):
            if path.is_file():
                zf.write(path, Path(package_root) / path.relative_to(output_dir))

    with tarfile.open(targz_path, "w:gz") as tf:
        for path in output_dir.rglob("*"):
            if path.is_file():
                tf.add(path, arcname=Path(package_root) / path.relative_to(output_dir))

    return zip_path, targz_path


def run_conversion(job_id: str, input_path: Path, document_stem: str):
    jobs: JobStore = app_data["jobs"]
    job_dir = JOB_ROOT / job_id
    output_dir = job_dir / "output"
    archive_dir = job_dir / "archives"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        jobs.update(job_id, status="running", stage="Loading models", progress=10)
        models = create_model_dict()

        jobs.update(job_id, stage="Converting PDF to Markdown", progress=20)
        config_parser = ConfigParser({"output_format": "markdown", "disable_multiprocessing": True})
        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=models,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )
        rendered = converter(str(input_path))

        jobs.update(job_id, stage="Normalizing output", progress=85)
        save_private_output(rendered, output_dir, document_stem)

        jobs.update(job_id, stage="Packaging archives", progress=92)
        zip_path, targz_path = make_archives(output_dir, archive_dir, document_stem)

        jobs.update(
            job_id,
            status="complete",
            stage="Complete",
            progress=100,
            output_dir=str(output_dir),
            zip_path=str(zip_path),
            targz_path=str(targz_path),
        )
    except Exception as exc:
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
    <h1>Private PDF to Markdown Converter</h1>
    <p class="muted">Personal, non-commercial conversion service. {auth_note}</p>
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
      <label for="pdf">PDF file</label>
      <input id="pdf" name="file" type="file" accept="application/pdf,.pdf" required>
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
    <p id="stage" class="muted">Waiting for a PDF.</p>
    <p id="error" class="error"></p>
    <div id="downloads" class="downloads"></div>
  </section>

  <footer>
    Powered by <a href="https://github.com/VikParuchuri/marker">Marker</a>. This private tool is intended only for the maintainer's personal, non-commercial document conversion use.
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
  stage.textContent = "Uploading PDF.";
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
    marker_web_token_cookie: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE)] = None,
    authorization: Annotated[Optional[str], Header()] = None,
):
    require_auth(request, marker_web_token_cookie, authorization)

    content = await file.read()
    validate_pdf_bytes(content)

    job_id = uuid.uuid4().hex
    document_stem = safe_stem(file.filename or "document.pdf")
    job_dir = JOB_ROOT / job_id
    input_dir = job_dir / "input"
    if job_dir.exists():
        shutil.rmtree(job_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"{document_stem}.pdf"
    input_path.write_bytes(content)

    job = Job(
        id=job_id,
        original_filename=file.filename or "document.pdf",
        document_stem=document_stem,
        status="queued",
        stage="Queued",
        progress=0,
        created_at=time.time(),
        updated_at=time.time(),
    )
    app_data["jobs"].add(job)
    executor.submit(run_conversion, job_id, input_path, document_stem)
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
    return FileResponse(
        archive_path,
        media_type=media_type,
        filename=archive_path.name,
    )


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "private_mode": bool(marker_web_token())})


@click.command()
@click.option("--port", type=int, default=8765, help="Port to run the private web app on")
@click.option("--host", type=str, default="127.0.0.1", help="Host to run the private web app on")
def private_web_cli(port: int, host: str):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
