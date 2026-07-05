# Skip Intro Status

Last updated: 2026-07-05

## Automated Test Status

| Area | Status |
| --- | --- |
| Mocked unit suite | 167 tests passing with `python3 test_video_metadata.py -v` |
| Coverage suite | Passing with `./test-container/run-coverage.sh` |
| Multi-Platform | linux/amd64 and linux/arm64 containers passing |
| Headless Kodi E2E | 4 tests passing via GitHub Actions (amd64) and local (arm64) |
| CI Pipeline | Fully integrated into `.github/workflows/build.yml` |

## Coverage Snapshot (58% Total)

Measured with `.coveragerc` against repo-owned Python files, excluding tests,
generated/container code, and vendored enzyme code.

| Module | Coverage |
| --- | ---: |
| `resources/lib/ui.py` | 83% |
| `resources/lib/metadata.py` | 79% |
| `resources/lib/database.py` | 76% |
| `browse_path.py` | 74% |
| `resources/lib/audio_intro.py` | 69% |
| `resources/lib/settings.py` | 62% |
| `resources/lib/database_manager.py` | 61% |
| `resources/lib/chapters.py` | 60% |
| `resources/lib/show.py` | 56% |
| `context.py` | 54% |
| `database_tools.py` | 49% |
| `default.py` | 46% |
| `resources/lib/kodi_ffmpeg.py` | 38% |

## E2E Coverage

The current E2E suite runs inside a Kodi container under Xvfb, generates
synthetic media with `ffmpeg`, seeds the addon SQLite database, and drives Kodi
through JSON-RPC.

Scenarios covered:

1. Kodi JSON-RPC is reachable and `plugin.video.skipintro` is enabled.
2. A show with manual time-based config skips near the configured intro end.
3. An unconfigured video does not jump.
4. A chapter-configured MKV skips near the configured chapter end.

## Security And Platform Coverage

- URL credentials, query strings, and fragments are stripped before logging/display.
- STRM/ffmpeg error paths redact private stream URLs.
- Database import rejects oversized files before reading.
- Import validators reject invalid ranges and bools used as numeric values.
- Show titles containing SQL syntax are stored as data through parameterized SQL.
- Legacy SQLite schema migration preserves rows and adds missing columns.
- Backup/export VFS joins preserve Kodi URL paths and strip generated filenames to basenames.
- Filename parsing covers POSIX paths, Windows paths, and tokenized URLs.

## Remaining Gaps

- `database_manager.py` still needs broader restore/import-mode coverage.
- `default.py` needs further coverage of the main service polling loop.
- Real-device smoke results still need to be recorded for Intel Mac, Windows, Raspberry Pi, Android, and iOS feasibility.
