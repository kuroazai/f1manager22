"""SQLite access to an unpacked save.

Two things the original got wrong, and they are the reason this is its own
module:

`execute` did not commit, while `commit` also closed the connection. So writes
went nowhere unless something later happened to commit, and committing twice
raised `ProgrammingError` on a closed cursor. You could not save your work
halfway through.

Here a transaction is explicit, and `commit` commits. Closing is closing.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

#: Anything the caller passes as a query parameter.
Params = Sequence[Any]


class SaveDatabaseError(RuntimeError):
    """The save database is missing, unreadable, or not the shape expected."""


class SaveDatabase:
    """One unpacked `main.db`.

    Use it as a context manager. On a clean exit it commits, and on an exception
    it rolls back, so a crash halfway through a set of changes leaves the save
    as it was rather than half-edited.
    """

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        if not self.path.is_file():
            raise SaveDatabaseError(
                f"no save database at {self.path}. Unpack a save first: "
                "f1m22 unpack"
            )
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> SaveDatabase:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None and not self.read_only:
            self.commit()
        else:
            self.rollback()
        self.close()

    def commit(self) -> None:
        """Commit. It does not close, which is the whole point."""
        if self.read_only:
            raise SaveDatabaseError("this database was opened read-only")
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[SaveDatabase]:
        """A nested unit of work that commits together or not at all."""
        try:
            yield self
        except Exception:
            self.rollback()
            raise
        else:
            self.commit()

    # -- reading -----------------------------------------------------------
    def query(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        cursor = self.connection.execute(sql, tuple(params))
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def query_one(self, sql: str, params: Params = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Params = ()) -> Any:
        """The first column of the first row, or None.

        The original did `.fetchone()[0]`, which raises `TypeError: 'NoneType'
        is not subscriptable` when the row is absent. That turned "this driver
        is not in your save" into a crash with a traceback that said nothing
        about drivers.
        """
        row = self.query_one(sql, params)
        return row[0] if row is not None else None

    # -- writing -----------------------------------------------------------
    def execute(self, sql: str, params: Params = ()) -> int:
        """Run a statement and return the number of rows it changed.

        The row count is returned rather than discarded because it is the only
        way to tell a successful update from one whose WHERE clause matched
        nothing. An `UPDATE ... WHERE StatID = 11` against a table whose IDs
        stop at 10 succeeds and changes nothing.
        """
        self._require_writable()
        cursor = self.connection.execute(sql, tuple(params))
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def execute_many(self, sql: str, rows: Sequence[Params]) -> int:
        """Run one statement over many parameter sets.

        One statement, not a list of them. The original passed a list of
        different queries as the first argument, which sqlite3 cannot do.
        """
        self._require_writable()
        if isinstance(sql, (list, tuple)):
            raise TypeError(
                "execute_many takes one SQL statement and many parameter sets, "
                "not many statements"
            )
        cursor = self.connection.executemany(sql, [tuple(r) for r in rows])
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def _require_writable(self) -> None:
        if self.read_only:
            raise SaveDatabaseError("this database was opened read-only")

    # -- introspection -----------------------------------------------------
    def tables(self) -> list[str]:
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return [row["name"] for row in rows]

    def columns(self, table: str) -> list[str]:
        # Identifier, so it cannot be a bound parameter. Checked against the
        # real table list first rather than interpolated blind.
        if table not in self.tables():
            raise SaveDatabaseError(f"no table {table!r} in {self.path.name}")
        return [row["name"] for row in self.query(f'PRAGMA table_info("{table}")')]

    def require_tables(self, *names: str) -> None:
        """Fail early, with the list, rather than once per missing table.

        A save from a different game version is the common cause, and one error
        naming everything absent is more use than the first one it hits.
        """
        present = set(self.tables())
        missing = [name for name in names if name not in present]
        if missing:
            raise SaveDatabaseError(
                f"{self.path.name} is missing {len(missing)} expected table(s): "
                + ", ".join(sorted(missing))
                + ". Is this an F1 Manager 2022 save?"
            )
