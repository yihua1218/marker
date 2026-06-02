import json
import zipfile
from pathlib import Path

import pytest

from marker.scripts import private_web
from marker.scripts.private_web import (
    Job,
    JobStore,
    content_disposition,
    display_stem,
    make_archives,
    safe_stem,
    save_auto_pipeline_output,
    save_docling_output,
    validate_upload_bytes,
)


def test_traditional_chinese_filename_helpers():
    assert display_stem("測試文件.pdf") == "測試文件"
    assert safe_stem("測試文件.pdf") == "document"

    header = content_disposition("測試文件.zip")
    assert 'filename="document.zip"' in header
    assert "filename*=UTF-8''" in header
    assert "%E6%B8%AC%E8%A9%A6%E6%96%87%E4%BB%B6.zip" in header


def test_windows_reserved_and_invalid_filename_handling():
    assert display_stem("CON.pdf") == "document"
    assert display_stem("報告<>:|?*.pdf") == "報告"
    assert safe_stem("CON.pdf") == "document"


def test_validate_upload_supports_declared_formats():
    validate_upload_bytes("sample.pdf", b"%PDF-1.4\n")
    validate_upload_bytes("sample.docx", b"PK\x03\x04")
    validate_upload_bytes("sample.html", b"<html></html>")

    with pytest.raises(Exception) as exc_info:
        validate_upload_bytes("sample.exe", b"MZ")
    assert getattr(exc_info.value, "status_code", None) == 400

    with pytest.raises(Exception) as exc_info:
        validate_upload_bytes("sample.pdf", b"not a pdf")
    assert getattr(exc_info.value, "status_code", None) == 400


def test_make_archives_preserves_unicode_package_root(tmp_path: Path):
    output_dir = tmp_path / "output"
    (output_dir / "images").mkdir(parents=True)
    (output_dir / "測試文件.md").write_text("ok", encoding="utf-8")
    (output_dir / "images" / "圖一.jpeg").write_bytes(b"x")

    zip_path, targz_path = make_archives(
        output_dir,
        tmp_path / "archives",
        "document-abcd1234",
        "測試文件",
    )

    assert zip_path.name == "document-abcd1234.zip"
    assert targz_path.name == "document-abcd1234.tar.gz"
    assert zipfile.ZipFile(zip_path).namelist() == [
        "測試文件/測試文件.md",
        "測試文件/images/圖一.jpeg",
    ]


def test_job_store_persists_and_migrates_output_format(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(private_web, "JOB_ROOT", tmp_path)
    store = JobStore()
    job = Job(
        id="abc",
        original_filename="測試文件.pdf",
        document_stem="document-abc",
        display_stem="測試文件",
        output_format="markdown",
        conversion_engine="marker",
        status="complete",
        stage="Complete",
        progress=100,
        created_at=1,
        updated_at=1,
    )
    store.add(job)

    loaded = JobStore()
    loaded.load()
    assert loaded.get("abc").display_stem == "測試文件"
    assert loaded.get("abc").output_format == "markdown"
    assert loaded.get("abc").conversion_engine == "marker"

    old_dir = tmp_path / "old"
    old_dir.mkdir()
    old_payload = {
        "id": "old",
        "original_filename": "old.pdf",
        "document_stem": "old",
        "status": "complete",
        "stage": "Complete",
        "progress": 100,
        "created_at": 1,
        "updated_at": 1,
    }
    (old_dir / "job.json").write_text(json.dumps(old_payload), encoding="utf-8")

    migrated = JobStore()
    migrated.load()
    assert migrated.get("old").output_format == "markdown"
    assert migrated.get("old").conversion_engine == "marker"
    assert migrated.get("old").display_stem == "old"


def test_job_store_requeues_in_progress_jobs_on_load(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(private_web, "JOB_ROOT", tmp_path)
    running_dir = tmp_path / "running"
    running_dir.mkdir()
    running_payload = {
        "id": "running",
        "original_filename": "report.pdf",
        "document_stem": "report-running",
        "display_stem": "report",
        "output_format": "markdown",
        "conversion_engine": "marker",
        "status": "running",
        "stage": "Converting to markdown",
        "progress": 20,
        "created_at": 1,
        "updated_at": 1,
    }
    (running_dir / "job.json").write_text(json.dumps(running_payload), encoding="utf-8")

    loaded = JobStore()
    loaded.load()

    job = loaded.get("running")
    assert job.status == "queued"
    assert job.stage == "Queued for resume"
    assert job.progress == 10
    assert job.error is None


def test_save_docling_output_uses_docling_converter(tmp_path: Path, monkeypatch):
    class FakeDocument:
        def export_to_markdown(self):
            return "# Docling"

        def export_to_html(self):
            return "<h1>Docling</h1>"

        def save_as_json(self, filename: str, indent: int = 2):
            Path(filename).write_text(json.dumps({"name": "Docling"}, indent=indent), encoding="utf-8")

    class FakePipeline:
        def convert_with_docling(self, source: str):
            assert source.endswith("input.pdf")
            return FakeDocument()

    monkeypatch.setattr(private_web, "DocumentConversionPipeline", FakePipeline)

    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")

    output_path = save_docling_output(input_path, tmp_path / "output", "result", "markdown")

    assert output_path.name == "result.md"
    assert output_path.read_text(encoding="utf-8") == "# Docling"
    metadata = json.loads((tmp_path / "output" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["conversion_engine"] == "docling"


def test_save_docling_output_reports_missing_dependency(tmp_path: Path, monkeypatch):
    class FakePipeline:
        def convert_with_docling(self, source: str):
            raise RuntimeError("Docling is not installed")

    monkeypatch.setattr(private_web, "DocumentConversionPipeline", FakePipeline)

    with pytest.raises(RuntimeError) as exc_info:
        save_docling_output(tmp_path / "input.pdf", tmp_path / "output", "result", "markdown")

    assert "Docling is not installed" in str(exc_info.value)


def test_save_auto_pipeline_output_writes_metadata(tmp_path: Path, monkeypatch):
    class FakePipeline:
        def process_pdf(self, pdf_path: str):
            assert pdf_path.endswith("input.pdf")
            return "# Auto", {"track": "docling", "quality_gate": {"passed": True}}

    monkeypatch.setattr(private_web, "DocumentConversionPipeline", FakePipeline)
    input_path = tmp_path / "input.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")

    output_path = save_auto_pipeline_output(input_path, tmp_path / "output", "result")

    assert output_path.name == "result.md"
    assert output_path.read_text(encoding="utf-8") == "# Auto"
    metadata = json.loads((tmp_path / "output" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["conversion_engine"] == "auto"
    assert metadata["pipeline_metadata"]["track"] == "docling"
