# AGENTS.md

Notes for anyone, human or otherwise, changing this code.

## What this is

A save editor for F1 Manager 2022. The save is a packed container; editing it
means unpacking to a folder, changing a SQLite `main.db`, and packing it back.

The arithmetic is separate from the SQL on purpose. `tyres.py` computes numbers
and touches no database, `operations.py` writes them. That is why `f1m22 preview`
works with no save, no configuration and no game installed, and why the model
can be tested without any of them.

## Start here

```bash
pip install -e ".[dev]"
pytest
f1m22 preview
```

`f1m22 preview` is the fastest way to see what the tool does. It needs nothing.

## The rules that matter

**Back up before writing. Always.** The thing being edited is someone's season.
`apply` calls `archive.backup()` before `repack`, and that ordering is not
negotiable. The original took no backups at all while overwriting in place.

**Never build a shell command from a string.** Use `subprocess.run` with an
argument list, as `savefile.py` does. The original interpolated paths into an
`os.system` string and forgot to quote one of them, so the default Windows save
path, which contains spaces, failed at the repack step after the database had
already been rewritten. There is a test with a space in the path; keep it.

**Check the exit code of anything external.** `os.system`'s return value was
discarded, so a failed unpack was followed by edits to a stale `main.db` from a
previous run. `_run` raises on a non-zero exit, and `unpack` additionally
verifies the database actually appeared.

**Return the row count from every write.** A statement whose WHERE matches
nothing succeeds. Without the count, an operation that silently does nothing
looks identical to one that worked, which is how the 2024 version of this tool
skipped four part stats for years. `Result.changed_nothing` surfaces it.

**`commit` commits. `close` closes.** They are separate. The original's `commit`
closed the cursor and the connection, so you could not commit twice and could
not keep working after saving.

**A dry run must be unable to write.** `SaveDatabase(..., read_only=True)`
refuses writes at the connection, rather than the caller remembering not to.

**Validate before touching the save.** `TyreSettings.__post_init__` and
`AeroSettings.__post_init__` reject nonsense, `require_tables` checks every
table all the operations need before any one of them runs. Half-edited is the
worst outcome available.

**No globals.** Everything an operation needs arrives in a `Plan`. The original
read an `ARGS` module global from inside a method, so the class could only be
used by running the script.

**Output is ASCII.** A pound sign or an em-dash crashes a legacy Windows console
code page, and this is a tool people run on Windows from a terminal.

**3.10 is the floor.** `requires-python` says `>=3.10`, so no `datetime.UTC`,
`StrEnum` or `tomllib`. mypy is pinned to 3.10 here and will catch it, which it
can do in this package because there are no third-party stubs to get in the way.

## Secrets and other people's code

**Configuration lives in the environment.** `.env` is gitignored and
`.env.example` has blank values. Do not add a tracked file anyone is expected to
edit; the original's `config.py` conflicted on every pull, and the same pattern
in another of these repositories published a Windows username and a Firefox
profile ID.

**The unpacker is not ours.** xAranaktu's `script.py` was previously committed
into this repository, under a LICENSE reading `Copyright (c) 2023 kuroazai`.
It is gone. The tool points at the user's own copy and the README says where to
get it. Do not vendor it back in.

**Nothing from a save folder goes in the repository.** `.gitignore` covers
`*.sav`, `result/`, `main.db` and `f1m22-backups/`.

## Testing

```bash
pytest
ruff check src tests
mypy
```

Everything runs offline with no game installed. Two fixtures make that work:

`tests/conftest.py` builds a SQLite save from `f1manager22.schema`, which is the
schema as the queries themselves use it. Every operation runs against real
SQLite, so invalid SQL and misspelled columns fail loudly.

`tests/test_savefile.py` stubs the unpacker with a few lines of Python, in three
flavours: one that works, one that exits zero and produces nothing, and one that
fails with a message. All three happen in the wild.

**The schema fixture has a limit, and it matters.** It proves the SQL is valid
and hits the rows it means to. It cannot prove the column names match a real
2022 save, because that needs a real save. `f1m22 check` exists for that, and if
you add a column to `schema.py`, you are asserting a real save has it.

**When you add an operation**, add it to `OPERATIONS`, declare the tables it
touches, and make sure `test_every_preset_runs_clean` still passes. That test
asserts every operation changes at least one row against the fixture, so a
statement that matches nothing fails the build rather than shipping.

## Things that look like bugs and are not

- `cash-infusion` has no WHERE clause. Every team is meant to get the money. It
  adds rather than assigns, so the season's finances are preserved; assigning
  would flatten all eleven balances to one number, which is what the same
  statement did wrong in the 2024 version.
- `aero` updates its whole table without a WHERE. `Parts_RaceSimConstants` is a
  single row of global settings, not per-team values.
- `dirty_air` is the total reduction shared across the three speed bands in
  proportion to their stock values, not a fraction taken off each. With the
  stock 0.98 everywhere, `0.30` removes `0.10` from each. There is a test
  pinning this, because it reads like a per-band fraction and is not.
- `suspicious_codes` warns rather than raising. A future game version could use
  something other than a three-letter code, so it is reported, not enforced.
- `Result.changed_nothing` is False during a dry run. Zero rows is the expected
  answer there, and warning about it trained people to ignore the warning.
