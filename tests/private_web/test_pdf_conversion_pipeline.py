from marker.pipelines.pdf_conversion import DocumentConversionPipeline


def test_quality_gate_accepts_clean_markdown():
    pipeline = DocumentConversionPipeline(min_markdown_chars=20)
    markdown = """
# Title

This is a clean document with normal text.

| A | B |
|---|---|
| 1 | 2 |
"""

    assert pipeline._evaluate_quality(markdown) is True
    assert pipeline._last_quality_report is not None
    assert pipeline._last_quality_report.passed is True


def test_quality_gate_rejects_malformed_tables():
    pipeline = DocumentConversionPipeline(min_markdown_chars=20)
    markdown = """
# Title

This document has a malformed table.

| A | B | C |
|---|---|
| 1 | 2 | 3 |
| 4 | 5 |
"""

    assert pipeline._evaluate_quality(markdown) is False
    assert "malformed_tables" in pipeline._last_quality_report.reasons


def test_quality_gate_rejects_garbled_formula_output():
    pipeline = DocumentConversionPipeline(min_markdown_chars=20)
    markdown = """
# Dense Paper

The result is $ \\frac{x}{y and □□□□ � � � with <unk> <unk> <unk> <unk>.
""" * 8

    assert pipeline._evaluate_quality(markdown) is False
    assert pipeline._last_quality_report.reasons
