<div align="center">

# Box2Box

**A Windows desktop viewer for the fixtures, results, grids and league tables in a Football Manager 27 (or 26) save.**

Saves are read with [fmsave](https://rhiever.github.io/fmsave/) and are never modified.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![GUI](https://img.shields.io/badge/GUI-CustomTkinter-green.svg)](https://customtkinter.tomschimansky.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20All%20Rights%20Reserved-red)](LICENSE)

**Database viewer** · entry point `fm_review.py` · launcher `Box2Box.bat`

**Release:** 1.0  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 1.0), launched with `Box2Box.bat`

</div>

---

<!-- Screenshots will be added under docs/screenshots/ when real captures from a Windows session are available. No placeholder images are included. -->

## Key features

- **Competitions hub.** Browse every competition in the save, classified into *Your Club*, *League*, *Cup*, *Youth / Reserves* and *Friendlies*. The hub shows entrants, fixture volume, matches played and season progress. Click a row to select that competition; double-click it, or pick it in the list on the left, to open it in the view you last used.
- **Fixture grid.** A high-contrast home-and-away matrix. When you follow a club, its row and column show results from that club's perspective (emerald for wins, amber for draws, crimson for defeats).
- **League standings.** Broadcast-style zone colours for promotion, play-offs and relegation, taken from the save's own competition rules where they can be matched — for example the Championship shows 1st–2nd promoted, 3rd–8th in the play-offs and 22nd–24th relegated. Where the rules cannot be matched (League One and League Two before their season starts), and for the Champions League and Europa League places of a 20-team top division, the zones are estimated from the league's size, and the note above the table says so. Zones are shown on the Overall table. Split the table instantly between **Overall**, **Home**, **Away** and **Form (last six matches)**.
- **Weekly results.** Every match in chronological order, grouped by calendar week (Monday start), matchday or date. Pick a club to view their campaign with W/D/L indicators and running points.
- **Coverage.** Transparent counts of played matches, matches still to play, and played matches with unrecovered scorelines ("n/a").
- **Competition names.** Saves do not store competition names, so a competition first appears by its id and best-known clubs, for example `[8] West Ham, Wolves, Burnley`. Use **Name this competition…** to name it. Names go in `competition_names.csv` (`database_id,name`), keyed on the game's database id, so they apply to every save and can be edited in Excel. fmsave reads the same format.

## Quick start

Double-click **Box2Box.bat**, then **Open save…**. Saves live in `Documents\Sports Interactive\Football Manager 27\games`. Reading one takes around half a minute. You can also drag a `.fm` save file onto the launcher to open it straight away.

From a terminal:

```powershell
.venv\Scripts\python fm_review.py ["path\to\save.fm"]
```

To set the environment up again:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Python 3.12 or newer is required. This working tree uses Python 3.14 in `.venv`.

## Exports

**Export ▾** (next to *Name this competition…*) saves the competition and season you are looking at:

- **Excel workbook (.xlsx)**, with these sheets:
  - Table, with its zone colours.
  - Grid, coloured as in the app.
  - Results, grouped as on screen.
  - Your followed team's results, with running points.
  - About: where the data came from.
- **Web page (.html):** one file with the same sections and colours, plus a box to show one team's matches. It opens in any browser and needs nothing else, so it can be shared as it is.
- **CSV files (.csv):** Results, Table, Grid and About, in a folder of their own, for your own analysis. Scores are written with an en dash (2–1) so that Excel does not turn them into dates.

Exports go to `Documents\Box2Box` (*Export ▾ → Open the export folder*), one per competition and season. Each is named after the competition, the season and the save's in-game date, for example `Championship 2026-27 (2026-07-16).xlsx`, so exporting the same save again replaces it while a later save gets a file of its own. Every export says which save it came from, how complete the data is, and whether the zones are the game's or estimated. If Excel has the workbook open, Box2Box leaves the old file alone and asks you to close it first.

## Project layout

| File | Purpose |
| --- | --- |
| `Box2Box.bat` | One-click launcher for the application |
| `fm_review.py` | The main Box2Box desktop application (CustomTkinter + tksheet) |
| `fm_data.py` | Pure data layer: parsing, grid matrices, standings and competition summaries |
| `fm_export.py` | Excel, web page and CSV exports of one competition and season |
| `palette.py` | The app's colours, shared by the window and the exports |
| `test_fm_data.py`, `test_fm_export.py`, `test_fm_review_ui.py`, `test_probe.py` | Test suite |
| `fm27_probe.py` | Save coverage probe |
| `fm27_probe_report.txt` | Probe report kept with the repository |
| `requirements.txt` | Pinned Python dependencies |
| `LICENSE` | Proprietary All Rights Reserved licence |
| `CHANGELOG.md` | Release history |

`competition_names.csv` and `box2box_settings.json` are created on the machine when you first name a competition or open a save. They are local files and are not part of the public tree.

## Tests

From the repository root, with the project environment:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

The same discovery command is:

```text
python -m unittest discover -s . -p "test_*.py" -v
```

The tests write only to temporary directories and do not need a real Football Manager save.

## Licence and copyright

Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.

Box2Box is proprietary software. Copying, distribution, modification, reverse engineering, sublicencing and commercial exploitation are prohibited without prior written consent. See [LICENSE](LICENSE) for the full terms.

Canonical repository: <https://github.com/hawkers63/Box2Box>
