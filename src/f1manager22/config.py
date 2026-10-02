"""Settings, from the environment rather than from a tracked file.

The original shipped `config.py` containing `save_folder = r""` and told you to
edit it. Two problems with that. It is a tracked file, so `git pull` conflicts
with your own change, and anyone who commits by habit publishes the path to
their home directory. The same mistake leaked a Windows username and a Firefox
profile ID out of another of these repositories.

So: environment variables, optionally from a `.env`, overridable per command.
Nothing you have to edit inside the package.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: The usual place on Windows. Only a starting guess, and it is reported rather
#: than assumed.
DEFAULT_SAVE_NAME = "autosave.sav"
WINDOWS_SAVE_HINT = (
    Path.home() / "Documents" / "My Games" / "F1 Manager 2022"
    / "Saved" / "SaveGames"
)


class ConfigError(RuntimeError):
    """The configuration is incomplete."""


def load_env_file(path: str = ".env", *, override: bool = False) -> dict[str, str]:
    """Read KEY=value lines into the environment.

    Hand-rolled rather than depending on python-dotenv: it is twenty lines and
    removes a dependency. Existing environment variables win unless `override`,
    so a real setup is never clobbered by a stray file.
    """
    loaded: dict[str, str] = {}
    source = Path(path)
    if not source.is_file():
        return loaded

    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


@dataclass
class Settings:
    """Where the save is, and where the unpacker is."""

    save_folder: Path | None = None
    save_name: str = DEFAULT_SAVE_NAME
    unpacker: Path | None = None
    profiles: Path | None = None

    @classmethod
    def from_env(cls, env_file: str | None = ".env") -> Settings:
        if env_file:
            load_env_file(env_file)
        folder = os.environ.get("F1M22_SAVE_FOLDER", "").strip()
        unpacker = os.environ.get("F1M22_UNPACKER", "").strip()
        profiles = os.environ.get("F1M22_PROFILES", "").strip()
        return cls(
            save_folder=Path(folder) if folder else None,
            save_name=os.environ.get("F1M22_SAVE_NAME", DEFAULT_SAVE_NAME).strip()
            or DEFAULT_SAVE_NAME,
            unpacker=Path(unpacker) if unpacker else None,
            profiles=Path(profiles) if profiles else None,
        )

    # -- resolution --------------------------------------------------------
    def resolve_save(self, override: str | None = None) -> Path:
        """The save file to work on.

        `override` is the `--save` argument, and it is honoured. In the original
        `--save` was declared, documented, and then never read: the path was
        hardcoded to `autosave.sav` a few lines further down.
        """
        if override:
            candidate = Path(override)
            # A bare name means "that save, in the configured folder", which is
            # how people actually use it.
            if candidate.parent == Path("."):
                folder = self._require_folder()
                return folder / candidate.name
            return candidate

        folder = self._require_folder()
        return folder / self.save_name

    def resolve_unpacker(self, override: str | None = None) -> Path:
        if override:
            return Path(override)
        if self.unpacker is None:
            raise ConfigError(
                "no unpacker configured. Download script.py from "
                "https://github.com/xAranaktu/F1-Manager-2022-SaveFile-Repacker "
                "and set F1M22_UNPACKER to it, or pass --unpacker"
            )
        return self.unpacker

    def _require_folder(self) -> Path:
        if self.save_folder is None:
            hint = (
                f"\nOn Windows it is usually: {WINDOWS_SAVE_HINT}"
                if WINDOWS_SAVE_HINT.parent.parent.is_dir()
                else ""
            )
            raise ConfigError(
                "no save folder configured. Set F1M22_SAVE_FOLDER, or pass a "
                "full path to --save." + hint
            )
        return self.save_folder

    def describe(self) -> str:
        """What is configured. No secrets here, but a home directory path is
        still personal, so this prints whether a path is set and valid rather
        than pasting it into anything shareable."""
        def state(path: Path | None, *, directory: bool = False) -> str:
            if path is None:
                return "not set"
            exists = path.is_dir() if directory else path.is_file()
            return f"{path}  ({'found' if exists else 'MISSING'})"

        return "\n".join([
            f"save folder   {state(self.save_folder, directory=True)}",
            f"save name     {self.save_name}",
            f"unpacker      {state(self.unpacker)}",
            f"profiles      {state(self.profiles) if self.profiles else 'bundled default'}",
        ])
