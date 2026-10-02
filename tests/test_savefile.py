"""Unpacking, repacking, and not losing the save.

The unpacker is stubbed with a small Python script, because the real one is a
separate project and is not redistributed here. What is being tested is this
side of the boundary: argument handling, exit codes, backups, and the paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from f1manager22.savefile import SaveArchive, SaveFileError

#: Writes a main.db into --result, like the real unpacker does.
GOOD_UNPACKER = """
import argparse, pathlib
parser = argparse.ArgumentParser()
parser.add_argument("--operation")
parser.add_argument("--input")
parser.add_argument("--result")
args = parser.parse_args()
if args.operation == "unpack":
    folder = pathlib.Path(args.result)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.db").write_bytes(b"not really a database")
else:
    pathlib.Path(args.result).write_bytes(b"repacked")
"""

#: Exits zero without producing anything.
SILENT_UNPACKER = "import sys; sys.exit(0)"

#: Fails, with something on stderr.
FAILING_UNPACKER = (
    "import sys; sys.stderr.write('cannot read this save'); sys.exit(3)"
)


@pytest.fixture
def save_folder(tmp_path: Path) -> Path:
    """A folder with a space in the name, which is the Windows default.

    This is the whole reason the original's repack step failed: its command was
    built by string interpolation and the last path was not quoted.
    """
    folder = tmp_path / "My Games" / "F1 Manager 2022"
    folder.mkdir(parents=True)
    (folder / "autosave.sav").write_bytes(b"original save contents")
    return folder


def make_unpacker(tmp_path: Path, source: str, name: str = "script.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_unpacks_through_a_path_containing_spaces(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
        python=sys.executable,
    )
    database = archive.unpack()
    assert database.is_file()
    assert database == archive.database_path
    assert " " in str(database)  # the thing that used to break


def test_repacks_through_a_path_containing_spaces(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
        python=sys.executable,
    )
    archive.unpack()
    assert archive.repack() == archive.save_path
    assert archive.save_path.read_bytes() == b"repacked"


def test_an_unpacker_that_silently_produces_nothing_is_caught(
    save_folder: Path, tmp_path: Path
) -> None:
    """Exit zero and no database. The original carried on and edited whatever
    main.db was left over from a previous run."""
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, SILENT_UNPACKER),
        python=sys.executable,
    )
    with pytest.raises(SaveFileError, match="no main.db"):
        archive.unpack()


def test_a_failing_unpacker_reports_its_own_error(
    save_folder: Path, tmp_path: Path
) -> None:
    """`os.system` discarded the exit code entirely."""
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, FAILING_UNPACKER),
        python=sys.executable,
    )
    with pytest.raises(SaveFileError, match="cannot read this save"):
        archive.unpack()


def test_a_missing_unpacker_says_where_to_get_it(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=tmp_path / "absent.py",
    )
    with pytest.raises(SaveFileError, match="xAranaktu"):
        archive.check()


def test_a_missing_save_is_reported(save_folder: Path, tmp_path: Path) -> None:
    archive = SaveArchive(
        save_path=save_folder / "no-such-save.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    with pytest.raises(SaveFileError, match="no save file"):
        archive.check()


def test_repacking_without_unpacking_first_is_refused(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    with pytest.raises(SaveFileError, match="nothing to repack"):
        archive.repack()


# -- backups ---------------------------------------------------------------

def test_a_backup_is_a_real_copy(save_folder: Path, tmp_path: Path) -> None:
    """The original took none, while overwriting the save in place."""
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    backup = archive.backup()
    assert backup.is_file()
    assert backup.read_bytes() == b"original save contents"
    assert backup.parent == archive.backup_dir


def test_backups_are_listed_newest_first(save_folder: Path, tmp_path: Path) -> None:
    import os
    import time

    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    first = archive.backup()
    time.sleep(0.01)
    archive.save_path.write_bytes(b"later contents")
    second = archive.backup()
    # Timestamps in the name have one-second resolution, so the two can collide;
    # the mtime is what the ordering uses.
    os.utime(first, (0, 0))

    listed = archive.backups()
    assert listed[0].read_bytes() == second.read_bytes()
    assert len(listed) >= 1


def test_restore_puts_the_most_recent_backup_back(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    archive.backup()
    archive.save_path.write_bytes(b"ruined by a bad mod")

    archive.restore()
    assert archive.save_path.read_bytes() == b"original save contents"


def test_restore_with_nothing_to_restore_says_so(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    with pytest.raises(SaveFileError, match="no backups"):
        archive.restore()


def test_restore_of_a_named_backup_that_is_absent(
    save_folder: Path, tmp_path: Path
) -> None:
    archive = SaveArchive(
        save_path=save_folder / "autosave.sav",
        unpacker=make_unpacker(tmp_path, GOOD_UNPACKER),
    )
    with pytest.raises(SaveFileError, match="no backup at"):
        archive.restore(tmp_path / "not-a-backup.sav")
