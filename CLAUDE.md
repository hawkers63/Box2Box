# Box2Box

A Windows desktop viewer for the fixtures, results, fixture grids and league tables in a Football
Manager 27 (or 26) save. It reads saves with [fmsave](https://rhiever.github.io/fmsave/) and never
changes them. README.md is the user's guide; this file is for Claude.

## "Let's get started."

The user opens each session with **"Let's get started."** Run this routine first, then report back
in a few lines:

1. **Repository**: `git status` and `git log --oneline -10`. Note anything uncommitted.
2. **Notes**: the user writes ideas and reports in `notes/notes_NN.txt`; the highest number is the
   newest. Read every note newer than the last one listed under *Status*.
3. **Error log**: read `box2box_errors.log` (not in git). The app appends a traceback whenever
   something fails; entries newer than the checkpoint under *Status* are bugs to look at first.
4. **Tests**: `.venv\Scripts\python -m unittest`. Everything should pass.
5. **Report**: the test result, any new errors or notes, and the next item in `ROADMAP.md` with a
   short plan. Ask before anything large or ambiguous; otherwise carry on.

Keep *Status* below and `ROADMAP.md` up to date as work is finished.

## Status

- Last updated: 14 November 2026.
- Notes read: notes_01 to notes_04.
- Error log reviewed up to: 2026-11-14 21:43:56. All entries up to then are fixed.
- Tests: 47 (test_fm_data, test_fm_review_ui, test_probe), all passing.
- Last session fixed: Championship play-off places (3rd to 8th, now taken from the save's own
  rules), the Competitions tab crash on teams the save cannot resolve, and picks in the left-hand
  list while the Competitions tab is open (they now open the competition).

## Roadmap

`ROADMAP.md` holds the plan, in the user's order: fixes (done), exports (next: Excel, HTML, CSV),
analysis (form, xG), then history across saves. It also lists the parked ideas and known
limitations, and has questions to settle with the user before exports start.

## Running and testing

- App: double-click `Box2Box.bat`, or `.venv\Scripts\python fm_review.py ["path\to\save.fm"]`.
- Tests: `.venv\Scripts\python -m unittest -v`. The UI tests open real windows off-screen. Lines
  such as `invalid command name "...check_dpi_scaling"` are CustomTkinter timers firing after a
  test window closes, not failures.
- Python 3.14 in `.venv`, packages pinned in `requirements.txt`. Install into `.venv` only.
- Check fixes against a real save as well as the tests. Reading a save takes about 30 seconds, so to
  iterate, read it once with fmsave, pickle the record lists (`fixtures`, `clubs`, `competitions`,
  `league_tables`, `competition_rules`, `managed_clubs`) to a scratch folder, and feed them to
  `fm_data.build_dataset`. Then run every competition through every view.

## Architecture

- `fm_data.py`: the data layer, with no UI code. `load_dataset` (runs on a worker thread) reads the
  save; `build_dataset` (pure) turns the records into a frozen `Dataset`. Everything a view shows
  is derived here and unit-tested without a window.
- `fm_review.py`: the window (CustomTkinter and tksheet). A save loads on a background thread and
  the result comes back through a queue polled with `after()`. The views are Results, Grid, Table
  and Competitions (the hub, which covers every competition at once).
- `fm27_probe.py`: a standalone report on what a save holds; its output is `fm27_probe_report.txt`.
- `competition_names.csv`: the user's competition names keyed on database id, shared by every save.

## Conventions

- British English everywhere: UI text, docstrings, comments and documents (colour, organise).
- Keep `fm_data.py` free of UI code. Work out display values there and test them headlessly.
- Never write to a save. Keep heavy work off the Tk main loop.
- Be honest about the data: tell unplayed matches from played ones with no recoverable score
  ("n/a"), and say when a value is estimated rather than read from the save.
- A failed import must leave the save that was already open untouched.

## fmsave facts worth knowing

- A team the save cannot resolve has `None` for its club uid, names and team slot (about 900
  fixtures per save). Never compare those fields with numbers unguarded.
- The save stores no competition names. The Championship is competition 8, database id 12, in the
  current career.
- Zones come from `save.competition_rules()`. fmsave links a rules block to the competition whose
  league table the save stores after it; before a season starts there is no table, so
  `fm_data.link_zone_rules` matches the block's round dates to a league's matchdays instead.
  Rounds can be unnumbered (fmsave reports 256). League One and League Two share a calendar, so
  until their tables exist their zones are estimated from the league's size.
- Stored league tables are already in the game's order, tie-breaks included. Never re-sort them.

## Git

- Remote `origin` is https://github.com/hawkers63/Box2Box (public), branch `main`.
- The user has asked Claude to commit and push when necessary: commit finished, tested work with
  clear messages and push to `origin main`.
- The repository is public. Never commit saves, `box2box_settings.json` (it holds a local path) or
  the error log; `.gitignore` covers them.
