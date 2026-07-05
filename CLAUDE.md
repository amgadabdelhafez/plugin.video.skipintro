# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kodi addon (`plugin.video.skipintro`) that detects, remembers, and skips TV show intros/outros. Runs as a Kodi service (background process) and also provides a context menu item for manually setting skip times. Requires Kodi 19 (Matrix)+ and Python 3.x.

## Commands

```bash
# Run tests (mocks Kodi modules so no Kodi installation needed)
python3 test_video_metadata.py -v

# Run coverage report for repo-owned Python files
./test-container/run-coverage.sh

# Run Linux ARM64 and AMD64 unit-test containers
./test-container/test-all.sh

# Run headless Kodi E2E with generated synthetic media
./test-container/run-e2e-container.sh

# Build release zip (from sibling directory)
cd ../repository.skipintro && ./build.sh
```

Current automated status:
- 167 mocked unit tests
- 4 headless Kodi E2E tests
- 58% measured coverage across repo-owned Python files
- Linux ARM64/AMD64 container and Kodi E2E commands are documented in `test-container/`

## Architecture

The addon registers three Kodi extension points (see `addon.xml`):
- **`xbmc.service`** → `default.py` — background service that monitors playback
- **`kodi.context.item`** → `context.py` — right-click "Set Skip Intro Times" for episodes/shows in the library
- **`xbmc.gui.skin`** — custom XML-based skip button overlay

### Entry Points

**`default.py`** — `SkipIntroPlayer(xbmc.Player)` subclass runs in a main loop polling every 500ms. On `onAVStarted`, it detects the show, looks up saved times, tries chapter autodetection when no saved markers exist, then sets a timer to show the skip button at the right moment. There is no synthetic default skip window; unconfigured shows do not jump.

**`context.py`** — Standalone script invoked from Kodi's context menu. Lets users choose between manual time input (MM:SS) or chapter number selection, then saves to the database.

**`reload.py`** — Developer utility that uses Kodi JSON-RPC to stop video and toggle the addon on/off for quick reload during development (connects to `localhost:1984`).

### Library Modules (`resources/lib/`)

| Module | Class | Role |
|---|---|---|
| `database.py` | `ShowDatabase` | SQLite persistence. Tables: `shows`, `shows_config`, `episodes`. Auto-migrates schema on init. |
| `metadata.py` | `ShowMetadata` | Identifies current show via Kodi info labels, falls back to filename regex (`SxxExx` / `xxXxx`). Also has a `get_chapters()` method using Kodi JSON-RPC. |
| `chapters.py` | `ChapterManager` | Gets chapter data from Kodi plus enzyme-based MKV chapter parsing through Kodi VFS, caches results per file, and falls back to InfoLabels for chapter count. |
| `settings.py` | `Settings` | Reads/validates addon settings from `resources/settings.xml`, enforces bounds, provides defaults. |
| `ui.py` | `PlayerUI`, `SkipIntroDialog` | `WindowXMLDialog` overlay for the skip button (`skip_button.xml`). |
| `show.py` | `ShowManager` | Higher-level facade combining `ShowMetadata` + `ShowDatabase`. |

### Key Design Details

- **Two chapter detection paths**: `ChapterManager` reads MKV chapter names/timestamps through Kodi VFS when possible, then falls back to InfoLabels for chapter count. `ShowMetadata.get_chapters()` also uses InfoLabels for platform-safe chapter count fallback.
- **Database schema**: `shows` (id, title) → `shows_config` (show-level intro/outro settings, supports both time-based and chapter-based) → `episodes` (per-episode overrides). The `get_show()` method auto-creates entries.
- **Skip button timing**: Uses `show_from_start` flag for chapter-only mode (button visible from start), otherwise waits until `intro_start` time is reached.
- **Path/security handling**: `metadata.sanitize_path()` strips credentials, query strings, and fragments before logging/display. Database backup/export paths use Kodi VFS-compatible joining and strip generated filenames down to basenames.
- **Localization**: String IDs defined in `resources/language/resource.language.en_gb/strings.po`, referenced by numeric ID (32000+) in `settings.xml`.

## Kodi API Patterns

- All logging uses `xbmc.log()` with `'SkipIntro: '` prefix
- Settings read via `xbmcaddon.Addon().getSetting()` / `.getSettingBool()`
- Paths translated via `xbmcvfs.translatePath()` (Kodi special:// protocol)
- UI dialogs via `xbmcgui.Dialog()` and `xbmcgui.WindowXMLDialog`
- Player events via `xbmc.Player` callback methods (`onAVStarted`, `onPlayBackStopped`, etc.)
