# Changelog

**Release:** 1.1  
**Status:** Current version on `main`  
**Application on disk:** `fm_review.py` (VERSION 1.1), launched with `Box2Box.bat`

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
