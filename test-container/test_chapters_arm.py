#!/usr/bin/env python3
"""
Test ChapterManager parsing logic on ARM64 using real chapter data
extracted from TV episodes on sweetnas.

This does NOT require the actual video files — it mocks the ffmpeg
subprocess to return the real ffmetadata output and tests that
ChapterManager parses it correctly.
"""
import sys
import os
import json
from unittest.mock import MagicMock, patch

# Mock Kodi modules before any addon imports
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 3
    LOGERROR = 2

    @staticmethod
    def log(msg, level):
        pass

    @staticmethod
    def executeJSONRPC(json_str):
        # Return a fake file path so ChapterManager proceeds
        return json.dumps({
            "result": {
                "item": {
                    "file": "/media/test_episode.mkv",
                    "title": "Test Episode"
                }
            }
        })

sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MagicMock()
sys.modules['xbmcaddon'] = MagicMock()
sys.modules['xbmcvfs'] = MagicMock()

# Now import ChapterManager
sys.path.insert(0, '/addon')
from resources.lib.chapters import ChapterManager

# Real ffmetadata extracted from test episodes
TEST_CASES = {
    "Friends.S02E02 (5 chapters, labeled Intro/Intro End)": """;FFMETADATA1
[CHAPTER]
START=0
END=112821000000
title=Start
[CHAPTER]
START=112821000000
END=157074000000
title=Intro
[CHAPTER]
START=157074000000
END=1352559000000
title=Intro End
[CHAPTER]
START=1352559000000
END=1353143000000
title=Credits Starting
[CHAPTER]
START=1353143000000
END=1363072000000
title=End Credits
""",

    "Silicon.Valley.S01E01 (6 chapters, timestamp-only names)": """;FFMETADATA1
[CHAPTER]
START=0
END=182432000000
title=00:00:00.000
[CHAPTER]
START=182432000000
END=504838000000
title=00:03:02.432
[CHAPTER]
START=504838000000
END=913329000000
title=00:08:24.838
[CHAPTER]
START=913329000000
END=1236110000000
title=00:15:13.329
[CHAPTER]
START=1236110000000
END=1691523000000
title=00:20:36.110
[CHAPTER]
START=1691523000000
END=1761396000000
title=00:28:11.523
""",

    "The.Office.US.S06E01 (4 chapters, generic names)": """;FFMETADATA1
[CHAPTER]
START=0
END=104021000000
title=Chapter 1
[CHAPTER]
START=104021000000
END=559476000000
title=Chapter 2
[CHAPTER]
START=559476000000
END=972889000000
title=Chapter 3
[CHAPTER]
START=972889000000
END=1321952000000
title=Chapter 4
""",
}

EXPECTED = {
    "Friends.S02E02 (5 chapters, labeled Intro/Intro End)": {
        "count": 5,
        "names": ["Start", "Intro", "Intro End", "Credits Starting", "End Credits"],
        "first_time": 0.0,
        "intro_start": 112.821,  # chapter 2 start
        "intro_end": 157.074,    # chapter 3 start (Intro End)
    },
    "Silicon.Valley.S01E01 (6 chapters, timestamp-only names)": {
        "count": 6,
        "first_time": 0.0,
    },
    "The.Office.US.S06E01 (4 chapters, generic names)": {
        "count": 4,
        "names": ["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4"],
        "first_time": 0.0,
    },
}


def make_mock_subprocess_result(ffmetadata_output):
    """Create a mock subprocess.run result."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = ffmetadata_output
    result.stderr = ""
    return result


def test_chapter_parsing():
    passed = 0
    failed = 0

    for name, metadata in TEST_CASES.items():
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")

        mgr = ChapterManager()

        # Mock subprocess.run to return our metadata and os.path.isfile
        with patch('subprocess.run', return_value=make_mock_subprocess_result(metadata)), \
             patch('os.path.isfile', return_value=True):
            chapters = mgr.get_chapters()

        expected = EXPECTED[name]

        # Test chapter count
        if len(chapters) == expected["count"]:
            print(f"  ✓ Chapter count: {len(chapters)}")
            passed += 1
        else:
            print(f"  ✗ Chapter count: expected {expected['count']}, got {len(chapters)}")
            failed += 1

        # Test chapter names if expected
        if "names" in expected:
            actual_names = [c['name'] for c in chapters]
            if actual_names == expected["names"]:
                print(f"  ✓ Chapter names match")
                passed += 1
            else:
                print(f"  ✗ Chapter names: expected {expected['names']}, got {actual_names}")
                failed += 1

        # Test first chapter time
        if chapters and abs(chapters[0]['time'] - expected["first_time"]) < 0.01:
            print(f"  ✓ First chapter time: {chapters[0]['time']}s")
            passed += 1
        elif chapters:
            print(f"  ✗ First chapter time: expected {expected['first_time']}, got {chapters[0]['time']}")
            failed += 1

        # Test intro times for Friends
        if "intro_start" in expected and len(chapters) >= 3:
            intro_start = chapters[1]['time']
            intro_end = chapters[2]['time']
            if abs(intro_start - expected["intro_start"]) < 0.01:
                print(f"  ✓ Intro start: {intro_start:.3f}s (chapter 'Intro')")
                passed += 1
            else:
                print(f"  ✗ Intro start: expected {expected['intro_start']}, got {intro_start}")
                failed += 1
            if abs(intro_end - expected["intro_end"]) < 0.01:
                print(f"  ✓ Intro end: {intro_end:.3f}s (chapter 'Intro End')")
                passed += 1
            else:
                print(f"  ✗ Intro end: expected {expected['intro_end']}, got {intro_end}")
                failed += 1

        # Print all chapters for visibility
        print(f"\n  Parsed chapters:")
        for i, ch in enumerate(chapters):
            print(f"    {i+1}. '{ch['name']}' at {ch['time']:.3f}s (end: {ch.get('end_time', '?')}s)")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"Platform: {os.uname().machine}")
    print(f"{'='*60}")

    return failed == 0


if __name__ == '__main__':
    success = test_chapter_parsing()
    sys.exit(0 if success else 1)
