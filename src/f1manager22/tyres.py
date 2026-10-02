"""The tyre model: grip, durability, temperature and wear.

This is the part of the mod that actually changes how a race feels. The game
ships with the three dry compounds performing almost identically, so there is no
reason to ever run anything but the softest. Spreading grip and durability apart
is what makes a one-stop versus two-stop decision mean something.

The arithmetic is kept here, separate from the SQL that applies it, so the
numbers can be checked without a save file. `TyreSettings.plan()` returns what
it would write, and nothing in this module touches a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import DRY_COMPOUNDS, TyreCompound

#: Four steps from softest to hardest across the five compounds. Spreading a
#: range over `len(compounds) - 1` rather than over a hardcoded 3 is the
#: difference between the hard tyre getting the full spread and getting
#: three-quarters of it.
_STEPS = len(TyreCompound) - 1


@dataclass(frozen=True)
class TyreSettings:
    """What the tyres should become.

    Defaults are the original script's, so the same command produces the same
    season. They are stated here rather than in `argparse` so the model is
    usable as a library and testable without a command line.
    """

    base_grip: float = 1.0
    base_life: float = 1.25
    #: How much grip the hardest compound gives up against the softest.
    grip_spread: float = 0.40
    #: How much longer the hardest compound lasts than the softest.
    life_spread: float = 0.55

    temp_increase_rate: float = 1.9
    temp_decrease_rate: float = 0.01

    min_extreme_wear: float = 0.30
    max_extreme_wear: float = 1.00
    min_optimal_wear: float = 0.10
    max_optimal_wear: float = 0.30

    min_optimal_grip: float = 0.65
    max_optimal_grip: float = 0.85
    min_extreme_grip: float = 0.45
    max_extreme_grip: float = 0.70

    def __post_init__(self) -> None:
        # Checked here rather than at the first odd race result. A negative
        # spread silently inverts the compounds, so the hard tyre becomes the
        # fastest and the soft the most durable.
        if self.grip_spread < 0 or self.life_spread < 0:
            raise ValueError("grip_spread and life_spread cannot be negative")
        if self.base_grip <= 0 or self.base_life <= 0:
            raise ValueError("base_grip and base_life must be positive")
        if self.grip_spread >= self.base_grip:
            raise ValueError(
                f"grip_spread ({self.grip_spread}) must be under base_grip "
                f"({self.base_grip}), or the hardest compound ends up with no grip"
            )
        if self.min_optimal_grip > self.max_optimal_grip:
            raise ValueError("min_optimal_grip cannot exceed max_optimal_grip")
        if self.min_extreme_wear > self.max_extreme_wear:
            raise ValueError("min_extreme_wear cannot exceed max_extreme_wear")

    # -- the curves --------------------------------------------------------
    def grip_for(self, compound: TyreCompound) -> float:
        """Grip, descending from the softest compound to the hardest."""
        step = self.grip_spread / _STEPS
        return round(self.base_grip - step * int(compound), 4)

    def life_for(self, compound: TyreCompound) -> float:
        """Durability, ascending from the softest compound to the hardest.

        Ascending, where grip descends. That pairing is the entire point: a soft
        tyre is fast and short-lived, a hard tyre slow and long-lived.

        The original computed both as a descending series and then reversed one
        of the two lists in place inside the setter, which meant the direction
        of the trade-off depended on which function you called and on a
        side effect to the caller's list.
        """
        step = self.life_spread / _STEPS
        return round(self.base_life + step * int(compound), 4)

    def temperature_curve(self, compound: TyreCompound) -> dict[str, float]:
        """Per-compound temperature and wear behaviour.

        A softer compound heats faster, cools faster and punishes you harder for
        being outside its window. The divisors are the original's and are
        preserved deliberately, because they are what the published settings
        were tuned against.
        """
        index = int(compound)
        return {
            "TempIncRate": round(self.temp_increase_rate + index / 20, 4),
            "TempDecRate": round(self.temp_decrease_rate + index / 25, 4),
            "MinExtremeWear": round(self.min_extreme_wear + index / 30, 4),
            "MaxExtremeWear": round(self.max_extreme_wear + index / 100, 4),
            "MinOptimalWear": round(self.min_optimal_wear + index / 30, 4),
            "MaxOptimalWear": round(self.max_optimal_wear + index / 100, 4),
            "MinOptimalGrip": round(self.min_optimal_grip + index / 7.5, 4),
            "MaxOptimalGrip": round(self.max_optimal_grip + index / 10, 4),
            "MinExtremeGrip": round(self.min_extreme_grip + index / 20, 4),
            "MaxExtremeGrip": round(self.max_extreme_grip + index / 15, 4),
        }

    def plan(self) -> dict[TyreCompound, dict[str, float]]:
        """Everything this would write, per compound, touching no database.

        This is what `--dry-run` prints. Being able to see the numbers before
        they go into a save matters when the save is your season.
        """
        return {
            compound: {
                "Grip": self.grip_for(compound),
                "Durability": self.life_for(compound),
                **self.temperature_curve(compound),
            }
            for compound in TyreCompound
        }

    def describe(self) -> str:
        """A table of the dry compounds, which is what people want to see."""
        lines = [f"{'compound':<14}{'grip':>8}{'life':>8}{'heats':>8}{'cools':>8}"]
        for compound in DRY_COMPOUNDS:
            curve = self.temperature_curve(compound)
            lines.append(
                f"{compound.name.lower():<14}"
                f"{self.grip_for(compound):>8.3f}"
                f"{self.life_for(compound):>8.3f}"
                f"{curve['TempIncRate']:>8.3f}"
                f"{curve['TempDecRate']:>8.3f}"
            )
        softest, hardest = DRY_COMPOUNDS[0], DRY_COMPOUNDS[-1]
        lines.append(
            f"soft to hard: {self.grip_for(softest) - self.grip_for(hardest):.3f} grip "
            f"given up for {self.life_for(hardest) - self.life_for(softest):.3f} life"
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class AeroSettings:
    """Dirty air, DRS and slipstream.

    These decide whether a faster car can actually get past. The stock values
    make following so costly that overtaking barely happens.
    """

    #: Total multiplier removed from the dirty-air bands, shared between them
    #: in proportion to their stock values. With the stock 0.98 in all three,
    #: 0.30 takes each to roughly 0.88, so following another car costs about ten
    #: percent more than it does unmodified. It is not a per-band fraction.
    dirty_air: float = 0.30
    drs: float = 1.05
    slipstream: float = 1.0005

    #: The stock multipliers the reduction is applied to, one per speed band.
    base_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "DirtyAirLowSpeedMultiplier": 0.98,
            "DirtyAirMediumSpeedMultiplier": 0.98,
            "DirtyAirHighSpeedMultiplier": 0.98,
        }
    )

    def __post_init__(self) -> None:
        if not 0 <= self.dirty_air < 1:
            raise ValueError(
                f"dirty_air must be between 0 and 1, got {self.dirty_air}. "
                "It is the total reduction shared across the three speed bands, "
                "not a multiplier and not a per-band fraction."
            )
        if self.drs < 1:
            raise ValueError("drs below 1 would make DRS slower than no DRS")

    def dirty_air_multipliers(self) -> dict[str, float]:
        """The reduction shared across the speed bands, keeping their ratios.

        Each band gives up `value / total * dirty_air`, so a band that starts
        higher gives up more and the bands stay in proportion to one another.

        The original had a branch for a negative reduction that could not run,
        because the caller already returned early unless the value was above
        zero. The validation in `__post_init__` is the honest version of that
        check, and it happens before anything is written.
        """
        total = sum(self.base_multipliers.values())
        if total <= 0:
            raise ValueError("base multipliers must sum to more than zero")

        return {
            name: round(value - (value / total) * self.dirty_air, 6)
            for name, value in self.base_multipliers.items()
        }

    def drs_multipliers(self) -> dict[str, float]:
        """DRS top speed and acceleration.

        `MinDRSAccelerationMultiplier` is pinned to 1 so DRS never makes a car
        accelerate worse than not using it, which the stock data allows.
        """
        return {
            "MaxDRSTopSpeedMultiplier": round(self.drs, 6),
            "MaxDRSAccelerationMultiplier": round(self.drs * 1.15, 6),
            "MinDRSAccelerationMultiplier": 1.0,
        }

    def slipstream_multipliers(self) -> dict[str, float]:
        return {"DirtyAirStraightSpeedMultiplier": round(self.slipstream, 6)}

    def plan(self) -> dict[str, float]:
        """Every race-constant column this would write."""
        return {
            **self.dirty_air_multipliers(),
            **self.drs_multipliers(),
            **self.slipstream_multipliers(),
        }
