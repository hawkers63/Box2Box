# Changelog

**Release:** 2.0  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 2.0), launched with `Box2Box.bat`

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0] - 2026-11-18

Keeps history across saves, and turns it into the Yearbook: a printable PDF of a whole season.

### Added

- **A local archive.** Every save you open is banked, after it has opened, into `box2box_archive.sqlite` beside the app. Fixtures are keyed on competition, season, the two clubs and which meeting it is, so a postponed match keeps its identity. A played result is never replaced by "not played" or a missing score, and importing the same saves in any order gives the same archive. A save that disagrees with the archive is refused as a different playthrough, and a failed import leaves the archive untouched. The detail bar reports each bank ("Banked: 412 new fixtures, 3 updated, 0 conflicts", or "Already banked.").
- **The Yearbook (PDF).** *Export ▾ → Yearbook (PDF)* (and the command palette) writes one banked season as a book: matchweeks with their dates, results and the table after each, with the last six results; cup rounds and European nights in date order with aggregates on second legs; a title page that states which saves it was built from and any gap between them; and the final table of each completed league. A postponed match prints on the day it was played, marked "Matchweek N, rescheduled". Light, ink-friendly, no badges.
- League tables as at a date in the data layer (`fm_data.standings_as_of`), and each club's nation kept on the loaded save.

### Notes

- Only competitions you have named appear in the book. When one is named "Premier League", the book keeps that league's country and the continental competitions.
- The save stores no extra time, penalties or away goals, so the book never prints them: a tie level after both legs names the club that went through only when a later round shows it, otherwise it says "level".
- New dependency: reportlab (with Pillow and charset-normalizer), and the DejaVu Sans font, which is included under its own licence.

## [1.8] - 2026-11-18

Four small right-click and Form-column touches, and a quieter unverified-build notice.

### Added

- **Show only from a Table row**: with a club followed, right-clicking another club's row offers **Show only {your club} v {that club}**, which opens Results filtered to their meetings.
- **Copy a club's results**: right-click any club's row (Results, Grid, Table or Analysis) and choose **Copy {club}'s results** to put that club's played matches on the clipboard for a post, as Markdown and HTML. The item is greyed for a club with no played match, and the club you follow does not change.
- **A place spark in the Form column**: a thin line under the form pills shows the club's league place after each of its last five matches, a better place sitting higher. It is drawn for tables of up to 100 teams.
- **A faint bevel on the form pills**: a lighter top edge and a darker bottom edge, thin enough to leave the letter's contrast untouched.

### Changed

- The "Unverified build" notice in the title band is now a small muted **UV** chip. Hovering it explains the build, that fmsave borrows the nearest known layouts, and that values are unconfirmed; clicking it opens the details. It disappears by itself once fmsave supports the build. The build-check note in exports is unchanged.


## [1.7] - 2026-11-18

Adds a standalone Windows build and head-to-head from the right-click menu, and refreshes the GitHub front page.

### Added

- **Head-to-head from the right-click menu** (Results, Grid, Table or Analysis): the greyed **Head-to-head…** is now active. On a row that names two clubs (a match or a Grid cell) it opens the inspector on every meeting between them across every competition and season the save holds; on a row that names only one club it reads **Head-to-head with {followed}** and compares the row's club with the one you follow. A pair with no meetings reads "No meetings in this save."
- **Standalone Windows build** (`dist\Box2Box\Box2Box.exe`, built by `build_exe.ps1`): a self-contained folder that bundles Python, CustomTkinter, tksheet, tkinterdnd2 (with its tkdnd native library), fmsave, openpyxl and the app icon — unzip and double-click. Settings and the error log are written next to the exe, so the folder is portable. Startup is under three seconds; the exe is not code-signed, so Windows SmartScreen prompts the first time. The source-tree workflow (`Box2Box.bat`, the `.venv` and `build_launcher.ps1`) is unchanged.

### Changed

- **A new front page on GitHub.** The README has a logo (a sky-blue football on a dark green pitch between two penalty boxes, in `docs/images/`), badges, a contents list, a features table, Mermaid diagrams of how a save reaches the screen, the views, how Box2Box starts and how its modules fit together, a keyboard and mouse table, a feature tour in fold-out sections and a release history. Two examples that named real clubs and an in-game date now use the made-up league from the screenshots.
- **fmsave bumped to 0.12.6** so it reads saves made after the 18 November 2026 Football Manager Steam update. Earlier versions refused them with a `ReaderCheckError` about the club table framing.

## [1.6] - 2026-11-17

Adds the cup bracket, every meeting between two clubs in the inspector, and a side-by-side season-vs-season standings table.

### Added

- **Cup bracket** (Analysis → Bracket): for a knockout cup, the last rounds drawn as a tree, with each tie's two sides, their goals in each match (or leg), the winner in bold and a line to the tie it fed, then the earlier rounds listed below. Two-legged ties are decided on aggregate and a replay belongs to its tie. A drawn match whose winner the save does not store (it keeps no extra time or penalties) shows the side that plays in the next round, starred, with the star explained. A competition that does not end in a single final says so and lists its rounds; a group or league phase is counted, not drawn as ties. Your followed club's boxes are outlined.
- **All meetings in the inspector** (Ctrl+I on a match): the inspector drawer's match view now lists every meeting between the two clubs across every competition and season the save holds, grouped by competition and season under a muted label, with the selected match highlighted.
- **Season against season** (Analysis → Positions → *Season vs season*): when a league has at least two seasons in the save, a two-segment switch at the top of the Positions panel flips between the matchday chart and a side-by-side standings table — Club | (Pos, Pts) × seasons | Δ Pos — with the newest season on the left and Δ Pos reading the previous season's position minus the latest's. Each season's column header says *(final)* when every league match has a score and *(in progress, X of Y)* otherwise, and its Pos column carries its own zone fill. A club that did not play in a season reads "—" in its cells; a pre-season or single-season league sees the matchday chart unchanged.

### Fixed

- The Ties panel no longer shows a replay (a drawn cup match played again within days) as a two-legged tie with a made-up aggregate. A replay is recognised by a drawn first match followed within four days; every second leg in the observer save came later.

## [1.5] - 2026-11-16

Adds copy for a post, a Ties panel and form tooltips, and clears the loose ends 1.4 left.

### Added

- **Ties** (Analysis → Ties): in a competition where the same two sides meet twice in a round, home and away, a table of each tie with both legs, the aggregate and where it stands ("Wrexham go through", "Second leg to play"). A level aggregate says that the save stores no away goals, extra time or penalties, so it is not decided there, and a leg with no recoverable score reads "n/a". Your followed club's ties are highlighted.
- **Copy for a post** (Export ▾ → Copy for a post ▸, or the command palette): copies the Table, your club's results (with your next match) or the latest round of results, ready for a career update on Reddit or the SI forums. One copy puts both Markdown (for Reddit and Discord) and an HTML table (for rich editors) on the clipboard. Every copy ends with the in-game date and how complete the data is, and a match with no recoverable score reads "n/a". If the HTML version cannot be written, the Markdown still is, and the line under the sheet says so.
- **Tooltips on form.** Hover a W, D, L or ? badge in the Table's form, the Analysis Form panel or the inspector drawer to see that match in words, for example "Won 2-1 v Leeds United, Sat 8 Aug". Where a badge cannot be matched to its match for certain, it shows no tooltip rather than a wrong one.
- **The inspector drawer scrolls** with the mouse wheel when its content is longer than the window. A new selection starts at the top; the same one redrawn (after a theme change, for example) keeps its place.

### Changed

- The window can no longer be made narrower than its controls need (about 1,410 pixels, or your screen's width if that is less), so the Standings, Group by and Show switches are never cut off.
- The right-click menu follows the colour theme.
- The command palette describes a competition you have not named by its best-known clubs and size, for example "Competition 12: Northbridge, Eastmoor · 20 teams".
- A refused drop's reason clears itself after a few seconds.
- The drawer's close mark is a solid ×.

### Fixed

- A failure while handing a newly read save to the window was reported as "Match statistics (xG) could not be read" and otherwise hidden; it is now reported as the error it is.
- Closing the window cancels every pending timer, so nothing runs on a window that has gone.

## [1.4] - 2026-11-16

Adds navigation: open a save by dropping it on the window, counts on the view switch, a command palette, a right-click menu and an inspector drawer.

### Added

- **Drop a save onto the window.** Drag one `.fm` file from Explorer onto the open window and it opens as **Open save…** does; the status bar says so while you drag. Anything else is refused with a reason (several files, a folder, a file that is not a `.fm` save), and so is a drop while a save is still being read. It uses the new `tkinterdnd2` library; if that is missing or cannot load, the window opens without drop support and says so.
- **Counts on the view switch**: `Results (254)` for matches still to play in the competition and season, `Competitions (500)` for how many the save holds, and `Table (N11)` for the followed team's current run once it is three or longer (W won, U unbeaten, N without a win, L lost; a + when a match with no recoverable score could make it longer). They show only in a window wide enough for them (about 1540 pixels); in a narrower one the switch shows plain names, as before.

- **Command palette** (Ctrl+K or Ctrl+P): find any competition, club, view, split or action by typing, and run it with Enter. Clubs come from the open competition and every senior league and cup in the save (never youth, reserve or friendly competitions); a club opens in its main league and is followed. `utd` finds *United*; case and accents are ignored.
- **Right-click menu** on Results, Grid, Table and Analysis rows: follow a club, **Show only** the meetings of the two clubs in a match (with a **Clear** button), export, copy, and a greyed **Head-to-head…** until saves from several seasons can feed it. The Competitions hub keeps its own menu.

- **Inspector drawer** (the **Inspector** button, or Ctrl+I): a drawer over the right edge of the sheet, shut until opened, describing what you select. A match shows its score, the statistics from the save's match report (xG, shots, shots on target, possession, passes, corners, fouls, cards), the form of the followed club and this season's meetings between the two clubs; a club shows its form, record, points per game, next match and expected goals; the Competitions hub shows the selected competition. A figure the save does not hold shows as a dash, never 0. The statistics are kept when the save's expected goals are read, so nothing is read from the save again.

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
