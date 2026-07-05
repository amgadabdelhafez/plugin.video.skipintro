# Manual Platform Smoke Matrix

Use this matrix for platforms that are not practical to require in CI. Keep
media and credentials local; do not commit Kodi profile data or private paths.

## Baseline Commands

- Unit tests: `python3 test_video_metadata.py -v`
- Coverage report: `./test-container/run-coverage.sh`
- Container unit matrix: `./test-container/test-all.sh`
- Headless Kodi E2E: `./test-container/run-e2e-container.sh`
- Compose alternative: `docker compose -f test-container/docker-compose.yml run --rm kodi-e2e-arm64`

## Platforms

| Platform | Minimum smoke check |
| --- | --- |
| Apple Silicon macOS | Run unit tests, coverage, arm64 container tests, and arm64 Kodi E2E. |
| Intel macOS | Run unit tests, coverage, and local Kodi playback smoke with one configured show. |
| Windows | Run unit tests, then verify Kodi playback with a Windows path and a SMB path. |
| Raspberry Pi | Run Kodi playback smoke with local or SMB media and verify DB persistence after restart. |
| Android | Run Kodi playback smoke with SMB or local media and verify InfoLabel chapter fallback. |
| iOS | Record feasibility only unless a supported Kodi environment is available; Kodi automation is constrained on iOS. |

## Smoke Scenarios

1. Configure a show-level intro from `00:00` to `00:10`; playback should skip near the start.
2. Play an unconfigured episode; playback should not jump.
3. Configure a chapter-based intro on a file with chapters; playback should skip to the configured end.
4. Use a media URL with credentials or query tokens; logs and exported JSON diagnostics must not expose credentials.
5. Back up and export the database to a Kodi VFS path such as `special://`, SMB, or NFS.
