"""Multi-format documentation parsers for Markdown, HTML, and reStructuredText (reST)."""

import re
from html.parser import HTMLParser
from pathlib import Path

from app.ingestion.chunker import ChunkDraft, MarkdownChunker
from app.ingestion.hasher import compute_sha256


class HTMLDocumentParser(HTMLParser):
    """
    Strips boilerplate and extracts structured text with hierarchical heading breadcrumbs
    from HTML documentation pages using standard library html.parser.
    """

    IGNORABLE_TAGS = {"script", "style", "nav", "footer", "header", "aside", "svg", "noscript"}
    HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

    def __init__(self, max_words: int = 400):
        super().__init__()
        self.max_words = max_words
        self.ignore_depth = 0
        self.current_heading_level: int | None = None
        self.heading_buffer: list[str] = []
        self.running_headings: list[tuple[int, str]] = []  # (level, text)
        self.sections: list[tuple[str, list[str]]] = []  # (breadcrumb, paragraphs)
        self.current_paragraphs: list[str] = []
        self.in_pre = False
        self.pre_buffer: list[str] = []
        self.title: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag_lower = tag.lower()
        if tag_lower in self.IGNORABLE_TAGS:
            self.ignore_depth += 1
            return
        if self.ignore_depth > 0:
            return

        if tag_lower in self.HEADING_TAGS:
            self._flush_section()
            self.current_heading_level = self.HEADING_TAGS[tag_lower]
            self.heading_buffer = []
        elif tag_lower == "pre":
            self.in_pre = True
            self.pre_buffer = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self.IGNORABLE_TAGS:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth > 0:
            return

        if tag_lower in self.HEADING_TAGS and self.current_heading_level is not None:
            heading_text = " ".join("".join(self.heading_buffer).split())
            if heading_text:
                if not self.title and self.current_heading_level == 1:
                    self.title = heading_text
                # Update running breadcrumb hierarchy
                while self.running_headings and self.running_headings[-1][0] >= self.current_heading_level:
                    self.running_headings.pop()
                self.running_headings.append((self.current_heading_level, heading_text))
            self.current_heading_level = None
            self.heading_buffer = []

        elif tag_lower == "pre":
            self.in_pre = False
            code_text = "".join(self.pre_buffer).strip()
            if code_text:
                self.current_paragraphs.append(f"```\n{code_text}\n```")
            self.pre_buffer = []

        elif tag_lower in ("p", "li", "tr"):
            self.current_paragraphs.append("\n")

    def handle_data(self, data: str):
        if self.ignore_depth > 0:
            return
        if self.current_heading_level is not None:
            self.heading_buffer.append(data)
        elif self.in_pre:
            self.pre_buffer.append(data)
        else:
            cleaned = data.strip()
            if cleaned:
                self.current_paragraphs.append(cleaned)

    def _flush_section(self):
        if self.current_paragraphs:
            breadcrumb = " > ".join(h[1] for h in self.running_headings) or "Document"
            combined_text = " ".join(self.current_paragraphs).strip()
            # Clean up newlines around code fences
            combined_text = re.sub(r"\s*```\s*", "\n```\n", combined_text)
            if combined_text:
                self.sections.append((breadcrumb, [combined_text]))
            self.current_paragraphs = []

    def parse(self, html_content: str, fallback_title: str = "Document") -> tuple[str, list[ChunkDraft]]:
        self.feed(html_content)
        self._flush_section()

        doc_title = self.title or fallback_title
        chunks: list[ChunkDraft] = []
        char_offset = 0

        for breadcrumb, paragraphs in self.sections:
            body = "\n\n".join(paragraphs).strip()
            if not body:
                continue

            # Split section if it exceeds max_words
            words = body.split()
            if len(words) <= self.max_words:
                chunk_text = f"## {breadcrumb}\n\n{body}"
                c_hash = compute_sha256(chunk_text)
                c_len = len(chunk_text)
                chunks.append(
                    ChunkDraft(
                        chunk_index=len(chunks),
                        heading=breadcrumb,
                        content=chunk_text,
                        char_start=char_offset,
                        char_end=char_offset + c_len,
                        content_hash=c_hash,
                    )
                )
                char_offset += c_len
            else:
                # Chunk large body in word slices
                step = self.max_words
                overlap = 40
                for start_idx in range(0, len(words), step - overlap):
                    sub_words = words[start_idx : start_idx + step]
                    if not sub_words:
                        break
                    sub_body = " ".join(sub_words)
                    chunk_text = f"## {breadcrumb}\n\n{sub_body}"
                    c_hash = compute_sha256(chunk_text)
                    c_len = len(chunk_text)
                    chunks.append(
                        ChunkDraft(
                            chunk_index=len(chunks),
                            heading=breadcrumb,
                            content=chunk_text,
                            char_start=char_offset,
                            char_end=char_offset + c_len,
                            content_hash=c_hash,
                        )
                    )
                    char_offset += c_len
                    if start_idx + step >= len(words):
                        break

        return doc_title, chunks


class RSTDocumentParser:
    """
    Parses reStructuredText (.rst) documents by recognizing section underlines,
    code blocks, directives, and tables, and producing clean semantic ChunkDraft items.
    """

    # reST adornment characters
    ADORNMENTS = set("=-~^\"'`:#*+.")

    def __init__(self, max_words: int = 400):
        self.max_words = max_words

    def parse(self, rst_content: str, fallback_title: str = "Document") -> tuple[str, list[ChunkDraft]]:
        lines = rst_content.splitlines()
        chunks: list[ChunkDraft] = []
        title = fallback_title

        # First pass: convert reST syntax into Markdown-like AST blocks
        # Adorned headers:
        # Title
        # =====
        parsed_blocks: list[tuple[str, int, str]] = []  # (type: 'heading'|'code'|'table'|'text', level, content)
        i = 0
        n = len(lines)
        levels_map: dict[str, int] = {}  # char -> level

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # Check for heading with underline on next line
            if i + 1 < n and stripped and len(lines[i + 1].strip()) >= len(stripped):
                next_line = lines[i + 1].strip()
                first_char = next_line[0]
                if first_char in self.ADORNMENTS and all(c == first_char for c in next_line):
                    # Found a section heading
                    if first_char not in levels_map:
                        levels_map[first_char] = len(levels_map) + 1
                    level = levels_map[first_char]
                    if level == 1 and title == fallback_title:
                        title = stripped
                    parsed_blocks.append(("heading", level, stripped))
                    i += 2
                    continue

            # Check for code-block directive
            if stripped.startswith((".. code-block::", ".. code::")):
                lang_match = re.search(r"\.\.\s*code(?:-block)?::\s*(\w+)?", stripped)
                lang = lang_match.group(1) if lang_match and lang_match.group(1) else ""
                code_lines = []
                i += 1
                while i < n and (not lines[i].strip() or lines[i].startswith("   ") or lines[i].startswith("\t")):
                    if lines[i].strip():
                        # Unindent 3 spaces or 1 tab
                        code_lines.append(re.sub(r"^(\s{3,4}|\t)", "", lines[i]))
                    else:
                        code_lines.append("")
                    i += 1
                code_text = f"```{lang}\n" + "\n".join(code_lines).strip() + "\n```"
                parsed_blocks.append(("code", 0, code_text))
                continue

            # Check for tables (+---+ or === ===)
            if stripped.startswith("+---") or (stripped.startswith("===") and " " in stripped):
                table_lines = [line]
                i += 1
                while i < n and lines[i].strip():
                    table_lines.append(lines[i])
                    i += 1
                parsed_blocks.append(("table", 0, "\n".join(table_lines)))
                continue

            # Check for generic directives (.. note::, .. warning::)
            if stripped.startswith(".. ") and "::" in stripped:
                directive_type = stripped[3 : stripped.index("::")].strip()
                body_lines = []
                i += 1
                while i < n and (not lines[i].strip() or lines[i].startswith("   ") or lines[i].startswith("\t")):
                    if lines[i].strip():
                        body_lines.append(re.sub(r"^(\s{3,4}|\t)", "", lines[i]))
                    i += 1
                callout_text = f"> **{directive_type.upper()}**: " + " ".join(body_lines).strip()
                parsed_blocks.append(("text", 0, callout_text))
                continue

            # Regular paragraph text
            if stripped:
                para_lines = [stripped]
                i += 1
                while i < n and lines[i].strip() and not lines[i].strip().startswith(".."):
                    # Check next line isn't a heading underline
                    if i + 1 < n and lines[i + 1].strip() and lines[i + 1].strip()[0] in self.ADORNMENTS and all(c == lines[i + 1].strip()[0] for c in lines[i + 1].strip()):
                        break
                    para_lines.append(lines[i].strip())
                    i += 1
                parsed_blocks.append(("text", 0, " ".join(para_lines)))
            else:
                i += 1

        # Second pass: group parsed blocks into sections and chunks
        running_headings: list[tuple[int, str]] = []
        current_content: list[str] = []
        char_offset = 0

        def flush_chunk():
            nonlocal current_content, char_offset
            if not current_content:
                return
            breadcrumb = " > ".join(h[1] for h in running_headings) or title
            body = "\n\n".join(current_content).strip()
            chunk_text = f"## {breadcrumb}\n\n{body}"
            c_hash = compute_sha256(chunk_text)
            c_len = len(chunk_text)
            chunks.append(
                ChunkDraft(
                    chunk_index=len(chunks),
                    heading=breadcrumb,
                    content=chunk_text,
                    char_start=char_offset,
                    char_end=char_offset + c_len,
                    content_hash=c_hash,
                )
            )
            char_offset += c_len
            current_content = []

        for b_type, b_level, b_text in parsed_blocks:
            if b_type == "heading":
                flush_chunk()
                while running_headings and running_headings[-1][0] >= b_level:
                    running_headings.pop()
                running_headings.append((b_level, b_text))
            else:
                current_content.append(b_text)

        flush_chunk()
        return title, chunks


class DocumentParserFactory:
    """Factory creating appropriate parser according to file extension."""

    @staticmethod
    def parse_file(file_path: Path, content: str) -> tuple[str, list[ChunkDraft]]:
        suffix = file_path.suffix.lower()
        fallback_title = file_path.stem.replace("_", " ").title()

        if suffix in (".html", ".htm"):
            parser = HTMLDocumentParser()
            return parser.parse(content, fallback_title=fallback_title)

        if suffix in (".rst", ".rest"):
            parser = RSTDocumentParser()
            return parser.parse(content, fallback_title=fallback_title)

        # Default to Markdown chunker
        chunker = MarkdownChunker()
        title = MarkdownChunker.extract_title(content, fallback=fallback_title)
        chunks = chunker.chunk_document(content, source_path=file_path.as_posix())
        return title, chunks
