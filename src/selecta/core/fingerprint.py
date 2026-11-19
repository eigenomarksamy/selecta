"""Compute and compare chromaprint audio fingerprints via fpcalc.

Shared, because confirming a duplicate candidate by what it *sounds like* is
the one check that does not care where the track list came from — the Rekordbox
reader and the library scan both end here.

**Why this shells out to `fpcalc -raw` instead of using pyacoustid.**
`acoustid.fingerprint_file` returns the *compressed* base64 fingerprint, and
turning that back into the integers a comparison needs goes through
`chromaprint.py`, a ctypes wrapper around the native `libchromaprint` shared
library. The standalone `fpcalc.exe` does not ship that library, so the obvious
install ("put fpcalc on PATH") produced a tool that could fingerprint every
track and then not compare any of them. `fpcalc -raw` emits the integers
directly, so comparison needs nothing that computing did not already require.

It runs through `core.tools`, so the browser build's WebAssembly fpcalc —
Chromaprint's own fpcalc.cpp, the same release (`wasm/build.sh`) — answers the
same command line there.

fpcalc only reads the first `DEFAULT_LENGTH_SECONDS` of audio. That is a
deliberate speed/accuracy trade: it is far more than enough to tell two
recordings apart, and it keeps each fingerprint about a thousand integers long.

**A path with no UTF-8 form is fingerprinted through a copy** (`_plain_named`).
NTFS names are unvalidated UTF-16, so one can hold half a surrogate pair. The
name reaches fpcalc intact, but fpcalc turns its wide argv into UTF-8 for
FFmpeg, which replaces the half pair, and FFmpeg then opens a file that does not
exist. Names in other scripts are unaffected: they have a UTF-8 form.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence

from selecta.core import paths, tools

#: Environment variable naming the fpcalc binary, honoured by pyacoustid too.
FPCALC_ENV = "FPCALC"
FPCALC_COMMAND = "fpcalc"

#: Seconds of audio fingerprinted per track. Also fpcalc's own default.
DEFAULT_LENGTH_SECONDS = 120

#: Seconds to wait on one file before giving up on it.
FPCALC_TIMEOUT = 120


@dataclass(frozen=True)
class Fingerprint:
    duration: float             # full track duration, not the fingerprinted window
    raw: tuple[int, ...]        # uncompressed 32-bit chromaprint subfingerprints


def fpcalc_binary(fpcalc_path: Optional[str] = None) -> str:
    """The fpcalc to run: explicit path, then `$FPCALC`, then whatever is on PATH."""
    return fpcalc_path or os.environ.get(FPCALC_ENV) or FPCALC_COMMAND


def compute(
    file_path: str,
    *,
    fpcalc_path: Optional[str] = None,
    length_seconds: int = DEFAULT_LENGTH_SECONDS,
) -> Optional[Fingerprint]:
    """Fingerprint one file, or return None if *this file* could not be read.

    A missing fpcalc binary raises `RuntimeError` instead of returning None:
    "every file failed" and "the tool is not installed" need to look different
    to the caller, because the second one makes the whole run meaningless.
    """
    if not os.path.isfile(file_path):
        return None

    try:
        with _plain_named(file_path) as readable_path:
            return _run_fpcalc(readable_path, fpcalc_path, length_seconds)
    except OSError:
        # The plain-named copy could not be made. Caught out here, so that a
        # vanished file is not mistaken for `_run_fpcalc`'s missing binary.
        return None


def _run_fpcalc(file_path: str, fpcalc_path: Optional[str], length_seconds: int) -> Optional[Fingerprint]:
    """`compute` on a path fpcalc can open."""
    cmd = [
        fpcalc_binary(fpcalc_path),
        "-raw",
        "-json",
        "-length",
        str(length_seconds),
        file_path,
    ]

    try:
        proc = tools.run(cmd, timeout=FPCALC_TIMEOUT)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"fpcalc not found (tried {cmd[0]!r}). Install the Chromaprint "
            f"command-line tool and put it on PATH, set ${FPCALC_ENV}, or pass "
            f"an explicit path."
        ) from exc
    except (subprocess.SubprocessError, OSError):
        # Timeout or a spawn failure on this one file.
        return None

    stdout = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0 or not stdout:
        # Unsupported codec, corrupt file, non-audio masquerading as audio.
        return None

    try:
        payload = json.loads(stdout)
        raw = tuple(int(v) for v in payload["fingerprint"])
        duration = float(payload["duration"])
    except (ValueError, TypeError, KeyError):
        return None

    if not raw:
        return None

    return Fingerprint(duration=duration, raw=raw)


@contextmanager
def _plain_named(file_path: str) -> Iterator[str]:
    """`file_path`, or a copy of it under a plain name if fpcalc would lose the name.

    Only on Windows, where fpcalc converts its argument. On POSIX a name with no
    UTF-8 form comes from `os.listdir` with its undecodable bytes escaped, and
    `subprocess` passes the same bytes back, so fpcalc gets the real name.
    Pyodide is POSIX, so the browser build never copies.

    A copy, not a hard link: a link needs `tmp/` on the library's volume, and a
    USB's FAT or exFAT has no hard links. The copy lives in a `paths.scratch`
    under `tmp/` and is deleted when the block exits. It is rare: the
    reference clone has no such name.
    """
    if os.name != "nt" or _has_utf8_form(file_path):
        yield file_path
        return
    ext = os.path.splitext(file_path)[1]
    # FFmpeg probes by content, but the extension is a hint worth keeping.
    plain_ext = ext if _has_utf8_form(ext) else ""
    with paths.scratch("fpcalc-name") as folder:
        copy = os.path.join(folder, "track" + plain_ext)
        shutil.copyfile(file_path, copy)
        yield copy


def _has_utf8_form(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def similarity(a: Fingerprint, b: Fingerprint) -> float:
    """Return a 0..1 similarity score between two chromaprint fingerprints.

    Compares the overlapping prefix via Hamming distance over the 32-bit
    subfingerprints: 1.0 is bit-identical, and unrelated audio sits near 0.5
    rather than 0, since half the bits of two random words agree by chance.
    """
    return similarity_raw(a.raw, b.raw)


def similarity_raw(raw_a: Sequence[int], raw_b: Sequence[int]) -> float:
    """`similarity` for callers that already hold the integer arrays."""
    n = min(len(raw_a), len(raw_b))
    if n == 0:
        return 0.0

    bits_diff = sum((x ^ y).bit_count() for x, y in zip(raw_a, raw_b))
    return 1.0 - bits_diff / (32.0 * n)
