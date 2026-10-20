"""Apply idempotent DDL scripts to the local warehouse."""

from __future__ import annotations

from pathlib import Path


def split_sql(script: str) -> list[str]:
    """Split a SQL script on semicolons, keeping dollar-quoted function bodies intact."""

    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    dollar_tag: str | None = None
    in_line_comment = False
    in_single_quote = False

    while index < len(script):
        if in_line_comment:
            buffer.append(script[index])
            if script[index] == "\n":
                in_line_comment = False
            index += 1
            continue
        if dollar_tag is not None:
            if script.startswith(dollar_tag, index):
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
                continue
            buffer.append(script[index])
            index += 1
            continue
        if in_single_quote:
            buffer.append(script[index])
            if script[index] == "'":
                if index + 1 < len(script) and script[index + 1] == "'":
                    buffer.append("'")
                    index += 2
                    continue
                in_single_quote = False
            index += 1
            continue
        if script.startswith("--", index):
            in_line_comment = True
            buffer.append("--")
            index += 2
            continue
        if script[index] == "'":
            in_single_quote = True
            buffer.append(script[index])
            index += 1
            continue
        if script[index] == "$":
            tag_end = index + 1
            while tag_end < len(script) and (script[tag_end].isalnum() or script[tag_end] == "_"):
                tag_end += 1
            if tag_end < len(script) and script[tag_end] == "$":
                dollar_tag = script[index : tag_end + 1]
                buffer.append(dollar_tag)
                index = tag_end + 1
                continue
        if script[index] == ";":
            statement = "".join(buffer).strip()
            if _has_sql(statement):
                statements.append(statement)
            buffer = []
            index += 1
            continue
        buffer.append(script[index])
        index += 1

    tail = "".join(buffer).strip()
    if _has_sql(tail):
        statements.append(tail)
    return statements


def _has_sql(statement: str) -> bool:
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return True
    return False


def apply_sql_directory(connection, ddl_dir: Path) -> list[str]:
    applied: list[str] = []
    for path in sorted(ddl_dir.glob("*.sql")):
        script = path.read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            for statement in split_sql(script):
                cursor.execute(statement)
        applied.append(path.name)
    return applied
