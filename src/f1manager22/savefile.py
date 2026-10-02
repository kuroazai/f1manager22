"""Unpacking and repacking a save, and not losing it.

The save is a packed container. Editing it means unpacking to a folder, changing
`main.db`, and packing it back. The unpacker is xAranaktu's `F1-Manager-2022-
SaveFile-Repacker`, which is a separate project and is not redistributed here;
you download it and point at it.

Three things went wrong in the original, and all three could cost you a season:

**It built shell commands by string interpolation.** `os.system(f'python
"{script}" --operation repack --result "{save}" --input {result}')`. The last
path is unquoted while the others are quoted, so a save folder containing a
space, which is the default on Windows, fails at the repack step. The database
has already been rewritten by then, so you are left with a modified `main.db`
and a save that was never repacked.

**It never checked whether anything worked.** `os.system` returns an exit code
and the return value was discarded, so a failed unpack was followed by edits to
whatever `main.db` happened to be lying around from last time.

**It took no backup**, while overwriting the save in place. The README said to
make backups at your own discretion.

Here: `subprocess.run` with an argument list, so quoting is not a thing that can
be got wrong; the exit code is checked; and a timestamped backup is taken before
the save is touched.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: Where the unpacker writes, relative to the save folder.
RESULT_DIRNAME = "result"
#: The database inside that folder.
MAIN_DB = "main.db"
#: Backups go here, beside the save.
BACKUP_DIRNAME = "f1m22-backups"
#: Generous, because repacking a late-season save is not instant.
DEFAULT_TIMEOUT = 300.0


class SaveFileError(RuntimeError):
    """The save, or the unpacker, is not where it should be."""


@dataclass
class SaveArchive:
    """One save file, and the tool that unpacks it."""

    save_path: Path
    unpacker: Path
    timeout: float = DEFAULT_TIMEOUT
    python: str = sys.executable

    def __post_init__(self) -> None:
        self.save_path = Path(self.save_path)
        self.unpacker = Path(self.unpacker)

    # -- paths -------------------------------------------------------------
    @property
    def folder(self) -> Path:
        return self.save_path.parent

    @property
    def result_dir(self) -> Path:
        return self.folder / RESULT_DIRNAME

    @property
    def database_path(self) -> Path:
        return self.result_dir / MAIN_DB

    @property
    def backup_dir(self) -> Path:
        return self.folder / BACKUP_DIRNAME

    # -- checks ------------------------------------------------------------
    def check(self) -> None:
        """Everything needed, verified before anything is modified."""
        problems = []
        if not self.save_path.is_file():
            problems.append(f"no save file at {self.save_path}")
        if not self.unpacker.is_file():
            problems.append(
                f"no unpacker at {self.unpacker}. Download script.py from "
                "https://github.com/xAranaktu/F1-Manager-2022-SaveFile-Repacker "
                "and point F1M22_UNPACKER at it"
            )
        if problems:
            raise SaveFileError("; ".join(problems))

    # -- backups -----------------------------------------------------------
    def backup(self) -> Path:
        """Copy the save aside, named by the time, and return where it went.

        Taken before every write. The whole point of this tool is editing
        something you have spent hours on.
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self.backup_dir / f"{self.save_path.stem}-{stamp}{self.save_path.suffix}"
        shutil.copy2(self.save_path, destination)
        return destination

    def backups(self) -> list[Path]:
        """Existing backups, newest first."""
        if not self.backup_dir.is_dir():
            return []
        return sorted(
            (p for p in self.backup_dir.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def restore(self, backup: str | Path | None = None) -> Path:
        """Put a backup back. Without an argument, the most recent one."""
        if backup is None:
            available = self.backups()
            if not available:
                raise SaveFileError(f"no backups in {self.backup_dir}")
            chosen = available[0]
        else:
            chosen = Path(backup)
            if not chosen.is_file():
                raise SaveFileError(f"no backup at {chosen}")

        shutil.copy2(chosen, self.save_path)
        return chosen

    # -- the external tool -------------------------------------------------
    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """Call the unpacker as an argument list.

        A list, never a shell string. Paths with spaces, brackets and ampersands
        all go through untouched, and nothing is interpreted by a shell.
        """
        command = [self.python, str(self.unpacker), *arguments]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SaveFileError(
                f"the unpacker did not finish within {self.timeout:.0f}s"
            ) from exc
        except OSError as exc:
            raise SaveFileError(f"could not run the unpacker: {exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise SaveFileError(
                f"the unpacker failed (exit {completed.returncode})"
                + (f": {detail[:500]}" if detail else "")
            )
        return completed

    def unpack(self) -> Path:
        """Unpack the save and return the path to its database."""
        self.check()
        self._run("--operation", "unpack",
                  "--input", str(self.save_path),
                  "--result", str(self.result_dir))

        if not self.database_path.is_file():
            # The tool exited zero without producing a database, which means it
            # did not understand the save. Editing a stale main.db from a
            # previous run is exactly the failure this prevents.
            raise SaveFileError(
                f"the unpacker reported success but there is no {MAIN_DB} in "
                f"{self.result_dir}. Is {self.save_path.name} an F1 Manager 2022 save?"
            )
        return self.database_path

    def repack(self) -> Path:
        """Pack the edited folder back into the save."""
        if not self.database_path.is_file():
            raise SaveFileError(
                f"nothing to repack: no {MAIN_DB} in {self.result_dir}"
            )
        self._run("--operation", "repack",
                  "--result", str(self.save_path),
                  "--input", str(self.result_dir))
        return self.save_path

    def describe(self) -> str:
        lines = [
            f"save      {self.save_path}",
            f"unpacker  {self.unpacker}",
            f"database  {self.database_path}"
            + ("" if self.database_path.is_file() else "  (not unpacked)"),
        ]
        existing = self.backups()
        lines.append(
            f"backups   {len(existing)} in {self.backup_dir}"
            if existing else f"backups   none yet, will go in {self.backup_dir}"
        )
        return "\n".join(lines)
