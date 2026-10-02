"""The operations, against a synthetic save.

Each test checks the rows actually changed, not just that the call returned.
A statement whose WHERE matches nothing succeeds, which is how the original's
part-stat loop skipped four stats for years without anyone noticing.
"""
from __future__ import annotations

import pytest

from f1manager22 import operations as ops
from f1manager22.db import SaveDatabase, SaveDatabaseError
from f1manager22.enums import DriverStat, TyreCompound


def test_every_operation_has_a_name_and_description() -> None:
    assert len(ops.OPERATIONS) == len(ops.BY_NAME)
    for operation in ops.OPERATIONS:
        assert operation.name
        assert operation.description
        assert operation.tables


def test_presets_only_name_real_operations() -> None:
    for name, members in ops.PRESETS.items():
        unknown = [m for m in members if m not in ops.BY_NAME]
        assert not unknown, f"preset {name} names {unknown}"


def test_selecting_an_unknown_operation_lists_the_real_ones() -> None:
    with pytest.raises(KeyError, match="tyres"):
        ops.select(["nonsense"])


def test_selecting_an_unknown_preset_lists_the_real_ones() -> None:
    with pytest.raises(KeyError, match="full"):
        ops.select(preset="nonsense")


# -- tyres -----------------------------------------------------------------

def test_tyres_spreads_grip_and_durability(database: SaveDatabase, plan) -> None:
    """Stock, the three dry compounds are within 0.02 of each other, so there is
    no reason to run anything but the softest."""
    before = {r["Type"]: r["Grip"] for r in
              database.query("SELECT Type, Grip FROM Tyres")}
    assert max(before.values()) - min(before.values()) < 0.2

    result = ops.run(database, ops.select(["tyres"]), plan)[0]
    assert result.rows == len(TyreCompound)

    rows = database.query("SELECT Type, Grip, Durability FROM Tyres ORDER BY Type")
    grips = [r["Grip"] for r in rows]
    lives = [r["Durability"] for r in rows]

    assert grips == sorted(grips, reverse=True)
    assert lives == sorted(lives)
    assert grips[0] - grips[-1] == pytest.approx(plan.tyres.grip_spread)


def test_tyres_writes_the_temperature_curve(database: SaveDatabase, plan) -> None:
    ops.run(database, ops.select(["tyres"]), plan)
    soft, hard = database.query(
        "SELECT TempIncRate FROM Tyres WHERE Type IN (?, ?) ORDER BY Type",
        (int(TyreCompound.SOFT), int(TyreCompound.HARD)),
    )
    assert soft["TempIncRate"] < hard["TempIncRate"]


def test_tyres_names_a_column_that_does_not_exist(
    database: SaveDatabase, plan
) -> None:
    """A real 2022 save from a different patch is the likely cause, and the
    error should say which column rather than just failing."""
    database.execute("ALTER TABLE Tyres RENAME COLUMN MinOptimalGrip TO Gone")
    database.commit()
    with pytest.raises(KeyError, match="MinOptimalGrip"):
        ops.run(database, ops.select(["tyres"]), plan)


# -- aero ------------------------------------------------------------------

def test_aero_reduces_dirty_air_and_pins_drs(database: SaveDatabase, plan) -> None:
    result = ops.run(database, ops.select(["aero"]), plan)[0]
    assert result.rows == 1

    row = database.query_one("SELECT * FROM Parts_RaceSimConstants")
    assert row["DirtyAirLowSpeedMultiplier"] < 0.98
    assert row["MinDRSAccelerationMultiplier"] == 1.0
    assert row["MaxDRSTopSpeedMultiplier"] == pytest.approx(plan.aero.drs)


# -- drivers ---------------------------------------------------------------

def test_drivers_applies_every_rating(database: SaveDatabase, plan) -> None:
    profiles = {p.code: p for p in plan.profiles()}
    result = ops.run(database, ops.select(["drivers"]), plan)[0]

    assert result.rows == len(profiles) * len(DriverStat)

    staff_id = database.scalar(
        "SELECT StaffID FROM Staff_DriverData WHERE DriverCode = ?",
        ("[DriverCode_Ham]",),
    )
    applied = {
        row["StatID"]: row["Val"]
        for row in database.query(
            "SELECT StatID, Val FROM Staff_PerformanceStats WHERE StaffID = ?",
            (staff_id,),
        )
    }
    for stat, expected in profiles["HAM"].ratings.items():
        assert applied[int(stat)] == expected


def test_a_driver_not_in_the_save_is_reported_not_fatal(
    save_path, plan, tmp_path
) -> None:
    """The original crashed on `.fetchone()[0]` here, so one unknown driver code
    ended the whole run."""
    with SaveDatabase(save_path) as database:
        database.execute(
            "DELETE FROM Staff_DriverData WHERE DriverCode = ?",
            ("[DriverCode_Ham]",),
        )

    with SaveDatabase(save_path) as database:
        result = ops.run(database, ops.select(["drivers"]), plan)[0]

    assert result.rows > 0  # the other nineteen still applied
    assert any("not in this save" in note for note in result.notes)
    assert any("Hamilton" in note for note in result.notes)


# -- levelling -------------------------------------------------------------

def test_equal_designs_flattens_every_design(database: SaveDatabase, plan) -> None:
    before = database.query("SELECT DISTINCT UnitValue FROM Parts_DesignStatValues")
    assert len(before) > 1

    ops.run(database, ops.select(["equal-designs"]), plan)
    after = database.query("SELECT DISTINCT UnitValue FROM Parts_DesignStatValues")
    assert len(after) == 1
    assert after[0]["UnitValue"] == plan.equal_design_unit_value


def test_equal_engines_covers_every_manufacturer(
    database: SaveDatabase, plan
) -> None:
    """The original built a subquery that reduced to `WHERE DesignID = ?` and
    then zipped a list of identical statements against parameters."""
    result = ops.run(database, ops.select(["equal-engines"]), plan)[0]
    assert result.rows > 0

    design_ids = {
        value
        for row in database.query(
            "SELECT EngineDesignID, ErsDesignID, GearboxDesignID "
            "FROM Parts_Enum_EngineManufacturers"
        )
        for value in row
    }
    for design_id in design_ids:
        values = database.query(
            "SELECT DISTINCT UnitValue FROM Parts_DesignStatValues WHERE DesignID = ?",
            (design_id,),
        )
        assert [v["UnitValue"] for v in values] == [plan.equal_engine_unit_value]


def test_equal_engines_with_no_manufacturers_says_so(
    database: SaveDatabase, plan
) -> None:
    database.execute("DELETE FROM Parts_Enum_EngineManufacturers")
    result = ops.run(database, ops.select(["equal-engines"]), plan)[0]
    assert result.changed_nothing
    assert any("no engine manufacturers" in note for note in result.notes)


def test_equal_tracks_removes_every_bias(database: SaveDatabase, plan) -> None:
    ops.run(database, ops.select(["equal-tracks"]), plan)
    rows = database.query(
        "SELECT DISTINCT Straights, SlowCorners, MediumCorners, FastCorners "
        "FROM Races_TeamPerformance"
    )
    assert len(rows) == 1
    assert all(value == 1.0 for value in rows[0])


def test_equal_pit_crew_and_expertise(database: SaveDatabase, plan) -> None:
    ops.run(database, ops.select(["equal-pit-crew", "equal-expertise"]), plan)

    crew = database.query("SELECT DISTINCT Val FROM Staff_PitCrew_PerformanceStats")
    assert [c["Val"] for c in crew] == [plan.pit_crew_rating]

    expertise = database.query("SELECT DISTINCT Expertise FROM Parts_TeamExpertise")
    assert [e["Expertise"] for e in expertise] == [plan.team_expertise]


def test_driver_buffs_applies_to_everyone(database: SaveDatabase, plan) -> None:
    result = ops.run(database, ops.select(["driver-buffs"]), plan)[0]
    total = database.scalar("SELECT COUNT(*) FROM Staff_DriverData")
    assert result.rows == total


# -- money -----------------------------------------------------------------

def test_cash_infusion_adds_and_does_not_flatten(
    database: SaveDatabase, plan
) -> None:
    """Adding, not assigning. Assigning would set all teams to one balance and
    erase the season's finances, which is what the same statement did wrong in
    the 2024 version of this tool."""
    before = {
        row["TeamID"]: row["Balance"]
        for row in database.query("SELECT TeamID, Balance FROM Finance_TeamBalance")
    }
    assert len(set(before.values())) > 1

    ops.run(database, ops.select(["cash-infusion"]), plan)

    after = {
        row["TeamID"]: row["Balance"]
        for row in database.query("SELECT TeamID, Balance FROM Finance_TeamBalance")
    }
    assert len(set(after.values())) > 1, "balances were flattened"
    for team, balance in before.items():
        assert after[team] == balance + plan.cash_infusion


# -- running ---------------------------------------------------------------

def test_a_dry_run_changes_nothing(database: SaveDatabase, plan) -> None:
    before = database.query("SELECT * FROM Tyres ORDER BY Type")
    results = ops.run(database, ops.select(preset="everything"), plan, dry_run=True)

    assert all(r.rows == 0 for r in results)
    assert all(any("would" in note for note in r.notes) for r in results)
    # Zero rows is the point of a dry run, so it must not be reported as a
    # statement that failed to match anything.
    assert not any(r.changed_nothing for r in results)
    assert all("check the schema" not in str(r) for r in results)
    assert [tuple(r) for r in database.query("SELECT * FROM Tyres ORDER BY Type")] == \
           [tuple(r) for r in before]


def test_a_missing_table_stops_everything_before_anything_runs(
    database: SaveDatabase, plan
) -> None:
    """Half-edited is the outcome to avoid."""
    before = database.scalar("SELECT Grip FROM Tyres WHERE Type = 0")
    database.execute("DROP TABLE Parts_RaceSimConstants")
    database.commit()

    with pytest.raises(SaveDatabaseError, match="Parts_RaceSimConstants"):
        ops.run(database, ops.select(["tyres", "aero"]), plan)

    assert database.scalar("SELECT Grip FROM Tyres WHERE Type = 0") == before


def test_every_preset_runs_clean(database: SaveDatabase, plan) -> None:
    """Each operation must touch at least one row against the schema fixture.
    A zero here means a statement that matches nothing."""
    results = ops.run(database, ops.select(preset="everything"), plan)
    empty = [r.name for r in results if r.changed_nothing]
    assert not empty, f"these changed nothing: {empty}"


def test_operations_are_independent(database: SaveDatabase, plan) -> None:
    """Running one must not depend on another having run first."""
    for operation in ops.OPERATIONS:
        results = ops.run(database, [operation], plan)
        assert results[0].name == operation.name
