# Changelog

**Release:** 1.3  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 1.3), launched with `Box2Box.bat`

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Drop a save onto the window.** Drag one `.fm` file from Explorer onto the open window and it opens as **Open save…** does; the status bar says so while you drag. Anything else is refused with a reason (several files, a folder, a file that is not a `.fm` save), and so is a drop while a save is still being read. It uses the new `tkinterdnd2` library; if that is missing or cannot load, the window opens without drop support and says so.
- **Counts on the view switch**: `Results (254)` for matches still to play in the competition and season, `Competitions (500)` for how many the save holds, and `Table (N11)` for the followed team's current run once it is three or longer (W won, U unbeaten, N without a win, L lost; a + when a match with no recoverable score could make it longer). They show only in a window wide enough for them (about 1540 pixels); in a narrower one the switch shows plain names, as before.

- **Command palette** (Ctrl+K or Ctrl+P): find any competition, club, view, split or action by typing, and run it with Enter. Clubs come from the open competition and every senior league and cup in the save (never youth, reserve or friendly competitions); a club opens in its main league and is followed. `utd` finds *United*; case and accents are ignored.
- **Right-click menu** on Results, Grid, Table and Analysis rows: follow a club, **Show only** the meetings of the two clubs in a match (with a **Clear** button), export, copy, and a greyed **Head-to-head…** until saves from several seasons can feed it. The Competitions hub keeps its own menu.

### Fixed

- The "Unverified build" notice keeps its amber, on a small dark chip. With a club followed, 1.3 turned the notice white on the club's tinted title band (in the default theme, for every built-in club), which on a red club looked like an error. Its colour no longer depends on the club.

## [1.3] - 2026-11-16

Adds colour themes, the colours of the club you follow, form drawn as badges, and the Box2Box icon with a launcher.

### Added

- **Theme ▾**, at the top right, with four colour themes: **Midnight Emerald** (the original look), **Cyber Pitch** (near-black with electric cyan), **Deep Slate & Gold** (broadcast slate with gold) and **High-Contrast** (white on black with yellow, where every coloured cell reads at 4.5:1 or better). The window changes at once, keeping the competition, season, followed team, view and scroll position, and the choice is remembered.
- **Form pills.** Form is drawn as rounded W, D, L and ? badges, in the theme's result colours, in the Table's Form column and the Analysis Form panel. The letters stay in the cells underneath, so copying still gives them.
- **Table details.** A narrow strip down the left of each Table row in its zone's colour; a colour key under the Table and Positions views, in place of the "green = promotion…" sentence; and a small bar under each goal difference, growing right in the win colour or left in the loss colour, scaled to the table's largest difference.
- **Club colours.** The club you follow lends its colours to the title band (with a stripe of both colours along its foot), the selected view and its own highlight in every view, never to a result, zone or heading colour, and always readable. The colours come from a built-in list of every English league club and the big sides of Spain, Germany, Italy, France, Portugal, the Netherlands, Scotland and Turkey. **Theme ▾ → Club colours…** sets or corrects them for the club you follow, and your choices are kept in your settings file. High-Contrast shows no club colours.
- **Exports follow the theme.** The Excel workbook and the web page are made in the colours the window had when you chose Export, club colours included: the workbook's zone, result, heading and followed-team fills, and the page's stylesheet, which is now written from the theme as CSS variables. The workbook's sheets stay white, and the followed team's name in Results is written in a colour that reads on white. CSV is unchanged.
- The Box2Box football icon on the main window, the About and save details windows and the naming dialog, and on the taskbar button, where Box2Box now appears as itself rather than as Python.
- `Box2Box.exe`, a small launcher that carries the icon, and a desktop shortcut to it. `build_launcher.ps1` compiles it from `launcher\Box2Box.cs` with the C# compiler that comes with Windows. It starts Box2Box as `Box2Box.bat` does and opens a save dropped onto it.

### Changed

- The web page export's stylesheet is written from the theme as CSS variables. Under Midnight Emerald, without club colours, the page and the Excel workbook come out exactly as in 1.2.
- The README has new screenshots and a section on themes and club colours.

### Fixed

- The README said the Form table shows the last six matches; it shows the last five.

## [1.2] - 2026-11-15

Adds the Analysis view: form, streaks, positions by matchday and expected goals (xG).

### Added

- **Analysis** view, beside Results, Grid and Table, with three panels:
  - **Form:** every team's last five results, current run, points per game, totals and longest runs (winning, unbeaten, without a win, losing), with the season's records.
  - **Positions:** each team's place after every matchday, ranked within each of the game's tables, coloured by zone and checked against the game's own table.
  - **xG:** each team's expected goals for and against beside its goals in the same matches, with over- and under-performance.
- Expected goals (xG) in Results, and the xG scoreline in the details line when a match is clicked.
- Every analysis states its coverage. A played match with no recoverable score shows as "?", counts in no total, and marks any run or record it could change; missing xG is left blank, never 0.00.

### Changed

- A save opens as soon as it has been read; its expected goals follow about 12 seconds later while you browse.
- Tables worked out from the results separate teams level on points as the competition's own rules list them, where results can settle it (wins first in MLS and Brazil), and say which order they used.

### Fixed

- The Team box now shows the right team after a competition is picked in the Competitions hub; it used to keep the previous competition's team.

## [1.1] - 2026-11-15

Adds an About screen that states who owns Box2Box and on what terms it may be used.

### Added

- An **About** button at the top right of the window. It opens the About screen: the version, the copyright notice, a short summary of the proprietary licence, and the full terms from `LICENSE`.
- The status bar shows the version and the copyright notice until a save is opened.
- Screenshot of the main window (no save open) in the README.

### Changed

- The test suite no longer reflects a private save.

### Removed

- The save-coverage probe tool and its report are no longer published with the repository.

## [1.0] - 2026-11-15

First numbered release of Box2Box, a Windows desktop viewer for the fixtures, results, grids and league tables stored in a Football Manager 27 (or 26) save. Saves are read with [fmsave](https://rhiever.github.io/fmsave/) and are never modified.

### Added

- Competitions hub, classified into Your Club, League, Cup, Youth / Reserves and Friendlies, with fixture volume and season progress.
- Fixture grid with a followed-club perspective and result colours.
- League standings with promotion, play-off and relegation zone colours from the save's rules where they can be matched, otherwise estimated and labelled as such; Overall, Home, Away and Form (last six) views.
- Chronological results grouped by calendar week (Monday start), matchday or date, with a followed-team campaign and running points.
- Coverage counts for played matches, matches still to play, and played matches with unrecovered scorelines.
- Competition names stored in `competition_names.csv`, keyed on the game's database id.
- Exports of the current competition and season to an Excel workbook, a standalone web page, or CSV files, written to `Documents\Box2Box`.
