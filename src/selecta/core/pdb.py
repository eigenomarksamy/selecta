"""Reading `export.pdb`, the DeviceSQL database Rekordbox writes to a USB.

A Pioneer USB carries its own database beside the audio: `PIONEER/rekordbox/
export.pdb`, what a CDJ reads. It is **not encrypted** (`exportLibrary.db`, the
newer OneLibrary file beside it, is SQLCipher; this is not that). It is a file of
fixed-size pages, each owned by one table, with rows packed into a heap from the
front of the page and an index of row offsets growing from the back. This
module reads it with the stdlib alone, so it runs wherever selecta does,
Pyodide included, and needs no extra.

The layout is the one Deep Symmetry documented for Crate Digger ("Rekordbox
Export Structure Analysis", and its `rekordbox_pdb.ksy`). It was checked row for
row against rbxport's `rbl-pdb`, built separately at a pinned commit and run
only as an oracle (plan, F6): no rbxport code is in this tree.

What it reads is what `quality` and `rekordbox` need: tracks, with the artist,
album, genre, key and label tables their ids point into. Playlists, artwork,
colours and the browse menus are left alone. Read-only: the file is read into
memory once and never opened for writing.

Load-bearing details:

- **Rows come from the presence bits, not the row count.** A deleted row's
  offset stays in its group; only the group's presence flags say it is gone.
- **Only data pages hold rows.** Each table's first page is an index page
  (flag 0x40) whose bytes are not rows; reading it as one gives noise.
- **A page chain is followed to the table's last page and no further**, and a
  page seen twice, out of range or owned by another table ends it with a
  `PdbError` rather than a loop or another table's rows.
- **Strings have three encodings**, chosen per string by its first byte: short
  ASCII (odd byte, length in the high 7 bits), long ASCII (0x40) and long
  UTF-16LE (0x90). Rekordbox writes any non-ASCII text as the third.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Iterator, Optional

#: Where a USB keeps it, relative to the USB's root.
EXPORT_PDB = os.path.join("PIONEER", "rekordbox", "export.pdb")

# Table types in the file header.
TRACKS, GENRES, ARTISTS, ALBUMS, LABELS, KEYS = 0, 1, 2, 3, 4, 5

_HEAP = 0x28            # rows start here in a page
_GROUP = 0x24           # bytes per group of 16 row offsets, from the page's end
_INDEX_PAGE = 0x40      # page flag: not a data page
_NO_COUNT = 0x1FFF      # the large row count's "not used" value

#: The track row's 21 string offsets, at 0x5E, by index.
_TRACK_STRINGS = {
    "date_added": 10,
    "release_date": 11,
    "mix_name": 12,
    "analyze_path": 14,
    # rbl-pdb calls this one `date_added`. It is later than slot 10 on exactly
    # the tracks analysed again after they were added (144 of 3,587 on the
    # reference USB), which is Deep Symmetry's reading, kept here.
    "analyze_date": 15,
    "comment": 16,
    "title": 17,
    "filename": 19,
    "file_path": 20,
}

#: The file-type codes a track row stores at 0x5A, which are also master.db's.
FILE_TYPES = {1: "mp3", 4: "m4a", 5: "flac", 11: "wav", 12: "aiff"}


class PdbError(ValueError):
    """The file is not an `export.pdb`, or is damaged where it was read."""


@dataclass(frozen=True)
class PdbTrack:
    """One row of the tracks table, its ids resolved to names.

    Numbers are as stored, with 0 meaning "not recorded"; the caller decides
    what 0 means for its purpose. `file_path` is the USB's own spelling,
    `/Contents/...` from the USB's root, always with forward slashes.
    """
    id: int
    title: str
    artist: str
    album: str
    genre: str
    key: str
    label: str
    file_path: str
    filename: str
    analyze_path: str
    file_type: int
    file_size: int
    bitrate_kbps: int
    sample_rate: int
    bit_depth: int
    duration_seconds: int      # whole seconds
    tempo_x100: int            # BPM times 100
    year: int
    track_number: int
    date_added: str
    analyze_date: str
    release_date: str
    comment: str
    artist_id: int
    album_id: int
    genre_id: int
    key_id: int
    label_id: int


class Pdb:
    """An `export.pdb` in memory: its tables, and the rows of each."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        if len(data) < 0x1C:
            raise PdbError("too short to be an export.pdb")
        zero, page_size, num_tables = struct.unpack_from("<III", data, 0)
        if zero != 0 or page_size not in (512, 1024, 2048, 4096, 8192, 16384):
            raise PdbError("not an export.pdb: no DeviceSQL header")
        if 0x1C + 16 * num_tables > page_size:
            raise PdbError(f"header lists {num_tables} tables, more than a page holds")
        self.page_size = page_size
        self.num_pages = len(data) // page_size
        #: table type -> (first page, last page)
        self.tables: dict[int, tuple[int, int]] = {}
        for i in range(num_tables):
            kind, _empty, first, last = struct.unpack_from("<IIII", data, 0x1C + 16 * i)
            self.tables.setdefault(kind, (first, last))

    @classmethod
    def open(cls, path: str) -> "Pdb":
        with open(path, "rb") as f:
            return cls(f.read())

    def rows(self, kind: int) -> Iterator[int]:
        """The offset in the file of every live row of table `kind`, in file order."""
        if kind not in self.tables:
            return
        first, last = self.tables[kind]
        seen: set[int] = set()
        page = first
        while True:
            if page in seen or not 0 < page < self.num_pages:
                raise PdbError(f"table {kind}: page chain breaks at page {page}")
            seen.add(page)
            start = page * self.page_size
            owner, next_page = struct.unpack_from("<II", self.data, start + 0x08)
            if owner != kind:
                raise PdbError(f"table {kind}: page {page} belongs to table {owner}")
            yield from self._page_rows(start)
            if page == last:
                return
            page = next_page

    def _page_rows(self, start: int) -> Iterator[int]:
        data = self.data
        small, flags = data[start + 0x18], data[start + 0x1B]
        if flags & _INDEX_PAGE:
            return
        (large,) = struct.unpack_from("<H", data, start + 0x22)
        count = large if large > small and large != _NO_COUNT else small
        end = start + self.page_size
        for group in range((count + 15) // 16):
            base = end - group * _GROUP
            (present,) = struct.unpack_from("<H", data, base - 4)
            for i in range(16):
                if present >> i & 1:
                    (offset,) = struct.unpack_from("<H", data, base - 6 - 2 * i)
                    yield start + _HEAP + offset

    def string(self, at: int) -> str:
        """The DeviceSQL string at file offset `at`."""
        data = self.data
        kind = data[at]
        if kind & 1:  # short ASCII: the length, header byte included, in the high 7 bits
            return data[at + 1:at + (kind >> 1)].decode("ascii", "replace")
        (length,) = struct.unpack_from("<H", data, at + 1)
        body = data[at + 4:at + length]
        if kind == 0x40:
            return body.decode("ascii", "replace")
        if kind == 0x90:
            return body.decode("utf-16-le", "replace")
        raise PdbError(f"unknown string kind 0x{kind:02x} at 0x{at:x}")

    # --- the named tables, as id -> name -------------------------------------

    def names(self, kind: int) -> dict[int, str]:
        """id -> name for the genres, artists, albums, labels or keys table."""
        read = {
            GENRES: self._simple_row,
            LABELS: self._simple_row,
            KEYS: self._key_row,
            ARTISTS: self._artist_row,
            ALBUMS: self._album_row,
        }[kind]
        out: dict[int, str] = {}
        for at in self.rows(kind):
            row_id, name = read(at)
            out.setdefault(row_id, name)
        return out

    def _simple_row(self, at: int) -> tuple[int, str]:
        (row_id,) = struct.unpack_from("<I", self.data, at)
        return row_id, self.string(at + 4)

    def _key_row(self, at: int) -> tuple[int, str]:
        (row_id,) = struct.unpack_from("<I", self.data, at)
        return row_id, self.string(at + 8)

    def _artist_row(self, at: int) -> tuple[int, str]:
        subtype, _shift, row_id = struct.unpack_from("<HHI", self.data, at)
        if subtype & 0x04:  # 0x64: the name is far, behind a 16-bit offset
            (offset,) = struct.unpack_from("<H", self.data, at + 0x0A)
        else:               # 0x60: near, behind an 8-bit one
            offset = self.data[at + 0x09]
        return row_id, self.string(at + offset)

    def _album_row(self, at: int) -> tuple[int, str]:
        (subtype,) = struct.unpack_from("<H", self.data, at)
        (row_id,) = struct.unpack_from("<I", self.data, at + 0x0C)
        if subtype & 0x04:  # 0x84: far
            (offset,) = struct.unpack_from("<H", self.data, at + 0x16)
        else:               # 0x80: near
            offset = self.data[at + 0x15]
        return row_id, self.string(at + offset)

    # --- tracks ----------------------------------------------------------------

    def tracks(self) -> list[PdbTrack]:
        """Every live track row, ids resolved against the named tables."""
        try:
            names = {kind: self.names(kind) for kind in (GENRES, ARTISTS, ALBUMS, LABELS, KEYS)}
            return [self._track(at, names) for at in self.rows(TRACKS)]
        except (struct.error, IndexError) as exc:
            # An offset past the end of the file: damaged, or not all copied.
            raise PdbError(f"a row points past the end of the file ({exc})") from exc

    def _track(self, at: int, names: dict[int, dict[int, str]]) -> PdbTrack:
        data = self.data
        (sample_rate,) = struct.unpack_from("<I", data, at + 0x08)
        (file_size,) = struct.unpack_from("<I", data, at + 0x10)
        key_id, _orig, label_id, _remixer, bitrate, track_number, tempo, genre_id, album_id, artist_id, row_id = (
            struct.unpack_from("<11I", data, at + 0x20))
        _disc, _plays, year, bit_depth, duration = struct.unpack_from("<5H", data, at + 0x4C)
        (file_type,) = struct.unpack_from("<H", data, at + 0x5A)
        offsets = struct.unpack_from("<21H", data, at + 0x5E)
        text = {field: self.string(at + offsets[i]) for field, i in _TRACK_STRINGS.items()}
        return PdbTrack(
            id=row_id,
            title=text["title"],
            artist=names[ARTISTS].get(artist_id, ""),
            album=names[ALBUMS].get(album_id, ""),
            genre=names[GENRES].get(genre_id, ""),
            key=names[KEYS].get(key_id, ""),
            label=names[LABELS].get(label_id, ""),
            file_path=text["file_path"],
            filename=text["filename"],
            analyze_path=text["analyze_path"],
            file_type=file_type,
            file_size=file_size,
            bitrate_kbps=bitrate,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            duration_seconds=duration,
            tempo_x100=tempo,
            year=year,
            track_number=track_number,
            date_added=text["date_added"],
            analyze_date=text["analyze_date"],
            release_date=text["release_date"],
            comment=text["comment"],
            artist_id=artist_id,
            album_id=album_id,
            genre_id=genre_id,
            key_id=key_id,
            label_id=label_id,
        )


def read_tracks(path: str) -> list[PdbTrack]:
    """Every track in the `export.pdb` at `path`."""
    return Pdb.open(path).tracks()


def find_export_pdb(directory: str) -> Optional[str]:
    """The `export.pdb` of the USB `directory` is on: in it or the nearest parent.

    A scan of `D:/` or of `D:/Contents/Artist` both find `D:/PIONEER/rekordbox/
    export.pdb`; a folder on no Rekordbox USB finds None.
    """
    here = os.path.abspath(directory)
    while True:
        candidate = os.path.join(here, EXPORT_PDB)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def usb_root(pdb_path: str) -> str:
    """The USB root an `export.pdb` belongs to: three levels up from the file."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(pdb_path))))


def on_disk(root: str, file_path: str) -> str:
    """A track's `/Contents/...` path as a path under the USB `root` on this machine."""
    return os.path.normpath(os.path.join(root, *file_path.lstrip("/").split("/")))
