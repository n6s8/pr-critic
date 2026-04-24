from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiffSelection:
    content: str
    included_files: list[str]
    omitted_files: int


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


def prepare_diff_for_prompt(diff: str, max_chars: int) -> DiffSelection:
    if len(diff) <= max_chars:
        return DiffSelection(content=diff, included_files=[], omitted_files=0)

    blocks = split_diff_by_file(diff)
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

    for path, block in blocks:
        block_len = len(block)
        separator_len = 2 if selected_blocks else 0
        if selected_blocks and block_len + separator_len > remaining:
            break

        if not selected_blocks and block_len > remaining:
            selected_blocks.append(block[:remaining].rstrip())
            selected_files.append(path)
            remaining = 0
            break

        selected_blocks.append(block)
        selected_files.append(path)
        remaining -= block_len + separator_len

    omitted = max(0, len(blocks) - len(selected_files))
    suffix = ""
    if omitted:
        suffix = f"\n\n... [diff truncated after {len(selected_files)} file(s); {omitted} omitted]"

    return DiffSelection(
        content="\n\n".join(selected_blocks).rstrip() + suffix,
        included_files=selected_files,
        omitted_files=omitted,
    )
