"""f1manager22 - edit an F1 Manager 2022 save.

    from f1manager22 import SaveArchive, SaveDatabase, Plan, select, run

    archive = SaveArchive(save_path="autosave.sav", unpacker="script.py")
    with SaveDatabase(archive.unpack()) as database:
        for result in run(database, select(preset="racing"), Plan()):
            print(result)
    archive.repack()

The tyre and aero models are pure arithmetic and touch no database, so the
numbers can be checked before they go anywhere:

    from f1manager22 import TyreSettings
    print(TyreSettings(grip_spread=0.6).describe())
"""
from .config import ConfigError, Settings, load_env_file
from .db import SaveDatabase, SaveDatabaseError
from .drivers import DriverProfile, load_profiles, suspicious_codes
from .enums import DRY_COMPOUNDS, DriverStat, Table, TyreCompound
from .operations import BY_NAME, OPERATIONS, PRESETS, Operation, Plan, Result, run, select
from .savefile import SaveArchive, SaveFileError
from .schema import TABLES, differences
from .tyres import AeroSettings, TyreSettings

__version__ = "1.0.0"

__all__ = [
    "Settings", "ConfigError", "load_env_file",
    "SaveDatabase", "SaveDatabaseError",
    "SaveArchive", "SaveFileError",
    "TyreSettings", "AeroSettings",
    "DriverProfile", "load_profiles", "suspicious_codes",
    "DriverStat", "TyreCompound", "Table", "DRY_COMPOUNDS",
    "Operation", "Result", "Plan", "OPERATIONS", "BY_NAME", "PRESETS",
    "select", "run",
    "TABLES", "differences",
    "__version__",
]
