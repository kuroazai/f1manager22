"""The command line.

    f1m22 config                  what is configured, and whether it is valid
    f1m22 preview                 the numbers a run would write, no save needed
    f1m22 check                   compare a save against the schema this expects
    f1m22 apply --dry-run         what would change, against your real save
    f1m22 apply                   unpack, change, repack, keeping a backup
    f1m22 backups                 list them
    f1m22 restore                 put the most recent one back

`apply` takes a backup before it touches anything, and `--dry-run` is a real
dry run: it opens the save read-only.

Output is ASCII. A pound sign or an em-dash crashes a legacy Windows console
code page, and this is a tool people run on Windows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import operations as ops
from .config import ConfigError, Settings
from .db import SaveDatabase, SaveDatabaseError
from .drivers import describe as describe_drivers
from .drivers import load_profiles
from .savefile import SaveArchive, SaveFileError
from .schema import differences
from .tyres import AeroSettings, TyreSettings

#: Shipped with the package, so a fresh clone works with no arguments.
BUNDLED_PROFILES = Path(__file__).resolve().parent / "data" / "F1_22.json"


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.from_env(args.env_file)


def _plan(args: argparse.Namespace, settings: Settings) -> ops.Plan:
    """Build the plan from arguments, falling back to the configured profiles."""
    profiles = (
        Path(args.profiles) if getattr(args, "profiles", None)
        else settings.profiles or BUNDLED_PROFILES
    )
    return ops.Plan(
        tyres=TyreSettings(
            base_grip=args.base_grip,
            base_life=args.base_life,
            grip_spread=args.grip_spread,
            life_spread=args.life_spread,
        ),
        aero=AeroSettings(
            dirty_air=args.dirty_air, drs=args.drs, slipstream=args.slipstream
        ),
        profiles_path=profiles,
        cash_infusion=args.cash,
    )


def _archive(args: argparse.Namespace, settings: Settings) -> SaveArchive:
    return SaveArchive(
        save_path=settings.resolve_save(args.save),
        unpacker=settings.resolve_unpacker(getattr(args, "unpacker", None)),
    )


# -- commands --------------------------------------------------------------

def cmd_config(args: argparse.Namespace) -> int:
    settings = _settings(args)
    print(settings.describe())
    print(f"bundled profiles {BUNDLED_PROFILES.name}: "
          f"{'found' if BUNDLED_PROFILES.is_file() else 'MISSING'}")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    """The numbers, with no save and no configuration. Always works."""
    settings = _settings(args)
    plan = _plan(args, settings)

    print("tyres")
    print(plan.tyres.describe())
    print("\naero")
    for name, value in plan.aero.plan().items():
        print(f"  {name:<34}{value}")

    print("\noperations that would run")
    try:
        selected = ops.select(args.only, args.preset)
    except KeyError as exc:
        print(f"  {exc}")
        return 1
    for operation in selected:
        print(f"  {operation.preview(plan)}")

    if plan.profiles_path is None:
        print("no driver profile file configured")
        return 1

    try:
        print("\n" + describe_drivers(load_profiles(plan.profiles_path), limit=5))
    except (OSError, ValueError) as exc:
        print(f"\ndriver profiles: {exc}")
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Compare an unpacked save against the schema this tool expects."""
    settings = _settings(args)
    try:
        archive = _archive(args, settings)
    except ConfigError as exc:
        print(exc)
        return 1

    if not archive.database_path.is_file():
        print(f"not unpacked yet: no main.db in {archive.result_dir}")
        print("run: f1m22 apply --dry-run")
        return 1

    with SaveDatabase(archive.database_path, read_only=True) as database:
        present = {table: database.columns(table) for table in database.tables()}

    print(f"{len(present)} table(s) in {archive.database_path.name}")
    problems = differences(present)
    if not problems:
        print("every table and column this tool uses is present")
        return 0

    print(f"\n{len(problems)} problem(s):")
    for problem in problems:
        print(f"  {problem}")
    print("\nOperations touching these would succeed and change nothing.")
    return 2


def cmd_apply(args: argparse.Namespace) -> int:
    settings = _settings(args)
    try:
        archive = _archive(args, settings)
        plan = _plan(args, settings)
        selected = ops.select(args.only, args.preset)
    except (ConfigError, KeyError, ValueError) as exc:
        print(exc)
        return 1

    try:
        archive.check()
        print(f"unpacking {archive.save_path.name}")
        database_path = archive.unpack()
    except SaveFileError as exc:
        print(exc)
        return 1

    try:
        with SaveDatabase(database_path, read_only=args.dry_run) as database:
            results = ops.run(database, selected, plan, dry_run=args.dry_run)
    except (SaveDatabaseError, KeyError, ValueError) as exc:
        print(f"\nnothing was changed: {exc}")
        return 1

    for result in results:
        print(result)

    if args.dry_run:
        print("\ndry run: the save was opened read-only and is untouched")
        return 0

    nothing = [r.name for r in results if r.changed_nothing]

    try:
        backup = archive.backup()
        print(f"\nbacked up to {backup.name}")
        archive.repack()
        print(f"repacked {archive.save_path.name}")
    except SaveFileError as exc:
        print(f"\nthe database was edited but repacking failed: {exc}")
        print("your original save is untouched; the edited main.db is still in "
              f"{archive.result_dir}")
        return 1

    if nothing:
        print(f"\nwarning: {', '.join(nothing)} changed nothing. "
              "Run 'f1m22 check' to see whether the schema matches.")
        return 2
    return 0


def cmd_backups(args: argparse.Namespace) -> int:
    settings = _settings(args)
    try:
        archive = _archive(args, settings)
    except ConfigError as exc:
        print(exc)
        return 1

    existing = archive.backups()
    if not existing:
        print(f"no backups in {archive.backup_dir}")
        return 0
    print(f"{len(existing)} backup(s), newest first:")
    for path in existing:
        size = path.stat().st_size / 1024
        print(f"  {path.name}  ({size:.0f} KB)")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    settings = _settings(args)
    try:
        archive = _archive(args, settings)
        restored = archive.restore(args.backup)
    except (ConfigError, SaveFileError) as exc:
        print(exc)
        return 1
    print(f"restored {restored.name} over {archive.save_path.name}")
    return 0


# -- wiring ----------------------------------------------------------------

def _add_tuning(parser: argparse.ArgumentParser) -> None:
    """The numbers. Defaults match the original script, so the same command
    produces the same season."""
    tyres = parser.add_argument_group("tyres")
    tyres.add_argument("--base-grip", type=float, default=1.0)
    tyres.add_argument("--base-life", type=float, default=1.25)
    tyres.add_argument("--grip-spread", type=float, default=0.40,
                       help="grip the hardest compound gives up against the softest")
    tyres.add_argument("--life-spread", type=float, default=0.55,
                       help="extra life the hardest compound gets")

    aero = parser.add_argument_group("aero")
    aero.add_argument("--dirty-air", type=float, default=0.30,
                      help="fraction of performance lost following another car")
    aero.add_argument("--drs", type=float, default=1.05)
    aero.add_argument("--slipstream", type=float, default=1.0005)

    other = parser.add_argument_group("other")
    other.add_argument("--cash", type=int, default=500_000_000,
                       help="added to every team's balance")
    other.add_argument("--profiles", help="a driver profile JSON file")

    selection = parser.add_argument_group("selection")
    selection.add_argument("--preset", default="full", choices=sorted(ops.PRESETS),
                           help="which set of changes to apply")
    selection.add_argument("--only", nargs="+", metavar="NAME",
                           help="run just these operations: "
                                + ", ".join(ops.BY_NAME))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="f1m22",
        description="Edit an F1 Manager 2022 save: tyres, aero, drivers, balance.",
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--save", help="save file, or a bare name in the save folder")
    parser.add_argument("--unpacker", help="path to xAranaktu's script.py")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("config", help="show what is configured").set_defaults(
        handler=cmd_config)

    preview = subparsers.add_parser(
        "preview", help="the numbers a run would write, no save needed")
    _add_tuning(preview)
    preview.set_defaults(handler=cmd_preview)

    subparsers.add_parser(
        "check", help="compare a save against the expected schema"
    ).set_defaults(handler=cmd_check)

    apply_parser = subparsers.add_parser("apply", help="edit the save")
    apply_parser.add_argument("--dry-run", action="store_true",
                              help="open the save read-only and report only")
    _add_tuning(apply_parser)
    apply_parser.set_defaults(handler=cmd_apply)

    subparsers.add_parser("backups", help="list backups").set_defaults(
        handler=cmd_backups)

    restore = subparsers.add_parser("restore", help="put a backup back")
    restore.add_argument("backup", nargs="?", help="defaults to the most recent")
    restore.set_defaults(handler=cmd_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
