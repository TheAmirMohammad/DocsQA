"""Block-aware Markdown chunker that preserves headings, code blocks, and tables."""

import re
from dataclasses import dataclass

from app.ingestion.hasher import compute_sha256


@dataclass
class ChunkDraft:
    chunk_index: int
    heading: str
    content: str
    char_start: int
    char_end: int
    content_hash: str


class MarkdownChunker:
    """
    Splits markdown documents into semantic chunks along headings while guaranteeing
    that fenced code blocks and markdown tables are never sliced in half.
    """

    def __init__(self, max_words: int = 400):
        self.max_words = max_words

    def chunk_document(self, text: str, source_path: str = "") -> list[ChunkDraft]:
        """
        One chunk per heading section, so a chunk's heading (and citation anchor) is the
        section its text came from. Sections longer than max_words split between blocks;
        a single oversized code block or table stays whole.
        """
        if not text or not text.strip():
            return []

        chunks: list[ChunkDraft] = []
        current: list[str] = []
        has_body = False
        breadcrumb = ""
        start_char = 0
        running_headings: list[tuple[int, str]] = []  # (level, title)

        def flush(end_char: int) -> None:
            nonlocal current, has_body, start_char
            if has_body:
                chunk_text = self._assemble_chunk(breadcrumb, current)
                chunks.append(ChunkDraft(
                    chunk_index=len(chunks),
                    heading=breadcrumb,
                    content=chunk_text,
                    char_start=start_char,
                    char_end=end_char,
                    content_hash=compute_sha256(chunk_text),
                ))
                current, has_body, start_char = [], False, end_char

        for block_type, block_level, block_content, start_pos, _end_pos in self._parse_blocks(text):
            if block_type == "heading":
                flush(start_pos)
                if not current:
                    start_char = start_pos
                while running_headings and running_headings[-1][0] >= block_level:
                    running_headings.pop()
                running_headings.append((block_level, block_content.strip()))
                breadcrumb = " > ".join(h[1] for h in running_headings)
                current.append(f"{'#' * block_level} {block_content}")
                continue

            words = sum(len(b.split()) for b in current)
            if has_body and words + len(block_content.split()) > self.max_words:
                flush(start_pos)
            current.append(block_content)
            has_body = True

        flush(len(text))
        return chunks

    def _assemble_chunk(self, heading: str, blocks: list[str]) -> str:
        body = "\n\n".join(b.strip() for b in blocks if b.strip())
        if heading and not body.startswith("#"):
            return f"[{heading}]\n\n{body}"
        return body

    def _parse_blocks(self, text: str) -> list[tuple[str, int, str, int, int]]:
        """
        Parses markdown text into atomic blocks:
        Returns list of (type, level, content, start_pos, end_pos)
        Types: 'heading', 'code', 'table', 'text'
        """
        lines = text.splitlines(keepends=True)
        blocks: list[tuple[str, int, str, int, int]] = []
        
        in_code_block = False
        code_fence = ""
        code_buffer: list[str] = []
        code_start = 0

        in_table = False
        table_buffer: list[str] = []
        table_start = 0

        text_buffer: list[str] = []
        text_start = 0

        curr_pos = 0

        def flush_text(end_char_pos: int):
            nonlocal text_buffer, text_start
            if text_buffer:
                content = "".join(text_buffer).strip()
                if content:
                    blocks.append(("text", 0, content, text_start, end_char_pos))
                text_buffer = []

        def flush_table(end_char_pos: int):
            nonlocal table_buffer, in_table, table_start
            if table_buffer:
                content = "".join(table_buffer).strip()
                if content:
                    blocks.append(("table", 0, content, table_start, end_char_pos))
                table_buffer = []
                in_table = False

        for line in lines:
            line_len = len(line)
            line_pos = curr_pos
            stripped = line.strip()

            # 1. Code Fence check (``` or ~~~)
            fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
            if fence_match:
                fence_tag = fence_match.group(1)
                if in_code_block:
                    # CommonMark: closing fence = same char, at least as long, no info string
                    if fence_tag[0] == code_fence[0] and len(fence_tag) >= len(code_fence) and stripped == fence_tag:
                        code_buffer.append(line)
                        content = "".join(code_buffer)
                        blocks.append(("code", 0, content, code_start, line_pos + line_len))
                        code_buffer = []
                        in_code_block = False
                        code_fence = ""
                        curr_pos += line_len
                        continue
                else:
                    flush_text(line_pos)
                    flush_table(line_pos)
                    in_code_block = True
                    code_fence = fence_tag
                    code_start = line_pos
                    code_buffer = [line]
                    curr_pos += line_len
                    continue

            if in_code_block:
                code_buffer.append(line)
                curr_pos += line_len
                continue

            # 2. Markdown Table line check (| ... |)
            is_table_line = stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 2
            if is_table_line:
                if not in_table:
                    flush_text(line_pos)
                    in_table = True
                    table_start = line_pos
                    table_buffer = [line]
                else:
                    table_buffer.append(line)
                curr_pos += line_len
                continue
            else:
                if in_table:
                    flush_table(line_pos)

            # 3. Heading check (# Heading)
            heading_match = re.match(r"^ {0,3}(#{1,6})\s+(.+)$", line.rstrip("\r\n"))
            if heading_match:
                flush_text(line_pos)
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                blocks.append(("heading", level, title, line_pos, line_pos + line_len))
                curr_pos += line_len
                continue

            # 4. Empty line (paragraph boundary)
            if not stripped:
                if text_buffer:
                    flush_text(line_pos)
                curr_pos += line_len
                continue

            # 5. Regular text / list line
            if not text_buffer:
                text_start = line_pos
            text_buffer.append(line)
            curr_pos += line_len

        # Final flushes
        if in_code_block and code_buffer:
            blocks.append(("code", 0, "".join(code_buffer), code_start, curr_pos))
        if in_table and table_buffer:
            blocks.append(("table", 0, "".join(table_buffer), table_start, curr_pos))
        if text_buffer:
            flush_text(curr_pos)

        return blocks
