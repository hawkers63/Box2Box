<div align="center">

# Box2Box

**A Windows desktop viewer for the fixtures, results, grids and league tables in a Football Manager 27 (or 26) save.**

Saves are read with [fmsave](https://rhiever.github.io/fmsave/) and are never modified.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![GUI](https://img.shields.io/badge/GUI-CustomTkinter-green.svg)](https://customtkinter.tomschimansky.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20All%20Rights%20Reserved-red)](LICENSE)

**Database viewer** · entry point `fm_review.py` · launcher `Box2Box.bat`

**Release:** 1.6  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 1.6), launched with `Box2Box.bat`

</div>

---

## Key features

- **Competitions hub.** Browse every competition in the save, classified into *Your Club*, *League*, *Cup*, *Youth / Reserves* and *Friendlies*. The hub shows entrants, fixture volume, matches played and season progress. Click a row to select that competition; double-click it, or pick it in the list on the left, to open it in the view you last used.
- **Fixture grid.** A high-contrast home-and-away matrix. When you follow a club, its row and column show results from that club's perspective (emerald for wins, amber for draws, crimson for defeats).
- **League standings.** Broadcast-style zone colours for promotion, play-offs and relegation, taken from the save's own competition rules where they can be matched — for example the Championship shows 1st–2nd promoted, 3rd–8th in the play-offs and 22nd–24th relegated. Where the rules cannot be matched (League One and League Two before their season starts), and for the Champions League and Europa League places of a 20-team top division, the zones are estimated from the league's size, and the note above the table says so. Zones are shown on the Overall table. Split the table instantly between **Overall**, **Home**, **Away** and **Form (last five matches)**. Form is drawn as coloured W, D, L and ? badges, each row has a strip down its left edge in its zone's colour, a colour key sits under the table, and a small bar under each goal difference shows how large it is. Hover a badge to see that match in words, for example "Won 2-1 v Leeds United, Sat 8 Aug"; the same works in the Analysis Form panel and the inspector. A table worked out from the results separates teams level on points as the competition's own rules list them, where results can settle it (wins first in MLS and Brazil, goal difference first in most leagues), and the note says which order it used.
- **Analysis.** Three looks at a season, each stating how much of it the save covers:
  - **Form:** every team's last five results, current run, points per game, totals (clean sheets and failures to score among them) and longest winning, unbeaten, winless and losing runs, with the season's records underneath. Click a team to follow it; its last five appear in words below the sheet. A played match whose score the save does not hold shows as **?**, counts in no total, and any run it touches reads "at least".
  - **Positions:** each team's place after every matchday, worked out from the results and ranked within each of the game's tables (conferences and zones included), coloured by zone, and checked against the game's own table. For a league with at least two seasons in the save, a *Matchday chart* / *Season vs season* switch at the top of the panel flips to a side-by-side final standings table, newest season on the left, with a Δ Pos column showing the move since the previous season. Each column says *(final)* when every league match has a score and *(in progress, X of Y)* otherwise, and carries its own zone fill; a club absent from a season reads "—".
  - **xG:** each team's expected goals for and against, from the match reports the save kept, beside its goals in the same matches. Over- and under-performance are green or red only where they average more than 0.25 goals a match. Missing values are left blank, never shown as 0.00.
- **Themes and club colours.** Four colour themes, switched at once from **Theme ▾**, and the colours of the club you follow worked into the title band, the selected view and the followed team's highlight. See *Themes and club colours* below.
- **Cup bracket.** **Analysis → Bracket** draws a knockout cup as a tree of its last rounds (the final and up to three rounds before it): each tie shows both sides and their goals in each match, the winner in bold, and a line to the tie it fed; the earlier rounds are listed below. Two legs are decided on aggregate and a replay belongs to its tie. The save does not store extra time or penalties, so the winner of a drawn match is the side that plays in the next round, marked with a star. A competition that does not end in a single final says so and lists its rounds, and a group or league phase is counted, not drawn. The panel is for cups; a league says so.
- **Ties.** In a competition with two-legged ties (the same two sides meeting twice in a round, home and away), **Analysis → Ties** lists each tie with both legs, the aggregate and where it stands, for example "Wrexham go through" or "Second leg to play". The save stores no away goals, extra time or penalties, so a level aggregate says it is not decided there. Elsewhere the panel says the competition has no two-legged ties. Rounds the save names (third round to final) keep their names; others read "Round 1", "Round 2".
- **Counts on the view switch.** In a window wide enough for them (about 1540 pixels), the switch shows how many matches are still to play in the competition and season (`Results (254)`), how many competitions the save holds (`Competitions (500)`), and the followed team's current run once it is three or longer (`Table (N11)`): **W** won in a row, **U** unbeaten, **N** without a win, **L** lost in a row, with a **+** when a match with no recoverable score could make the run longer. In a narrower window the switch shows plain names, so the counts never squeeze the controls beside it. The window itself cannot be made narrower than its controls need (about 1,410 pixels, or your screen's width if that is less).
- **Command palette.** **Ctrl+K** or **Ctrl+P** opens a search box over the window; type a few letters, press **Enter**, and you are there. It finds competitions, clubs, the five views, the Table's splits, Results' groupings, the Analysis panels, and actions (exports, themes, **Open save…**, **About** and the like). Up and Down move, **Esc** closes. Clubs are those of the open competition plus every senior league and cup in the save, never youth, reserve or friendly competitions; a club opens in its main league and is followed. Matching ignores case and accents, and `utd` finds *United*.
- **Right-click menu.** Right-click a row in Results, Grid, Table or Analysis to follow either club on it, to **Show only** the meetings of the two clubs in a match (a note and **Clear** button show while the filter is on), to export, or to copy. **Head-to-head…** is there but greyed: it needs saves from more than one season.
- **Inspector.** The **Inspector** button beside Export, or **Ctrl+I**, opens a drawer over the right edge of the sheet; the same button, **Ctrl+I**, **Esc** or its ✕ close it. It stays shut until you ask, follows whatever you select, and never takes the keyboard from the sheet. When its content is longer than the window, it scrolls with the mouse wheel. Select a match (a Results row or a Grid cell) to see its date, kick-off, round and status, the score, the statistics the save's match report holds (xG, shots, shots on target, possession, passes, corners, fouls and cards for each side), the followed club's last five results and run, and every meeting between the two clubs across every competition and season the save holds, grouped by competition and season. Select a club (a Table, Analysis or Grid row) to see its form, record, points per game, next match and expected goals. In the Competitions hub it describes the selected competition. A figure the save does not hold shows as **—**, never 0, and a match with no report says so.
- **Copy for a post.** **Export ▾ → Copy for a post ▸** (or the command palette) copies the **Table**, **My club's results** (with your next match) or the **Recent results** (the latest round) as a table ready to paste into a Reddit or SI forums career update. One copy puts two versions on the clipboard: Markdown text, which Reddit's editor takes, and an HTML table, which a rich editor takes. Each ends with the in-game date and how complete the data is, and a match with no recoverable score reads "n/a". Zone and club colours are left out, because forums strip them.
- **Weekly results.** Every match in chronological order, grouped by calendar week (Monday start), matchday or date. Pick a club to view their campaign with W/D/L indicators and running points. Matches with a match report in the save show their expected goals (xG); click one for its xG scoreline, for example `Hull City [1.82] 2-1 [0.45] Leeds United`.
- **Coverage.** Transparent counts of played matches, matches still to play, and played matches with unrecovered scorelines ("n/a").
- **Competition names.** Saves do not store competition names, so a competition first appears by its id and best-known clubs, for example `[8] West Ham, Wolves, Burnley`. Use **Name this competition…** to name it. Names go in `competition_names.csv` (`database_id,name`), keyed on the game's database id, so they apply to every save and can be edited in Excel. fmsave reads the same format.

## Glimpse

The main window on a made-up league of fictional clubs, in the Midnight Emerald theme. Nothing here is read from a save: the data is invented for the picture, and so is the followed club, whose colours were set by hand with **Club colours…**.

<div align="center">
  <img src="docs/screenshots/main-window.png" alt="Box2Box main window" width="80%">
</div>

The four themes on the same made-up league: Midnight Emerald, Cyber Pitch, Deep Slate & Gold and High-Contrast.

<div align="center">
  <img src="docs/screenshots/themes.png" alt="The four Box2Box themes" width="80%">
</div>

## Quick start

Double-click the **Box2Box** shortcut on the desktop (see below) or **Box2Box.bat**, then **Open save…**. Saves live in `Documents\Sports Interactive\Football Manager 27\games`. Reading one takes around half a minute. The save opens as soon as it has been read; its expected goals follow about 12 seconds later, while you browse. You can also drag a `.fm` save file onto the launcher to open it straight away, or onto the open window to switch to it: one save at a time, and not while another is still being read. Dropping onto the window uses `tkinterdnd2` (installed from `requirements.txt`); without it the window works as before and says so.

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

## Themes and club colours

**Theme ▾**, at the top right, changes the window's colours at once, and you stay where you are: the competition, season, team, view and scroll position do not move. Four themes come with Box2Box:

- **Midnight Emerald**, the original look and the default.
- **Cyber Pitch**: near-black surfaces with electric cyan.
- **Deep Slate & Gold**: broadcast slate with gold headings and controls.
- **High-Contrast**: white on black with yellow, where every coloured cell reads at 4.5:1 or better (the usual measure of readable text). It shows no club colours.

Your choice is remembered in `box2box_settings.json`.

The club you follow also lends its colours to the title band (with a stripe of both colours along its foot), the selected view and the followed team's highlight. They never replace a colour that carries meaning: results, zones and headings keep theirs, and a club colour is lightened or darkened until it can be read and stands apart from what surrounds it.

The colours come from a built-in list: every English league club, and the big sides of Spain, Germany, Italy, France, Portugal, the Netherlands, Scotland and Turkey. For another club, or to correct one, follow that club and choose **Theme ▾ → Club colours…**: pick its main and second colours with Windows' colour picker, or choose **No club colours**, or **Use the built-in colours** to undo a change. Your changes are kept in `box2box_settings.json`, which stays on your machine.

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

Exports are made in the colours the window has when you choose Export: its theme, and the colours of the club you follow if it has any. The workbook's sheets stay white, and CSV files are plain text.

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
| `palette.py` | The app's colour themes and how club colours are worked into them, shared by the window and the exports |
| `club_colours.py` | Football clubs' colours, for the followed club's tint |
| `command_palette.py` | The command palette: how a query finds and ranks items, and the overlay that shows them |
| `inspector.py` | The inspector drawer: what it can show, and the overlay that draws it |
| `tooltip.py` | The small tooltip shown over form badges |
| `bracket.py` | The cup bracket: where each tie's box goes (pure layout) and the canvas that draws it |
| `clipboard.py` | Puts text and an HTML table on the Windows clipboard together, for Copy for a post |
| `test_fm_data.py`, `test_fm_export.py`, `test_fm_review_ui.py`, `test_palette.py`, `test_club_colours.py`, `test_command_palette.py`, `test_inspector.py`, `test_tooltip.py`, `test_clipboard.py`, `test_bracket.py`, `test_probe.py` | Test suite |
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
