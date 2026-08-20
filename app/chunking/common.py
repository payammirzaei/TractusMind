from dataclasses import dataclass


@dataclass(frozen=True)
class TextRange:
    text: str
    start_line: int
    end_line: int
    part: int


def split_text_by_lines(
    text: str,
    *,
    start_line: int,
    max_chars: int,
    overlap_lines: int = 3,
) -> list[TextRange]:
    """Split oversized text on line boundaries while retaining small overlap."""
    if len(text) <= max_chars:
        line_count = max(1, text.count("\n") + 1)
        return [
            TextRange(
                text=text,
                start_line=start_line,
                end_line=start_line + line_count - 1,
                part=1,
            )
        ]

    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    ranges: list[TextRange] = []
    cursor = 0
    part = 1

    while cursor < len(lines):
        end = cursor
        current_chars = 0
        while end < len(lines):
            next_size = len(lines[end])
            if end > cursor and current_chars + next_size > max_chars:
                break
            current_chars += next_size
            end += 1

        if end == cursor:
            end = cursor + 1

        chunk_text = "".join(lines[cursor:end]).strip()
        if chunk_text:
            ranges.append(
                TextRange(
                    text=chunk_text,
                    start_line=start_line + cursor,
                    end_line=start_line + end - 1,
                    part=part,
                )
            )
            part += 1

        if end >= len(lines):
            break

        next_cursor = max(cursor + 1, end - max(0, overlap_lines))
        cursor = next_cursor

    return ranges
