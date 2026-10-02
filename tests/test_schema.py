"""The schema declaration, which is both the fixture and the checker."""
from __future__ import annotations

from f1manager22.db import SaveDatabase
from f1manager22.enums import Table
from f1manager22.schema import TABLES, create_statements, differences


def test_every_table_the_operations_name_is_declared() -> None:
    """Otherwise an operation targets a table the fixture does not build, and
    its test fails for the wrong reason."""
    for table in Table:
        assert str(table) in TABLES, f"{table} is not in the schema"


def test_the_fixture_builds_every_declared_table(save_path) -> None:
    with SaveDatabase(save_path, read_only=True) as database:
        built = set(database.tables())
    assert set(TABLES) <= built


def test_every_declared_column_exists_in_the_fixture(save_path) -> None:
    with SaveDatabase(save_path, read_only=True) as database:
        for table, columns in TABLES.items():
            present = set(database.columns(table))
            assert set(columns) <= present, f"{table} is missing columns"


def test_create_statements_are_idempotent(save_path) -> None:
    """IF NOT EXISTS, so running them against a real save cannot clobber it."""
    with SaveDatabase(save_path) as database:
        for statement in create_statements():
            database.execute(statement)


def test_differences_reports_a_missing_table() -> None:
    present = {name: list(columns) for name, columns in TABLES.items()}
    del present["Tyres"]
    problems = differences(present)
    assert any("missing table: Tyres" in p for p in problems)


def test_differences_reports_a_missing_column() -> None:
    present = {name: list(columns) for name, columns in TABLES.items()}
    present["Tyres"] = [c for c in present["Tyres"] if c != "Grip"]
    problems = differences(present)
    assert any("Grip" in p for p in problems)


def test_differences_on_a_matching_save_is_empty(save_path) -> None:
    with SaveDatabase(save_path, read_only=True) as database:
        present = {table: database.columns(table) for table in database.tables()}
    assert differences(present) == []


def test_a_save_with_extra_tables_is_fine(save_path) -> None:
    """A real save has well over a hundred tables. Only the ones used matter."""
    with SaveDatabase(save_path) as database:
        database.execute("CREATE TABLE Something_Else (Id INTEGER)")
        present = {table: database.columns(table) for table in database.tables()}
    assert differences(present) == []
