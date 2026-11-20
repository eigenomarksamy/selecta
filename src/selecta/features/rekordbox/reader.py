"""Read tracks from a Rekordbox library.

Source resolution order:
  1. A master.db given directly (--db-path) or sitting on the USB. When it is a
     library's rather than the USB's own (no row points inside --usb-path),
     it is scoped to the USB by filename, as in 2.
  2. The local Rekordbox master.db (pyrekordbox auto-locates it). This is the
     only source that carries the analyzed BPM and key, so it is preferred even
     when a USB is supplied. With --usb-path we then restrict the result to the
     tracks actually on the USB (matched by filename) and merge in any USB files
     missing from the local DB via their ID3 tags.
  3. The USB's own export.pdb (`core.pdb`), or one given as --db-path: the
     analysis Rekordbox exported with the tracks, BPM and key included, for a
     USB with no library behind it. USB files it has no row for are read from
     their tags, as in 2.
  4. ID3 tags from the USB's Contents/ folder (last resort; no analyzed BPM/key).

exportLibrary.db, the newer database beside export.pdb, is not read.

Returns plain `Track` dataclasses so the rest of the pipeline doesn't depend on
pyrekordbox's ORM objects.
"""
from __future__ import annotations

import os
from typing import Optional

from selecta.core.pdb import EXPORT_PDB, PdbError, on_disk, read_tracks, usb_root
from selecta.core.rekordbox_db import iter_content, open_database
from selecta.core.tags import tracks_from_files
from selecta.core.track import AUDIO_EXTS as _AUDIO_EXTS, Track, iter_audio_files


def resolve_db_path(usb_path: Optional[str], db_path: Optional[str]) -> str:
    if db_path:
        return db_path
    if not usb_path:
        raise ValueError("Either --usb-path or --db-path must be provided.")
    return os.path.normpath(os.path.join(usb_path, "PIONEER", "rekordbox", "master.db"))


def load_tracks(db_path: str, *, usb_path: Optional[str] = None) -> list[Track]:
    """Open the Rekordbox library and return all content rows as Track objects.

    See the module docstring for the source resolution order.
    """
    db_path = os.path.normpath(db_path)
    usb_root = usb_path or os.path.dirname(os.path.dirname(db_path))
    contents_dir = os.path.normpath(os.path.join(usb_root, "Contents"))

    # An export.pdb named by path: tier 3 with that file.
    if db_path.lower().endswith(".pdb"):
        return _load_pdb_tracks(db_path, usb_path)

    # 1. A master.db we can open directly (explicit --db-path or one on the USB).
    if db_path.endswith("master.db") and os.path.isfile(db_path):
        try:
            tracks = _load_v6_tracks(db_path, usb_path)
        except Exception as e:
            print(f"master.db at {db_path} failed to load: {e}")
        else:
            if usb_path and tracks and not _any_under(tracks, usb_path):
                # A library's master.db named by path (in the browser build the
                # only way in), not the USB's own: its rows point at the
                # library's drive, so scope it to the USB as tier 2 does. A
                # folder without Contents/ is scoped as it is.
                files_dir = contents_dir if os.path.isdir(contents_dir) else os.path.normpath(usb_path)
                print(f"using {db_path}'s analysis, scoped to {files_dir}")
                return _scope_to_usb(tracks, files_dir)
            return tracks

    # 2. The local Rekordbox master.db — the only source with analyzed BPM/key.
    try:
        local_tracks = _load_local_master_db()
    except Exception as e:
        print(f"local Rekordbox master.db unavailable: {e}")
    else:
        if usb_path and os.path.isdir(contents_dir):
            print(f"using local Rekordbox analysis, scoped to USB at {contents_dir}")
            return _scope_to_usb(local_tracks, contents_dir)
        print("using local Rekordbox master.db (full library)")
        return local_tracks

    # 3. The USB's own export.pdb: its exported analysis, BPM and key included.
    pdb_path = os.path.join(usb_root, EXPORT_PDB)
    if usb_path and os.path.isfile(pdb_path):
        try:
            return _load_pdb_tracks(pdb_path, usb_path)
        except (OSError, PdbError) as e:
            print(f"export.pdb at {pdb_path} failed to load: {e}")

    # 4. Last resort: ID3 tags from the USB (no analyzed BPM/key available).
    if os.path.isdir(contents_dir):
        print(f"falling back to ID3 tags from {contents_dir} (BPM/key will be sparse)")
        return _load_id3_tracks(contents_dir, usb_root)

    raise FileNotFoundError(
        f"Could not find a Rekordbox database or Contents folder. "
        f"Tried: {db_path}, local master.db, {contents_dir}"
    )


def _load_v6_tracks(db_path: str, usb_path: Optional[str]) -> list[Track]:
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"master.db not found at {db_path}")

    tracks: list[Track] = []
    with open_database(db_path, log=print) as db:
        for row in iter_content(db):
            file_path = _resolve_file_path(row, usb_path=usb_path)
            if not file_path:
                continue
            tracks.append(
                Track(
                    id=str(_get(row, "ID")),
                    title=_get(row, "Title") or "",
                    artist=_artist_name_v6(row),
                    file_path=file_path,
                    bpm=_bpm_v6(row),
                    key=_key_name_v6(row),
                    duration_seconds=_duration_v6(row),
                )
            )
    return tracks


def _load_pdb_tracks(pdb_path: str, usb_path: Optional[str]) -> list[Track]:
    """Every audio file on the USB, with its export.pdb row's analysis where it has one.

    Rows are matched to files by path, which is exact here: the database and
    the files are the same USB's. The USB is `--usb-path`, or the one the file
    sits on. Files without a row are read from their tags, as tier 2 does.
    """
    root = os.path.normpath(usb_path) if usb_path else usb_root(pdb_path)
    by_path: dict[str, Track] = {}
    for t in read_tracks(pdb_path):
        if not t.file_path:
            continue
        file_path = on_disk(root, t.file_path)
        by_path.setdefault(os.path.normcase(file_path), Track(
            id=str(t.id),
            title=t.title,
            artist=t.artist,
            file_path=file_path,
            bpm=t.tempo_x100 / 100.0 if t.tempo_x100 else None,
            key=t.key or None,
            duration_seconds=float(t.duration_seconds) if t.duration_seconds else None,
        ))

    contents_dir = os.path.join(root, "Contents")
    files_dir = contents_dir if os.path.isdir(contents_dir) else root
    tracks: list[Track] = []
    unmatched: list[str] = []
    for path in iter_audio_files(files_dir):
        track = by_path.get(os.path.normcase(path))
        if track is not None:
            tracks.append(track)
        else:
            unmatched.append(path)
    print(f"using {pdb_path}: {len(tracks)} USB track(s) with exported analysis, "
          f"{len(unmatched)} via ID3 only")
    if unmatched:
        tracks.extend(tracks_from_files(unmatched, start_idx=len(tracks), log=print))
    return tracks


def _load_local_master_db() -> list[Track]:
    """Load every track from the local Rekordbox master.db (auto-located)."""
    tracks: list[Track] = []
    with open_database(log=print) as db:
        for row in iter_content(db):
            folder = _get(row, "FolderPath") or ""
            if not folder:
                continue
            tracks.append(
                Track(
                    id=str(_get(row, "ID")),
                    title=_get(row, "Title") or "",
                    artist=_artist_name_v6(row),
                    file_path=os.path.normpath(folder),
                    bpm=_bpm_v6(row),
                    key=_key_name_v6(row),
                    duration_seconds=_duration_v6(row),
                )
            )
    return tracks


def _scope_to_usb(local_tracks: list[Track], contents_dir: str) -> list[Track]:
    """Restrict local-DB tracks to those present on the USB.

    Matches USB audio files to local tracks by filename. Matched tracks keep the
    local analysis (BPM/key) but point at the USB copy. USB files with no local
    match are read from their ID3 tags so they aren't dropped (BPM/key blank).
    """
    by_name: dict[str, Track] = {}
    for t in local_tracks:
        by_name.setdefault(os.path.basename(t.file_path).lower(), t)

    tracks: list[Track] = []
    matched = 0
    unmatched_files: list[str] = []
    for root, _, files in os.walk(contents_dir):
        for filename in files:
            if not filename.lower().endswith(_AUDIO_EXTS):
                continue
            usb_file = os.path.normpath(os.path.join(root, filename))
            local = by_name.get(filename.lower())
            if local is not None:
                matched += 1
                tracks.append(
                    Track(
                        id=local.id,
                        title=local.title,
                        artist=local.artist,
                        file_path=usb_file,
                        bpm=local.bpm,
                        key=local.key,
                        duration_seconds=local.duration_seconds,
                    )
                )
            else:
                unmatched_files.append(usb_file)

    if unmatched_files:
        tracks.extend(tracks_from_files(unmatched_files, start_idx=len(tracks), log=print))
    print(f"matched {matched} USB track(s) to local analysis, {len(unmatched_files)} via ID3 only")
    return tracks


def _any_under(tracks: list[Track], root: str) -> bool:
    """Whether any track's file is inside `root`, compared as Windows compares paths."""
    prefix = os.path.normcase(os.path.join(os.path.normpath(root), ""))
    return any(os.path.normcase(os.path.normpath(t.file_path)).startswith(prefix) for t in tracks)


def _load_id3_tracks(contents_dir: str, usb_root: str) -> list[Track]:
    """Walk Contents/ and read ID3 tags + duration from audio files."""
    return tracks_from_files(list(iter_audio_files(contents_dir)), start_idx=0, log=print)


def _get(row, attr: str, default=None):
    return getattr(row, attr, default)


def _artist_name_v6(row) -> str:
    artist = _get(row, "Artist")
    if artist is None:
        return ""
    name = getattr(artist, "Name", None)
    return name or str(artist) or ""


def _key_name_v6(row) -> Optional[str]:
    key = _get(row, "Key")
    if key is None:
        return None
    name = getattr(key, "ScaleName", None) or getattr(key, "Name", None)
    return name or None


def _bpm_v6(row) -> Optional[float]:
    raw = _get(row, "BPM")
    if raw is None:
        return None
    try:
        bpm = float(raw)
    except (TypeError, ValueError):
        return None
    return bpm / 100.0 if bpm > 1000 else bpm


def _duration_v6(row) -> Optional[float]:
    raw = _get(row, "Length")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _resolve_file_path(row, *, usb_path: Optional[str]) -> Optional[str]:
    folder = _get(row, "FolderPath") or ""
    if not folder:
        return None
    if usb_path and folder.startswith("/"):
        return os.path.normpath(os.path.join(usb_path, folder.lstrip("/")))
    return folder

