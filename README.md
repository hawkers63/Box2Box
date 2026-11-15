<div align="center">

# Box2Box

**A Windows desktop viewer for the fixtures, results, grids and league tables in a Football Manager 27 (or 26) save.**

Saves are read with [fmsave](https://rhiever.github.io/fmsave/) and are never modified.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![GUI](https://img.shields.io/badge/GUI-CustomTkinter-green.svg)](https://customtkinter.tomschimansky.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20All%20Rights%20Reserved-red)](LICENSE)

**Database viewer** · entry point `fm_review.py` · launcher `Box2Box.bat`

**Release:** 1.2  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 1.2), launched with `Box2Box.bat`

</div>

---

## Key features

- **Competitions hub.** Browse every competition in the save, classified into *Your Club*, *League*, *Cup*, *Youth / Reserves* and *Friendlies*. The hub shows entrants, fixture volume, matches played and season progress. Click a row to select that competition; double-click it, or pick it in the list on the left, to open it in the view you last used.
- **Fixture grid.** A high-contrast home-and-away matrix. When you follow a club, its row and column show results from that club's perspective (emerald for wins, amber for draws, crimson for defeats).
- **League standings.** Broadcast-style zone colours for promotion, play-offs and relegation, taken from the save's own competition rules where they can be matched — for example the Championship shows 1st–2nd promoted, 3rd–8th in the play-offs and 22nd–24th relegated. Where the rules cannot be matched (League One and League Two before their season starts), and for the Champions League and Europa League places of a 20-team top division, the zones are estimated from the league's size, and the note above the table says so. Zones are shown on the Overall table. Split the table instantly between **Overall**, **Home**, **Away** and **Form (last six matches)**. A table worked out from the results separates teams level on points as the competition's own rules list them, where results can settle it (wins first in MLS and Brazil, goal difference first in most leagues), and the note says which order it used.
- **Analysis.** Three looks at a season, each stating how much of it the save covers:
  - **Form:** every team's last five results, current run, points per game, totals (clean sheets and failures to score among them) and longest winning, unbeaten, winless and losing runs, with the season's records underneath. Click a team to follow it; its last five appear in words below the sheet. A played match whose score the save does not hold shows as **?**, counts in no total, and any run it touches reads "at least".
  - **Positions:** each team's place after every matchday, worked out from the results and ranked within each of the game's tables (conferences and zones included), coloured by zone, and checked against the game's own table.
  - **xG:** each team's expected goals for and against, from the match reports the save kept, beside its goals in the same matches. Over- and under-performance are green or red only where they average more than 0.25 goals a match. Missing values are left blank, never shown as 0.00.
- **Weekly results.** Every match in chronological order, grouped by calendar week (Monday start), matchday or date. Pick a club to view their campaign with W/D/L indicators and running points. Matches with a match report in the save show their expected goals (xG); click one for its xG scoreline, for example `Hull City [1.82] 2-1 [0.45] Leeds United`.
- **Coverage.** Transparent counts of played matches, matches still to play, and played matches with unrecovered scorelines ("n/a").
- **Competition names.** Saves do not store competition names, so a competition first appears by its id and best-known clubs, for example `[8] West Ham, Wolves, Burnley`. Use **Name this competition…** to name it. Names go in `competition_names.csv` (`database_id,name`), keyed on the game's database id, so they apply to every save and can be edited in Excel. fmsave reads the same format.

## Glimpse

A screenshot of the main window, captured on Windows with no save open.

<div align="center">
  <img src="docs/screenshots/main-window.png" alt="Box2Box main window" width="80%">
</div>

## Quick start

Double-click the **Box2Box** shortcut on the desktop (see below) or **Box2Box.bat**, then **Open save…**. Saves live in `Documents\Sports Interactive\Football Manager 27\games`. Reading one takes around half a minute. The save opens as soon as it has been read; its expected goals follow about 12 seconds later, while you browse. You can also drag a `.fm` save file onto the launcher to open it straight away.

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

## Start Box2Box from the desktop

`Box2Box.exe` is a small launcher that carries the Box2Box football icon. It starts Box2Box exactly as `Box2Box.bat` does, with the project's own Python, and a save dropped onto it opens straight away. Build it once, from PowerShell in the Box2Box folder:

```powershell
.\build_launcher.ps1
```

This compiles `launcher\Box2Box.cs` with the C# compiler that comes with Windows, so nothing else needs installing. It writes `Box2Box.exe` next to `Box2Box.bat` and puts a **Box2Box** shortcut on the desktop; add `-NoShortcut` to leave the desktop alone. Keep the exe in the Box2Box folder and start it from the shortcut, because on its own it cannot find the app. It never needs rebuilding when Box2Box is updated, and `Box2Box.bat` still works as before.

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
| `build_launcher.ps1`, `launcher/Box2Box.cs` | Builds `Box2Box.exe`, the launcher with the icon, and its desktop shortcut |
| `icon/football-64-sky-blue.ico` | The Box2Box icon: windows, taskbar and launcher |
| `fm_review.py` | The main Box2Box desktop application (CustomTkinter + tksheet) |
| `fm_data.py` | Pure data layer: parsing, grid matrices, standings, form, positions, expected goals and competition summaries |
| `fm_export.py` | Excel, web page and CSV exports of one competition and season |
| `palette.py` | The app's colours, shared by the window and the exports |
| `test_fm_data.py`, `test_fm_export.py`, `test_fm_review_ui.py`, `test_probe.py` | Test suite |
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

The tests write only to temporary directories and do not need a real Football Manager save. They do not reflect a private save. The probe smoke test in `test_probe.py` is skipped when the private local tool `fm27_probe.py` is not present, so a fresh clone still passes.

## Licence and copyright

Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.

Box2Box is proprietary software. Copying, distribution, modification, reverse engineering, sublicencing and commercial exploitation are prohibited without prior written consent. See [LICENSE](LICENSE) for the full terms.

The app shows the same notice: **About**, at the top right of the window, gives the version, the copyright notice and the full licence.

Canonical repository: <https://github.com/hawkers63/Box2Box>
