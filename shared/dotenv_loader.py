"""Load your OpenRouter key (and any other secrets) from a .env file.

One key, every pattern. This walks up from the script that calls it to the
repository root and loads the nearest ``.env`` it finds, so you can keep a
single ``.env`` in the repo's top folder and every agent under it, the finished
patterns and your own copies alike, reads that one file. You set your key once.

Three rules make it predictable and safe:

* A value already set in your real environment always wins. If you have exported
  ``OPENROUTER_API_KEY`` in your shell, no file overrides it.
* The nearest ``.env`` wins. A ``.env`` next to a pattern's ``run_agent.py``
  overrides the one at the repo root, key by key, if you ever want a per-pattern
  override.
* The search stops at the repository root (the folder holding ``pyproject.toml``
  or ``.git``), so it never wanders into unrelated ``.env`` files higher up.

The ``.env`` file is git-ignored, so your key never travels into the repo. The
repo ships ``.env.example`` as a template: copy it to ``.env`` and put your real
key in the copy, by hand. Your key never goes into a chat or a command history.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The marker a copied-but-not-yet-filled key still carries. If we see it, the
# reader has not pasted their real key yet, so we say so plainly instead of
# letting the value through to fail later as an opaque 401.
PLACEHOLDER_MARK = "REPLACE-WITH-YOUR-KEY"


def _dirs_up_to_repo_root(start: Path) -> list[Path]:
    """The starting directory and each parent, up to and including the repo root.

    The repo root is the first directory that holds ``pyproject.toml`` or a
    ``.git`` entry. If neither is ever found we stop at the filesystem root.
    """
    start = start.resolve()
    dirs: list[Path] = []
    for directory in (start, *start.parents):
        dirs.append(directory)
        if (directory / "pyproject.toml").is_file() or (directory / ".git").exists():
            break
    return dirs


def load_dotenv(start: Path | str | None = None) -> list[Path]:
    """Load ``.env`` files from ``start`` up to the repo root into the environment.

    ``start`` defaults to the current working directory; pass the calling
    script's own folder (``HERE``) so the search is anchored to the script, not
    to wherever it was launched from. Files are loaded nearest-first with
    set-if-absent semantics, so an environment value already set wins, then the
    nearest file, then files closer to the root. Returns the files it loaded.
    """
    start_dir = Path(start) if start is not None else Path.cwd()
    loaded: list[Path] = []
    for directory in _dirs_up_to_repo_root(start_dir):
        env_file = directory / ".env"
        if env_file.is_file():
            _load_file(env_file)
            loaded.append(env_file)
    return loaded


def _load_file(env_file: Path) -> None:
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if PLACEHOLDER_MARK in value:
            print(
                f"Note: {key} in {env_file} still holds the placeholder. Open "
                f"that file and replace it with your real key, then run again.",
                file=sys.stderr,
            )
            continue
        os.environ.setdefault(key, value)
