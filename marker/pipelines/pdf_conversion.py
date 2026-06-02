import asyncio
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "structured", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


logger = logging.getLogger("PDFPipeline")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    markdown_length: int
    table_count: int
    malformed_table_count: int
    garbled_character_count: int
    garbled_character_ratio: float
    formula_issue_count: int
    artifact_count: int
    reasons: Tuple[str, ...]


class DocumentConversionPipeline:
    def __init__(
        self,
        marker_config: Optional[Dict[str, Any]] = None,
        min_markdown_chars: int = 200,
        max_garbled_ratio: float = 0.015,
        max_malformed_table_ratio: float = 0.2,
        max_formula_issue_density: float = 0.01,
        use_docling_gpu: Optional[bool] = None,
    ):
        self.marker_config = marker_config or {}
        self.min_markdown_chars = min_markdown_chars
        self.max_garbled_ratio = max_garbled_ratio
        self.max_malformed_table_ratio = max_malformed_table_ratio
        self.max_formula_issue_density = max_formula_issue_density
        self.use_docling_gpu = use_docling_gpu
        self._docling_converter = None
        self._marker_models = None
        self._last_quality_report: QualityGateResult | None = None

        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    def _get_docling_converter(self):
        if self._docling_converter is not None:
            return self._docling_converter

        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise RuntimeError(
                "Docling is not installed. Install this project with the docling extra, "
                "for example: pip install 'marker-pdf[docling]'."
            ) from exc

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        if hasattr(pipeline_options, "table_structure_options"):
            pipeline_options.table_structure_options.do_cell_matching = True

        ocr_options = EasyOcrOptions()
        if hasattr(ocr_options, "use_ocr"):
            ocr_options.use_ocr = True
        if self.use_docling_gpu is not None and hasattr(ocr_options, "use_gpu"):
            ocr_options.use_gpu = self.use_docling_gpu
        pipeline_options.ocr_options = ocr_options

        self._docling_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        return self._docling_converter

    def _run_docling(self, pdf_path: str) -> str:
        """
        Executes the primary conversion using IBM Docling with OCR enabled.
        """
        start = time.perf_counter()
        try:
            document = self.convert_with_docling(pdf_path)
            markdown = document.export_to_markdown()
            logger.info(
                "Docling conversion completed",
                extra={
                    "structured": {
                        "track": "docling",
                        "pdf_path": pdf_path,
                        "duration_seconds": round(time.perf_counter() - start, 4),
                        "markdown_length": len(markdown),
                    }
                },
            )
            return markdown
        except Exception:
            logger.exception(
                "Docling conversion failed",
                extra={
                    "structured": {
                        "track": "docling",
                        "pdf_path": pdf_path,
                        "duration_seconds": round(time.perf_counter() - start, 4),
                    }
                },
            )
            raise

    def convert_with_docling(self, pdf_path: str):
        return self._get_docling_converter().convert(pdf_path).document

    def _evaluate_quality(self, markdown_content: str) -> bool:
        """
        Evaluates the generated markdown quality based on layout, table integrity, and structural heuristics.
        Returns True if quality is acceptable (PASS), False if fallback is required (FAIL).
        """
        result = self._evaluate_quality_details(markdown_content)
        self._last_quality_report = result
        logger.info(
            "Quality gate evaluated Docling output",
            extra={"structured": {"track": "quality_gate", "quality": asdict(result)}},
        )
        return result.passed

    def _evaluate_quality_details(self, markdown_content: str) -> QualityGateResult:
        markdown_length = len(markdown_content.strip())
        table_count, malformed_table_count = self._count_table_issues(markdown_content)
        garbled_character_count = self._count_garbled_characters(markdown_content)
        garbled_character_ratio = garbled_character_count / max(markdown_length, 1)
        formula_issue_count = self._count_formula_issues(markdown_content)
        artifact_count = self._count_structural_artifacts(markdown_content)

        reasons: list[str] = []
        if markdown_length < self.min_markdown_chars:
            reasons.append("markdown_too_short")

        if table_count and malformed_table_count / table_count > self.max_malformed_table_ratio:
            reasons.append("malformed_tables")

        if garbled_character_ratio > self.max_garbled_ratio:
            reasons.append("garbled_text")

        formula_issue_density = formula_issue_count / max(markdown_content.count("\n") + 1, 1)
        if formula_issue_density > self.max_formula_issue_density:
            reasons.append("formula_corruption")

        if artifact_count >= 8 and artifact_count / max(markdown_content.count("\n") + 1, 1) > 0.03:
            reasons.append("structural_artifacts")

        return QualityGateResult(
            passed=not reasons,
            markdown_length=markdown_length,
            table_count=table_count,
            malformed_table_count=malformed_table_count,
            garbled_character_count=garbled_character_count,
            garbled_character_ratio=round(garbled_character_ratio, 6),
            formula_issue_count=formula_issue_count,
            artifact_count=artifact_count,
            reasons=tuple(reasons),
        )

    def _count_table_issues(self, markdown_content: str) -> tuple[int, int]:
        table_count = 0
        malformed_count = 0
        current_table: list[str] = []

        for line in markdown_content.splitlines() + [""]:
            stripped = line.strip()
            if "|" in stripped and stripped.count("|") >= 2:
                current_table.append(stripped)
                continue

            if current_table:
                table_count += 1
                if self._table_is_malformed(current_table):
                    malformed_count += 1
                current_table = []

        return table_count, malformed_count

    def _table_is_malformed(self, rows: list[str]) -> bool:
        column_counts = [self._markdown_table_column_count(row) for row in rows]
        data_counts = [count for count in column_counts if count > 1]
        if len(data_counts) < 2:
            return True

        dominant_count = max(set(data_counts), key=data_counts.count)
        mismatches = sum(1 for count in data_counts if count != dominant_count)
        if mismatches / len(data_counts) > 0.25:
            return True

        separator_rows = [row for row in rows if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", row)]
        return bool(separator_rows) and any(
            self._markdown_table_column_count(row) != dominant_count for row in separator_rows
        )

    def _markdown_table_column_count(self, row: str) -> int:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return len(re.split(r"(?<!\\)\|", row))

    def _count_garbled_characters(self, markdown_content: str) -> int:
        garbled_pattern = re.compile(r"[\uFFFD\u25A1\u25A0\u25AF\u25CC\uFEFF�□■�]")
        control_count = sum(
            1
            for char in markdown_content
            if (ord(char) < 32 and char not in "\n\r\t") or 0xE000 <= ord(char) <= 0xF8FF
        )
        return len(garbled_pattern.findall(markdown_content)) + control_count

    def _count_formula_issues(self, markdown_content: str) -> int:
        issue_count = 0
        if markdown_content.count("$") % 2:
            issue_count += 1
        for opener, closer in ((r"\[", r"\]"), (r"\(", r"\)")):
            if markdown_content.count(opener) != markdown_content.count(closer):
                issue_count += 1

        formula_like_lines = [
            line for line in markdown_content.splitlines()
            if "$" in line or "\\" in line or re.search(r"[∑∫√≈≤≥]", line)
        ]
        for line in formula_like_lines:
            if line.count("{") != line.count("}"):
                issue_count += 1
            if re.search(r"\\[A-Za-z]{12,}", line):
                issue_count += 1
            if re.search(r"([_^])\s{2,}", line):
                issue_count += 1
        return issue_count

    def _count_structural_artifacts(self, markdown_content: str) -> int:
        patterns = (
            r"<loc_\d+>",
            r"<unk>",
            r"\[MISSING_[A-Z_]+\]",
            r"(?:\s\|\s){8,}",
            r"[-_=]{20,}",
        )
        return sum(len(re.findall(pattern, markdown_content, flags=re.IGNORECASE)) for pattern in patterns)

    def _run_marker_fallback(self, pdf_path: str) -> str:
        """
        Executes the heavy fallback conversion using Marker.
        """
        start = time.perf_counter()
        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered

        if self._marker_models is None:
            self._marker_models = create_model_dict()

        marker_config = {
            "output_format": "markdown",
            "disable_multiprocessing": True,
            **self.marker_config,
        }
        config_parser = ConfigParser(marker_config)
        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=self._marker_models,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service(),
        )
        rendered = converter(pdf_path)
        markdown, _, _ = text_from_rendered(rendered)
        logger.info(
            "Marker fallback conversion completed",
            extra={
                "structured": {
                    "track": "marker",
                    "pdf_path": pdf_path,
                    "duration_seconds": round(time.perf_counter() - start, 4),
                    "markdown_length": len(markdown),
                    "gpu_acceleration_requested": True,
                }
            },
        )
        return markdown

    def process_pdf(self, pdf_path: str) -> Tuple[str, Dict[str, Any]]:
        """
        Main entry point for processing a PDF file through the multi-stage pipeline.
        Returns the final markdown content and execution metadata.
        """
        start = time.perf_counter()
        metadata: Dict[str, Any] = {
            "source_path": str(Path(pdf_path)),
            "pipeline": "docling_quality_gate_marker_fallback",
            "track": None,
            "docling_error": None,
            "quality_gate": None,
            "duration_seconds": None,
        }

        try:
            docling_markdown = self._run_docling(pdf_path)
            if self._evaluate_quality(docling_markdown):
                metadata["track"] = "docling"
                metadata["quality_gate"] = asdict(self._last_quality_report)
                metadata["duration_seconds"] = round(time.perf_counter() - start, 4)
                logger.info("Pipeline completed on fast track", extra={"structured": metadata})
                return docling_markdown, metadata
            metadata["quality_gate"] = asdict(self._last_quality_report)
        except Exception as exc:
            metadata["docling_error"] = str(exc)

        marker_markdown = self._run_marker_fallback(pdf_path)
        metadata["track"] = "marker"
        metadata["duration_seconds"] = round(time.perf_counter() - start, 4)
        logger.info("Pipeline completed on fallback track", extra={"structured": metadata})
        return marker_markdown, metadata

    async def process_pdf_async(self, pdf_path: str) -> Tuple[str, Dict[str, Any]]:
        return await asyncio.to_thread(self.process_pdf, pdf_path)
