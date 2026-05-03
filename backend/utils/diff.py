from __future__ import annotations

from dataclasses import dataclass
import math

MAX_FILES = 10
MAX_CHUNKS = 5
MAX_LINES_PER_CHUNK = 200
SMART_REVIEW_MAX_CHUNKS = 3
SMART_REVIEW_TOKEN_BUDGET = 900
SMART_TOTAL_INPUT_TOKEN_BUDGET = 1800
SMART_BRANCH_TOKEN_BUDGET = 1500
SMART_CRITIC_TOKEN_BUDGET = 650
SMART_SELECTOR_TOKEN_BUDGET = 500


@dataclass(frozen=True)
class DiffSelection:
    content: str
    included_files: list[str]
    omitted_files: int


@dataclass(frozen=True)
class DiffChunk:
    index: int
    total: int
    content: str
    included_files: list[str]


@dataclass(frozen=True)
class LLMDiffPacket:
    content: str
    included_files: list[str]
    selected_chunks: int
    omitted_chunks: int
    estimated_tokens: int


_PATH_KEYWORDS = {
    "auth": 8,
    "login": 8,
    "session": 7,
    "permission": 7,
    "admin": 7,
    "security": 8,
    "secret": 8,
    "token": 7,
    "password": 8,
    "crypto": 8,
    "encrypt": 8,
    "decrypt": 8,
    "payment": 7,
    "billing": 7,
    "checkout": 7,
    "api": 6,
    "route": 5,
    "controller": 5,
    "service": 4,
    "db": 6,
    "query": 7,
    "sql": 7,
    "migration": 6,
    "config": 4,
    "workflow": 5,
    "docker": 4,
}

_EXTENSION_PRIORITY = {
    ".py": 7,
    ".ts": 7,
    ".tsx": 7,
    ".pyi": 6,
    ".js": 6,
    ".jsx": 6,
    ".go": 7,
    ".rs": 7,
    ".java": 7,
    ".kt": 7,
    ".cs": 7,
    ".rb": 6,
    ".php": 6,
    ".swift": 6,
    ".yml": 1,
    ".yaml": 1,
    ".json": 1,
    ".toml": 1,
    ".env": 1,
    ".sh": 4,
    ".md": 0,
}

_LOW_PRIORITY_SEGMENTS = ("test", "spec", "fixture", "docs", "example", "snapshot", "__snapshots__", "verify_")
_RISKY_CONTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    ("auth", 3),
    ("password", 4),
    ("token", 3),
    ("session", 3),
    ("db.", 3),
    ("query", 3),
    ("select ", 3),
    ("insert ", 3),
    ("update ", 3),
    ("delete ", 3),
    ("/api/", 2),
    ("request.", 2),
    ("missing validation", 5),
    ("proper validation", 4),
    ("global[", 5),
    ("string.fromcharcode", 4),
    ("baseexception", 3),
    ("except exception", 3),
)


def split_diff_by_file(diff: str) -> list[tuple[str, str]]:
    if not diff.strip():
        return []

    blocks: list[tuple[str, str]] = []
    current_lines: list[str] = []
    current_path = "unknown"

    for line in diff.replace("\r\n", "\n").split("\n"):
        if line.startswith("diff --git "):
            if current_lines:
                blocks.append((current_path, "\n".join(current_lines).strip()))
            parts = line.split()
            current_path = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else "unknown"
            current_lines = [line]
            continue

        current_lines.append(line)

    if current_lines:
        blocks.append((current_path, "\n".join(current_lines).strip()))

    return [(path, block) for path, block in blocks if block]


def _path_priority(path: str) -> int:
    normalized = path.lower()
    score = 0
    filename = normalized.rsplit("/", 1)[-1]

    is_backend_code = (
        normalized.endswith((".py", ".pyi"))
        or (normalized.endswith((".ts", ".tsx", ".js", ".jsx")) and any(segment in normalized for segment in ("backend", "server", "api", "service")))
    )
    if is_backend_code:
        score += 25

    for segment, weight in _PATH_KEYWORDS.items():
        if segment in normalized:
            score += weight

    ext = ""
    if "." in filename:
        ext = "." + normalized.rsplit(".", 1)[-1]
    score += _EXTENSION_PRIORITY.get(ext, 2)

    if any(segment in normalized for segment in _LOW_PRIORITY_SEGMENTS):
        score -= 4

    return score


def _block_priority(path: str, block: str) -> tuple[int, int]:
    score = _path_priority(path)
    added_lines = block.count("\n+")
    removed_lines = block.count("\n-")
    normalized_block = block.lower()
    if "@@ " in block:
        score += 2
    if "TODO" in block or "FIXME" in block:
        score += 1
    for pattern, weight in _RISKY_CONTENT_PATTERNS:
        if pattern in normalized_block:
            score += weight
    return score, added_lines + removed_lines


def _prioritize_blocks(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted(
        blocks,
        key=lambda item: (_block_priority(item[0], item[1])[0], _block_priority(item[0], item[1])[1], item[0]),
        reverse=True,
    )


def _select_review_blocks(blocks: list[tuple[str, str]], *, max_files: int = MAX_FILES) -> list[tuple[str, str]]:
    prioritized = _prioritize_blocks(blocks)
    return prioritized[:max_files]


def _is_low_priority_path(path: str) -> bool:
    normalized = path.lower()
    return (
        normalized.endswith((".md", ".json", ".yml", ".yaml", ".toml", ".env"))
        or any(segment in normalized for segment in ("docs/", "/docs", "config/", "/config"))
    )


def estimate_tokens(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / 4))


def _split_block_by_hunk(path: str, block: str, max_chars: int, *, max_lines: int = MAX_LINES_PER_CHUNK) -> list[tuple[str, str]]:
    if len(block) <= max_chars and len(block.splitlines()) <= max_lines:
        return [(path, block)]

    line_suffix = " ... [line truncated for token budget]"
    max_line_chars = max(80, max_chars - len(line_suffix))
    lines = [
        line if len(line) <= max_chars else f"{line[:max_line_chars]}{line_suffix}"
        for line in block.split("\n")
    ]
    header_lines: list[str] = []
    hunks: list[list[str]] = []
    current_hunk: list[str] | None = None

    for line in lines:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = [line]
            continue

        if current_hunk is None:
            header_lines.append(line)
        else:
            current_hunk.append(line)

    if current_hunk:
        hunks.append(current_hunk)

    if not hunks:
        chunks: list[tuple[str, str]] = []
        current_chunk: list[str] = []
        for line in lines:
            projected = "\n".join(current_chunk + [line]).strip()
            if (
                current_chunk
                and (len(projected) > max_chars or len(current_chunk) + 1 > max_lines)
            ):
                chunks.append((path, "\n".join(current_chunk).strip()))
                current_chunk = [line]
            else:
                current_chunk.append(line)
        if current_chunk:
            chunks.append((path, "\n".join(current_chunk).strip()))
        return chunks or [(path, block)]

    chunks: list[tuple[str, str]] = []
    header_only = list(header_lines)
    current_lines = list(header_only)

    for hunk in hunks:
        if (
            len("\n".join(current_lines + hunk).strip()) <= max_chars
            and len(current_lines + hunk) <= max_lines
        ):
            current_lines.extend(hunk)
            continue

        if current_lines != header_only:
            chunks.append((path, "\n".join(current_lines).strip()))
            current_lines = list(header_only)

        if (
            len("\n".join(header_only + hunk).strip()) <= max_chars
            and len(header_only + hunk) <= max_lines
        ):
            current_lines = list(header_only) + hunk
            continue

        # Split a very large hunk by diff lines while repeating file + hunk headers.
        hunk_header = hunk[0]
        body_lines = hunk[1:]
        current_piece = list(header_only) + [hunk_header]
        for line in body_lines:
            projected_piece = "\n".join(current_piece + [line]).strip()
            projected_line_count = len(current_piece) + 1
            if (
                (len(projected_piece) > max_chars or projected_line_count > max_lines)
                and len(current_piece) > len(header_only) + 1
            ):
                chunks.append((path, "\n".join(current_piece).strip()))
                current_piece = list(header_only) + [hunk_header, line]
            else:
                current_piece.append(line)
        if current_piece and current_piece != header_only:
            chunks.append((path, "\n".join(current_piece).strip()))
        current_lines = list(header_only)

    if current_lines and current_lines != header_only:
        chunks.append((path, "\n".join(current_lines).strip()))

    return chunks or [(path, block)]


def chunk_diff_for_review(
    diff: str,
    max_chars: int,
    *,
    max_chunks: int | None = None,
    max_files: int = MAX_FILES,
    max_lines_per_chunk: int = MAX_LINES_PER_CHUNK,
) -> list[DiffChunk]:
    if not diff.strip():
        return [DiffChunk(index=0, total=1, content="", included_files=[])]

    all_blocks = split_diff_by_file(diff)
    blocks = _select_review_blocks(all_blocks, max_files=max_files)
    if not blocks:
        selection = prepare_diff_for_prompt(diff, max_chars=max_chars)
        return [DiffChunk(index=0, total=1, content=selection.content, included_files=selection.included_files)]

    chunkable_blocks: list[tuple[str, str]] = []
    for path, block in blocks:
        chunkable_blocks.extend(
            _split_block_by_hunk(
                path,
                block,
                max_chars=max_chars,
                max_lines=max_lines_per_chunk,
            )
        )

    packed_chunks: list[tuple[str, list[str]]] = []
    current_parts: list[str] = []
    current_files: list[str] = []

    for path, block in chunkable_blocks:
        projected_parts = current_parts + [block]
        projected_text = "\n\n".join(projected_parts).strip()
        projected_line_count = len(projected_text.splitlines())
        if current_parts and (len(projected_text) > max_chars or projected_line_count > max_lines_per_chunk):
            packed_chunks.append(("\n\n".join(current_parts).strip(), current_files))
            current_parts = [block]
            current_files = [path]
            continue

        current_parts = projected_parts
        if path not in current_files:
            current_files.append(path)

    if current_parts:
        packed_chunks.append(("\n\n".join(current_parts).strip(), current_files))

    omitted_file_count = max(0, len(all_blocks) - len(blocks))
    if omitted_file_count and packed_chunks:
        last_content, last_files = packed_chunks[-1]
        packed_chunks[-1] = (
            f"{last_content}\n\n... [additional lower-priority files omitted: {omitted_file_count}]",
            last_files,
        )

    effective_max_chunks = MAX_CHUNKS if max_chunks is None else min(max_chunks, MAX_CHUNKS)
    if effective_max_chunks > 0 and len(packed_chunks) > effective_max_chunks:
        kept_chunks = packed_chunks[:effective_max_chunks]
        omitted_chunks = packed_chunks[effective_max_chunks:]
        kept_files = {file_path for _, files in kept_chunks for file_path in files}
        omitted_files = sorted(
            {
                file_path
                for _, files in omitted_chunks
                for file_path in files
                if file_path not in kept_files
            }
        )
        note = (
            f"... [additional diff chunks omitted due to token budget: {len(omitted_chunks)}"
            f"; prioritized review kept {len(kept_files)} file(s)"
        )
        if omitted_files:
            preview = ", ".join(omitted_files[:3])
            note += f"; omitted files include {preview}"
            if len(omitted_files) > 3:
                note += ", ..."
        note += "]"

        last_content, last_files = kept_chunks[-1]
        kept_chunks[-1] = (f"{last_content}\n\n{note}", last_files)
        packed_chunks = kept_chunks

    total = len(packed_chunks) or 1
    return [
        DiffChunk(index=index, total=total, content=content, included_files=files)
        for index, (content, files) in enumerate(packed_chunks)
    ]


def build_llm_diff_packet(
    diff: str,
    *,
    max_files: int = 8,
    max_chunks: int = SMART_REVIEW_MAX_CHUNKS,
    max_lines_per_chunk: int = 120,
    max_chars_per_chunk: int = 1200,
    token_budget: int = SMART_REVIEW_TOKEN_BUDGET,
) -> LLMDiffPacket:
    chunks = chunk_diff_for_review(
        diff,
        max_chars=max_chars_per_chunk,
        max_chunks=MAX_CHUNKS,
        max_files=max_files,
        max_lines_per_chunk=max_lines_per_chunk,
    )

    selected_parts: list[str] = []
    selected_files: list[str] = []
    selected_chunks = 0
    estimated_tokens = 0

    for chunk in chunks:
        if selected_chunks >= max_chunks:
            break
        if selected_chunks >= 2 and all(_is_low_priority_path(file_path) for file_path in chunk.included_files):
            continue

        projected_content = (
            chunk.content
            if not selected_parts
            else "\n\n".join([*selected_parts, chunk.content])
        )
        projected_tokens = estimate_tokens(projected_content)
        if selected_parts and projected_tokens > token_budget:
            break

        if not selected_parts and projected_tokens > token_budget:
            trimmed_lines: list[str] = []
            for line in chunk.content.splitlines():
                candidate = "\n".join(trimmed_lines + [line])
                if trimmed_lines and estimate_tokens(candidate) > token_budget:
                    break
                trimmed_lines.append(line)
            if trimmed_lines:
                selected_parts.append("\n".join(trimmed_lines))
                selected_chunks += 1
                estimated_tokens = estimate_tokens(selected_parts[0])
                for file_path in chunk.included_files:
                    if file_path not in selected_files:
                        selected_files.append(file_path)
            break

        selected_parts.append(chunk.content)
        selected_chunks += 1
        estimated_tokens = projected_tokens
        for file_path in chunk.included_files:
            if file_path not in selected_files:
                selected_files.append(file_path)

    selected_content = "\n\n".join(part.strip() for part in selected_parts if part.strip())
    omitted_chunks = max(0, len(chunks) - selected_chunks)
    if omitted_chunks and selected_content:
        note = f"\n\n... [smart filter omitted {omitted_chunks} chunk(s)]"
        if estimate_tokens(f"{selected_content}{note}") <= token_budget:
            selected_content = f"{selected_content}{note}"
        estimated_tokens = estimate_tokens(selected_content)

    return LLMDiffPacket(
        content=selected_content,
        included_files=selected_files,
        selected_chunks=selected_chunks,
        omitted_chunks=omitted_chunks,
        estimated_tokens=estimated_tokens,
    )


def build_reasoning_diff_packet(
    diff: str,
    *,
    token_budget: int,
    max_files: int = 6,
    max_chunks: int = 2,
    max_lines_per_chunk: int = 80,
    max_chars_per_chunk: int = 1000,
) -> LLMDiffPacket:
    return build_llm_diff_packet(
        diff,
        max_files=max_files,
        max_chunks=max_chunks,
        max_lines_per_chunk=max_lines_per_chunk,
        max_chars_per_chunk=max_chars_per_chunk,
        token_budget=token_budget,
    )


def prepare_diff_for_prompt(diff: str, max_chars: int) -> DiffSelection:
    if len(diff) <= max_chars and len(diff.splitlines()) <= MAX_LINES_PER_CHUNK:
        return DiffSelection(content=diff, included_files=[], omitted_files=0)

    blocks = _select_review_blocks(split_diff_by_file(diff), max_files=MAX_FILES)
    if not blocks:
        truncated = diff[:max_chars].rstrip()
        return DiffSelection(
            content=f"{truncated}\n\n... [diff truncated at {max_chars} chars]",
            included_files=[],
            omitted_files=0,
        )

    selected_blocks: list[str] = []
    selected_files: list[str] = []
    remaining = max_chars
    remaining_lines = MAX_LINES_PER_CHUNK

    for path, block in blocks:
        block_len = len(block)
        block_lines = len(block.splitlines())
        separator_len = 2 if selected_blocks else 0
        if selected_blocks and (block_len + separator_len > remaining or block_lines > remaining_lines):
            break

        if not selected_blocks and (block_len > remaining or block_lines > remaining_lines):
            trimmed_lines = block.splitlines()[:remaining_lines]
            trimmed_block = "\n".join(trimmed_lines)
            selected_blocks.append(trimmed_block[:remaining].rstrip())
            selected_files.append(path)
            remaining = 0
            remaining_lines = 0
            break

        selected_blocks.append(block)
        selected_files.append(path)
        remaining -= block_len + separator_len
        remaining_lines -= block_lines

    omitted = max(0, len(blocks) - len(selected_files))
    suffix = ""
    if omitted:
        suffix = f"\n\n... [diff truncated after {len(selected_files)} file(s); {omitted} omitted]"

    return DiffSelection(
        content="\n\n".join(selected_blocks).rstrip() + suffix,
        included_files=selected_files,
        omitted_files=omitted,
    )
