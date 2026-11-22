# Changelog

**Release:** 2.11  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 2.11), launched with `Box2Box.bat`

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.11] - 2026-11-22

The Schedule shows how close together a club's fixtures are, and the Hub puts the next opponent in context.

### Added

- **Fixture gap (Schedule).** A "Fixture gap" option, off by default and remembered between sessions, shows on each dated row the calendar days since the club's previous dated fixture in any competition, for example "2 days since cup fixture". It is worked out from the club's whole season before any filter, so a league-only filter still counts a midweek cup tie. The first dated fixture has no gap; an undated fixture, or a fixture whose predecessor may be an undated one, reads "Gap unknown"; a fixture still to come reads "2 days after cup fixture (scheduled)".
- **Previous meeting (Hub).** When the stepper is on a matchday, a "Previous meeting" row beneath the upcoming opponent gives the date, competition and score of the latest earlier meeting of the two teams in the open save, across competitions and seasons. Only played matches dated strictly before the selected match count, so a meeting on the same day is left out on purpose. A meeting with no recoverable score reads "Score unavailable"; none, or an opponent the save cannot resolve, reads "No earlier meeting found in this save".

## [2.10] - 2026-11-22

The Yearbook gains a season trajectory, honours that say how sure they are, and a retrospective of the club you follow.

### Added

- **Season trajectory.** When the Yearbook marks a club, a chart plots its place on the calculated table after each matchweek, on the date that table is calculated to. A matchweek the club had not played, or with no printed table, is a gap: the line stops and nothing is drawn across it. Shaded bands are the latest table's zones and are labelled as estimated. In the reader, moving over a point lists the club's results printed on that matchweek's page, and nothing more. A club in no league gets a short note instead of a chart. Matchweek numbers are never called calendar weeks. The PDF draws the same places on the same dates.
- **Honours, with their evidence.** A finished league names its calculated leader, never an official champion (points deductions are not in the results), and says when a tie on points rests on a tie-break the calculation cannot follow. Clubs in the promotion and play-off places are listed as places, not as promotion or a play-off win. A cup winner is named only from a decisive final score or an aggregate; a level final stays unresolved. Each reason is a numbered footnote, worded identically in the reader and the PDF.
- **Club season retrospective.** For the marked club: its place and record in each league, its longest unbeaten run and longest run without a win (league matches, with their dates), its biggest win by margin, how far it went in each cup, and a pointer to the trajectory. It uses results only: no venue, attendance, scorer or manager detail. With no marked club the chapter is left out.

### Fixed

- **Open save and the progress bar** could switch back on while a save's expected goals were still being read, if the Schedule and Hub finished building first. They now stay locked until all background work for the save has finished, and a schedule from an older save or selection is ignored.

## [2.9] - 2026-11-19

Club roundels, and a Hub you can step back through the season.

### Added

- **Club roundels.** A small two-colour roundel, drawn from a club's colours (Theme ▾ → Club colours…), now sits beside each opponent on the Schedule, beside the followed club at the top of the Hub, and beside the next opponent on the Hub. It is an aid to telling clubs apart, not a club crest. A club with no colours gets a plain grey roundel. Its initials read at 4.5:1 or better in every theme, and in High-Contrast it is outlined in white. Results keep their W, D, L or ? letters, the H, A or N venue, and their own colours, whatever the club's colours. Exports, CSV files and the Yearbook are unchanged.
- **Matchday stepper on the Hub.** ‹ Previous, Next › and a slider move the Hub's position, table excerpt, form and next match to any of the followed club's league matchdays, each as it stood just before that match's kick-off. The label names the matchday and the date of its snapshot (a matchday played late keeps its number). Nothing from the chosen match or any later one is counted, including other matches the same day and matches with no kick-off time. **Today** returns to the save's own date. A finished season ends with a step after the last match; a club with no league steps through its matches without a league position; undated matches are counted but not placed. Following another club or opening another save starts the stepper again at the save's date.
- **A table excerpt on the Hub**: the followed club and the clubs round it, worked out from the results.

### Fixed

- **The Hub's league position** now appears. It was never shown before.
- **Schedule and Hub follow a theme change** at once, instead of keeping the colours they opened with.

## [2.8] - 2026-11-19

A better way to read the Yearbook before you save it, and the edition you save is the one you read.

### Added

- **Reader spreads.** In *Read before saving…*, choose **Single page** or **Reader spread** at the foot of the window. A reader spread puts two pages of the window side by side; it is not two printed pages of the PDF. The title page and an odd last page stand alone, and a window narrower than about 1300 px shows single pages until it is widened. Your choice is remembered.
- **Chapter strip.** A row of the chapters near the page you are reading sits above the book; click one to jump to it. Long competition names are shortened in the strip, and the full list stays on the left.
- **Bookmarks.** Each season's volume reopens at the page you left it on, even after closing Box2Box. A newer edition of the same volume reopens at the same page when it still has it, and at the title page otherwise.
- **Home and End** go to the first and last page of the book.

### Changed

- **Schedule and Hub show when they are open.** Their buttons beside Inspector take the accent colour while their view is on screen.
- **The reading window looks more like a book**: serif headings and a hairline frame round the title page. Tables keep their plain face and colours.

### Fixed

- **Choosing another season while the reading window is open** now loads that season into the window. Before, it brought the season already open to the front.
- **Save this edition saves the book you are reading.** If a newer save has been banked since the book was built, Box2Box names both editions and asks: refresh to the newer edition and save that, save the edition you are reading, or save nothing.

## [2.7] - 2026-11-19

A club's whole season in one place: the Schedule and the Hub.

### Added

- **Schedule view** (Ctrl+Shift+S, the Schedule button beside Inspector, or the palette). Every fixture of the club you follow, across all its competitions, with the club, scope and season named above it. Schedule and Hub cover a club rather than one competition, so they sit beside the competition view switch, not on it. Filter by competition, home or away, month, result or a search; a chip shows active filters and Clear removes them. It opens at the next match to play, and a same-day match not yet finished counts as still to play.
- **Hub view** (Ctrl+Shift+H, the Hub button or the palette). The followed club at a glance: its role, league position, recent form and next match with a countdown. It works on observer saves and when no club is followed.
- **The followed club stays followed.** Follow a club from the right-click menu, the palette or Theme ▾ → Follow club…, and it stays followed while you browse other competitions; opening a new save clears it. The palette also offers "Clear followed club", which empties the Schedule and Hub at once.

### Changed

- **Result pills read better.** The win and draw colours are a little darker, so white text on them meets the WCAG AA 4.5:1 contrast ratio in every theme. The new colours also reach the Excel and web-page exports: wins and home wins `#04875e` (was `#059669`), draws `#ae5f05` (was `#d97706`).

### Fixed

- **Yearbook biggest rise and fall** name every club that shares the move, not only the first.

## [2.6] - 2026-11-19

Remembers expected goals, so the Yearbook can show them even after the save that held them is gone.

### Added

- **The archive keeps expected goals (schema 3).** Each banked fixture can hold its home and away xG, stored to four decimal places; a fixture whose save kept no match report holds nothing (never 0). A figure is stored only when the save's report joined that fixture and both values are finite numbers of zero or more. Older archives are upgraded in place on first open and nothing is filled in by the upgrade. **A schema 3 archive cannot be opened by Box2Box 2.5 or earlier**, which refuse it and leave it untouched.
- **Banked when they arrive.** A save opens at once and is banked as before; its match statistics follow a few seconds later, and the figures are then added to the fixtures just banked (the detail bar says "Expected goals banked for N matches."). Opening a save you banked before 2.6 fills in its figures the same way. A save whose statistics could not be read adds nothing and says nothing.
- **Merging figures:** a missing figure is filled from any save and never replaces a stored one; two different figures for one match are a conflict, recorded beside the score conflicts (the archive's conflicts now say which kind), with the later save kept. Importing saves in any order gives the same archive.
- **xG on the Yearbook's final tables:** xG and xGA columns appear for a league where at least one club has a figure. A club with reports for only some of its matches shows the total of those, and the note says "Expected goals for N of M played matches."; a league with no reports gets no columns, not a column of blanks. **G-xG** (goals scored minus xG) appears only when every match of every club has a report. Only matches played with a score count, so the totals sit beside the same goals as the table. Weekly tables and cup pages never carry them. The read window shows the same columns and note.

### Changed

- The final table's columns are a little narrower when expected goals are present (the name column is 43 mm).

## [2.5] - 2026-11-19

Keeps every edition of a season's Yearbook, adds a contents to the PDF, and lets you read the book in the window before you save it.

### Added

- **Editions.** Saving a Yearbook no longer replaces the last one. Each edition is a file in `Documents\Box2Box\Yearbooks\<season>\`, named from the last in-game date the archive holds for that volume (`Yearbook 2026-27 (in-game 12 Nov 2026).pdf`), the same date the title page prints. A later date writes a new file and leaves the older edition alone ("Saved a new edition, 19 Nov 2026. The 12 Nov 2026 edition is unchanged."). Saving the same coverage again builds nothing and says "This edition is already saved."; **Build it again** rewrites that one file when you want a fresh draw. A failed build leaves every edition as it was.
- **A menu for each season** under *Export ▾ → Yearbook (PDF)*: **Save the latest edition**, **Build it again** (when that edition exists), **Read before saving…**, then the saved editions newest first; choosing one opens its file without rebuilding it.
- **Read before saving…** opens the book in a window: each page's lines and its table with the same columns as the PDF (± and PPG included) and the same footnotes, a list of the competitions to jump to, Previous and Next (or the arrow keys), and **Save this edition**. It reads the same page model as the PDF and builds off the main thread; nothing is written until you save.
- **A contents inside the PDF:** bookmarks for the season, each competition (at its first page; a league's play-off rounds belong to the league), each league's "How they stood" and the final tables. Matchweeks are not bookmarked.
- **Command palette:** **Save Yearbook edition…** and **Open latest Yearbook**.

### Changed

- The palette's "Export Yearbook (PDF)…" is now "Save Yearbook edition…".
- The Yearbook never includes the U18 Premier League or the U18 Professional Development League, even if you have named them.

## [2.4.1] - 2026-11-18

Fixes the standalone build and adds a single-file build.

### Fixed

- **The standalone `Box2Box.exe` had no window icon, and About said "The LICENSE file was not found".** The icon and `LICENSE` are bundled data, which PyInstaller 6 unpacks into `_internal\`, but they were looked for beside the exe. Bundled data is now read from the bundle folder (`sys._MEIPASS` when frozen, the source folder otherwise). Everything the app writes or you edit (settings, the error log, `box2box_archive.sqlite`, `competition_names.csv`) still sits beside the exe.

### Added

- **A single-file build:** `.\build_exe.ps1 -OneFile` writes `dist\Box2Box.exe` (about 37 MB) from the new `Box2Box-onefile.spec`; the one-folder build is unchanged. The single exe unpacks itself to a temporary folder on each start, so it takes a few seconds longer to open; its settings, log, archive and names file are still written beside the exe, never in the temporary folder.

## [2.4] - 2026-11-18

Shows the whole season at a glance: where every club stood, week by week, and a few figures from the results.

### Added

- **How they stood:** for each league with tables for two or more matchweeks, a landscape page of every club's place after every matchweek, in the order of the latest table. A blank means the club had not yet played; the last column is the current place, shaded by zone. The places are the ones the weekly tables printed, so the grid and the book cannot disagree. Weeks that will not fit at 7 pt split into equal parts (for example matchweeks 1-23 and 24-46) with the same clubs on each; no week or club is ever dropped. The grid comes after the weekly pages and before the final tables, and appears for a season still in progress too. European league phases do not get one.
- **From the results:** under the final table of each finished league, the most wins, best goal difference, fewest goals against and most draws; the biggest rise and biggest fall (a club's largest climb or drop between two matchweeks, naming both); and the longest winning and unbeaten runs. Clubs that share a record are all named. A club that had not played every week is left out of the rise and fall, and the note says so. A match with no score ends a run, and the strip says so. It names no player, manager or award, because the save holds none.

### Changed

- The Yearbook is drawn with two page layouts (portrait and landscape); the title page still carries no footer, and a book that ends on a grid no longer risks a blank last page.

## [2.3] - 2026-11-18

Makes the Yearbook's tables show how the season moved.

### Added

- **A "±" column on every weekly league table:** places gained or lost since the previous printed table of the same competition (`▲2`, `▼1`, `•` for no change), in the book's win, loss and muted inks. A club that had not yet played reads `–`, and so does every club on a competition's first table. A cup night does not reset it.
- **PPG on every weekly and final league table:** points per scored match to two decimals. A played match with no recoverable score is left out, never counted as a draw, and the figure carries a `*` with a note under the table.
- **Home and away records after each finished league's final table**, for the same clubs in the overall order and with the overall place and shading, calculated from the results.
- **Mark a club:** *Export ▾ → Yearbook (PDF)* offers "Mark {club} in bold" while a club is followed. It is off each time the app starts. The marked club's name is bold with a rule under its row; there is no fill.

### Changed

- Weekly tables with the new columns use a slightly narrower club-name column (50 mm); no real club name wraps. A table without them (a European league phase) is unchanged.

### Fixed

- The command-palette test that chooses a view by typing and Enter failed once on a busy machine: it now waits until the search box holds focus before sending the key.

## [2.2] - 2026-11-18

Teaches the Yearbook the shape of the European cups, play-offs and one-match finals.

### Changed

- **One-match competitions** (the Community Shield, the UEFA Super Cup) are a single dated block ("Community Shield · Sun 16 Aug") instead of a matchweek with a two-club table. A season opener keeps its place in date order.
- **Play-offs are named:** cup rounds inside a league read "Championship play-offs, Semi-final, 1st leg". A continental competition's knockout rounds do not.
- **European competitions read properly.** The league phase is "Matchday N" with its table cut to the top 16; the qualifying rounds are ties with 1st and 2nd legs and aggregates. The save reuses round numbers for separate qualifying rounds and may store a tie's legs in consecutive rounds, so the book now separates rounds by date and joins legs by the pair that plays them.

## [2.1] - 2026-11-18

Refines the Yearbook after a first review of a real volume.

### Changed

- **Yearbook level ties use an asterisk.** A side that went through a level tie is marked `*` after its name, with one footnote under the block: "* went through a level tie, decided in extra time or on penalties". The save stores no shootout, extra-time or 90-minute score, so the book still never prints one. An aggregate stays in brackets on the second leg, and a level tie nobody is known to have won reads "(level)".
- **European league phases read "Matchday N"** instead of "Round N", and get a table after the last day of each matchday, cut to the top 16 ("Top 16 of 36 shown"). A league phase is recognised by nearly the same clubs playing round after round, or a pair meeting again, so its drawn games no longer get tie notes.
- **Long club names use the game's short name** (over 24 characters, and only when the game has a shorter one).
- **Table zones in the final stretch.** A league table shows promotion, play-off and relegation places (and, for a 20-club top division, estimated Champions League and Europa League places) from the last 11 matches of a season of up to 38, or the last 10 of a longer one (Premier League from match 27, Championship from match 36), and always in the final table. Tinted position cells and a line under the table say what the shading means.
- **Pages are a little more compact**, and a small block that comes just before a matchweek which cannot share its page now follows that matchweek instead of leaving an empty page.
- **The archive upgrades itself to schema 2** (it now keeps each competition's zone rules and the game's short club names). Older archives are migrated on first open; opening a save you have already banked fills in what the older archive lacked.

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
