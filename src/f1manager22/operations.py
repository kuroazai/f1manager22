"""The changes, each one named and self-describing.

The original was a list of method calls at the bottom of a script. You got all
of them or you edited the file. There was no way to see what a change would do
before it did it, and no way to apply only the tyre changes.

Here each change is an `Operation` with a name, a description and an `apply`
that returns how many rows it touched. That gives three things for free: a
`--dry-run` that explains itself, selecting operations by name, and a row count
that tells you whether a WHERE clause actually matched anything.

Every operation declares the tables it needs, so a save from the wrong game
version fails up front with a list rather than part way through.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .db import SaveDatabase
from .drivers import DriverProfile, load_profiles, suspicious_codes
from .enums import Table, TyreCompound
from .tyres import AeroSettings, TyreSettings


@dataclass
class Result:
    """What an operation did."""

    name: str
    rows: int
    notes: list[str] = field(default_factory=list)
    #: A dry run reports zero rows by design, so it must not be mistaken for a
    #: statement that matched nothing.
    dry_run: bool = False

    @property
    def changed_nothing(self) -> bool:
        """Worth surfacing. A statement that matches no rows still succeeds, so
        a zero here usually means a column or ID changed between versions.

        False for a dry run, where zero is the expected and correct answer.
        """
        return self.rows == 0 and not self.dry_run

    def __str__(self) -> str:
        line = self.name if self.dry_run else f"{self.name}: {self.rows} row(s)"
        if self.changed_nothing:
            line += "  <- changed nothing, check the schema"
        return "\n".join([line] + [f"    {note}" for note in self.notes])


@dataclass(frozen=True)
class Operation:
    """One change to a save."""

    name: str
    description: str
    tables: tuple[str, ...]
    apply: Callable[[SaveDatabase, Plan], Result]

    def preview(self, plan: Plan) -> str:
        """What it would do, without a database."""
        return f"{self.name:<18} {self.description}"


@dataclass
class Plan:
    """Everything the operations need, in one place.

    Passed to each operation rather than read from module-level globals. The
    original referenced an `ARGS` global from inside a method, so importing the
    class and calling it raised `NameError` unless `__main__` had happened to
    run first. It could only be used as a script.
    """

    tyres: TyreSettings = field(default_factory=TyreSettings)
    aero: AeroSettings = field(default_factory=AeroSettings)
    profiles_path: Path | None = None
    cash_infusion: int = 500_000_000
    equal_design_unit_value: int = 25
    equal_engine_unit_value: int = 100
    pit_crew_rating: float = 100.0
    team_expertise: int = 1000
    driver_improvability: int = 100
    driver_aggression: int = 100

    _profiles: list[DriverProfile] | None = field(default=None, repr=False)

    def profiles(self) -> list[DriverProfile]:
        """Driver profiles, loaded once."""
        if self._profiles is None:
            if self.profiles_path is None:
                raise ValueError("no driver profile file configured")
            self._profiles = load_profiles(self.profiles_path)
        return self._profiles


# -- helpers ---------------------------------------------------------------

def _set_columns(
    database: SaveDatabase, table: str, values: dict[str, float], where: str = ""
) -> int:
    """UPDATE one table's columns, checking the columns exist first.

    The check matters because SQLite raises on an unknown column, and the error
    names the column but not which of the eleven tables was meant. Verifying up
    front lets the message say both.
    """
    present = set(database.columns(table))
    unknown = [name for name in values if name not in present]
    if unknown:
        raise KeyError(
            f"{table} has no column(s) {', '.join(sorted(unknown))}. "
            f"It has: {', '.join(sorted(present))}"
        )

    assignments = ", ".join(f'"{name}" = ?' for name in values)
    clause = f" WHERE {where}" if where else ""
    return database.execute(
        f'UPDATE "{table}" SET {assignments}{clause}', tuple(values.values())
    )


# -- the operations --------------------------------------------------------

def _apply_tyres(database: SaveDatabase, plan: Plan) -> Result:
    """Grip, durability and the temperature curve, per compound.

    Written per compound with a WHERE, rather than as a table-wide UPDATE
    followed by per-row corrections. The original did the latter, which meant
    the result depended on the order the setters were called in, and a reordering
    would have silently flattened the compounds.
    """
    rows = 0
    notes = []
    columns = set(database.columns(str(Table.TYRES)))
    for compound, values in plan.tyres.plan().items():
        unknown = [name for name in values if name not in columns]
        if unknown:
            raise KeyError(
                f"{Table.TYRES} has no column(s) {', '.join(sorted(unknown))}. "
                f"It has: {', '.join(sorted(columns))}"
            )
        # Issued directly rather than through _set_columns, because the WHERE
        # needs the compound bound after the SET values.
        changed = database.execute(
            f'UPDATE "{Table.TYRES}" SET '
            + ", ".join(f'"{name}" = ?' for name in values)
            + " WHERE Type = ?",
            (*values.values(), int(compound)),
        )
        rows += changed
        if changed == 0:
            notes.append(f"no row for {compound.name.lower()} (Type = {int(compound)})")
    notes.insert(0, f"soft grip {plan.tyres.grip_for(TyreCompound.SOFT):.3f} "
                    f"-> hard grip {plan.tyres.grip_for(TyreCompound.HARD):.3f}")
    return Result("tyres", rows, notes)


def _apply_aero(database: SaveDatabase, plan: Plan) -> Result:
    """Dirty air, DRS and slipstream.

    One statement for the whole table, which is correct here: the race
    constants are a single row of global settings, not per-team values.
    """
    values = plan.aero.plan()
    rows = _set_columns(database, str(Table.RACE_CONSTANTS), values)
    return Result("aero", rows, [
        f"dirty air {plan.aero.dirty_air:.0%} loss, DRS {plan.aero.drs}, "
        f"slipstream {plan.aero.slipstream}"
    ])


def _apply_drivers(database: SaveDatabase, plan: Plan) -> Result:
    """Driver ratings from the profile file.

    Drivers absent from the save are collected and reported rather than
    crashing. The original did `.fetchone()[0]`, so one driver missing from your
    save ended the run with a TypeError that said nothing about drivers.
    """
    rows = 0
    missing = []
    for profile in plan.profiles():
        staff_id = database.scalar(
            f'SELECT StaffID FROM "{Table.DRIVERS}" WHERE DriverCode = ?',
            (profile.save_code,),
        )
        if staff_id is None:
            missing.append(f"{profile.name} ({profile.code})")
            continue

        rows += database.execute_many(
            f'UPDATE "{Table.DRIVER_STATS}" SET Val = ? '
            "WHERE StaffID = ? AND StatID = ?",
            [(value, staff_id, int(stat)) for stat, value in profile.ratings.items()],
        )

    notes = [f"{len(plan.profiles()) - len(missing)} driver(s) updated"]
    if missing:
        notes.append(f"not in this save: {', '.join(missing)}")
        odd = suspicious_codes([p for p in plan.profiles()
                                if f"{p.name} ({p.code})" in missing])
        if odd:
            notes.append(
                "and these IDs are not three-letter codes, which is the likely "
                "reason: " + ", ".join(odd)
            )
    return Result("drivers", rows, notes)


def _apply_equal_designs(database: SaveDatabase, plan: Plan) -> Result:
    """Flatten every part design, so no team starts with better hardware."""
    unit = plan.equal_design_unit_value
    rows = _set_columns(
        database, str(Table.DESIGN_STATS),
        {"UnitValue": unit, "Value": unit * 10},
    )
    return Result("equal-designs", rows, [f"every design stat to {unit}"])


def _apply_equal_engines(database: SaveDatabase, plan: Plan) -> Result:
    """Flatten engine, ERS and gearbox designs across manufacturers.

    The original built a self-referential subquery, `WHERE DesignID = ? AND
    StatID IN (SELECT StatID FROM Parts_DesignStatValues WHERE DesignID = ?)`,
    which is just `WHERE DesignID = ?` with extra steps. It also appended a
    separate query string per design and then zipped them against parameters.
    One statement over the collected IDs does the same work.
    """
    manufacturers = database.query(
        f'SELECT EngineDesignID, ErsDesignID, GearboxDesignID '
        f'FROM "{Table.ENGINE_MANUFACTURERS}"'
    )
    design_ids = sorted({
        value
        for row in manufacturers
        for value in (row["EngineDesignID"], row["ErsDesignID"], row["GearboxDesignID"])
        if value is not None
    })
    if not design_ids:
        return Result("equal-engines", 0, ["no engine manufacturers in this save"])

    unit = plan.equal_engine_unit_value
    rows = database.execute_many(
        f'UPDATE "{Table.DESIGN_STATS}" SET UnitValue = ?, Value = ? WHERE DesignID = ?',
        [(unit, unit * 10, design_id) for design_id in design_ids],
    )
    return Result("equal-engines", rows,
                  [f"{len(design_ids)} design(s) across "
                   f"{len(manufacturers)} manufacturer(s) to {unit}"])


def _apply_equal_tracks(database: SaveDatabase, plan: Plan) -> Result:
    """Remove per-team track bias, so a circuit suits everyone equally."""
    rows = _set_columns(database, str(Table.TRACK_PERFORMANCE), {
        "Straights": 1.0, "SlowCorners": 1.0,
        "MediumCorners": 1.0, "FastCorners": 1.0,
    })
    return Result("equal-tracks", rows)


def _apply_equal_pit_crew(database: SaveDatabase, plan: Plan) -> Result:
    rows = _set_columns(database, str(Table.PIT_CREW_STATS),
                        {"Val": plan.pit_crew_rating})
    return Result("equal-pit-crew", rows, [f"every pit crew stat to {plan.pit_crew_rating}"])


def _apply_equal_expertise(database: SaveDatabase, plan: Plan) -> Result:
    expertise = plan.team_expertise
    rows = _set_columns(database, str(Table.TEAM_EXPERTISE), {
        "Expertise": expertise, "SeasonStartExpertise": expertise,
    })
    return Result("equal-expertise", rows, [f"every team to {expertise}"])


def _apply_driver_buffs(database: SaveDatabase, plan: Plan) -> Result:
    """Make every driver develop, and race, aggressively."""
    rows = _set_columns(database, str(Table.DRIVERS), {
        "Improvability": plan.driver_improvability,
        "Aggression": plan.driver_aggression,
    })
    return Result("driver-buffs", rows)


def _apply_cash_infusion(database: SaveDatabase, plan: Plan) -> Result:
    """Give every team money.

    No WHERE, deliberately, and unlike the same statement in the 2024 version of
    this tool where the missing WHERE was a bug. Here every team is meant to get
    it, which is why the amount is added rather than assigned: assigning would
    set all eleven teams to an identical balance and erase the season so far.
    """
    rows = database.execute(
        f'UPDATE "{Table.TEAM_BALANCE}" SET Balance = Balance + ?',
        (plan.cash_infusion,),
    )
    return Result("cash-infusion", rows,
                  [f"+{plan.cash_infusion:,} to each of {rows} team(s)"])


OPERATIONS: tuple[Operation, ...] = (
    Operation("tyres", "Spread grip and durability across the compounds",
              (str(Table.TYRES),), _apply_tyres),
    Operation("aero", "Reduce dirty air, strengthen DRS and slipstream",
              (str(Table.RACE_CONSTANTS),), _apply_aero),
    Operation("drivers", "Set driver ratings from the profile file",
              (str(Table.DRIVERS), str(Table.DRIVER_STATS)), _apply_drivers),
    Operation("driver-buffs", "Maximise driver improvability and aggression",
              (str(Table.DRIVERS),), _apply_driver_buffs),
    Operation("equal-designs", "Flatten every part design stat",
              (str(Table.DESIGN_STATS),), _apply_equal_designs),
    Operation("equal-engines", "Flatten engine, ERS and gearbox designs",
              (str(Table.ENGINE_MANUFACTURERS), str(Table.DESIGN_STATS)),
              _apply_equal_engines),
    Operation("equal-tracks", "Remove per-team track bias",
              (str(Table.TRACK_PERFORMANCE),), _apply_equal_tracks),
    Operation("equal-pit-crew", "Level every pit crew",
              (str(Table.PIT_CREW_STATS),), _apply_equal_pit_crew),
    Operation("equal-expertise", "Level every team's part expertise",
              (str(Table.TEAM_EXPERTISE),), _apply_equal_expertise),
    Operation("cash-infusion", "Add to every team's balance",
              (str(Table.TEAM_BALANCE),), _apply_cash_infusion),
)

BY_NAME = {operation.name: operation for operation in OPERATIONS}

#: What the original script applied, in its order. Kept as a named set so the
#: documented behaviour has not changed for anyone who used it.
PRESET_FULL = (
    "equal-designs", "equal-tracks", "equal-engines", "aero",
    "tyres", "drivers", "cash-infusion",
)
#: Just the racing, no economy or stat levelling. The tyre and aero changes are
#: what actually alter how a race plays out.
PRESET_RACING = ("tyres", "aero")
#: Everything, including the levelling the original left commented out.
PRESET_EVERYTHING = tuple(BY_NAME)

PRESETS = {
    "full": PRESET_FULL,
    "racing": PRESET_RACING,
    "everything": PRESET_EVERYTHING,
}


def select(names: list[str] | None = None, preset: str = "full") -> list[Operation]:
    """Resolve names or a preset into operations, in a defined order."""
    if names:
        unknown = [name for name in names if name not in BY_NAME]
        if unknown:
            raise KeyError(
                f"unknown operation(s): {', '.join(unknown)}. Available: "
                + ", ".join(BY_NAME)
            )
        return [BY_NAME[name] for name in names]

    if preset not in PRESETS:
        raise KeyError(
            f"unknown preset {preset!r}. Available: " + ", ".join(PRESETS)
        )
    return [BY_NAME[name] for name in PRESETS[preset]]


def run(
    database: SaveDatabase,
    operations: list[Operation],
    plan: Plan,
    *,
    dry_run: bool = False,
) -> list[Result]:
    """Apply operations, or report what they would do.

    Required tables are checked for all of them before any one runs, so a save
    from the wrong version does not get half-edited.
    """
    required = sorted({table for op in operations for table in op.tables})
    database.require_tables(*required)

    if dry_run:
        return [
            Result(op.name, 0, [f"would: {op.description}"], dry_run=True)
            for op in operations
        ]

    results = []
    for operation in operations:
        results.append(operation.apply(database, plan))
    return results
