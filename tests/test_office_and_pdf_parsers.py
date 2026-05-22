"""Unit tests for PDF, Word (.docx/.doc), Excel (.xlsx/.xls/.csv/.tsv), and PowerPoint (.pptx/.ppt) parsers."""

import io
from pathlib import Path

import docx
import openpyxl
import pptx
import pypdf
import pytest
from pypdf import PdfWriter
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.parsers import (
    DocumentParserFactory,
    ExcelDocumentParser,
    PDFDocumentParser,
    PowerPointDocumentParser,
    WordDocumentParser,
)
from app.ingestion.pipeline import IngestionPipeline


def _build_minimal_pdf_bytes(title: str = "Test PDF Document", body: str = "This is PDF content.") -> bytes:
    """Create a minimal valid PDF with bookmarks and extractable text stream."""
    writer = PdfWriter()
    page1 = writer.add_blank_page(width=300, height=300)
    stream_content = f"BT /F1 12 Tf 50 250 Td ({title}) Tj 0 -20 Td ({body}) Tj ET".encode("latin1")
    stream_obj = pypdf.generic.DecodedStreamObject()
    stream_obj.set_data(stream_content)
    page1_stream_obj = writer._add_object(stream_obj)

    font_dict = pypdf.generic.DictionaryObject({
        pypdf.generic.NameObject("/Type"): pypdf.generic.NameObject("/Font"),
        pypdf.generic.NameObject("/Subtype"): pypdf.generic.NameObject("/Type1"),
        pypdf.generic.NameObject("/BaseFont"): pypdf.generic.NameObject("/Helvetica"),
    })
    font_obj = writer._add_object(font_dict)

    page1[pypdf.generic.NameObject("/Contents")] = page1_stream_obj
    page1[pypdf.generic.NameObject("/Resources")] = pypdf.generic.DictionaryObject({
        pypdf.generic.NameObject("/Font"): pypdf.generic.DictionaryObject({
            pypdf.generic.NameObject("/F1"): font_obj
        })
    })
    writer.add_outline_item("Chapter 1: Intro", 0)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_minimal_docx_bytes(title: str = "Architecture Guide") -> bytes:
    """Create an in-memory .docx file with title, headings, paragraphs, and a table."""
    doc = docx.Document()
    doc.core_properties.title = title
    doc.add_heading("Section 1: Overview", level=1)
    doc.add_paragraph("DocsQA uses a multi-stage retrieval architecture.")

    doc.add_heading("Section 2: Components", level=2)
    doc.add_paragraph("The components are listed in the table below:")
    tbl = doc.add_table(rows=3, cols=2)
    tbl.cell(0, 0).text = "Component"
    tbl.cell(0, 1).text = "Role"
    tbl.cell(1, 0).text = "Vector DB"
    tbl.cell(1, 1).text = "pgvector index"
    tbl.cell(2, 0).text = "Reranker"
    tbl.cell(2, 1).text = "Cross-encoder scoring"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_minimal_xlsx_bytes(title: str = "Financial Forecast") -> bytes:
    """Create an in-memory .xlsx file with multiple sheets and rows."""
    wb = openpyxl.Workbook()
    wb.properties.title = title
    ws1 = wb.active
    ws1.title = "Q3 Projections"
    ws1.append(["Metric", "Budget", "Actual"])
    ws1.append(["Compute", "$10,000", "$9,200"])
    ws1.append(["Storage", "$2,500", "$2,100"])

    ws2 = wb.create_sheet(title="Headcount")
    ws2.append(["Team", "Engineers"])
    ws2.append(["AI Platform", "8"])
    ws2.append(["Core Backend", "12"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_minimal_pptx_bytes(title: str = "System Overview") -> bytes:
    """Create an in-memory .pptx presentation with slides, tables, and notes."""
    prs = pptx.Presentation()
    prs.core_properties.title = title

    # Slide 1: Title slide
    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "DocsQA System Overview"
    slide1.placeholders[1].text = "Presenter: Amir Mohammad\nPlatform Engineering"

    # Slide 2: Bullet points and table
    slide2 = prs.slides.add_slide(prs.slide_layouts[5])  # Title only
    slide2.shapes.title.text = "Retrieval Pipeline"

    # Add text box with bullets
    tx_box = slide2.shapes.add_textbox(pptx.util.Inches(1), pptx.util.Inches(1.5), pptx.util.Inches(4), pptx.util.Inches(2))
    tf = tx_box.text_frame
    p1 = tf.paragraphs[0]
    p1.text = "Dense vector search with HNSW"
    p2 = tf.add_paragraph()
    p2.text = "Sparse full-text search with tsvector"
    p2.level = 1

    # Add table
    tbl_shape = slide2.shapes.add_table(2, 2, pptx.util.Inches(1), pptx.util.Inches(4), pptx.util.Inches(4), pptx.util.Inches(1.5))
    tbl_shape.table.cell(0, 0).text = "Strategy"
    tbl_shape.table.cell(0, 1).text = "Latency"
    tbl_shape.table.cell(1, 0).text = "Vector"
    tbl_shape.table.cell(1, 1).text = "12ms"

    # Add speaker notes
    slide2.notes_slide.notes_text_frame.text = "Ensure connection pooling is configured before testing."

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pdf_document_parser():
    """Verify PDFDocumentParser extracts title, outlines, page text, and anchors."""
    pdf_bytes = _build_minimal_pdf_bytes(title="My PDF Document", body="This is a test paragraph inside PDF.")
    parser = PDFDocumentParser()
    title, chunks = parser.parse(pdf_bytes, fallback_title="Fallback Title")

    assert title == "Fallback Title"
    assert len(chunks) >= 1
    assert "Page 1" in chunks[0].heading
    assert "[Page 1]" in chunks[0].content
    assert "test paragraph inside PDF" in chunks[0].content
    assert chunks[0].content_hash != ""


def test_docx_document_parser():
    """Verify WordDocumentParser extracts headings, paragraphs, and markdown tables."""
    docx_bytes = _build_minimal_docx_bytes("DocsQA Engineering Guide")
    parser = WordDocumentParser()
    title, chunks = parser.parse(docx_bytes, fallback_title="Untitled")

    assert title == "DocsQA Engineering Guide"
    assert len(chunks) >= 1

    all_content = "\n\n".join(c.content for c in chunks)
    assert "Section 1: Overview" in all_content
    assert "multi-stage retrieval architecture" in all_content
    assert "| Component | Role |" in all_content
    assert "| Vector DB | pgvector index |" in all_content


def test_xlsx_document_parser():
    """Verify ExcelDocumentParser extracts worksheets and formats markdown tables."""
    xlsx_bytes = _build_minimal_xlsx_bytes("Q3 Operational Budget")
    parser = ExcelDocumentParser()
    title, chunks = parser.parse(xlsx_bytes, fallback_title="Spreadsheet")

    assert title == "Q3 Operational Budget"
    assert len(chunks) >= 2  # Two sheets

    all_content = "\n\n".join(c.content for c in chunks)
    assert "Q3 Projections" in all_content
    assert "| Metric | Budget | Actual |" in all_content
    assert "| Compute | $10,000 | $9,200 |" in all_content
    assert "Headcount" in all_content
    assert "| Team | Engineers |" in all_content


def test_pptx_document_parser():
    """Verify PowerPointDocumentParser extracts slide titles, bullets, tables, and notes."""
    pptx_bytes = _build_minimal_pptx_bytes("Architecture Deck")
    parser = PowerPointDocumentParser()
    title, chunks = parser.parse(pptx_bytes, fallback_title="Deck")

    assert title == "Architecture Deck"
    assert len(chunks) == 2  # 2 slides

    slide1_chunk = chunks[0]
    assert "DocsQA System Overview" in slide1_chunk.heading or "Slide 1" in slide1_chunk.heading
    assert "Amir Mohammad" in slide1_chunk.content

    slide2_chunk = chunks[1]
    assert "Retrieval Pipeline" in slide2_chunk.heading
    assert "Dense vector search" in slide2_chunk.content
    assert "| Strategy | Latency |" in slide2_chunk.content
    assert "Ensure connection pooling is configured" in slide2_chunk.content


def test_csv_and_tsv_parser():
    """Verify ExcelDocumentParser correctly handles delimited text files."""
    csv_data = "Name,Department,Location\nAlice,Engineering,Remote\nBob,Design,HQ\n"
    parser = ExcelDocumentParser()
    title_csv, chunks_csv = parser.parse(csv_data, fallback_title="Employee Directory", suffix=".csv")

    assert title_csv == "Employee Directory"
    assert len(chunks_csv) == 1
    assert "| Name | Department | Location |" in chunks_csv[0].content
    assert "| Alice | Engineering | Remote |" in chunks_csv[0].content

    tsv_data = "Item\tPrice\tQty\nLaptop\t1200\t5\nMonitor\t300\t10\n"
    title_tsv, chunks_tsv = parser.parse(tsv_data, fallback_title="Inventory", suffix=".tsv")
    assert title_tsv == "Inventory"
    assert len(chunks_tsv) == 1
    assert "| Item | Price | Qty |" in chunks_tsv[0].content
    assert "| Laptop | 1200 | 5 |" in chunks_tsv[0].content


def test_legacy_doc_and_ppt_fallback():
    """Verify fallback string extraction for legacy binary .doc and .ppt streams."""
    legacy_doc_data = (
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        + "Legacy Word Manual".encode("utf-16le")
        + b"\x00\x00"
        + b"This is content inside a binary doc."
    )
    word_parser = WordDocumentParser()
    title, chunks = word_parser.parse(legacy_doc_data, fallback_title="Legacy Doc", is_legacy_doc=True)

    assert title != ""
    assert len(chunks) >= 1
    assert any("Legacy Word Manual" in c.content or "binary doc" in c.content for c in chunks)


def test_document_parser_factory_routing():
    """Verify DocumentParserFactory routes each file extension to the right parser."""
    docx_bytes = _build_minimal_docx_bytes("Factory Docx")
    title_docx, chunks_docx = DocumentParserFactory.parse_file(Path("manual.docx"), docx_bytes)
    assert title_docx == "Factory Docx"
    assert "Section 1: Overview" in chunks_docx[0].content

    xlsx_bytes = _build_minimal_xlsx_bytes("Factory Xlsx")
    title_xlsx, chunks_xlsx = DocumentParserFactory.parse_file(Path("metrics.xlsx"), xlsx_bytes)
    assert title_xlsx == "Factory Xlsx"
    assert "| Metric | Budget | Actual |" in chunks_xlsx[0].content

    pptx_bytes = _build_minimal_pptx_bytes("Factory Pptx")
    title_pptx, chunks_pptx = DocumentParserFactory.parse_file(Path("slides.pptx"), pptx_bytes)
    assert title_pptx == "Factory Pptx"
    assert len(chunks_pptx) == 2

    pdf_bytes = _build_minimal_pdf_bytes("Factory PDF", "Factory PDF body")
    title_pdf, chunks_pdf = DocumentParserFactory.parse_file(Path("whitepaper.pdf"), pdf_bytes)
    assert title_pdf != ""
    assert "Factory PDF body" in chunks_pdf[0].content


@pytest.mark.asyncio
async def test_pipeline_ingests_all_office_and_pdf_formats(db_session: AsyncSession, tmp_path):
    """End-to-end test verifying IngestionPipeline indexes Word, Excel, PPT, and PDF files."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    # Write each format into docs directory
    (docs_dir / "guide.docx").write_bytes(_build_minimal_docx_bytes("Word Guide"))
    (docs_dir / "budget.xlsx").write_bytes(_build_minimal_xlsx_bytes("Excel Budget"))
    (docs_dir / "pitch.pptx").write_bytes(_build_minimal_pptx_bytes("PowerPoint Pitch"))
    (docs_dir / "whitepaper.pdf").write_bytes(_build_minimal_pdf_bytes("PDF Whitepaper", "Vector database architecture"))
    (docs_dir / "data.csv").write_text("Tool,Type\nDocsQA,Retrieval\nPostgreSQL,Database\n", encoding="utf-8")

    pipeline = IngestionPipeline(db_session)
    job = await pipeline.ingest_directory(str(docs_dir))

    assert job.status == "completed"
    assert job.docs_scanned == 5
    assert job.docs_modified == 5
    assert job.chunks_created >= 5

    # Incremental scan without modifications should skip all 5 files
    job_second = await pipeline.ingest_directory(str(docs_dir))
    assert job_second.docs_scanned == 5
    assert job_second.docs_modified == 0
    assert job_second.chunks_created == 0
