"""The tyre and aero arithmetic. No database involved."""
from __future__ import annotations

import pytest

from f1manager22.enums import DRY_COMPOUNDS, TyreCompound
from f1manager22.tyres import AeroSettings, TyreSettings


def test_grip_falls_and_life_rises_across_the_compounds() -> None:
    """The entire point of the mod, and the thing the original got muddled.

    A soft tyre must be fast and short-lived, a hard tyre slow and long-lived.
    The original computed both as descending series and then called
    `values.reverse()` inside one of the two setters, so the direction of the
    trade-off depended on which function you happened to call, and the reverse
    mutated the caller's list on the way through.
    """
    settings = TyreSettings()
    grips = [settings.grip_for(c) for c in DRY_COMPOUNDS]
    lives = [settings.life_for(c) for c in DRY_COMPOUNDS]

    assert grips == sorted(grips, reverse=True), "grip must fall soft to hard"
    assert lives == sorted(lives), "life must rise soft to hard"


def test_the_spread_is_the_full_distance_from_soft_to_hard() -> None:
    settings = TyreSettings(base_grip=1.0, grip_spread=0.4)
    softest = settings.grip_for(TyreCompound.SOFT)
    hardest = settings.grip_for(TyreCompound.WET)
    assert softest - hardest == pytest.approx(0.4)


def test_planning_is_pure() -> None:
    """Calling it twice gives the same answer, and nothing is mutated."""
    settings = TyreSettings()
    assert settings.plan() == settings.plan()


def test_every_compound_gets_every_column() -> None:
    plan = TyreSettings().plan()
    assert set(plan) == set(TyreCompound)
    expected = set(plan[TyreCompound.SOFT])
    for values in plan.values():
        assert set(values) == expected


def test_a_softer_compound_heats_faster() -> None:
    settings = TyreSettings()
    soft = settings.temperature_curve(TyreCompound.SOFT)
    hard = settings.temperature_curve(TyreCompound.HARD)
    assert soft["TempIncRate"] < hard["TempIncRate"]


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"grip_spread": -0.1}, "negative"),
        ({"life_spread": -0.1}, "negative"),
        ({"base_grip": 0}, "positive"),
        ({"base_life": -1}, "positive"),
        ({"grip_spread": 1.5}, "under base_grip"),
        ({"min_optimal_grip": 0.9, "max_optimal_grip": 0.5}, "cannot exceed"),
        ({"min_extreme_wear": 2.0, "max_extreme_wear": 1.0}, "cannot exceed"),
    ],
)
def test_nonsense_settings_are_refused(kwargs: dict, fragment: str) -> None:
    """The original validated none of this, so a negative spread silently
    inverted the compounds and the hard tyre became the fastest."""
    with pytest.raises(ValueError, match=fragment):
        TyreSettings(**kwargs)


def test_a_spread_as_large_as_the_base_would_leave_no_grip() -> None:
    with pytest.raises(ValueError):
        TyreSettings(base_grip=1.0, grip_spread=1.0)


# -- aero ------------------------------------------------------------------

def test_dirty_air_reduction_keeps_the_bands_in_proportion() -> None:
    settings = AeroSettings(dirty_air=0.3)
    multipliers = settings.dirty_air_multipliers()

    assert set(multipliers) == set(settings.base_multipliers)
    # The three stock values are equal, so the reduced ones must be too.
    assert len(set(multipliers.values())) == 1
    for name, value in multipliers.items():
        assert value < settings.base_multipliers[name]


def test_no_dirty_air_reduction_leaves_the_values_alone() -> None:
    settings = AeroSettings(dirty_air=0.0)
    assert settings.dirty_air_multipliers() == pytest.approx(
        settings.base_multipliers
    )


def test_drs_never_accelerates_worse_than_no_drs() -> None:
    """The stock data allows a minimum multiplier below 1, which means opening
    DRS can cost you acceleration."""
    assert AeroSettings().drs_multipliers()["MinDRSAccelerationMultiplier"] == 1.0


def test_drs_acceleration_exceeds_top_speed_gain() -> None:
    multipliers = AeroSettings(drs=1.05).drs_multipliers()
    assert (multipliers["MaxDRSAccelerationMultiplier"]
            > multipliers["MaxDRSTopSpeedMultiplier"])


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"dirty_air": 1.5}, "between 0 and 1"),
        ({"dirty_air": -0.1}, "between 0 and 1"),
        ({"drs": 0.9}, "slower than no DRS"),
    ],
)
def test_nonsense_aero_is_refused(kwargs: dict, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        AeroSettings(**kwargs)


def test_dirty_air_is_shared_across_the_bands_not_applied_to_each() -> None:
    """The semantic is easy to get wrong, so it is pinned here.

    `dirty_air` is the total reduction shared between the three speed bands in
    proportion to their stock values. It is not a fraction taken off each one.
    With the stock 0.98 everywhere, 0.30 removes 0.10 from each band rather
    than 0.294.
    """
    settings = AeroSettings(dirty_air=0.30)
    reduced = settings.dirty_air_multipliers()

    for name, value in reduced.items():
        stock = settings.base_multipliers[name]
        assert stock - value == pytest.approx(0.30 / 3, abs=1e-6)

    # The total removed across all three is exactly the figure asked for.
    removed = sum(settings.base_multipliers.values()) - sum(reduced.values())
    assert removed == pytest.approx(0.30)


def test_a_higher_band_gives_up_more_keeping_the_ratios() -> None:
    settings = AeroSettings(
        dirty_air=0.30,
        base_multipliers={
            "DirtyAirLowSpeedMultiplier": 1.00,
            "DirtyAirMediumSpeedMultiplier": 0.50,
            "DirtyAirHighSpeedMultiplier": 0.50,
        },
    )
    reduced = settings.dirty_air_multipliers()
    low_loss = 1.00 - reduced["DirtyAirLowSpeedMultiplier"]
    medium_loss = 0.50 - reduced["DirtyAirMediumSpeedMultiplier"]
    assert low_loss == pytest.approx(medium_loss * 2)
