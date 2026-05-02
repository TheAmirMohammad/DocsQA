"""Unit tests for the AST and block-aware MarkdownChunker."""

from app.ingestion.chunker import MarkdownChunker


def test_chunker_preserves_code_blocks():
    doc = """# Introduction
This is some introductory text before the code block.

```python
def important_function(x: int) -> int:
    # Line 1
    # Line 2
    # Line 3
    # Line 4
    # Line 5
    return x * 42
```

After the code block, here is some follow-up explanation.
"""
    chunker = MarkdownChunker(max_words=50)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 1
    # Ensure the entire code block is present in a single chunk
    code_found = False
    for chunk in chunks:
        if "def important_function" in chunk.content:
            code_found = True
            assert "return x * 42" in chunk.content
            assert "```python" in chunk.content
            assert "```" in chunk.content
    assert code_found, "Code block was not found intact"


def test_chunker_preserves_markdown_tables():
    doc = """# API Reference

Here is the parameter table:

| Parameter | Type | Required | Description |
|---|---|---|---|
| id | int | Yes | The unique identifier |
| name | str | Yes | The name of the item |
| price | float | No | The price of the item |
| tags | list | No | List of metadata tags |

End of section.
"""
    chunker = MarkdownChunker(max_words=30)
    chunks = chunker.chunk_document(doc)

    table_found = False
    for chunk in chunks:
        if "| Parameter | Type |" in chunk.content:
            table_found = True
            assert "| id | int |" in chunk.content
            assert "| tags | list |" in chunk.content
    assert table_found, "Markdown table was not preserved intact"


def test_chunker_heading_breadcrumbs():
    doc = """# Guide
## Authentication
### OAuth2
Here are details about OAuth2 password bearer flow.

## Database
Here are details about database sessions.
"""
    chunker = MarkdownChunker(max_words=20)
    chunks = chunker.chunk_document(doc)

    oauth_chunk = next((c for c in chunks if "OAuth2" in c.heading), None)
    assert oauth_chunk is not None
    assert "Guide > Authentication > OAuth2" in oauth_chunk.heading


def test_empty_document_handling():
    chunker = MarkdownChunker()
    assert chunker.chunk_document("") == []
    assert chunker.chunk_document("   \n\n  ") == []


def test_each_section_is_its_own_chunk_with_correct_heading():
    doc = """# Guide
Intro paragraph.

## Install
Run pip install.

## Usage
Call the function.
"""
    chunks = MarkdownChunker(max_words=400).chunk_document(doc)
    by_heading = {c.heading: c.content for c in chunks}
    assert "Run pip install." in by_heading["Guide > Install"]
    assert "Call the function." in by_heading["Guide > Usage"]
    assert "Call the function." not in by_heading["Guide > Install"]


def test_oversized_code_block_is_never_split():
    code = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(200)) + "\n```"
    doc = f"# Big\nSome words here.\n\n{code}\n\nTrailing text."
    chunks = MarkdownChunker(max_words=50).chunk_document(doc)
    holders = [c for c in chunks if "x0 = 0" in c.content]
    assert len(holders) == 1 and "x199 = 199" in holders[0].content


def test_longer_fence_is_not_closed_by_inner_shorter_fence():
    doc = "# Doc\nIntro.\n\n````md\n```python\nx = 1\n```\n# not a heading\n````\n\nAfter.\n"
    chunks = MarkdownChunker(max_words=400).chunk_document(doc)
    assert len(chunks) == 1
    assert "# not a heading" in chunks[0].content and chunks[0].heading == "Doc"
