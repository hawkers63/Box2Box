# Box2Box

A Windows desktop database and analytical viewer for the fixtures, results, matrices, and league tables
stored in a Football Manager 27 (or 26) save. It reads saves using [fmsave](https://rhiever.github.io/fmsave/)
and never modifies them.

## Running it

Double-click **Box2Box.bat**, then **Open save…**. Saves live in
`Documents\Sports Interactive\Football Manager 27\games`. Reading one takes around half a minute.
You can also drag a `.fm` save file onto the `.bat` launcher to open it straight away.

From a terminal:
```powershell
.venv\Scripts\python fm_review.py ["path\to\save.fm"]
```

## What it shows

- **Competitions Hub**:
  - Browse every competition across the save in a dedicated explorer tab, classified into categories (*Your Club*, *League*, *Cup*, *Youth / Reserves*, *Friendlies*).
  - View total entrants, fixture volume, matches played, and season completion progress. Click a row to select that competition; double-click it, or pick it in the list on the left, to open it in the view you last used.
- **Vibrant Fixture Grid**:
  - High-contrast cross-table matrix (Home teams down rows, Away teams across columns).
  - **Followed Club Perspective**: when following your club, their entire row and column dynamically reflect their results from their perspective (Emerald for wins, Amber for draws, Crimson for defeats).
- **Enriched League Standings**:
  - Broadcast-style zone colours for promotion, play-offs and relegation, taken from the save's own competition rules: the Championship shows 1st–2nd promoted, 3rd–8th in the play-offs and 22nd–24th relegated. Where the rules can't be matched to a competition (League One and League Two before their season starts), and for the Champions League and Europa League places of a 20-team top division, the zones are estimated from the league's size, and the note above the table says so. Zones are shown on the Overall table.
  - **Split Views**: instant toggling between **Overall**, **Home**, **Away**, and **Form (Last 6 matches)** standings.
- **Weekly Sequential Results**:
  - Every match in chronological order, grouped by calendar week (Monday start), matchday, or date.
  - Pick a club to view their dedicated campaign with W/D/L indicators and running points totals.
- **Coverage Transparency**:
  - Transparent tracking of played matches, matches to play, and played matches with unrecovered scorelines ("n/a").

## Exports

**Export ▾** (next to *Name this competition…*) saves the competition and season you are looking at:

- **Excel workbook (.xlsx)**, with these sheets:
  - Table, with its zone colours.
  - Grid, coloured as in the app.
  - Results, grouped as on screen.
  - Your followed team's results, with running points.
  - About: where the data came from.
- **Web page (.html)**: one file with the same sections and colours, plus a box to show one team's
  matches. It opens in any browser and needs nothing else, so it can be shared as it is.
- **CSV files (.csv)**: Results, Table, Grid and About, in a folder of their own, for your own
  analysis. Scores are written with an en dash (2–1) so that Excel does not turn them into dates.

Exports go to `Documents\Box2Box` (*Export ▾ → Open the export folder*), one per competition and
season. Each is named after the competition, the season and the save's in-game date, e.g.
`Championship 2026-27 (2026-07-16).xlsx`, so exporting the same save again replaces it while a
later save gets a file of its own. Every export says which save it came from, how complete the data
is, and whether the zones are the game's or estimated. If Excel has the workbook open, Box2Box
leaves the old file alone and asks you to close it first.

## Competition names

Saves don't store competition names, so a competition first appears by its id and best-known
clubs, e.g. `[8] West Ham, Wolves, Burnley`. Use **Name this competition…** to name it. Names go
in `competition_names.csv` (`database_id,name`), keyed on the game's database id, so they apply
to every save and can be edited in Excel. fmsave reads the same format.

## Files

| File | Purpose |
| --- | --- |
| `Box2Box.bat` | One-click launcher for the application |
| `fm_review.py` | The main Box2Box desktop application (CustomTkinter + tksheet) |
| `fm_data.py` | Pure data layer: parsing, grid matrices, standings, and competition summaries |
| `fm_export.py` | Excel, web page and CSV exports of one competition and season |
| `palette.py` | The app's colours, shared by the window and the exports |
| `test_fm_data.py`, `test_fm_export.py`, `test_fm_review_ui.py`, `test_probe.py` | Full test suite (`.venv\Scripts\python -m unittest -v`) |
| `fm27_probe.py` | The save coverage probe; report at `fm27_probe_report.txt` |
| `competition_names.csv`, `box2box_settings.json` | Your custom names and last-opened save (created on use) |
| `notes/` | Design notes and progress reports |
| `ROADMAP.md` | What is done, what comes next, parked ideas and known limitations |
| `CLAUDE.md` | Working notes for Claude Code: the session routine, roadmap and conventions |

## Setting up again

```
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```
