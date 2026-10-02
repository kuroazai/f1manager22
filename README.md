# f1manager22

Make an F1 Manager 2022 season race properly. The game ships with the three dry
compounds performing within about two percent of each other, so there is never a
reason to run anything but the softest, and following another car costs so much
that overtaking barely happens.

This spreads grip and durability apart, reduces dirty air, and sets driver
ratings from a profile file you can edit.

```bash
pip install -e .
f1m22 preview                 # see the numbers, no save and no setup needed
f1m22 apply --dry-run         # what it would change, save opened read-only
f1m22 apply                   # unpack, change, repack, keeping a backup
```

> **F1 Manager 2024?** Use [f1-manager-25](https://github.com/kuroazai/f1-manager-25)
> instead. This one is for the 2022 save format.

---

## What it changes

| Operation | What it does |
|---|---|
| `tyres` | Spreads grip and durability across the compounds, and sets the temperature and wear curves per compound |
| `aero` | Reduces dirty air, strengthens DRS and slipstream |
| `drivers` | Sets driver ratings from a profile file |
| `driver-buffs` | Maximises improvability and aggression |
| `equal-designs` | Flattens every part design stat |
| `equal-engines` | Flattens engine, ERS and gearbox designs |
| `equal-tracks` | Removes per-team track bias |
| `equal-pit-crew` | Levels every pit crew |
| `equal-expertise` | Levels every team's part expertise |
| `cash-infusion` | Adds to every team's balance |

Three presets, or pick operations by name:

```bash
f1m22 apply --preset racing          # just tyres and aero
f1m22 apply --preset full            # the original script's set
f1m22 apply --preset everything      # all ten
f1m22 apply --only tyres drivers     # exactly these
```

## The tyre model

This is the part that changes how a race feels, so the numbers are visible
before they go anywhere near a save:

```
$ f1m22 preview
tyres
compound          grip    life   heats   cools
soft             1.000   1.250   1.900   0.010
medium           0.900   1.387   1.950   0.050
hard             0.800   1.525   2.000   0.090
soft to hard: 0.200 grip given up for 0.275 life
```

Grip descends from soft to hard while durability ascends. That pairing is the
whole point: a soft tyre is fast and short-lived, a hard tyre slow and
long-lived, and a one-stop versus two-stop decision finally means something.

Tune it:

```bash
f1m22 preview --grip-spread 0.6 --life-spread 0.8    # a bigger trade-off
f1m22 preview --dirty-air 0.5                        # easier to follow
```

Settings are validated before anything is written. A negative spread, or a
spread wider than the base grip, is refused rather than silently inverting the
compounds so that the hard tyre becomes the fastest.

## Setting up

```bash
pip install -e ".[dev]"
cp .env.example .env
```

Then fill in two paths:

- `F1M22_SAVE_FOLDER` — on Windows, usually
  `C:\Users\<you>\Documents\My Games\F1 Manager 2022\Saved\SaveGames`
- `F1M22_UNPACKER` — xAranaktu's
  [SaveFile-Repacker](https://github.com/xAranaktu/F1-Manager-2022-SaveFile-Repacker).
  That is a separate project and is **not** included here. Download `script.py`
  from it and point at the file.

`f1m22 config` tells you whether both paths actually exist, which is a faster
way to find a typo than a stack trace.

Configuration comes from the environment, not from a file inside the package.
The original shipped a `config.py` you were told to edit, which conflicts on
every `git pull` and publishes your home directory path if you ever commit it
by habit.

## Your save

Every `apply` takes a timestamped backup before touching anything:

```bash
f1m22 backups      # list them, newest first
f1m22 restore      # put the most recent one back
f1m22 restore <name-of-a-backup>
```

`--dry-run` is a real dry run. The database is opened read-only, so a write is
refused by the connection rather than merely not attempted.

If the repack step fails after the database was edited, the original save is
still untouched and the message says where the edited `main.db` is.

## When it changes nothing

Every operation reports how many rows it touched, because a statement whose
WHERE clause matches nothing succeeds:

```
tyres: 5 row(s)
equal-tracks: 0 row(s)  <- changed nothing, check the schema
```

That almost always means a column or an ID moved between game patches. To find
out which:

```bash
f1m22 check
```

It compares your unpacked save against the schema the tool expects and names
every missing table and column, rather than failing on the first one.

## As a library

```python
from f1manager22 import Plan, SaveArchive, SaveDatabase, run, select

archive = SaveArchive(save_path="autosave.sav", unpacker="script.py")
with SaveDatabase(archive.unpack()) as database:
    for result in run(database, select(preset="racing"), Plan()):
        print(result)
archive.repack()
```

The tyre and aero models are pure arithmetic and touch no database at all:

```python
from f1manager22 import TyreSettings
print(TyreSettings(grip_spread=0.6).describe())
```

The original could not be used this way. One of its methods read an `ARGS`
global that only existed once `__main__` had run, so importing the class and
calling it raised `NameError`.

## Driver profiles

Twenty drivers at their career peak ship with the package. The format is plain
so it can be edited by hand:

```json
[{"driver": "Lewis Hamilton", "ID": "HAM", "cornering": 96, "braking": 95, ...}]
```

```bash
f1m22 apply --only drivers --profiles ./my-grid.json
```

`ID` is the three-letter FIA code. A profile missing a rating, carrying a
non-numeric one, or outside 1-100 is rejected before anything is applied,
because half a driver's ratings updated is worse than none: it looks fine and
races wrong.

A driver in the file but not in your save is reported and skipped. In the
original that reached `.fetchone()[0]` and ended the entire run with
`TypeError: 'NoneType' object is not subscriptable`.

## What was wrong with the original

It was one 459-line script. These are the defects, each one verified rather than
assumed:

**It could not be installed.** `requirements.txt` listed `sqlite3`, which is in
the standard library and not on PyPI, so `pip install -r requirements.txt`
failed on its first line. That was step 1 of the install instructions.

**`--save` did nothing.** The argument was declared, documented in the README,
and never read. The path was hardcoded to `autosave.sav` thirty lines further
down. `--load_season` and `--save_season` were declared and never read either.

**A save folder with a space in it broke the repack.** Commands were built by
string interpolation, and the repack command's last path was unquoted while the
unpack command's was quoted. The default Windows save path contains two spaces.
The database had already been rewritten by then, so you were left with a
modified `main.db` and a save that was never repacked.

**Nothing checked whether the unpacker worked.** `os.system` returns an exit
code and the return value was discarded, so a failed unpack was followed by
edits to whatever `main.db` happened to be lying around from a previous run.

**No backups**, while overwriting the save in place. The README said to make
them at your own discretion.

**`execute` never committed, and `commit` closed the connection.** So writes
went nowhere unless something later happened to commit, and committing twice
raised `ProgrammingError` on a closed cursor.

**Grip and durability were computed in the same direction.** Both were built as
descending series, and one of the two setters then called `values.reverse()` —
mutating the caller's list on the way through. So which way the trade-off ran
depended on which function you called.

**`update_design_stats` could not run.** It passed a list of different SQL
statements as the first argument to `executemany`, which takes one statement.

**`set_driver_data` used `os.getcwd()`** to find its data file, so it only
worked when run from the repository root.

**The shipped driver file had one bad ID.** Nineteen drivers used their
three-letter code; Mick Schumacher's was `"Schumacher"`, which becomes
`[DriverCode_Schumacher]` and matches nothing. Combined with the `.fetchone()[0]`
above, the driver step could never complete.

**`config.py` was a tracked file you had to edit**, and the equivalent mistake
in another of these repositories leaked a Windows username and a Firefox
profile ID.

**xAranaktu's `script.py` was committed** into a repository whose LICENSE reads
`MIT License, Copyright (c) 2023 kuroazai`, while the README correctly told you
to download it yourself. It has been removed; the tool points at your copy.

**A nonexistent Django editor** was advertised in the README.

## Layout

```
src/f1manager22/
├── cli.py          the commands; every writing one has --dry-run
├── config.py       settings from the environment, not from a tracked file
├── db.py           SaveDatabase: explicit transactions, commit does not close
├── enums.py        the game's IDs, declared once
├── schema.py       the tables and columns used; builds the test save, and
│                   backs `f1m22 check`
├── savefile.py     unpack and repack via the external tool, with backups
├── tyres.py        the tyre and aero arithmetic; touches no database
├── drivers.py      profile parsing and validation
├── operations.py   the ten changes, each named and self-describing
└── data/           the bundled driver profiles
```

## Development

```bash
pip install -e ".[dev]"
pytest              # 112 tests
ruff check src tests
mypy
```

No test needs the game, a save file, or the unpacker. The suite builds a SQLite
database from `f1manager22.schema` and stubs the unpacker with a small script,
so every statement runs against real SQLite and every path is exercised,
including one with a space in it.

What that proves and what it does not: it proves each statement is valid SQL,
targets columns that exist, matches the rows it intends to, and leaves the values
it claims. It does not prove the column names match a real 2022 save, which can
only be checked against one. `f1m22 check` is the tool for that.

CI runs on Windows as well as Linux, because that is where this tool runs and
because the last bug it caught was a path containing a space.

## Credits

Save unpacking and repacking is
[xAranaktu/F1-Manager-2022-SaveFile-Repacker](https://github.com/xAranaktu/F1-Manager-2022-SaveFile-Repacker),
a separate project. Download it yourself; it is not redistributed here.

## Licence

MIT. See [LICENSE](LICENSE). The licence covers this repository's own code only.
