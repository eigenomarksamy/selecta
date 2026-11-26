@../meta-eigenomar/standards/claude-ecosystem.md

# selecta: Claude instructions

selecta is a personal music-library toolchain for a DJ workflow: one command,
seven isolated features over a shared core, and three front ends that run
them: the CLI, a local web page (`selecta web`) and a browser build. The browser
build is static files on Cloudflare Workers at selecta.eigenomar.com, deployed
on every push to `main`.

```text
selecta catalog  selecta duplicates  selecta rekordbox  selecta analyze  selecta quality
       \                 |                   |                 |              /
        \_______________________ selecta.core __________________________________/
                                  /           \
              selecta playlist-diff           selecta playlist-export

selecta web — a front end over all of the above, beside cli.py (selecta.web)
browser     — every command in a browser tab via Pyodide, at selecta.eigenomar.com
              (selecta.browser); fpcalc, ffprobe and ffmpeg as WebAssembly (wasm/)
```

## commands

```ps1
pip install -e ".[all]"       # or .[rekordbox] / .[analyze] / .[quality] / bare

selecta catalog "C:\Music\postmodern"
selecta catalog "F:\Songs" --missing-metadata   # tracks lacking a title/artist
selecta duplicates "F:/Songs"            # borrows fpcalc if none is installed
selecta duplicates "F:/Songs" --skip-fingerprint   # sizing run only, see below
selecta rekordbox --usb-path D:/ --duplicates-by-name
selecta analyze D:/                      # beat grids + phrases, no database needed
selecta quality "F:/Songs"               # measured vs claimed, -> out/quality/quality_Songs.csv
selecta quality D:/ --limit 50           # a USB; sample before the ~1 h full run
selecta playlist-diff "<spotify playlist link>" "F:\Songs"   # needs $SELECTA_SPOTIFY_CLIENT_ID
selecta playlist-diff "D:\export.csv" "F:\Songs"             # CSV export: no account needed
selecta playlist-export "<spotify playlist link>"            # -> out/playlist-export/<name>.csv

cd frontend; npm install; npm run build   # builds the page into src/selecta/web/static/
selecta web                               # http://127.0.0.1:8770, opens the browser

wsl bash wasm/build.sh                    # the audio tools as WebAssembly -> wasm/prebuilt/ (~5 min once); commit them
python build_browser.py                   # the browser build -> dist/ (npm ci, Pyodide, wheels, tools)
python build_browser.py --no-install      # same, skipping npm ci
npx wrangler dev                          # serves dist/ with _headers, http://127.0.0.1:8787
```

`pyproject.toml` is the only Python dependency manifest; there is no
`requirements.txt`. Fingerprinting needs the `fpcalc` binary and `selecta
quality` needs `ffprobe`/`ffmpeg`, which pip cannot install. (`selecta
duplicates` and `selecta rekordbox` borrow a temporary `fpcalc` when none is
installed; see `core/fpcalc_fetch.py`.) Both are documented in a comment at the
bottom of `pyproject.toml`. pyacoustid is deliberately *not* a dependency; see
`core/fingerprint.py`. Node builds the page and is never needed at run time.

**There is no test suite, linter config or CI.** Changes are verified by running
the tools on real inputs and comparing against the measured baselines under
[design](#design):

- **The reference clone** is a full copy of the reference Pioneer USB: 3,664
  audio files, 3,665 analysed tracks, 29,593 files in all. It lives outside the
  repository; ask the developer for its path. **The local library** is the
  developer's Rekordbox `master.db` (3,514 tracks), which `rekordbox` and
  `quality` read by default.
- A regression check for `catalog` is to regenerate a CSV and diff it against a
  previous one. For `rekordbox`, `git worktree add` an older commit and diff the
  two exports on identical inputs. Most baselines are byte-identical reports,
  and a change that should not move a report is checked that way.

Before proposing a commit, run whatever the change touches: `selecta --help`
and the affected command on real inputs against its baseline; `npm run build`
in `frontend/` for any page change (it type-checks first); and `python
build_browser.py --no-install` for a change to the browser build or anything it
ships. State how many tracks each figure was measured on.

## plan

The plan is [docs/plan.md](docs/plan.md): verification first, then the known
debt, a regression harness and a persistent state root, then the five planned
features, as tickets in lanes (V, F, H, S, L, G, R, X, C, W, SET, DOC, SCM, MIG),
with the decisions already made (D1–D6). Each ticket has a stable anchor, its id in
lowercase, and exactly one GitHub issue titled `<id>: <title>` whose body links
that anchor. An id is never reused or renumbered, and the lanes are numbered
across the ecosystem, so a lane can skip numbers.

When work ships: the ticket's heading ends in *done*, it gets a *Result* with
what was measured, the plan's log gets a dated line, *Where selecta stands* is
updated if a command's status moved, and the issue closes. This file and the
README change with the code they describe. Where the plan and this file disagree
about what exists, this file wins.

**Five ideas are designed but not implemented**: the library manager, Serato
and Traktor export, rbxport integration, genre enrichment, and `selecta dig`.
The README's "Ideas" section says what each is and why. Nothing named there
exists in the tree; do not read a mention of one as a module to import or
extend. What the existing structure already decides for them:

- **The writers are new features.** `rekordbox` and `analyze` never write, and
  that does not change. Every writer is its own command, so a bug in one cannot
  be reached from a command whose contract is that it touches nothing. A writer
  backs up `master.db` first and refuses to run while Rekordbox holds it open.
- Serato needs `GEOB` frames written into the audio files themselves. **Nothing
  in selecta modifies an audio file today**; treat that as new ground.
- The manager will want readers `rekordbox` and `analyze` already have
  (`reader.py`'s source resolution, `core/anlz.py`). Rule 1 applies: shared
  pieces move to `core` first, as `core/rekordbox_db.py` did for `quality`.
- New dependencies stay extras, behind the handler, per rule 2. `selecta --help`
  must keep working with none of them installed.
- **`dig` breaks assumptions the local-only features share, so do not model it
  on them.** It is network-first, so its results are not reproducible from
  local inputs; it needs credentials (environment variables, never committed,
  degrading to the sources that have keys rather than failing); and it needs a
  *persistent* cache, which neither `out/` (reports) nor `tmp/` (deleted on
  exit) is. That is the state root, S5, whose location D1 decided.
  `core/spotify.py` is the Spotify adapter it would start from. Each source is
  an adapter behind one interface, because most of the interesting ones are
  gated or closed; re-verify the README's source table before building (G0).
  It stays read-only against every service.
- **rbxport** ([rbxport](https://github.com/chrisle/rbxport)) is a real
  GPL-2.0-or-later Rust/Tauri app whose crates read and write `export.pdb`,
  `exportLibrary.db`, `master.db` and ANLZ. It is meant as an oracle for
  selecta's readers and as the writer selecta's reports hand playlists to,
  **not** linked into selecta: linking makes a combined GPL work, and the
  browser build would distribute it.

## design

### layout

| Path | Purpose |
| --- | --- |
| `src/selecta/cli.py` | Top-level parser; each feature registers one subcommand |
| `src/selecta/core/` | Shared, dependency-light. Knows nothing about any feature |
| `src/selecta/features/catalog/` | `selecta catalog`: filesystem catalog and audit |
| `src/selecta/features/duplicates/` | `selecta duplicates`: duplicate scan over a music folder |
| `src/selecta/features/rekordbox/` | `selecta rekordbox`: Rekordbox reader and duplicate detection |
| `src/selecta/features/analyze/` | `selecta analyze`: beat grids and phrase structure off a Pioneer USB |
| `src/selecta/features/quality/` | `selecta quality`: audio measured (bitrate, transcode cutoff, loudness, peaks, clipping) beside what tags and Rekordbox claim |
| `src/selecta/features/playlist_diff/` | `selecta playlist-diff`: Spotify playlist tracks a folder does not have |
| `src/selecta/features/playlist_export/` | `selecta playlist-export`: a Spotify playlist to CSV |
| `src/selecta/web/` | `selecta web`: local web UI. **A front end like `cli.py`, not a feature**; imports no feature. Stdlib only |
| `src/selecta/web/static/` | The built page. Gitignored, written by `npm run build` in `frontend/` |
| `frontend/` | The page's source: React 19, TypeScript 7, Vite 8. `package-lock.json` is committed, `node_modules/` is not |
| `src/selecta/browser.py` | The browser build's Python half. **A front end like `cli.py` and `selecta.web`, not a feature**; imports no feature |
| `frontend/src/browser/` | The browser build's page side: the API swapped in for `src/api.ts`, the Pyodide worker, the audio tools' runner (`tools.ts`), the Spotify login, `_headers` |
| `wasm/` | The browser build's audio tools: `build.sh` (Linux or WSL only) builds fpcalc, ffprobe and `selecta_ffmpeg.c` as WebAssembly into `wasm/prebuilt/`, **committed** with its `stamp.json`, because Cloudflare's build cannot run `build.sh` |
| `build_browser.py` | Builds the browser version into `dist/` (gitignored): page, self-hosted Pyodide, wheels, and `wasm/prebuilt/`'s modules |
| `wrangler.jsonc` | Cloudflare Workers config serving `dist/` at selecta.eigenomar.com. `.wrangler/` is its gitignored state |
| `docs/rekordbox.md` | Detailed Rekordbox reference |
| `docs/analyze.md` | Detailed ANLZ and phrase-analysis reference |
| `docs/plan.md` | The plan; see [plan](#plan) |
| `project.yaml` | The repository's manifest for the eigenomar ecosystem: where the plan and the other documents are |
| `out/`, `tmp/` | Reports and scratch, untracked (gitignored) |

### the two architectural rules

These are the point of the structure. Breaking either undoes it.

1. **A feature may import from `selecta.core`. A feature must never import
   from a sibling feature.** If two features need the same thing, it goes in
   `core`.
2. **`add_parser` stays cheap: argparse only.** Third-party imports belong
   inside the command handler (see any `features/*/__init__.py`), so
   `selecta --help` and unrelated subcommands work without every optional
   dependency installed. `pyrekordbox` and `numpy` are extras, not base
   dependencies.

**`selecta.web` is not an exception to rule 1, because it is not a feature.**
It drives every command, which no feature may do, so it sits beside `cli.py` in
`cli.FRONTENDS` rather than in `FEATURES`, and even so it imports no feature: it
reads the parser, runs subprocesses, and reads report files. Keep it that way;
a web view that needs a feature's logic means that logic moves to `core`.
**`selecta.browser` is the same kind of thing**, a front end that runs commands
through `cli.main` and reuses `web/schema.py` and `web/reports.py`, and is held
to the same rule. It is not in `cli.FRONTENDS`: it is no subcommand, only the
module the browser build's worker imports.

Each feature package exposes `add_parser(subparsers, parents=())` and sets
`handler=` via `set_defaults`; `cli.py` dispatches on it and returns its value
as the exit code. `parents` carries the shared `--out-dir`/`--tmp-dir` parser so
those flags can be typed after the subcommand: pass it straight through to
`subparsers.add_parser(parents=list(parents))`.

### `selecta.core`

- `track.py`: the one `Track` model (frozen dataclass), `AUDIO_EXTS`, and
  `iter_audio_files`, the one directory walk, kept beside the extension list so
  the two cannot drift. It skips macOS AppleDouble `._Track.mp3` stubs, which
  match `AUDIO_EXTS` but are 4 KB of resource-fork metadata (192 on the
  reference clone). Readers convert Rekordbox ORM rows and tag objects into
  `Track`, so nothing downstream depends on pyrekordbox or mutagen types. Keep
  it that way.
- `text.py`: normalization. **Two strictnesses live here deliberately:**
  `normalize_loose` strips mix suffixes (catalog wants that; it only has tags to
  go on), `normalize_simple` does not (Rekordbox has BPM, key and duration to
  fall back on and errs toward keeping distinct releases distinct). They are in
  one file so the divergence is visible. Do not "unify" them without being
  asked.
- `tags.py`: five readers, each best-effort, so an unreadable tag never aborts
  a run.
  - `read_basic_tags`: eyed3, title and artist, reports errors. mp3 only.
  - `tracks_from_files`: mutagen, a full `Track` with BPM, key and duration.
    Batch-shaped, and it *drops* files whose duration it cannot read: right for
    the duplicate prefilter, wrong for a caller that needs a name on every row.
  - `read_title_artist_raw`: mutagen, two fields for one file, None for an
    absent field plus an error string for an unreadable file. It exists for
    `catalog --missing-metadata`, which cannot use "Unknown": a track tagged
    with the literal artist "Unknown" (the reference clone has one, a
    vinyl-only white label) would read as untagged, and a corrupt file as merely
    untagged. `read_title_artist` is a thin wrapper that answers "Unknown".
  - `read_audio_header`: an `AudioHeader` of what the file *claims* about its
    audio: bitrate and CBR/VBR mode, sample rate, bit depth (lossless only),
    length, encoder, ReplayGain, for `quality` to set beside a measurement. Its
    bitrate is mutagen's reading of the header, which for a VBR mp3 without a
    Xing/LAME header is the *first frame's*; that is the claim, and why
    `quality` measures the stream rather than trusting it. The encoder prefers
    LAME's own header (a tagger cannot touch it) over `TSSE`, which says
    "Lavf…" whenever ffmpeg re-encoded a rip. ReplayGain comes from the tag in
    any of five spellings, else from the gain LAME stores in its header (3 of
    600 sampled files carry the tag, 139 the LAME gain).

  Load-bearing details, each a bug once:
  - **No per-container branch.** Every mutagen tag object has `.get`, so
    sniffing the container on it sent FLAC and OGG down the ID3 path, where
    `TBPM`/`TKEY` do not exist: no BPM, no key, and a title stringified from a
    list (`"['Somefunkydrum']"`). `_tag` tries each field's ID3, Vorbis and MP4
    spelling in turn; the names do not collide across formats, so the first hit
    is right. `_first` is the other half: Vorbis values are lists, ID3 values
    are frames.
  - **`_tag` skips a name the container rejects.** Vorbis comments allow only
    ASCII keys, so `tags.get("\xa9ART")` on a FLAC *raises* `ValueError`, and
    the lookup reaches the MP4 spelling only when the field is absent. Uncaught,
    a FLAC or OGG missing a title or artist lost its whole read.
  - **Multi-value fields are joined with `/` (`MULTI_VALUE_SEP`), not NUL.**
    ID3v2.4 lets one frame hold several values, which mutagen and eyed3
    stringify NUL-joined (233 artist tags on the reference clone). `playlist-diff`
    splits artists on `/`. `_first` joins frames, `read_basic_tags` re-joins
    eyed3's strings. Vorbis and MP4 lists still take the first value; the clone
    has no multi-value ones to test a join against.
  - A BPM tag of `0` is read as absent: a placeholder would otherwise satisfy
    `require_bpm` and then compare against nothing.
- `rekordbox_db.py`: opening a `master.db` (explicit, or the local install's)
  and walking its content rows, shared by `rekordbox` and `quality`. `load_files`
  converts rows to a plain `RekordboxFile`, Rekordbox's own claims about a file
  (bitrate, sample rate, bit depth, file type, length in whole seconds), where
  0 means "not recorded" and is read as None. Those claims are not always right:
  54 rows of the local library list a ~130 kbps VBR mp3 as 32 kbps. Rows with
  no `FolderPath` are streaming entries and skipped. Read-only.
  **pyrekordbox is bounded below 0.5** (`pyproject.toml`): 0.5.0 replaced
  `pyrekordbox.db6`, which `open_database` uses, with `masterdb`, and the
  browser build pins 0.4.4. With 0.5 installed anyway, `open_database` raises
  `UnsupportedPyrekordbox`, which names the installed version. It is a
  `RuntimeError`, not an `ImportError`, because callers read an `ImportError`
  as "not installed" (plan, F8).
  `load_export_files` makes the same `RekordboxFile`s from a USB's own
  `export.pdb` (`pdb.py`), its `/Contents/...` paths made absolute under the
  USB, with no pyrekordbox and nothing to decrypt.
  **`open_database` is a context manager, and works without sqlcipher3.** With
  it, pyrekordbox opens the file. Without it (always in the browser build, and
  on any platform sqlcipher3 has no wheel for) the file is decrypted into a
  plain copy under `tmp/` (`sqlcipher.py`), pyrekordbox opens that with
  `unlock=False` (stdlib `sqlite3`), and the copy is deleted on exit;
  `engine.dispose()` first, or Windows refuses the delete. A non-empty
  `master.db-wal` is warned about: its pages are not in the file. Both tiers'
  `rekordbox --export-csv` are byte-identical with sqlcipher3 hidden
  (`sys.modules["sqlcipher3"] = None`).
- `sqlcipher.py`: SQLCipher 4 decryption, page by page: PBKDF2-HMAC-SHA512
  (256,000 iterations) for the key, AES-256-CBC per 4096-byte page, the last 80
  bytes of each the IV and an HMAC-SHA512 that is **checked on every page** (a
  wrong key or a damaged page is an error, not a database of noise). The local
  `master.db` (17,525 pages) decrypts with every HMAC matching, and all 48
  tables, 59,214 rows and the schema equal sqlcipher3's read. ~4 s natively; in
  Pyodide 0.3 s (PBKDF2), 1.1 s (AES) and 0.4 s (HMAC). **pycryptodome, not
  `cryptography`:** the latter's Rust extension panics on import in Pyodide
  314, and Pyodide's stdlib has no `hashlib.pbkdf2_hmac` (no OpenSSL). The
  `rekordbox` extra carries it.
- `pdb.py`: reads `export.pdb`, the DeviceSQL database a Pioneer USB carries
  for the players, **with the stdlib alone**: it is not encrypted (only
  `exportLibrary.db` beside it is, and that is not read). Fixed-size pages, each
  one table's, rows in a heap from the front and their offsets in groups of 16
  from the back. Tracks, and the artist, album, genre, key and label tables
  their ids point into; nothing else. The layout is Deep Symmetry's published
  analysis (Crate Digger), and **its rows equal rbxport's `rbl-pdb`'s** on the
  reference USB: 3,587 tracks and all five named tables, every field in file
  order (plan, F6). `rbl-pdb` is run as an oracle only, so no GPL code is here.
  Load-bearing: rows are live by the group's **presence bits**, not the row
  count (a deleted row keeps its offset); a table's first page is an index page
  (flag 0x40) and holds no rows; a page chain is followed to the table's last
  page, and a loop, a page out of range or another table's page is a
  `PdbError`; strings are short ASCII, long ASCII (0x40) or UTF-16LE (0x90)
  by their first byte (85 titles on the reference USB are the last).
  `rbl-pdb` names string slot 15 `date_added`; it is Deep Symmetry's analysis
  date (later than slot 10 on the 144 tracks analysed again), and both are
  kept. `find_export_pdb` finds the USB a folder is on by walking up. 0.3 s
  for the reference USB.
- `tools.py`: running fpcalc, ffprobe and ffmpeg (`run`), so a front end can
  change how: `runner` is a subprocess by default and the browser build's
  WebAssembly otherwise (`selecta.browser._run_tool`). **stdout is streamed in
  exactly `chunk_size` pieces however the tool wrote it** (`_Rechunk`), which is
  load-bearing: `quality` sums its spectrum over whole FFT frames per chunk, so
  other chunking would change the report. `available(tool)` replaces
  `shutil.which` for callers. Set by the browser build and nothing else.
- `anlz.py`: reads Rekordbox's own analysis (beat grid, phrase structure) out of
  the `PIONEER/USBANLZ/` files on a Pioneer USB, the only ANLZ reader. Backs
  `selecta analyze`; see `docs/analyze.md`. **It walks the ANLZ tag chain and
  parses one tag at a time instead of calling `AnlzFile.parse_file`, and both
  halves of that are load-bearing.** *Selective*, because waveform tags are
  almost all of the bytes and nothing renders them: parsing only
  `ANALYSIS_TAGS` takes a full-library scan from 8m28s to 49s. *One tag at a
  time*, because pyrekordbox parses a file as a single construct `Struct`, so
  one tag it dislikes loses the whole file: `PQTZ` declares its second header
  word `Const(0x00080000)` when only the high half is fixed, which discards 119
  of 3,665 beat grids, and newer Rekordbox emits `PVDI`/`PVB2` tags it has never
  seen. The binary layouts come from `pyrekordbox.anlz`; this module never
  re-describes them, it chooses which to parse and survives the ones that fail.
  Key is *not* in ANLZ (database only), and cue points are deliberately
  unparsed: the reference USB has one hot cue in 3,665 tracks.
- `grouping.py`: `UnionFind`, for collapsing pairwise matches into groups.
  Feature-specific group *construction* stays in the feature.
- `duplicates.py`: the two-stage detector (metadata prefilter, fingerprint
  confirm, union-find), `find_duplicates_by_name`, and `fingerprint_preflight`,
  shared by `duplicates` and `rekordbox`. **Which prefilter dimensions are
  available depends on the source, so `require_bpm` and `key_must_match` are
  config, not assumptions:** a Rekordbox library has analysed BPM and key for
  everything, a plain folder has only what the tags carry. Duration is the one
  dimension always present (decoded from the stream, not read from a tag), so it
  is always required and the others are opt-in. A non-required dimension is
  still used when both tracks in a pair happen to have it.
  **Progress counts tracks fingerprinted, not pairs compared** (every
  `FINGERPRINT_PROGRESS_EVERY`, ~140 lines on the reference clone): fingerprinting
  is the time, so a front end's bar, which draws the line's first `N/M`, keeps
  pace with the clock and never runs backwards. `tracks_from_files` reports
  "reading tags: N/M" the same way (`log=`).
- `fingerprint.py`: chromaprint via `fpcalc`; similarity is Hamming distance over
  the int32 subfingerprints. **It shells out to `fpcalc -raw -json` rather than
  using pyacoustid, and that is load-bearing.** `acoustid.fingerprint_file`
  returns the *compressed* base64 fingerprint, and decoding that goes through
  `chromaprint.py`, a ctypes wrapper around the native `libchromaprint`, which
  the standalone `fpcalc.exe` does not ship: every track fingerprints and the
  first comparison raises `ImportError: couldn't find libchromaprint`. `-raw`
  returns the integers directly. Do not "modernize" this back onto pyacoustid.
  Unrelated tracks score ~0.5, not ~0: half the bits of two random 32-bit words
  agree by chance, hence the 0.85 threshold. A missing binary raises
  `RuntimeError`; a file that merely fails to decode returns `None`. Callers
  depend on that distinction. fpcalc runs through `core.tools`.
  **On Windows, a path with no UTF-8 form is fingerprinted through a copy**
  (`_plain_named`). fpcalc converts its wide argv to UTF-8 for FFmpeg, and a
  lone surrogate (see [text encoding](#text-encoding)) has no UTF-8 form, so
  the name arrived intact and FFmpeg still opened a file that does not exist.
  The copy goes into a `paths.scratch` under `tmp/` and is deleted when fpcalc
  exits. Do not replace it with a hard link: a link needs `tmp/` on the
  library's volume, and FAT and exFAT have no hard links. POSIX needs no copy,
  because `subprocess` passes escaped bytes back unchanged, and the browser
  build is POSIX. A failed copy returns `None`, caught apart from the
  missing-binary `FileNotFoundError`.
- `fpcalc_fetch.py`: the escape hatch for the one dependency pip cannot install.
  `borrowed_fpcalc()` is a context manager: it yields an installed fpcalc if
  there is one (downloading nothing), otherwise it fetches the pinned
  Chromaprint release into a `paths.scratch` under `tmp/`, unpacks the binary,
  checks it runs, and yields that, **and a `finally` deletes it when the block
  exits, on success, on error and on Ctrl-C alike.** That `finally` is `_purge`,
  not `paths.scratch`'s own removal, and the difference is load-bearing on
  Windows: `scratch` removes with `ignore_errors=True`, and after a long run the
  just-executed `.exe` can still be held open by a scanner, so `rmtree` loses on
  a sharing violation and says nothing. `_purge` retries for a few seconds and,
  if it still cannot, says so. Nothing touches PATH. Stdlib only (`urllib`,
  `zipfile`, `tarfile`), because the thing that makes fingerprinting possible
  must not itself need a missing dependency. `CHROMAPRINT_VERSION` is pinned so a
  run cannot silently change binaries. With a `core.tools.runner` set (the
  browser build) it yields None at once.
- `playlist.py`: the `Playlist`/`PlaylistTrack` model, playlist-link parsing,
  and the playlist CSV format **in both directions**: `read_playlist_csv`
  (lenient: columns found by alias, only title and artist required, because
  exporters disagree on header names) and `write_playlist_csv` (fixed:
  Exportify's column names plus `Playlist Name`, except `Track Duration`, a
  clock where Exportify writes milliseconds; the reader parses that column only
  as m:ss or h:mm:ss). **They share a file so they
  cannot drift:** an export must read back into `playlist-diff`, and every
  column the reader uses is spelled as one of its aliases. Track references are
  held as Spotify URIs and turned into links on demand (`url`). Export-only
  fields stay at their defaults on a CSV read back. Stdlib only.
- `spotify.py`: PKCE login on a one-shot loopback server, then
  `GET /playlists/{id}/items`. Shared by `playlist-diff` and `playlist-export`.
  **Spotify's February 2026 changes are the constraint everything here is
  shaped around:** playlist contents only for playlists the user owns or
  collaborates on, the app owner must have Premium, 5 users per app, `/tracks`
  renamed `/items` and `track` renamed `item` in each entry (both keys are
  read). A 403 raises `PlaylistNotAccessible`, a `SpotifyError` subclass, with a
  neutral message; **the advice is the caller's**, because it differs:
  `playlist-diff` says "export it to CSV with Exportify", `playlist-export`
  cannot say that about itself and says "copy it into a playlist of your own".
  Client credentials **cannot work**: no user, so nothing is owned. No client
  secret exists anywhere: PKCE needs only the ID (`SELECTA_SPOTIFY_CLIENT_ID`).
  The redirect URI defaults to `http://127.0.0.1:8765/callback`
  (`SELECTA_SPOTIFY_REDIRECT_URI` overrides; without a port, a free one is
  picked). Spotify rejects `localhost` by name. **The token is not saved**: that
  waits for the state root (plan, S5). The browser build's page keeps its own
  login in localStorage; that is the page's, not this module's.
  **Two hooks exist for the browser build and nothing else:** `supplied_token`
  (set, `login` returns it instead of logging in) and `transport` (how
  `_request` sends; `urlopen` by default). A tab has no socket for the loopback
  redirect or for urllib, so `selecta.browser` sets both, and everything between
  stays this module's. Do not branch on "am I in a browser" here instead.
  Stdlib only.
- `report.py`: all CSV, JSON and sidecar writers. `newline=""` here is what
  stops the `csv` module writing blank lines between rows on Windows.
  `write_csv` takes `encoding="utf-8-sig"` for a file meant to be opened in
  Excel, which reads BOM-less UTF-8 as ANSI; only the playlist export uses it.
  Every report is opened with `REPORT_ERRORS` (`backslashreplace`) through
  `open_report`, which `analyze` streams its CSVs through too. The catalog
  sidecar alone is `surrogatepass`; see [text encoding](#text-encoding).
  `write_duplicate_report` is the shared duplicate CSV and JSON writer, so a
  folder scan and a Rekordbox run emit the same shape and can be diffed.
- `paths.py`: the counterpart to `report.py`: `report` decides *how* a file is
  written, `paths` decides *where*. Two process-global roots, set once by
  `cli.py` from `--out-dir`/`--tmp-dir` (falling back to `SELECTA_OUT_DIR`/
  `SELECTA_TMP_DIR`, then `./out` and `./tmp`). `out_dir(feature)` gives
  `out/<feature>/`; `scratch(prefix)` is a context manager yielding a temp dir
  under `tmp/` that is removed on exit, so a hard kill leaves debris somewhere
  visible and gitignored rather than in the system temp directory.
  `resolve_output(path, feature, default_name)` is the rule every output flag
  goes through: `None` gives the default under `out/<feature>/`, a bare filename
  that name under `out/<feature>/`, and anything with a directory component is
  used verbatim, which keeps `--export-csv D:/x.csv` working. Stdlib only, so
  `add_parser` may import it.

### features

#### `catalog`

One run does three things (`exporter.run`): export with a path sidecar, report
duplicates, then cross-validate by re-walking the directory and set-diffing it
against the sidecar. **The sidecar and the cross-validation are the point**: this
is an auditable export, not a dump. Preserve that property. Handles `.mp3` only,
not the full `AUDIO_EXTS` set (deferred on purpose; the export is a baseline).

- **A failed audit exits 1** (D3), so a script can gate on it, and both web
  front ends show the job as failed. 1, not 2, because `--missing-metadata` uses
  2 for a path that is not a directory. The audit is printed either way.
- **Any path style works.** `exporter.run` makes the directory absolute before
  anything else, so the sidecar records the same `os.path.abspath` spelling
  `validate_mp3_csv` compares against: forward slashes, backslashes, a trailing
  separator and a relative path give byte-identical CSVs and sidecars. Keep the
  normalization at the top of `run`: the export and the audit must see one
  spelling.
- **`--missing-metadata` is a second mode, not a fourth step.** It skips the
  export and runs `missing_metadata.run`: every audio file whose tags lack a
  title, an artist or both, printed and written to
  `out/catalog/missing_metadata_<folder>.csv`. A flag rather than a nested
  subcommand because `selecta catalog <dir>` has a positional argparse would
  read as the subcommand name. It covers all of `AUDIO_EXTS` (untagged files are
  disproportionately WAV and AIFF), reads through `read_title_artist_raw` so an
  absent field is None, and counts a whitespace-only tag as missing. An
  unreadable file is reported as missing both, with the reason in `error`. The
  CSV is written even when empty, so a rerun after retagging replaces the old
  list. Exit code 0, or 2 for a path that is not a directory.

**Measured baseline**, `--missing-metadata` on the reference clone (3,664
files): ~8 s, **36 missing**: 3 title only, 16 artist only, 17 both (8 mp3, 8
wav, 1 aiff), 0 unreadable.

#### `duplicates`

`__init__.py` (parser), then `command.py`: walk the folder, read tags, run
`core.duplicates`, write the shared report to `out/duplicates/`. Read-only: it
never moves or deletes a file. What it owns is the *defaults*, and those are the
point.

**Why the defaults differ from `rekordbox`.** A folder has no analysis data, so
BPM and key are usually absent from the tags, and requiring them would silently
drop most of the library. The prefilter keys on duration alone by default and
the fingerprint does the deciding. `--require-bpm`/`--require-key` are for
libraries known to be fully tagged. On the reference clone (3,664 files) BPM is
tagged on 1,814 (50%) and key on 3,656 (99.8%), so `--require-key` is nearly
free there while `--require-bpm` would discard half of it.

**`--skip-fingerprint` is a sizing tool, not an answer.** Duration-only
bucketing is deliberately permissive: on a 3,459-track folder it produced 57,176
candidate pairs, which union-find chained into one group of 3,297.

`command.py` pre-flights `PREFLIGHT_TRACKS` files first, through
`core.duplicates.fingerprint_preflight`: without `fpcalc` every pair is dropped
and the run would end with a meaningless "0 duplicate groups". More than one
file is tried so one corrupt track cannot abort a healthy run, and only files
that exist are tried. The pre-flight swallows the `RuntimeError` for a missing
binary, which keeps a missing fpcalc an error message rather than a traceback.
The whole detection runs inside `core.fpcalc_fetch.borrowed_fpcalc`, and
`--no-fetch-fpcalc` opts out. **Everything that fingerprints must stay inside
that `with` block**: leaving it deletes the binary. `rekordbox` does the same.

**Measured baseline** (the reference clone, 3,664 files): 9m12s wall, 64,157
candidate pairs, 178 confirmed, **158 groups** (148 pairs, 10 triples), 9 tracks
unfingerprintable. Fingerprinting runs ~0.14 s a track and is the bulk of the
time. The widest duration spread inside a group is 0.84 s, and the groups
include an mp3/flac pair and several same-audio, different-filename hits. A run
on this folder that reports far more or far fewer groups means something
changed.

#### `rekordbox`

**Read-only by design.** Never writes to the USB or the Rekordbox database;
output goes only to `--output-dir` or `--export-csv`. Preserve this.

- `reader.py`: four-tier source resolution: an explicit or USB `master.db`,
  then the **local** Rekordbox `master.db` (preferred even when a USB is
  given, then scoped to the USB by filename via `_scope_to_usb`), then the
  USB's own `export.pdb` through `core/pdb.py` (the analysis exported with the
  tracks, matched to the USB's files by path; files without a row are read
  from their tags), then raw ID3 tags. An explicit `--db-path` to a `.pdb` is
  the third tier with that file. **Tier 1 is scoped the
  same way when the explicit `master.db` is a library's rather than the USB's
  own** (no row points inside `--usb-path`), so `--db-path <local master.db>
  --usb-path D:/` matches tier 2 byte for byte. The browser build depends on
  it: a picked `master.db` is the only way in there, and its paths mean nothing
  in a tab. Opening the database is `core/rekordbox_db.py`'s; what a row becomes
  (a `Track`) stays here.
- Detection lives in `core/duplicates.py` and `core/fingerprint.py`, shared with
  `duplicates`, so a change there affects both. This feature supplies the track
  list and the config (BPM and key required, because a Rekordbox library has
  them), and borrows fpcalc and pre-flights it as `duplicates` does.
- **This feature reads no ANLZ.** `core/anlz.py` is the only ANLZ reader. Do not
  write another here, and do not restore an old one from the history as a
  reference: it searched for `PSGL` and `PKEY` tags, neither of which exists in
  the format (the real tags are `PPTH`, `PQTZ`, `PQT2`, `PVBR`, `PCOB`, `PCO2`,
  `PWAV`/`PWV2`–`PWV7`, `PWVC`, `PSSI`), and brute-forced byte offsets for its
  BPM.

`_artist_name_v6` returns `""` when the local database has no linked artist row,
which is common, so a local-database-only export has blank artists and
`--duplicates-by-name` is correspondingly weak. Attaching the USB brings the ID3
fallback into play and fills them in.

**Measured baseline** (the local library, 3,514 tracks): 290 candidate pairs,
492 tracks fingerprinted, 6 groups; the report is byte-identical with fpcalc on
PATH and with a borrowed one. `--export-csv` and `--duplicates-by-name` are
byte-identical between runs on the same inputs.

#### `analyze`

`__init__.py` (parser), then `command.py`: stream `core.anlz.read_usb` and write
the reports. **Read-only**, like `rekordbox`. See `docs/analyze.md` for the
format.

The one thing it answers that nothing else can: **what Rekordbox worked out**
about a track, as opposed to what the library contains. Beat grid and phrase
structure live only in `PIONEER/USBANLZ/`, so this is the only feature that
needs no Rekordbox install and no `master.db`.

- **Title and artist are the one thing in the report not from ANLZ.** The format
  records a path, never a name, so `command.py` reads them from the audio file's
  tags via `core.tags.read_title_artist`, only for tracks whose file resolved,
  "Unknown" for a file that carries none (38 of 3,665, all untagged WAV and
  AIFF). About a second: mutagen reads the tag header, not the audio.
- **The command streams rather than collects, and that is the design.** A
  library's beat grids are millions of `Beat` objects; rows are written as
  tracks are read, which is why `--export-beats` costs disk and not memory.
  `read_usb(with_beats=)` exists for the same reason: the summary fields (BPM,
  first downbeat, variable tempo) are computed during the parse.
- **Phrase labels depend on the mood**, which is why `_phrase_label` takes it:
  mid and low moods name phrases by kind alone (Intro, Verse 1–6, Bridge,
  Chorus, Outro), while high mood uses fewer kinds and carries the variant in
  separate flags (`k1` picks the second Intro/Chorus/Outro, `k2`/`k3` pick which
  Up). That is 20 labels. An unrecognized kind is reported as `Unknown (mood M,
  kind K)` rather than given a plausible name, so a format change surfaces.

**Measured baseline** (the reference clone, 3,665 tracks): 49 s wall warm,
~1m15s cold, beat grid 3,655 (99.7%), phrases 3,646 (99.5%), 76,118 phrases,
moods high 2,314 / mid 1,251 / low 81, 2 variable-tempo tracks, 119 recovered
beat grids, 0 unknown labels. Of the 1,814 tracks carrying a `TBPM` tag, 17.3%
disagree with the grid by more than 0.5 BPM, 97 of them tagged at exactly half
the real tempo: the grid is a measurement, the tag is a claim.

#### `quality`

What each file's audio **is**, beside what its metadata **claims**. `__init__.py`
(parser), then `command.py`: walk (`iter_audio_files`, every `AUDIO_EXTS` type,
recursive, so a USB root works), then per file on a worker thread: names
(`core.tags.read_title_artist`), the file's claims
(`core.tags.read_audio_header`), Rekordbox's claims (`claims.RekordboxIndex`
over `core.rekordbox_db.load_files`) and the measurement (`measure.py`);
`compare.py` turns disagreements into flags; one CSV,
`out/quality/quality_<folder>.csv`. **Read-only.**

- `measure.py`: **one decode per file, and that is the design.** ffprobe for
  the stream layout, then a single ffmpeg whose `ebur128` filter (with
  `peak=true`) measures loudness and true peak *on the way through*, while the
  PCM it outputs streams into numpy for clipping, the spectrum, effective bit
  depth and stereo correlation. **`-v verbose` is load-bearing**: only at that
  level does ffmpeg end with the input stream's packet bytes (bytes over decoded
  duration is the true bitrate; tags and cover art are not packets) and its
  decode-error count. Its stderr runs to several KB before any audio, more than
  a Windows pipe buffers, so it is drained on a thread. The spectral cutoff is
  the highest frequency above -60 dB relative to the 1–8 kHz median, and
  *sharp* when the level falls ≥25 dB across it; the smoothing pads with edge
  values, because zero padding lifts every lossy file's floor at Nyquist above
  the threshold. Effective bit depth is exact (an int ≤24 bits survives
  float32), so 16-bit audio padded to 24 shows. A file that decodes to nothing
  keeps only its error: ebur128 still prints a 0.0 dB "peak" over no audio.
  **`Decoders` is load-bearing for cancel.** Ctrl-C (and `selecta web`'s cancel,
  the same signal) reaches the ffmpegs running at that moment, but worker
  threads start fresh ones from queued files before the main thread notices.
  Every ffprobe and ffmpeg is registered; an aborted run kills what is in flight
  and starts nothing more (0.8 s, no process left). Killing is fine here, unlike
  for the Python process, because these only read.
- `claims.py`: `RekordboxIndex`: a file's row by path, then by (name, size),
  which is how a USB copy is recognized, then by name only if exactly one row
  has it. A shared name matches nothing rather than putting another file's
  claims beside this measurement. The report's `rb_match` says which.
- `compare.py`: `Flag(kind, text)`. **Every threshold is named there and was set
  against the full reference clone, not picked**; read the comments before
  moving one. A "?" in a kind (`transcode?`, `lossy source?`, `upsampled?`) is
  evidence, not a verdict, as `maybe` is in `playlist-diff`. Bitrate is compared
  only for lossy audio.
- `command.py`: threads, not processes: the work is ffmpeg plus numpy that
  releases the GIL, and processes measured only 8% faster. The main thread waits
  with a 0.5 s timeout so KeyboardInterrupt lands. `--jobs 1` runs on the calling
  thread with no pool, which the browser build (no threads) forces; the report
  is byte-identical either way. "measured N/M" is printed from 0, after every
  file in a run under 2,500 files and at most every `PROGRESS_EVERY` above, so a
  slow run in a tab still moves its bar. Results are sorted by path, so a report
  is byte-identical whatever `--jobs` was. Columns are grouped by aspect:
  measured (no prefix), then `meta_` (the file's header and tags), then `rb_`;
  `issues` holds the flag kinds and `flags` the sentences, in the same order.

The Rekordbox claims come from the **local** `master.db` (or `--db-path`, which
also takes an `export.pdb`). When none was named and the local one cannot be
read, they come from the `export.pdb` of the USB being scanned
(`core.pdb.find_export_pdb`), matched by path. The local library stays first so
the baselines measured against it do not move. With neither, or with
`--no-rekordbox`, the `rb_` columns are blank and the run says why. On the
reference clone alone the USB's export matches 3,586 of 3,664 files by path;
the other 78 have no row in it (plan, F6). That run, 54m46s, flags 533: the
baseline's counts below except rekordbox bitrate, 120 (94 claimed at 32 kbps).
The browser build mounts a picked USB's
`export.pdb` for this, and there, with no `master.db` picked, `--limit 100`
matches 100 of 100 by path, with `rb_` columns identical to native (plan, F9).

`--output-csv` requires a value here, while `rekordbox --export-csv` accepts the
bare flag. That asymmetry is deliberate: this parser has a positional
`directory`, and an `nargs="?"` flag would swallow it.

**Measured baseline** (the reference clone, 3,664 files, default `--jobs` 8):
52m20s warm, 63m cold; 3,663 measured, 1 undecodable (an AIFF whose FORM header
claims 1,118 bytes of a 48 MB file). Rekordbox matched 3,069 (name+size 3,064,
name 5). **484 flagged**: clipping 227, transcode? 196 (123 at 320 kbps, 70 at
192, most with no encoder tag), rekordbox bitrate 66 (VBR without a Xing header:
48 show 32 kbps and 12 show 320), mono in stereo 23, header length 1 (a file
claiming 8:04 that holds 7:00), and undecodable 1. Loudness median -9.9 LUFS (p1
-18.4, p99 -6.2); true peak above 0 dBTP in 3,071; clip rate median 0.0009%, p90
0.054%. Cutoffs: honest 128s at 16.1–16.9 kHz, 192s at 18.8–19.1, 320s at 19.5
and up, most at 20–20.5. Two runs are cell-for-cell identical in every measured
and claimed column.

**Why a run is slow on the development machine, and what it is not.** ~2 s of
ffmpeg per track, true peak a third of it (ebur128's 4x oversampling). 8 jobs on
8 cores give only 1.3–2.5x over serial, and not because of the GIL: plain
`ffmpeg → NUL` scales the same. The antivirus uses ~2.5 cores scanning every
file ffmpeg opens while total CPU sits at 38%. More `--jobs` will not help past
~4 there; `--limit` samples.

#### `playlist-diff`

`__init__.py` (parser), then `command.py`: load the playlist (a CSV path via
`core.playlist.read_playlist_csv`, or a link via `core.spotify`), read the
folder's tags (`core.tags.read_title_artist_raw`, all of `AUDIO_EXTS`), match,
checking each file that matches by name (`checks.py`), then write
`missing_<playlist>.csv` (missing, maybe and mismatch, with `local_duration`)
and `matched_<playlist>.csv` (with Spotify's `duration` and `local_duration`)
to `out/playlist-diff/`. **Read-only** on the playlist and the files. A 403 from
Spotify is reported here with the CSV advice, not as a failure.

- `matching.py`: title and artist, three outcomes: `owned`, `maybe`, `missing`.
  **`maybe` is the design, not a hedge:** a false `owned` hides a track the user
  will never buy, so a different version (original vs a named remix) or a file
  with no artist to confirm stays visible with the file it nearly matched.
  `NEUTRAL_VERSION_WORDS` is what makes "Extended Mix" and "Radio Edit" the same
  track; anything else in a version (a remixer, dub, vip) must agree. Artists
  split on `/` first among others (304 tags on the reference clone list several
  artists that way). Each file is read several ways (tags, "Artist - Title"
  inside the title tag, cleaned filename), because the worst-tagged files are
  rips that only have the name in one place. Deliberately **not** `core/text.py`'s
  normalizers: neither handles Spotify's `Title - Remix` convention or accents,
  and a third strictness there would muddy the documented two. **When
  enrichment or `dig` needs "is this owned", this module moves to `core` (rule
  1, plan G9); it is not imported across.** `match` takes a `vet` and tries
  **every** file that matches by name, the first passing one winning in each
  tier, so a mix saved under a track's name cannot hide the real file beside it.
  Only when all fail is the answer the fourth outcome, `mismatch`, naming the
  first that failed.
- `checks.py`: whether the file that matched by name is the track. Three ways a
  file fails: **unreadable** (mutagen), **cut off** (its size under
  `CUT_OFF_RATIO`, 0.95, of what its header's bitrate and length imply) and
  **far off Spotify's length** (at least `LONGER_RATIO`, 2×, *and*
  `LONGER_SECONDS`, 10 min, longer, or at most `SHORTER_RATIO`, 0.3×). With no
  length in the playlist, under `MIN_TRACK_SECONDS` (35 s). **The length rule is
  loose on purpose:** a 7-minute extended mix against Spotify's 3:30 edit stays
  owned. Every threshold was set on the reference clone: every healthy file's
  size ratio is ≥ 1.000 and below 0.95 sit exactly the two files `quality` finds
  damaged by decoding; real tracks top out at 12–13.5 min and the files beyond
  are mixes (19–122 min); the 15 files under 30 s are samples. Only files that
  matched are read, one header each, cached per path.

**Measured baseline** (the reference clone): a full run reads 3,664 files in
~9–11.5 s. A synthetic 55-track Exportify-format playlist built from the library
(owned tracks re-spelled Spotify-style, rips matched via title tags, fake
remixes, invented tracks, real titles under wrong artists) comes out 55/55 as
constructed; that is a consistency check, not an accuracy figure. A playlist made
from every tagged file's own title, artist and length (3,628 rows, the
"self-playlist") is the byte-identity check for a change to matching. Reports
are byte-identical in Pyodide.

#### `playlist-export`

`__init__.py` (parser), then `command.py`: parse the link, log in, fetch, and
`core.playlist.write_playlist_csv` to `out/playlist-export/<playlist>.csv`
(`--output-csv` through `resolve_output`). Everything that knows Spotify or the
CSV format is in core, shared with `playlist-diff`. **Read-only** against
Spotify: read-only scopes, one file written.

**Its other job is to stand in for the missing saved login.** Every run logs in,
so the workflow for repeated diffs is export once, then `playlist-diff <the csv>
<folder>` as often as needed. That only works because the writer and reader share
`core/playlist.py`; a change to either must keep the round trip (export, read
back, same titles, artists, durations, URIs, playlist name). It **cannot** export
someone else's playlist (same endpoint, same 403), so it must not suggest itself
as the way around `playlist-diff`'s 403. Podcast episodes and tracks Spotify
removed (null `item`) are skipped and counted; local files are written with their
`spotify:local:` URI.

**Verified** against a simulated API only (`_get` and `login` patched, the real
`fetch_playlist` paginating two pages): every column, quotes and accents, the
BOM, local files, skipped counts, `--output-csv` both forms, the 403 message, and
the round trip into `playlist-diff`. With a real client ID, checked by hand on
2026-11-19: it and `playlist-diff` read a real playlist from the CLI, `selecta
web` and the browser build, and an account not on the app's user list got the
403 message (plan, V1).

### `selecta web`

`__init__.py` (parser, argparse only), then `server.py` (stdlib
`ThreadingHTTPServer`: the built page plus a JSON API), `schema.py`, `jobs.py`,
`reports.py`. The page is `frontend/`, built into `static/`. Stdlib only on the
Python side, so `selecta web` needs no extra.

- `schema.py`: **the forms are the argparse tree.** `cli.build_parser()` is read
  through `_actions`/`_choices_actions` (underscored, but what argparse's own help
  formatter uses), so a new flag on any command appears in the UI with no web
  change. Form values go back to an argv here and are **parsed by a fresh real
  parser before anything runs**, with `error` patched to raise rather than
  `sys.exit`, not `redirect_stderr`, which is process-global and this runs on a
  server thread. `PATH_HINTS` (keyed by `dest`) is the only thing argparse cannot
  say: which boxes get a Browse button. A checkbox always means "pass this flag",
  so `--no-key-match` (store_false, dest `key_must_match`) is ticked to pass it.
  Positionals go after `--`.
- `jobs.py`: **one subprocess per run**, `python -m selecta.web.child`. Three
  reasons, any one sufficient: commands report by `print`; `core.paths` roots are
  process-global; a process can be stopped and a thread cannot. **Cancel must not
  kill**: the child is in its own process group (`CREATE_NEW_PROCESS_GROUP`),
  gets `CTRL_BREAK_EVENT`, and `child.py` maps SIGBREAK to KeyboardInterrupt, so
  `finally` blocks run and a borrowed fpcalc is deleted. Only a child alive after
  `CANCEL_GRACE` (15 s, longer than `_purge`'s retries) is killed. A child does
  not see the Ctrl-C that stops the server, so `shutdown()` cancels every running
  job, and `serve` calls it in a `finally`. `PYTHONIOENCODING=utf-8` on the child,
  or a piped stdout on Windows uses the ANSI code page. Outputs are the
  `wrote <path>` lines every command prints, plus anything under
  `out/<command>/` touched during the run. One run per command at a time; jobs
  are in memory.
- `reports.py`: generic on purpose: CSV as rows, anything else as bytes. The
  dedicated views interpret report formats **in the browser** from each feature's
  file names and columns; nothing here imports a feature. CSVs under 64 MB are
  parsed once and cached (filter, numeric-aware sort, blanks last); larger ones
  (`--export-beats`) are paged by streaming only.
- `server.py`: **who else can call the API is the design question**: it starts
  commands and reads files, and any website in the same browser can send
  requests to 127.0.0.1. Four layers: bound to 127.0.0.1; a per-launch token
  exchanged at `/auth` for an HttpOnly SameSite=Strict cookie (named per port,
  since cookies ignore ports); a `Host` check against DNS rebinding; and refusal
  of `Sec-Fetch-Site` other than same-origin/none plus a foreign `Origin` on
  POST, because SameSite treats every port on 127.0.0.1 as one site. Do not add
  CORS headers or an `0.0.0.0` bind without redesigning this; LAN access was
  considered and declined. Served narrowly: reports only under the out root or a
  path a job reported writing, audio only in `AUDIO_EXTS` (with Range, for
  seeking), directory *names* for the path picker. Two Windows traps:
  `mimetypes` reads the registry, where `.js` is often `text/plain`, so static
  types are hardcoded; and `SO_REUSEADDR` lets a second socket share a taken port
  on Windows, so it is off there and `SO_EXCLUSIVEADDRUSE` is on. Default port
  8770, never 8765 (Spotify's login).
- `frontend/`: hash routing (one page, no server routes), one `<audio>` for the
  whole page (`player.tsx`), types mirroring the API in `api.ts`. Views:
  `DuplicatesView` (any `duplicates.json`; A/B keeps the playback position within
  a group; warns on metadata-only groups), `PlaylistDiffView` (only for files in
  a `playlist-diff` folder, since catalog's `missing_metadata_*.csv` has the same
  shape of name; it checks the columns, falling back to a table), `QualityView`
  (any `quality_*.csv`, columns checked the same way; a contradicted claim is
  highlighted by `compare.py`'s tolerances, but the flags themselves always come
  from the report, never recomputed in the page), and `TableView` for everything
  else. `pages/SpotifySetup.tsx` (`#/spotify`) is the step-by-step client ID
  guide for both builds; its redirect URI comes from the session
  (`spotify_redirect_uri`), and `?section=` scrolls to a heading, since the
  router owns the `#`. Its facts are Spotify's and move; it says when they were
  checked. A play button appears only on a path that is absolute on this
  machine. `npm run dev` proxies `/api` and `/auth` to a running `selecta web`
  (`SELECTA_WEB_BACKEND`) and rewrites `Origin`, or the POST check refuses it.

**Read-only like what it runs.** No view deletes or moves a file, and none
should.

**Verified** with an HTTP test script against a live server (auth, every refusal
above, paging, filter and sort, Range audio, path traversal, real jobs and their
outputs), a cancel of a real `duplicates` run mid-fingerprint with a borrowed
fpcalc (0.3 s, `tmp/` empty after), `shutdown()` with a job running, the Vite
proxy, and headless Edge via `puppeteer-core` for every view in light, dark and
phone width, with zero console errors. The full 3,664-row `quality` report loads
in 170 ms. A Spotify login driven from the UI with a real client ID was checked
by hand on 2026-11-19 (plan, V1).

### the browser build

The third front end. Static files on Cloudflare Workers (`wrangler.jsonc`: assets
only, no Worker script); Python runs in the visitor's tab through Pyodide 314.0.7
(Python 3.14) in a Web Worker. **Every command is online**
(`selecta.browser.ONLINE_COMMANDS`). Where a command needs something a tab lacks,
a core hook supplies it, and **no feature branches on being in a browser**:
fpcalc, ffprobe and ffmpeg run as WebAssembly through `core.tools.runner`,
`master.db` is decrypted by `core.sqlcipher`, and the Spotify login goes through
`core.spotify`'s two hooks. `HIDDEN_FIELDS` cuts the forms down (output
locations, tool paths, `--jobs`).

- `frontend/src/api.ts` stays the page's only link to a backend. `vite build
  --mode browser` redirects every import of it to `src/browser/api.ts` (a plugin
  in `vite.config.ts`; `src/browser/` itself still gets the real one, for
  `ApiError`), which answers the same calls in the tab. Shared components ask
  `browser` (`null` in the server build) for the little only the browser has:
  the boot screen, a picker instead of `PathPicker`, `isPlayable`/`audioSrc` for
  the player. **Keep browser-only behaviour behind `browser`**, so `npm run
  build` and `selecta web` stay as they are.
- `src/selecta/browser.py`: one entry point, `call(name, args_json)`, answering
  JSON with the status `selecta web`'s server would have sent: `boot`,
  `commands`, `prepare` (form to argv through `schema.build`; refuses an offline
  command, a path not picked in this tab, a Spotify link without a login,
  `quality --limit` over `QUALITY_LIMIT`; forces `quality --jobs 1`), `run`
  (`cli.main` in process), `outputs` (the `jobs.py` rule), `table`
  (`reports.TableReader`). `_run_tool` is `core.tools.runner` here.
- `src/browser/worker.ts` boots Pyodide, mounts picks, and runs one command at a
  time; messages are handled strictly in order. `src/browser/api.ts` keeps job
  records and logs (polled exactly as from the server), a copy of every report,
  and the picked folders.

What is load-bearing:

- **The audio tools are three WebAssembly programs, instantiated afresh per
  run** (`wasm/build.sh`, `frontend/src/browser/tools.ts`). fpcalc is Chromaprint
  1.6.1's own `fpcalc.cpp` and ffprobe is FFmpeg 7.1.1's own, both built against
  FFmpeg 7.1.1 audio-only. **ffmpeg is not ffmpeg:** since 6.0 the ffmpeg program
  requires threads, and 5.1, the last without, prints no decode-error count and
  decodes differently. So `wasm/selecta_ffmpeg.c` is the one command line `quality`
  runs, on the 7.1.1 libraries, mirroring fftools where `measure.py` looks: the
  first audio stream, others discarded, `threads=auto`, errors counted as fftools
  counts them, the guessed channel layout for a bare channel count (WAVs without
  a mask fail without it), the filtergraph built from the first frame, and the
  closing "packets read (N bytes) … decode errors" line in fftools' format.
  Anything else on its command line is refused.
  - *Fresh per run:* a program's globals are per process. *Synchronous:*
    Python's call is. The modules are worker-only and `WASM_ASYNC_COMPILATION=0`,
    so the instance is ready when the factory returns; the glue is patched (and
    the patch checked) to reuse the module compiled once, which makes an instance
    ~2 ms. *stdout* is a device handing 256 KiB pieces to Python's callback, and
    `core.tools` regroups them to the pipe's read size; a cancel lands in that
    callback, so it stops a decode mid-track.
  - *Files:* `providePicked` gives each instance the files its argv names: a
    picked folder's File mounted with WORKERFS (no copy, read through 1 MiB
    blocks), a picked single file copied. 1.7–1.8 MB per module, 5.3 MB in all.
  - *Parity with the native programs* (36 files: all 7 FLAC, 8 WAV, the AIFF, 20
    MP3): ffprobe's JSON identical on all; fpcalc identical on 23, the rest at
    similarity 0.99997; the ffmpeg tool's samples byte-identical for every
    lossless file and its statistics and loudness identical on all. MP3 samples
    differ in the last bits (no x86 vector code), which in 100 tracks moves
    `clipped_samples` by 1–4 in 11 rows and nothing else.
- **`wasm/prebuilt/` is committed, because `wasm/build.sh` cannot run where
  `build_browser.py` runs on Cloudflare** (it needs Emscripten, and compiling
  FFmpeg on every deploy, with nothing cached between builds, was rejected).
  `stamp.json`, written by `build.sh`, holds the sha256 of each source
  (`TOOL_SOURCES`, CRLF read as LF) and each module; `build_browser.py` checks
  both before `npm ci` and refuses a stale or altered set, so a change to `wasm/`
  cannot deploy with modules built before it: rerun `build.sh` in WSL or on
  Linux, and commit. `.gitattributes` keeps the modules byte-exact (`-text`) and
  `build.sh` LF. A rebuild from a warm Emscripten cache is byte-identical.
- **Packages and tools on demand.** `COMMAND_PACKAGES` (SQLAlchemy,
  python-dateutil, pycryptodome: 3.4 MB) and `COMMAND_TOOLS` are loaded before a
  command's first run, not at boot, so a first visit is 16 MB. `build_browser.py`
  reads both from `selecta.browser`, so what it ships cannot disagree.
  `--without-tools` builds without `wasm/`'s output: `NEEDS_TOOLS` (`duplicates`,
  `quality`) go offline.
- **`master.db` is a single-file pick** (Chromium's folder picker refuses
  AppData), copied into `/picked`, decrypted per run into `/tmp`. psutil is
  stubbed and pyrekordbox's platform warnings silenced (`_shim_pyrekordbox`,
  `boot`).
- **`quality` is capped at `QUALITY_LIMIT` (100) per run**, one file at a time:
  5.4–6.3 s a track in a tab. A library is for selecta on a machine.
- **Module worker.** Pyodide 314 refuses a classic one, hence Vite's
  `worker.format: "es"`.
- **The pyrekordbox shim** (`browser._shim_pyrekordbox`). `import
  pyrekordbox.anlz` runs the package `__init__`, which imports the database
  layer, sqlcipher3, which has no Pyodide build. A bare module carrying the
  package's `__path__` goes into `sys.modules` first; `anlz` itself needs only
  construct and numpy. Wheels are `--no-deps` for that reason (and eyed3's
  spurious `coverage`). numpy and packaging are Pyodide's own builds. No
  micropip: `loadPackage` installs wheel URLs.
- **The mount filter** (`src/browser/files.ts`). Only audio (`AUDIO_EXTS`,
  AppleDouble stubs included, since the catalog export counts them), anything
  under `USBANLZ`, and the USB's `PIONEER/rekordbox/export.pdb` are mounted:
  14,852 of 29,593 files on the reference USB, the rest being mostly
  `PIONEER/Artwork`. The rules come from `browser.boot`, that is from
  `core.track`, `core.anlz` and `core.pdb`, so they cannot drift. The
  `export.pdb` is what `quality` and `rekordbox` fall back to in a tab, where
  no local library exists (plan, F9).
- **NTFS order in `readdir`.** The catalog export writes rows in `os.walk` order,
  so matching a Windows run byte for byte needs NTFS's listing order (each UTF-16
  unit uppercased, compared unit by unit). Sorting files before mounting cannot
  give it: WORKERFS keeps a directory in a plain object, and objects list
  integer-like keys ("1977") first. `worker.ts` replaces WORKERFS's `readdir`
  with a sorted one.
- **The block cache in WORKERFS's `read`.** Every read is a blob slice plus a
  synchronous FileReaderSync round trip, ~0.7–1 ms almost regardless of size,
  and tag readers make several small reads per file. Reads go through 64 KiB
  blocks, 4 kept per open file: the file's own bytes, so it cannot change a
  result. `--missing-metadata`: no cache 33–35 s, 64 KiB 18–20 s, 256 KiB 18 s,
  1 MiB 28 s. `?block=N` on the page (0 = off) overrides it and logs each run's
  I/O to `console.debug`, a measuring knob.
- **Cancel interrupts Python, and a cancelled run changes no report.** `_headers`
  sends `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp` (Vite's browser-mode dev server
  too), so the page is cross-origin isolated and has SharedArrayBuffer. The page
  writes the job's number, then SIGINT, into an Int32Array shared with the worker
  (`protocol.ts`), and Pyodide's interrupt buffer turns that into a
  KeyboardInterrupt, `finally` blocks and all. Three things make it safe:
  - *All or nothing for `/out`.* `worker.ts`'s `run` renames `/out` aside and
    runs into an empty one; `putBack` then restores the earlier reports, and
    keeps what the run wrote only if it was not cancelled. It relies on no
    command reading its own earlier reports (none does). Whether a run was
    cancelled is the shared job number, read after the run, not how Python
    ended.
  - *`browser._on_cancel`* raises only inside `run`'s `try`, and once per run. A
    late cancel reaches Python during some other call, which must not fail for
    it; the page signals every 250 ms, because Pyodide clears the buffer
    unatomically and can drop a write; a second raise would cut the first one's
    `finally` short. The worker clears a stale signal before each run.
  - *The restart as the fallback:* without isolation, or if the command has not
    stopped after 5 s (`CANCEL_GRACE_MS`), the page terminates the worker and
    starts another, which re-mounts every pick and restores every report.
- **Reports live on the page as well as in Python's `/out`.** After each run the
  worker sends every file the run wrote back as bytes. Those copies survive a
  restart, are what `api.reports()` lists (instantly, even while a run blocks the
  worker) and what *Open raw* opens; `api.table()` goes to Python and waits out a
  run. Each report is held twice, which matters only for `--export-beats`.
- **Pickers.** Chromium: `showDirectoryPicker`, which asks to *view*; the handle
  crosses to the worker uncloned and is walked there. Firefox and Safari:
  `<input webkitdirectory>`, filtered on the page and handed over 1,000 Files per
  message so progress can show; Chromium offers it too for a folder it refuses.
  Mounted at `/music/<folder name>`; a pick of a same-named folder replaces the
  mount. Picks die with the tab but form values persist, so `prepare` checks the
  path and says to pick again.
- **The CSP** (`src/browser/_headers`): `default-src 'none'`, and `connect-src
  'self' https://accounts.spotify.com https://api.spotify.com` is what makes
  "your files never leave the browser" enforced rather than claimed, in the page
  and the worker alike. The two Spotify hosts are the playlist commands' and
  nothing else. `'wasm-unsafe-eval'` for Pyodide and the audio tools, `media-src
  blob:` for playback. Everything is self-hosted for this reason: do not add a
  CDN or any other origin. A test that byte-compares reports needs a second tab
  with the CSP bypassed: `fetch(blob:)` is connect-src.
- **The Spotify login** (`src/browser/spotify.ts`). The tab itself goes to
  Spotify's login and comes back to the site root with a code (PKCE, the
  visitor's own client ID, scopes from `core.spotify.SCOPES` via boot), traded
  for a token as the module loads; the query comes off at once so a reload cannot
  resend it, and the hash route the login started from is restored. A redirect
  rather than a popup because the page's COOP cuts a popup's `opener`; the cost is
  a reload, which forgets picked folders and reports, so the box says to log in
  first. That cost is also why the login is **kept in localStorage** (unlike the
  CLI's): once per browser, renewed with the refresh token 5 min before expiry,
  until *Log out*. `/me` is called at login because a development-mode app lets
  anyone log in and then answers 403 to accounts not on its user list. The
  client ID is each visitor's own (5 users per app), with a 32-hex soft check.
  Each run of a command with a `playlist` field is handed `{client_id, token}`,
  which `_spotify_login` installs for that run only, and `prepare` refuses a link
  without one. The worker reads the API with synchronous XMLHttpRequest (`_xhr`,
  over `pyodide.http.pyxhr`) as `core.spotify.transport`.
  **Spotify's `INVALID_CLIENT` pages are Spotify's and never send anyone back**
  (OAuth forbids redirecting for a client it cannot identify), which shapes two
  things. `checkClient` stops an unknown ID before the tab leaves: Spotify has no
  call for this, so it is asked to trade a code it never issued, and answers
  `invalid_client` for an unknown client and `invalid_grant` for a known one.
  Only `invalid_client` stops the login; any other answer, or none within
  `CHECK_MS` (5 s), carries on, so a change on Spotify's side costs the check and
  never a login. It cannot see an unregistered redirect URI, which also answers
  `invalid_grant`, so that page stays reachable and the way home is Back. **Back
  restores the page from the back/forward cache as it was left**, so
  `SpotifyLogin` clears `leaving` on a persisted `pageshow`, or the button would
  stay on "Opening Spotify…". Short of memory the browser evicts the page
  instead, and Back is a plain reload.
- **Self-hosted assets** (`build_browser.py`): only the four core files from the
  npm package `frontend/package.json` pins (keep `PYODIDE_VERSION` in step),
  numpy and packaging from jsDelivr checked against the lock's sha256, and the
  lock itself trimmed into `python.json`, so `pyodide/v<version>/` holds only
  release files and is cached as immutable. 16.4 MB on a first visit. The audio
  tools go under `tools/<hash>/`, named by their content, and are cached as
  immutable too. The build fails if Cloudflare's limits are exceeded (25 MiB per
  file, 20,000 files per version on the free plan); it makes 31 files, the
  largest 9.6 MB.

**Measured baseline** (reference USB, Edge 155 headless, `wrangler dev`, warm
disk cache; native from the same machine): start 2.4–2.9 s; picking the USB
12–13 s, ~10 s of it the browser listing 29,593 files; `catalog
--missing-metadata` 18–20 s (native 5.6 s), `catalog` 21 s (8.3 s), `analyze`
85–88 s (68 s), `playlist-diff` CSV 21 s (8.3 s), `duplicates` on all 3,664
tracks 30.5 min (9m12s) with the native 158 groups, `quality --limit 100` with a
picked `master.db` 9 min (~5.4 s a track; native 8 jobs ~2m15s). Every report is
byte-identical to native once `C:\…\` paths are mapped to `/music/<folder>/…`
(and `analysis.json`'s CRLF, which is Windows text mode, not the browser).
Cancel: `catalog` 0.2 s after the click, `analyze` 0.4 s, `quality` mid-decode
0.4 s, with every report unchanged; the restart fallback 0.2 s. Isolation costs
nothing measurable. **One whole-library `duplicates` run stalled** (every Edge
process at 0% CPU after ~27 min, no error anywhere), and the rerun finished. Two
more runs in Edge 158 on 2026-11-20 finished too, in 21–24 min with the same 158
groups. The cause of the stall is unknown (plan, V6).

**Verified** in headless Edge via `puppeteer-core` with the CSP enforced: every
command through the real forms, byte-compared to native; playback of a picked
file; cancel through the interrupt and through the restart; the Spotify login
against a local fake Spotify over HTTPS (reached with `--host-resolver-rules` and
`--ignore-certificate-errors`, not puppeteer's request interception, which stalls
the worker's own fetches), and the client ID check and Back against the real one,
with a real ID stopping at Spotify's login page; light, dark and phone width with
no horizontal scroll; zero console errors. When driving it, pass
`--memory-pressure-off` (with little memory free the back/forward cache is
evicted), and poll from Node, because `waitForSelector` never returns under this
page's CSP. A real Spotify login from the live site was checked by hand on
2026-11-19 (V1). The real pickers were checked by hand on 2026-11-21 (V4):
`showDirectoryPicker` on a real folder, a drive root in both pickers, and the
real `master.db` through the Windows file dialog, with Rekordbox closed and
open. A library-scale `rekordbox` fingerprint run and a multi-hour `quality`
file in a tab (V5), and the three cancel paths no test could time (V7), passed
by hand on 2026-11-24. Firefox 157 and WebKit 27.2 were checked through
Playwright on 2026-11-24 (V3): the `webkitdirectory` picker, the module worker
and the interrupt cancel work in both, and Firefox's `catalog` over the
reference clone matches native. **Not verified:** real Safari. **Known
failure:** in WebKit, runs over the clone's own files die at the first read
with Pyodide's fatal `NotFoundError` from `FileReaderSync`, cause unknown
(plan, V9). Drive Firefox and WebKit with `playwright-core` at the version
whose `browsers.json` matches the installed builds, and pick folders with
`setFiles(<folder>)` on the file chooser **Choose folder…** opens.

### conventions

- Windows-first examples: drive letters, PowerShell. Every command must still run
  on Linux (the ecosystem's portability conventions); paths are built with
  `pathlib`, never by string.
- `core/` and the feature `__init__`/`command` modules use `from __future__
  import annotations`, type hints, and module docstrings that explain *why*. Match
  that there. Older modules (`exporter.py`) are looser and untyped; match the
  surrounding file rather than upgrading it in place.
- Progress is reported by passing a `progress`/`log` callable, not by printing
  from library code. Keep `print` in `command.py` and handlers. `selecta web`
  relies on this: it shows whatever a command prints, draws a progress bar from
  any `N/M` in it, and finds reports by `wrote <path>`; keep printing those. The
  bar also shows the time left in the step (`JobPage.tsx`'s `useRemaining`): each
  new count is stamped when the page sees it, the rate is taken over the last 2
  minutes, a new total starts a new step, and it says "estimating…" for the first
  20 s, so a command that prints its count at an even pace gets a good estimate.
- `frontend/` is strict TypeScript with no linter; `npm run build` type-checks
  first. Match its style: 2-space, double quotes, function components, a comment
  saying *why* above anything non-obvious.
- `.gitignore` excludes `*.csv`, `*.txt`, `*.mp3`, `out/` and `tmp/`. **No CSV or
  TXT file in this repository is tracked**: every catalog export, report and
  sidecar is a local artifact.
- Every text file is LF in the index and on checkout (`.gitattributes`).

### text encoding

Two encoder failures shape how selecta prints and writes text.

#### printing: `cli.main` changes the error handler, not the encoding

On Windows a redirected stdout is a plain file in the ANSI code page (cp1252)
with strict errors; only a real console gets UTF-8. So a `print` of a character
outside cp1252 would raise `UnicodeEncodeError` and lose the run's output
(`playlist-diff` prints each track before writing any report). The reference
clone has 48 non-cp1252 audio paths.

The first thing `cli.main` does, before anything can print (`--help` included),
is `reconfigure(errors="backslashreplace")` on stdout and stderr (skipped where
the stream is None, as under pythonw). Whatever cannot be encoded prints as
`\uXXXX`, and lone surrogates, which not even strict UTF-8 can encode, print the
same way. A console is untouched: it is UTF-8, and 강남스타일 shows as itself.

**Do not switch redirected output to UTF-8 instead**, which looks like the
obvious fix: PowerShell 5.1's `>` does not pass a program's bytes through. It
decodes them with `[Console]::OutputEncoding` (often IBM437) and re-encodes, so
UTF-8 output turns every non-ASCII character into mojibake (`é` → `├⌐`) in the
default shell, while cp1252 output is right there for everything cp1252 covers.
The README's "Where output goes" gives the recipe for real characters in a
redirected file (`PYTHONUTF8=1` plus a UTF-8 `[Console]::OutputEncoding`).

`selecta web`: `child.py` runs with `PYTHONIOENCODING=utf-8` from `jobs.py`
(keep it, it makes the pipe UTF-8) and the same error handler, so a job that
prints a surrogate name does not die. The browser build: `selecta.browser.run`
calls `cli.main` on every run; Pyodide's stdout is a `TextIOWrapper`,
`reconfigure` works on it, and repeating it is harmless.

**A trap when verifying anything here:** Claude Code's shell sets
`PYTHONIOENCODING=utf-8:surrogateescape`, which hides the crash. Run
`Remove-Item env:PYTHONIOENCODING` first, or use a fresh PowerShell window. And
capture a UTF-8 program's output (node, or `PYTHONUTF8=1`) with Git Bash's `>`,
not PowerShell's, for the reason above.

#### reports: a lone surrogate is escaped, except in the catalog sidecar

NTFS stores names as unvalidated UTF-16, so a file name may hold half a surrogate
pair, and `os.listdir` returns it as `'\ud800'`, which strict UTF-8 cannot write.
The reference clone has no such name; fixtures are made by copying a track to
one.

- **Reports**: the six characters `\ud800`: `REPORT_ERRORS` in `core/report.py`,
  also what `cli.main` prints for it. In JSON this is no approximation: inside a
  string it is JSON's own escape for that code point, and `json.load` gives the
  exact path back. In CSV it keeps the file valid UTF-8 for Excel, `selecta web`,
  `find_repeated` and `read_playlist_csv`, at the cost of an ambiguity a report
  can live with: in a full Windows path, `a\ud800.mp3` is also what a file
  `ud800.mp3` in a folder `a` looks like.
- **The catalog sidecar**: exact, `surrogatepass` in `write_lines` and
  `read_lines`. The cross-validation set-diffs the sidecar against a fresh walk,
  and must compare identities, not renderings: the ambiguity above would let two
  files share one line. The cost: a line holding such a name is not valid UTF-8,
  so an editor shows replacement characters there. **Do not move the sidecar onto
  `REPORT_ERRORS`** to make it uniform.
- **Fingerprints**: fpcalc cannot open such a name, so on Windows
  `core/fingerprint.py` fingerprints a copy under a plain name (plan, F5).

**Verified** on fixtures (the clone's PSY pair, an untagged `Трек.mp3`, a
playlist CSV with Korean titles, two NTFS names with lone surrogates): `catalog`
(both modes) and `playlist-diff` exit 0 with every report written under
PowerShell `>`, `| Out-String`, cmd `> NUL` and Git Bash `>`; a real console
shows 강남스타일 as glyphs; surrogate names keep the audit `is_valid: True` and
round-trip through `duplicates --skip-fingerprint`'s JSON; `selecta web` shows
Korean titles in its job logs; the browser build's run log is unchanged.
`quality` and `playlist-export` redirected with non-cp1252 names to print, under
PowerShell `>` and cmd `>` (`playlist-export` against a fake Spotify through
`supplied_token` and `transport`), and on POSIX in WSL `playlist-export` and
`catalog` under `C.UTF-8`, `LC_ALL=C` and `PYTHONIOENCODING=ascii`, all exit 0
with every report written (plan, V8). Not verified: `quality` on POSIX.

## delivery

- **CI:** none. The plan accepts the gap (its "Linux and other portability
  notes"): Cloudflare's build runs `build_browser.py` on Linux on every deploy,
  which covers `npm ci`, the page's type check and build, and the wheels, and the
  browser build runs every command's Python in Pyodide on POSIX paths.
- **Deployment:** Cloudflare's Git-connected Workers build deploys
  selecta.eigenomar.com on every push to `main`: build command `python3
  build_browser.py`, deploy command `npx wrangler deploy`. It serves `dist/`,
  which the build makes, so a file added to the repository is not served unless
  the build copies it. `npx wrangler deploy` from a local build gives the same
  result. Pushing to `main` is deploying.
- **The audio tools** are built with `wsl bash wasm/build.sh` (Linux or WSL
  only, a pinned Emscripten, FFmpeg 7.1.1 and Chromaprint 1.6.1, hash-checked)
  and committed in `wasm/prebuilt/` with `stamp.json`; `build_browser.py` refuses
  to ship modules built before a change to `wasm/`.
- **Releases:** none. The version is `pyproject.toml`'s, `0.2.0`, with
  `frontend/package.json` in step.
- **Branching:** work lands on `main`.
