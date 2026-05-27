# MD5Mate Changelog

## Unreleased

- Focused MD5Mate on the desktop app experience.
- Simplified desktop export behavior to always write standard md5sum lines.
- Removed the desktop format selector from advanced options.
- Increased advanced option row spacing and styled the thread spinner arrows for clearer interaction.
- Improved recursive-scan checkbox contrast with clear checked and unchecked states.

## 1.0.0 - 2026-05-22

- Rebuilt the legacy MD5 calculator into a clean desktop package.
- Replaced the tkinter desktop UI with a modern PySide6/Qt workstation interface.
- Added drag-and-drop path selection, summary cards, a cleaner result table, and a dedicated reminder panel.
- Simplified the first screen so core actions stay prominent; advanced output/thread options are collapsed by default.
- Added explicit light styling for Qt combo-box popup menus.
- Added configurable thread count for batch hashing.
- Added error collection and visible error reminders in the desktop UI.
- Added MD5, CSV, and text report output writers.
- Added pytest coverage for filters, hashing, errors, output, verification, and UI presentation formatting.
- Added open-source project metadata, README, build script, and MIT license.
