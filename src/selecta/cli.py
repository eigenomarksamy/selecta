"""Top-level `selecta` command.

Each feature registers one subcommand and sets `handler` on its parser to the
function that runs it. Feature `add_parser` functions import argparse only, so
building the parser (and therefore `selecta --help`) never touches pyrekordbox,
pyacoustid, ffmpeg or the network.

`--out-dir` and `--tmp-dir` are shared by every subcommand via a parent parser
rather than defined on the top-level one, so they can be typed after the
subcommand where they read naturally: `selecta catalog --out-dir ./reports <dir>`.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from selecta import __version__, web
from selecta.core import paths
from selecta.features import (
    analyze,
    catalog,
    duplicates,
    playlist_diff,
    playlist_export,
    quality,
    rekordbox,
)

FEATURES = (catalog, duplicates, rekordbox, analyze, quality, playlist_diff, playlist_export)

# Front ends over FEATURES rather than features themselves: `selecta web` drives
# every command, which rule 1 forbids a feature to do. Registered the same way.
FRONTENDS = (web,)


def _common_parser() -> argparse.ArgumentParser:
    """Options every subcommand inherits. `add_help=False` — the child owns -h."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--out-dir", default=None, metavar="DIR",
        help=f"Root for generated reports (default: {paths.DEFAULT_OUT_DIR}, "
             f"or ${paths.OUT_DIR_ENV}). Each feature writes to <DIR>/<feature>/.",
    )
    common.add_argument(
        "--tmp-dir", default=None, metavar="DIR",
        help=f"Root for scratch files, cleaned up on exit "
             f"(default: {paths.DEFAULT_TMP_DIR}, or ${paths.TMP_DIR_ENV}).",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="selecta",
        description="Music library toolchain: catalog, reconcile with Rekordbox, and verify audio quality.",
    )
    parser.add_argument("--version", action="version", version=f"selecta {__version__}")

    common = _common_parser()
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for module in FEATURES + FRONTENDS:
        module.add_parser(subparsers, parents=[common])

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    # A redirected stdout on Windows is the ANSI code page with strict errors,
    # so one track name outside it ended the run with UnicodeEncodeError —
    # before playlist-diff had written anything. Only the error handler
    # changes: switching the encoding to UTF-8 would turn every accent into
    # mojibake under PowerShell 5.1's `>`, which re-decodes what it captures.
    # First, so that nothing (--help included) prints before it.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # None under pythonw
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")

    parser = build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2

    # Set the roots before any handler resolves a destination against them.
    paths.configure(args.out_dir, args.tmp_dir)

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
