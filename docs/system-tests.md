# System tests of the browser build

Hand-run tests of the deployed site,
[selecta.eigenomar.com](https://selecta.eigenomar.com), for the
plan's phase 0 tickets [V4](plan.md#v4), [V5](plan.md#v5) and [V7](plan.md#v7).
They cover what a scripted browser can't fake: a real file dialog, a
library-sized run in a real tab, and a cancel timed by a person.

Each scenario lists its setup, the steps, what passes and what to note. A
scenario that fails, or that can't be done, is still a result. Note what
happened. A session then writes each ticket's result and the plan's log entry
from your notes, and for a failure it adds the known limit to the README, which
is what each ticket's *done when* asks for.

## Before you start

- **Browser:** current Edge or Chrome. Note its version from `edge://version` or
  `chrome://version`.
- **The live site,** in a normal window unless a scenario says InPrivate.
- **DevTools open on the Console** (F12) for every run. A scenario passes only
  if the Console shows no red errors. Note any that appear.
- **Isolation, checked once:** type `crossOriginIsolated` into the Console. It
  must print `true`. If it prints `false`, stop and note it, because every
  cancel would then restart Python and V7 can't be checked.
- **Inputs:**
  - the reference clone, the full folder copy of the reference USB, which the
    [native baselines](#native-baselines) were measured on. V5 and V7 use it;
  - a drive root for V4, written as `D:\` below whatever its letter. That's the
    reference USB plugged in, or, failing that, the clone mapped to a drive
    letter with `subst D: <clone folder>`, which `subst D: /d` undoes. Note
    which one you used;
  - your Rekordbox library's `master.db`;
  - a folder holding nothing but one long mix, two hours or more;
  - a small folder of 5–10 tracks.
- **For V5's long runs:** keep the machine plugged in with sleep off, and keep
  the tab in front, since a hidden tab may be slowed down.

### How the page works

Choose a command on the home page. In its form, each folder field has a
**Choose folder…** button, and in Edge and Chrome a *use the other picker* link
under it. The database field has **Choose master.db…**. A pick shows a progress
bar, then *Picked:* with the number of audio files and Rekordbox analysis files.
**Run selecta *command*** opens the job page. That page shows the log, the
elapsed time and the exit code, and has a **Cancel** button that asks you to
confirm. **Reports** lists every report the tab holds. A reload forgets every
report and every pick.

## V4 · Real pickers

Edge or Chrome. Every pick goes through a real dialog, which is why no script
can do these.

| # | Pick | Then run | Passes when |
| --- | --- | --- | --- |
| 4.1 | **Choose folder…** on the small folder | `catalog` on it | The browser asks to let the page *view* the folder, *Picked:* gives the right number of audio files, and the run ends with exit code 0 and a report in Reports |
| 4.2 | **Choose folder…** on `D:\` | `rekordbox` with the USB path and *export CSV* | It mounts (*Picked:* about 3,664 audio files plus the analysis files) and the run ends with exit code 0. If the browser refuses the drive, note its exact words: the README already allows for that, and 4.2 then passes if 4.3 does |
| 4.3 | *use the other picker* on `D:\` | the same | The browser may ask whether to *upload* the files. It's no upload, so allow it. After about 10 s of listing, *Picked:* matches 4.2, and the log says about 3,586 USB tracks with exported analysis and 78 via ID3 only |
| 4.4 | **Choose master.db…**, with Rekordbox closed. Type `%APPDATA%\Pioneer\rekordbox` into the dialog's file name box, press Enter, and pick `master.db` | `quality` on `D:\`, *limit* 20, with that `master.db` | *Picked:* names `master.db`, the run ends with exit code 0, and the report's `rb_` columns are filled for the files it matched |
| 4.5 | as 4.4, with Rekordbox open | the same | As 4.4, or note the error. Rekordbox may keep the file locked |

Note for each one: the browser's prompts word for word, and the time from
choosing the folder to *Picked:*.

## V5 · Browser runs at library scale

Edge or Chrome. For each run, note the elapsed time from the job page. Also note
the tab's peak memory from the browser's task manager (Shift+Esc), checked now
and then during the run.

**5.1 · `rekordbox` with fingerprints over the whole library.** Pick the
reference clone's folder with whichever picker worked in V4. Pick no
`master.db`, and leave *skip fingerprint* off. Then run it.

- **Passes when** the run ends with exit code 0, and its log and
  `duplicates.csv` match the [native baseline](#native-baselines): 3,664 tracks
  loaded, 446 candidate pairs and 131 groups.
- **If it stalls,** meaning the progress hasn't moved for 5 minutes and the
  tab's CPU in Shift+Esc is near 0, don't close the tab. Note the time,
  screenshot the task manager, and call a session to capture the worker's
  state, as [V6](plan.md#v6) planned to.

**5.2 · `quality` on the long mix.** Pick the folder that holds only the mix,
pick no `master.db`, and run `quality`.

- **Passes when** the run ends with exit code 0 and measures 1 file, and its
  row matches the [native baseline](#native-baselines) in every measured
  column, with neither `undecodable` nor `decode errors` among its `issues`.

## V7 · The three cancel paths no test could time

Edge or Chrome, with `crossOriginIsolated` true. Each cancel leaves a
signature on the job page, which tells you which path it took:

| Path | Job page | Log ends with |
| --- | --- | --- |
| The ordinary cancel, already verified | cancelled, exit code 130 | `cancelled`, then *Nothing this run wrote was kept; earlier reports are as they were.* |
| **7.1** the grace-period fallback | cancelled, no exit code | *cancelled: the command did not stop in time, so Python was restarted in this tab. Earlier reports are kept.* |
| **7.2** a cancel that lands as the run ends | succeeded, exit code 0, or (rarely) cancelled, exit code 0 | *The command had finished before the cancel reached it; its reports are kept.*, or (rarely) *Nothing this run wrote was kept; …* |
| **7.3** a cancel before the run starts | cancelled, no exit code | *Nothing this run wrote was kept; …*, with no `cancelled` line before it |

**Around every V7 scenario:**

1. **Before:** run `catalog` on the small folder, so the tab holds a report.
   Then screenshot Reports, which lists each report and when it was written.
2. **After:** Reports must list the same files with the same times, plus the new
   ones only when the run succeeded. One of them must still open. Then run
   `catalog` on the small folder again **without picking it again**. That run
   must succeed, which shows the tab is healthy and, after a restart, that the
   pick was mounted again.

The first run of `quality` in a tab installs its packages and audio tools
first, and the log says *installing … for selecta quality (once per tab)*.
While they install, Python isn't running, so a cancel can't stop it. 7.1 and 7.3
both use that wait: how long the install takes after the cancel decides which
path the cancel takes. A fresh InPrivate window makes the install download
again, and DevTools' Network throttling sets how long that takes.

**7.1 · The grace-period fallback.** When a command hasn't stopped 5 s after
the cancel, the page ends Python and starts it again.

1. Open the site in a new InPrivate window, open DevTools, and wait for the page
   to be ready. Then do *Before*.
2. In DevTools' Network tab, set throttling to *Slow 4G* or *3G*.
3. Run `quality` on the small folder. As soon as the *installing …* line shows,
   click **Cancel** and confirm.
4. Set throttling back to *No throttling* right away, because the restart
   downloads Python again.

- **Passes when** 7.1's signature appears about 5 s after you confirm, and
  *After* holds.
- **If you get 7.3's signature,** the install finished within the 5 s. Throttle
  harder and try again, in a new InPrivate window.

**7.2 · A cancel that lands as the run ends.** A confirm dialog holds up the
page but not Python, and that makes the timing exact.

1. Do *Before*. Then run `catalog` on the small folder.
2. On the job page, click **Cancel** at once, and leave the confirm dialog
   open.
3. Wait 30 s, so the run finishes behind the dialog. Then confirm.

- **Passes when** the job shows *succeeded* with the 7.2 line, the new report is
  in Reports and opens, and *After* holds. The *After* run must not be
  cancelled by the late signal.
- **Then by hand, without the dialog trick:** run `catalog` on the reference
  clone, which takes about 20 s. Click **Cancel** at about 18 s, and confirm the moment the
  log shows the run is done. Do this 3 times. Any signature in the table passes,
  as long as Reports agrees with it. Note which ones you got.

**7.3 · A cancel sent before the run starts.** The run is held up behind
something else, and Python must drop it without starting it.

1. Open the site in a new InPrivate window, with no throttling. Then do
   *Before*.
2. Run `quality` on the small folder. As soon as *installing …* shows, click
   **Cancel** and confirm.

- **Passes when** 7.3's signature appears and *After* holds.
- **If you get exit code 130,** the install ended before you confirmed. In a new
  InPrivate window, add a custom throttling profile and lower its download
  speed until the install outlasts your click. **If you get 7.1's signature,**
  you throttled too hard.
- **A caveat to note with the result:** the plan's wording is a run waiting
  behind *another call*. That case and this one stop the run at the same point,
  the first lines of `run` in `frontend/src/browser/worker.ts`. But the only
  calls a run can queue behind finish in well under a second, so no hand can
  time it. A scripted check, which [H1](plan.md#h1)'s browser tier could hold,
  is the way to cover that exact case.

## Native baselines

Native runs on the development machine on 2026-11-21, for comparison with 5.1
and 5.2. A tab is expected to take several times as long. Only the time
should differ: the reports match native apart from their paths, which are
`/music/<folder>/…` in a tab.

**5.1:** `selecta rekordbox --usb-path <clone> --db-path
<clone>/PIONEER/rekordbox/export.pdb`, which reads the same data a tab gets from
the USB alone. *3586 USB track(s) with exported analysis, 78 via ID3 only*, 3,664
tracks loaded, 446 candidate pairs from 3,617 eligible tracks, 131 duplicate
groups. It took 2 min 26 s, including fetching `fpcalc`.

**5.2:** `selecta quality <folder> --no-rekordbox` on a 2 h 11 min mix, a
320 kbps MP3 of 315 MB. It took 52 s.

| Column | Native |
| --- | --- |
| `bitrate_kbps` | 320.0 |
| `cutoff_khz`, `cutoff_sharp` | 20.22, yes |
| `sample_rate` | 44100 |
| `duration_s` | 7878.02 |
| `integrated_lufs`, `loudness_range_lu`, `replaygain_db` | -9.9, 8.5, -8.1 |
| `true_peak_dbtp`, `sample_peak_dbfs`, `plr_db` | 1.1, 0.28, 11.0 |
| `clipped_samples`, `clip_rate_pct` | 2062970, 0.2969 |
| `stereo_correlation` | 1.0000 |
| `decode_errors` | 0 |
| `issues` | clipping; mono in stereo |
