"""Database access, and the two things the original got wrong."""
from __future__ import annotations

from pathlib import Path

import pytest

from f1manager22.db import SaveDatabase, SaveDatabaseError


def test_a_missing_database_says_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(SaveDatabaseError, match="unpack"):
        SaveDatabase(tmp_path / "absent.db")


def test_commit_does_not_close(save_path: Path) -> None:
    """The original's `commit` closed the cursor and the connection, so you
    could not commit twice and could not keep working after saving."""
    database = SaveDatabase(save_path)
    try:
        database.execute("UPDATE Tyres SET Grip = 0.5 WHERE Type = 0")
        database.commit()
        database.execute("UPDATE Tyres SET Grip = 0.6 WHERE Type = 1")
        database.commit()

        assert database.scalar("SELECT Grip FROM Tyres WHERE Type = 0") == 0.5
        assert database.scalar("SELECT Grip FROM Tyres WHERE Type = 1") == 0.6
    finally:
        database.close()


def test_writes_are_committed(save_path: Path) -> None:
    """The original's `execute` did not commit, so a write went nowhere unless
    something else happened to commit later."""
    with SaveDatabase(save_path) as database:
        database.execute("UPDATE Tyres SET Grip = 0.42 WHERE Type = 0")

    with SaveDatabase(save_path, read_only=True) as database:
        assert database.scalar("SELECT Grip FROM Tyres WHERE Type = 0") == 0.42


def test_an_exception_rolls_the_whole_thing_back(save_path: Path) -> None:
    """Half-edited is the worst outcome for a save file."""
    with SaveDatabase(save_path, read_only=True) as database:
        before = database.scalar("SELECT Grip FROM Tyres WHERE Type = 0")

    with pytest.raises(RuntimeError, match="boom"), SaveDatabase(save_path) as database:
        database.execute("UPDATE Tyres SET Grip = 0.1 WHERE Type = 0")
        raise RuntimeError("boom")

    with SaveDatabase(save_path, read_only=True) as database:
        assert database.scalar("SELECT Grip FROM Tyres WHERE Type = 0") == before


def test_read_only_refuses_to_write(save_path: Path) -> None:
    """What makes --dry-run a real dry run rather than a promise."""
    with SaveDatabase(save_path, read_only=True) as database:
        with pytest.raises(SaveDatabaseError, match="read-only"):
            database.execute("UPDATE Tyres SET Grip = 0.1")
        with pytest.raises(SaveDatabaseError, match="read-only"):
            database.commit()


def test_scalar_on_a_missing_row_is_none_not_a_crash(save_path: Path) -> None:
    """The original did `.fetchone()[0]`, which raises TypeError when the row is
    absent. A driver not in your save ended the run with a traceback that said
    nothing about drivers."""
    with SaveDatabase(save_path, read_only=True) as database:
        assert database.scalar(
            "SELECT StaffID FROM Staff_DriverData WHERE DriverCode = ?",
            ("[DriverCode_Nobody]",),
        ) is None


def test_execute_reports_rows_changed(save_path: Path) -> None:
    """The only way to tell a successful update from one that matched nothing."""
    with SaveDatabase(save_path) as database:
        assert database.execute("UPDATE Tyres SET Grip = 1.0 WHERE Type = 0") == 1
        assert database.execute("UPDATE Tyres SET Grip = 1.0 WHERE Type = 99") == 0


def test_execute_many_refuses_a_list_of_statements(save_path: Path) -> None:
    """Which is what the original passed, and sqlite3 cannot do."""
    with (
        SaveDatabase(save_path) as database,
        pytest.raises(TypeError, match="one SQL statement"),
    ):
        database.execute_many(
            ["UPDATE Tyres SET Grip = ?", "UPDATE Tyres SET Durability = ?"],
            [(1.0,)],
        )


def test_columns_on_an_unknown_table_names_the_table(save_path: Path) -> None:
    with (
        SaveDatabase(save_path, read_only=True) as database,
        pytest.raises(SaveDatabaseError, match="Nonsense"),
    ):
        database.columns("Nonsense")


def test_require_tables_lists_everything_missing_at_once(save_path: Path) -> None:
    """One error naming all of them beats the first one it happens to hit."""
    with SaveDatabase(save_path, read_only=True) as database:
        database.require_tables("Tyres", "Staff_DriverData")  # present

        with pytest.raises(SaveDatabaseError) as caught:
            database.require_tables("Tyres", "Missing_One", "Missing_Two")

    message = str(caught.value)
    assert "Missing_One" in message
    assert "Missing_Two" in message
    assert "2022" in message  # says what kind of save it expected


def test_a_transaction_commits_together(save_path: Path) -> None:
    database = SaveDatabase(save_path)
    try:
        with pytest.raises(RuntimeError), database.transaction():
            database.execute("UPDATE Tyres SET Grip = 0.11 WHERE Type = 0")
            raise RuntimeError("stop")
        assert database.scalar("SELECT Grip FROM Tyres WHERE Type = 0") != 0.11
    finally:
        database.close()
