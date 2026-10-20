from pathlib import Path

from nih import __version__
from nih.cli import main
from warehouse.apply import split_sql

ROOT = Path(__file__).resolve().parents[1]


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_check_skips_a_missing_database(monkeypatch, capsys):
    monkeypatch.setattr("warehouse.audit.database_reachable", lambda settings=None: False)
    assert main(["check"]) == 0
    assert "synthetic derivation self-check: ok" in capsys.readouterr().out


def test_check_can_require_the_database(monkeypatch, capsys):
    monkeypatch.setattr("warehouse.audit.database_reachable", lambda settings=None: False)
    assert main(["check", "--require-db"]) == 1
    assert "not reachable" in capsys.readouterr().out


def test_sql_function_body_is_one_statement():
    script = (ROOT / "warehouse" / "ddl" / "015_period_bounds.sql").read_text(encoding="utf-8")
    statements = split_sql(script)
    assert len(statements) == 1
    assert "elsif period_span = 'q1_q3'" in statements[0]


def test_every_table_documents_its_grain():
    ddl = ROOT / "warehouse" / "ddl"
    for path in sorted(ddl.glob("*.sql")):
        script = path.read_text(encoding="utf-8")
        creates = script.lower().count("create table")
        grains = script.count("GRAIN:")
        assert creates == grains, path.name


def test_mart_descriptions_document_grain():
    schema = (ROOT / "transformations" / "dbt" / "models" / "schema.yml").read_text(encoding="utf-8")
    for model in (
        "unit_sales_incremental_quarter",
        "financial_flow_incremental_quarter",
        "financial_line_as_disclosed",
        "weekly_sell_through",
    ):
        assert f"name: {model}" in schema
    assert schema.count("GRAIN:") >= 7


def test_repository_does_not_embed_published_results():
    banned = ("million units", "17.37", "19.86", "1,905.8", "1905.8", "23.68", "156.59")
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or _ignored(path):
            continue
        if path.name == "test_foundation.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for phrase in banned:
            if phrase in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {phrase}")
    assert offenders == []


def _ignored(path: Path) -> bool:
    parts = path.parts
    if set(parts) & {".venv", "venv", "target", "logs", ".git", "__pycache__", ".pytest_cache"}:
        return True
    if "data" in parts:
        index = parts.index("data")
        if index + 1 < len(parts) and parts[index + 1] in {"raw", "cleaned", "processed"}:
            return True
    return False
