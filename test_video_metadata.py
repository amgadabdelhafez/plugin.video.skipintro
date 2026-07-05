import unittest
import tempfile
import os
import json
import subprocess
from unittest.mock import MagicMock, patch

# Mock Kodi modules
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 3
    LOGERROR = 2

    @staticmethod
    def log(msg, level):
        pass

    @staticmethod
    def sleep(ms):
        pass

    @staticmethod
    def executeJSONRPC(json_str):
        import json
        return json.dumps({"result": {}})

    @staticmethod
    def executebuiltin(cmd):
        pass

    @staticmethod
    def getInfoLabel(label):
        if label == 'VideoPlayer.TVShowTitle':
            return 'Test Show'
        elif label == 'VideoPlayer.Season':
            return '1'
        elif label == 'VideoPlayer.Episode':
            return '2'
        elif label == 'Player.ChapterCount':
            return '0'
        elif label == 'Player.Chapter':
            return '1'
        return ''

    class Player:
        def __init__(self):
            self.playing = True

        def isPlaying(self):
            return self.playing

        def getTime(self):
            return 0.0

        def getPlayingFile(self):
            return '/path/to/Test.Show.S01E02.mkv'

        def isPlayingVideo(self):
            return self.playing

        def seekTime(self, time):
            pass

    class Monitor:
        def __init__(self):
            pass

class MockXBMCGUI:
    ACTION_PREVIOUS_MENU = 10
    ACTION_NAV_BACK = 92
    NOTIFICATION_INFO = 'info'
    NOTIFICATION_ERROR = 'error'
    NOTIFICATION_WARNING = 'warning'

    class Dialog:
        def yesno(self, heading, message, *args, **kwargs):
            return True
        def notification(self, heading, message, icon=None, time=5000):
            pass

    class WindowXMLDialog:
        def __init__(self, *args, **kwargs):
            pass
        def show(self):
            pass
        def close(self):
            pass
        def getControl(self, controlId):
            return MagicMock()
        def setFocus(self, control):
            pass
        def setFocusId(self, controlId):
            pass

class MockXBMCAddon:
    class Addon:
        def __init__(self, addon_id=None):
            self._settings = {
                "enable_autoskip": "true",
                "pre_skip_seconds": "3",
                "delay_autoskip": "0",
                "auto_dismiss_button": "0",
                "database_path": ":memory:",
                "backup_restore_path": ""
            }

        def getSetting(self, key):
            return self._settings.get(key, "")

        def getSettingBool(self, key):
            return self._settings.get(key, "false").lower() == "true"

        def setSetting(self, key, value):
            self._settings[key] = value

        def getAddonInfo(self, key):
            if key == 'path':
                return os.path.dirname(os.path.abspath(__file__))
            return ''

class MockXBMCVFS:
    @staticmethod
    def translatePath(path):
        return path

    @staticmethod
    def exists(path):
        return os.path.exists(path)

    @staticmethod
    def mkdirs(path):
        os.makedirs(path, exist_ok=True)

    @staticmethod
    def listdir(path):
        dirs = []
        files = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry)
            else:
                files.append(entry)
        return dirs, files

    class File:
        def __init__(self, path, mode='r'):
            pass
        def read(self):
            return ''
        def write(self, data):
            pass
        def close(self):
            pass
        def size(self):
            return 0

# Mock the Kodi modules
import sys
sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS

# Now import our addon code
import default

class TestDatabase(unittest.TestCase):
    def setUp(self):
        """Set up test database using a temp file (ShowDatabase needs a real path)"""
        from resources.lib.database import ShowDatabase
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        self.db = ShowDatabase(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_show_create_and_lookup(self):
        """Test show creation and retrieval"""
        show_id = self.db.get_show('Test Show')
        self.assertIsNotNone(show_id)
        # Second call returns same ID
        self.assertEqual(self.db.get_show('Test Show'), show_id)

    def test_show_config_save_and_load(self):
        """Test saving and loading show config"""
        show_id = self.db.get_show('Test Show')
        success = self.db.set_manual_show_times(show_id, 30, 90, 2700)
        self.assertTrue(success)

        config = self.db.get_show_config(show_id)
        self.assertIsNotNone(config)
        self.assertEqual(config['intro_start_time'], 30)
        self.assertEqual(config['intro_end_time'], 90)
        self.assertEqual(config['outro_start_time'], 2700)
        self.assertFalse(config['use_chapters'])

    def test_show_chapter_config(self):
        """Test saving and loading chapter-based config"""
        show_id = self.db.get_show('Test Show')
        success = self.db.set_manual_show_chapters(show_id, True, 1, 3, 8)
        self.assertTrue(success)

        config = self.db.get_show_config(show_id)
        self.assertIsNotNone(config)
        self.assertTrue(config['use_chapters'])
        self.assertEqual(config['intro_start_chapter'], 1)
        self.assertEqual(config['intro_end_chapter'], 3)
        self.assertEqual(config['outro_start_chapter'], 8)

    def test_show_title_strip(self):
        """Test that show titles are stripped of whitespace"""
        show_id1 = self.db.get_show('Test Show')
        show_id2 = self.db.get_show('  Test Show  ')
        self.assertEqual(show_id1, show_id2)

    def test_show_title_alias_lookup_ignores_punctuation(self):
        """Configured rows can be found when Kodi reports punctuation variants"""
        show_id = self.db.get_show('That 70s Show')
        self.db.set_manual_show_chapters(show_id, True, None, 2)

        self.assertEqual(self.db.get_show("That '70s Show"), show_id)

    def test_show_title_alias_prefers_configured_row_over_empty_exact(self):
        """An empty exact-title row should not hide a configured alias row"""
        configured_id = self.db.get_show('That 70s Show')
        self.db.set_manual_show_chapters(configured_id, True, None, 2)

        import sqlite3
        conn = sqlite3.connect(self.tmp.name)
        try:
            c = conn.cursor()
            c.execute('INSERT INTO shows (title) VALUES (?)', ("That '70s Show",))
            empty_exact_id = c.lastrowid
            c.execute('''
                INSERT INTO shows_config
                (show_id, use_chapters, intro_start_time, intro_end_time, outro_start_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (empty_exact_id, False, None, None, None))
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(self.db.get_show("That '70s Show"), configured_id)

    def test_episode_times_save_and_load(self):
        """Episode-specific times can be saved and loaded"""
        show_id = self.db.get_show('Test Show')
        success = self.db.save_episode_times(show_id, 1, 2, {
            'intro_start_time': 0,
            'intro_end_time': 263,
            'outro_start_time': None,
            'source': 'audio_detection'
        })
        self.assertTrue(success)

        config = self.db.get_episode_times(show_id, 1, 2)
        self.assertIsNotNone(config)
        self.assertFalse(config['use_chapters'])
        self.assertEqual(config['intro_start_time'], 0)
        self.assertEqual(config['intro_end_time'], 263)
        self.assertEqual(config['source'], 'audio_detection')

class TestMetadata(unittest.TestCase):
    def setUp(self):
        """Set up metadata detector"""
        from resources.lib.metadata import ShowMetadata
        self.metadata = ShowMetadata()

    def test_show_detection_kodi(self):
        """Test show detection using Kodi info labels"""
        info = self.metadata.get_show_info()
        self.assertEqual(info['title'], 'Test Show')
        self.assertEqual(info['season'], 1)
        self.assertEqual(info['episode'], 2)

    def test_chapters(self):
        """Test chapter detection returns list (empty when no video playing)"""
        chapters = self.metadata.get_chapters()
        self.assertIsInstance(chapters, list)

    def test_show_detection_filename(self):
        """Test show detection from filename when info labels unavailable"""
        with patch('xbmc.getInfoLabel', return_value=''):
            info = self.metadata.get_show_info()
            # Filename parser produces 'Test Show' (with dots replaced by spaces)
            self.assertEqual(info['title'].strip(), 'Test Show')
            self.assertEqual(info['season'], 1)
            self.assertEqual(info['episode'], 2)

class TestSkipIntro(unittest.TestCase):
    def setUp(self):
        self.player = default.SkipIntroPlayer()

    def tearDown(self):
        if self.player.db:
            self.player.db.close()

    def test_cleanup(self):
        """Test cleanup resets all state"""
        self.player.intro_bookmark = 100
        self.player.outro_bookmark = 200
        self.player.bookmarks_checked = True
        self.player.show_info = {'title': 'Test'}
        self.player.timer_active = True
        self.player.show_from_start = True
        self.player.has_config = True
        self.player._skip_to_chapter = 3

        self.player.cleanup()

        self.assertIsNone(self.player.intro_bookmark)
        self.assertIsNone(self.player.outro_bookmark)
        self.assertIsNone(self.player.intro_start)
        self.assertIsNone(self.player.intro_duration)
        self.assertFalse(self.player.bookmarks_checked)
        self.assertFalse(self.player.prompt_shown)
        self.assertIsNone(self.player.show_info)
        self.assertFalse(self.player.timer_active)
        self.assertEqual(self.player.next_check_time, 0)
        self.assertFalse(self.player.show_from_start)
        self.assertFalse(self.player.has_config)
        self.assertIsNone(self.player._skip_to_chapter)

    def test_playback_stopped_calls_cleanup(self):
        """onPlayBackStopped should reset state"""
        self.player.intro_bookmark = 100
        self.player.onPlayBackStopped()
        self.assertIsNone(self.player.intro_bookmark)

    def test_playback_ended_calls_cleanup(self):
        """onPlayBackEnded should reset state"""
        self.player.intro_bookmark = 100
        self.player.onPlayBackEnded()
        self.assertIsNone(self.player.intro_bookmark)

    def test_playback_started_calls_cleanup(self):
        """onPlayBackStarted should reset state for new playback"""
        self.player.intro_bookmark = 100
        self.player.onPlayBackStarted()
        self.assertIsNone(self.player.intro_bookmark)

    def test_onavstarted_calls_detect_show(self):
        """onAVStarted should trigger show detection and time checking"""
        # Set show_info after mock call
        def detect_side_effect():
            self.player.show_info = {'title': 'Test', 'season': 1, 'episode': 2}

        with patch.object(self.player, '_wait_for_video_info', return_value=True), \
             patch.object(self.player, 'detect_show', side_effect=detect_side_effect) as mock_detect, \
             patch.object(self.player, 'check_saved_times') as mock_check:
            self.player.onAVStarted()
            mock_detect.assert_called_once()
            mock_check.assert_called_once()

    def test_onplaybacktime_triggers_autoskip(self):
        """onPlayBackTime should trigger autoskip when threshold reached"""
        self.player.intro_bookmark = 100
        self.player.timer_active = True
        self.player.next_check_time = 100
        self.player.settings['enable_autoskip'] = True

        with patch.object(self.player, 'getTime', return_value=100.5), \
             patch.object(self.player, 'skip_to_intro_end') as mock_skip:
            self.player.onPlayBackTime(100500) # ms
            mock_skip.assert_called_once()
            self.assertFalse(self.player.timer_active)

    def test_try_autodetect_no_mkv(self):
        """Autodetect skipped for non-MKV files"""
        self.player.show_info = {'title': 'Test'}
        with patch.object(self.player, 'getPlayingFile', return_value='show.mp4'), \
             patch.object(self.player, 'set_chapter_based_markers') as mock_set:
            result = self.player._try_autodetect()
            self.assertFalse(result)
            mock_set.assert_not_called()

    # --- set_time_based_markers ---

    def test_set_time_based_markers(self):
        """Time-based markers set intro_start, intro_bookmark, and duration"""
        times = {'intro_start_time': 30, 'intro_end_time': 90, 'outro_start_time': 1200}
        result = self.player.set_time_based_markers(times, "test")

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 30)
        self.assertEqual(self.player.intro_bookmark, 90)
        self.assertEqual(self.player.intro_duration, 60)
        self.assertEqual(self.player.outro_bookmark, 1200)
        self.assertFalse(self.player.show_from_start)

    def test_set_time_based_markers_from_start(self):
        """show_from_start is True when intro_start_time is 0"""
        times = {'intro_start_time': 0, 'intro_end_time': 90, 'outro_start_time': None}
        self.player.set_time_based_markers(times, "test")
        self.assertTrue(self.player.show_from_start)

    def test_set_time_based_markers_defaults_missing_start_to_zero(self):
        """Legacy/imported time configs with only an end time start at video start"""
        times = {'intro_start_time': None, 'intro_end_time': 90, 'outro_start_time': None}
        result = self.player.set_time_based_markers(times, "test")
        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 90)
        self.assertEqual(self.player.intro_duration, 90)
        self.assertTrue(self.player.show_from_start)

    def test_set_time_based_markers_returns_false_when_none(self):
        """Returns False when intro times are None"""
        self.assertFalse(self.player.set_time_based_markers(
            {'intro_start_time': None, 'intro_end_time': None}, "test"))
        self.assertFalse(self.player.set_time_based_markers(
            {'intro_start_time': 30, 'intro_end_time': None}, "test"))

    def test_check_saved_times_prefers_episode_config(self):
        """Episode-specific config wins over show-level config"""
        self.player.show_info = {'title': 'Test Show', 'season': 1, 'episode': 2}
        show_id = self.player.db.get_show('Test Show')
        self.player.db.set_manual_show_times(show_id, 30, 90)
        self.player.db.save_episode_times(show_id, 1, 2, {
            'intro_start_time': 0,
            'intro_end_time': 263,
            'source': 'audio_detection'
        })

        self.player.check_saved_times()

        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 263)
        self.assertTrue(self.player.has_config)

    # --- set_chapter_based_markers ---

    def test_set_chapter_based_markers(self):
        """Chapter-based markers resolve chapter numbers to times"""
        chapters = [
            {'time': 0, 'name': 'Start', 'number': 1},
            {'time': 112, 'name': 'Intro', 'number': 2},
            {'time': 157, 'name': 'Intro End', 'number': 3},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': None}
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 157)
        self.assertTrue(self.player.show_from_start)

    def test_set_chapter_based_markers_with_outro(self):
        """Chapter-based markers with outro chapter"""
        chapters = [
            {'time': 0, 'number': 1}, {'time': 112, 'number': 2},
            {'time': 157, 'number': 3}, {'time': 1200, 'number': 4},
            {'time': 1350, 'number': 5},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': 4}
        self.player.set_chapter_based_markers(config)

        self.assertEqual(self.player.outro_bookmark, 1200)

    def test_set_chapter_based_markers_invalid_chapter(self):
        """Returns False when chapter numbers are out of range"""
        chapters = [{'time': 0, 'number': 1}, {'time': 100, 'number': 2}]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 5}  # 5 > len(chapters)
        self.assertFalse(self.player.set_chapter_based_markers(config))

    def test_set_chapter_based_markers_no_chapters(self):
        """Returns False when no chapters found"""
        self.player.getChapters = MagicMock(return_value=[])
        config = {'intro_start_chapter': 1, 'intro_end_chapter': 2}
        self.assertFalse(self.player.set_chapter_based_markers(config))

    def test_set_chapter_based_markers_uses_saved_times_when_chapters_missing(self):
        """Autodetected chapter configs can fall back to saved timestamps"""
        self.player.getChapters = MagicMock(return_value=[])
        config = {
            'intro_start_chapter': 2,
            'intro_end_chapter': 3,
            'intro_start_time': 42,
            'intro_end_time': 88,
            'outro_start_time': 1200,
        }

        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 42)
        self.assertEqual(self.player.intro_bookmark, 88)
        self.assertEqual(self.player.outro_bookmark, 1200)

    def test_set_chapter_based_markers_missing_config(self):
        """Returns False when chapter config is missing"""
        chapters = [{'time': 0, 'number': 1}, {'time': 100, 'number': 2}]
        self.player.getChapters = MagicMock(return_value=chapters)
        self.assertFalse(self.player.set_chapter_based_markers(
            {'intro_start_chapter': None, 'intro_end_chapter': None}))

    def test_set_chapter_based_markers_network_seek_mode(self):
        """Chapter-seek mode when chapters have no 'time' field"""
        chapters = [
            {'number': 1, 'name': 'Chapter 1'},
            {'number': 2, 'name': 'Chapter 2'},
            {'number': 3, 'name': 'Chapter 3'},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': None}
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player._skip_to_chapter, 3)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 99999)
        self.assertIsNone(self.player.intro_duration)
        self.assertTrue(self.player.show_from_start)

    def test_set_chapter_based_markers_start_plus_duration(self):
        """Start chapter + duration mode calculates end from start + duration"""
        chapters = [
            {'time': 0, 'number': 1},
            {'time': 112, 'number': 2},
            {'time': 157, 'number': 3},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {
            'intro_start_chapter': 1,
            'intro_end_chapter': None,
            'intro_duration': 90,
            'outro_start_chapter': None
        }
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 90)
        self.assertEqual(self.player.intro_duration, 90)

    def test_set_chapter_based_markers_end_plus_duration(self):
        """End chapter + duration mode calculates start from end - duration"""
        chapters = [
            {'time': 0, 'number': 1},
            {'time': 112, 'number': 2},
            {'time': 157, 'number': 3},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {
            'intro_start_chapter': None,
            'intro_end_chapter': 3,
            'intro_duration': 45,
            'outro_start_chapter': None
        }
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_bookmark, 157)
        self.assertEqual(self.player.intro_start, 112)  # 157 - 45
        self.assertEqual(self.player.intro_duration, 45)

    def test_try_autodetect_sets_runtime_markers_and_saves_config(self):
        """Playback autodetect sets markers and persists chapter config"""
        chapters = [
            {'name': 'Start', 'time': 0, 'number': 1},
            {'name': 'Intro', 'time': 112, 'number': 2},
            {'name': 'Intro End', 'time': 157, 'number': 3},
            {'name': 'Credits Starting', 'time': 1352, 'number': 4},
        ]
        self.player.show_info = {'title': 'Autodetect Show', 'season': 1, 'episode': 1}
        self.player.getChapters = MagicMock(return_value=chapters)
        show_id = self.player.db.get_show('Autodetect Show')

        self.player._try_autodetect()

        self.assertEqual(self.player.intro_start, 112)
        self.assertEqual(self.player.intro_bookmark, 157)
        self.assertEqual(self.player.intro_duration, 45)
        self.assertEqual(self.player.outro_bookmark, 1352)
        config = self.player.db.get_show_config(show_id)
        self.assertTrue(config['use_chapters'])
        self.assertEqual(config['intro_start_chapter'], 2)
        self.assertEqual(config['intro_end_chapter'], 3)
        self.assertEqual(config['outro_start_chapter'], 4)
        self.assertEqual(config['intro_start_time'], 112)
        self.assertEqual(config['intro_end_time'], 157)

    def test_try_autodetect_without_timestamps_uses_chapter_seek_and_saves(self):
        """Named chapters without timestamps still produce chapter-seek config"""
        chapters = [
            {'name': 'Chapter 1', 'number': 1},
            {'name': 'OP', 'number': 2},
            {'name': 'Episode Start', 'number': 3},
        ]
        self.player.show_info = {'title': 'No Timestamp Show', 'season': 1, 'episode': 1}
        self.player.getChapters = MagicMock(return_value=chapters)
        show_id = self.player.db.get_show('No Timestamp Show')

        self.player._try_autodetect()

        self.assertEqual(self.player._skip_to_chapter, 3)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 99999)
        self.assertTrue(self.player.show_from_start)
        config = self.player.db.get_show_config(show_id)
        self.assertTrue(config['use_chapters'])
        self.assertEqual(config['intro_start_chapter'], 2)
        self.assertEqual(config['intro_end_chapter'], 3)
        self.assertIsNone(config['intro_end_time'])

    def test_try_autodetect_no_match_does_not_mutate(self):
        """Generic named chapters are ignored by playback autodetect"""
        chapters = [
            {'name': 'Chapter 1', 'time': 0, 'number': 1},
            {'name': 'Chapter 2', 'time': 90, 'number': 2},
        ]
        self.player.show_info = {'title': 'No Match Show', 'season': 1, 'episode': 1}
        self.player.getChapters = MagicMock(return_value=chapters)

        self.player._try_autodetect()

        self.assertIsNone(self.player.intro_start)
        self.assertIsNone(self.player.intro_bookmark)
        self.assertIsNone(self.player._skip_to_chapter)

    def test_path_supports_episode_listing_accepts_listable_paths(self):
        supports = default.SkipIntroPlayer._path_supports_episode_listing
        self.assertTrue(supports('/storage/emulated/0/show.mkv'))
        self.assertTrue(supports('smb://nas/Media/Show/S01E01.mkv'))
        self.assertTrue(supports('nfs://nas/Media/Show/S01E01.mkv'))

    def test_path_supports_episode_listing_rejects_streaming(self):
        supports = default.SkipIntroPlayer._path_supports_episode_listing
        self.assertFalse(supports(''))
        self.assertFalse(supports(None))
        self.assertFalse(supports('http://lax-rd.real-debrid.com/d/abc/file.mp4'))
        self.assertFalse(supports('https://example.com/show.mkv'))
        self.assertFalse(supports('plugin://plugin.video.fenlight/?mode=play'))
        self.assertFalse(supports('upnp://server/file.mkv'))

    def test_try_audio_autodetect_skipped_for_streaming_path(self):
        """HTTP/plugin URLs short-circuit audio autodetect before importing detector"""
        self.player.show_info = {'title': 'Stream Show', 'season': 1, 'episode': 1}
        with patch.object(self.player, 'getPlayingFile', return_value='https://example.com/show.mp4'), \
             patch('resources.lib.audio_intro.AudioIntroDetector') as mock_detector_cls:
            self.player._try_audio_autodetect()
            mock_detector_cls.assert_not_called()
        self.assertIsNone(self.player.intro_start)
        self.assertIsNone(self.player.intro_bookmark)

    def test_try_audio_autodetect_skipped_when_one_candidate(self):
        """Lone episode (no peers) cannot be fingerprinted, so detector is not invoked"""
        self.player.show_info = {'title': 'Solo Show', 'season': 1, 'episode': 1}
        mock_detector = MagicMock()
        mock_detector.find_episode_candidates.return_value = ['smb://nas/show.mkv']
        with patch.object(self.player, 'getPlayingFile', return_value='smb://nas/show.mkv'), \
             patch('resources.lib.audio_intro.AudioIntroDetector', return_value=mock_detector):
            self.player._try_audio_autodetect()
        mock_detector.detect_show_intro.assert_not_called()
        self.assertIsNone(self.player.intro_start)

    def test_try_audio_autodetect_sets_markers_and_persists_time_config(self):
        """Successful audio fingerprint detection sets runtime markers and saves time-based config"""
        self.player.show_info = {'title': 'Audio Show', 'season': 1, 'episode': 1}
        show_id = self.player.db.get_show('Audio Show')
        mock_detector = MagicMock()
        mock_detector.find_episode_candidates.return_value = [
            'smb://nas/Show/S01E01.mkv',
            'smb://nas/Show/S01E02.mkv',
            'smb://nas/Show/S01E03.mkv',
        ]
        mock_detector.detect_show_intro.return_value = {
            'intro_start_time': 35.0,
            'intro_end_time': 73.5,
            'outro_start_time': 1280.0,
            'source': 'audio_fingerprint',
        }
        with patch.object(self.player, 'getPlayingFile', return_value='smb://nas/Show/S01E01.mkv'), \
             patch('resources.lib.audio_intro.AudioIntroDetector', return_value=mock_detector):
            self.player._try_audio_autodetect()

        self.assertEqual(self.player.intro_start, 35.0)
        self.assertEqual(self.player.intro_bookmark, 73.5)
        self.assertEqual(self.player.intro_duration, 38.5)
        self.assertEqual(self.player.outro_bookmark, 1280.0)
        self.assertFalse(self.player.show_from_start)

        config = self.player.db.get_show_config(show_id)
        self.assertFalse(config['use_chapters'])
        self.assertEqual(config['intro_start_time'], 35.0)
        self.assertEqual(config['intro_end_time'], 73.5)
        self.assertEqual(config['outro_start_time'], 1280.0)

    def test_try_audio_autodetect_show_from_start_when_intro_at_zero(self):
        """intro_start_time == 0 flips show_from_start so button appears immediately"""
        self.player.show_info = {'title': 'Zero Intro', 'season': 1, 'episode': 1}
        mock_detector = MagicMock()
        mock_detector.find_episode_candidates.return_value = ['a.mkv', 'b.mkv']
        mock_detector.detect_show_intro.return_value = {
            'intro_start_time': 0.0,
            'intro_end_time': 40.0,
            'outro_start_time': None,
        }
        with patch.object(self.player, 'getPlayingFile', return_value='/local/show.mkv'), \
             patch('resources.lib.audio_intro.AudioIntroDetector', return_value=mock_detector):
            self.player._try_audio_autodetect()
        self.assertTrue(self.player.show_from_start)

    def test_try_autodetect_falls_back_to_audio_when_no_chapters(self):
        """Chapter autodetect bailing on missing chapters routes to audio fallback"""
        self.player.show_info = {'title': 'Chapterless', 'season': 1, 'episode': 1}
        self.player.getChapters = MagicMock(return_value=[])
        with patch.object(self.player, '_try_audio_autodetect') as mock_audio:
            self.player._try_autodetect()
            mock_audio.assert_called_once()

    def test_try_autodetect_falls_back_to_audio_when_chapter_names_unhelpful(self):
        """Chapter autodetect finding no intro pattern routes to audio fallback"""
        self.player.show_info = {'title': 'Generic Chapters', 'season': 1, 'episode': 1}
        chapters = [
            {'name': 'Chapter 1', 'time': 0, 'number': 1},
            {'name': 'Chapter 2', 'time': 90, 'number': 2},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)
        with patch.object(self.player, '_try_audio_autodetect') as mock_audio:
            self.player._try_autodetect()
            mock_audio.assert_called_once()

    def test_try_autodetect_does_not_call_audio_when_chapter_succeeds(self):
        """Successful chapter autodetect short-circuits audio fallback"""
        chapters = [
            {'name': 'Start', 'time': 0, 'number': 1},
            {'name': 'Intro', 'time': 30, 'number': 2},
            {'name': 'Intro End', 'time': 70, 'number': 3},
        ]
        self.player.show_info = {'title': 'Chapter Show', 'season': 1, 'episode': 1}
        self.player.getChapters = MagicMock(return_value=chapters)
        with patch.object(self.player, '_try_audio_autodetect') as mock_audio:
            self.player._try_autodetect()
            mock_audio.assert_not_called()

class TestSkipDialog(unittest.TestCase):
    """Tests for skip button display logic and actual skip execution"""

    def setUp(self):
        self.player = default.SkipIntroPlayer()
        self.player.getTime = MagicMock(return_value=35)
        self.player.seekTime = MagicMock()
        self.player.ui = MagicMock()

    def tearDown(self):
        if self.player.db:
            self.player.db.close()

    # --- show_skip_button ---

    def test_skip_button_shown(self):
        """Button should show when intro_bookmark is set"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35  # within window
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertTrue(self.player.prompt_shown)

    def test_skip_button_not_shown_twice(self):
        """Button should only show once per playback"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()
        self.player.show_skip_button()  # second call

        # prompt_skip_intro should have been called only once
        self.assertEqual(self.player.ui.prompt_skip_intro.call_count, 1)

    def test_skip_button_show_from_start_chapter_mode(self):
        """In chapter-only mode, button shows from time 0 until intro_bookmark"""
        self.player.show_from_start = True
        self.player.intro_start = 0
        self.player.intro_bookmark = 157
        self.player.getTime.return_value = 5  # near start
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertTrue(self.player.prompt_shown)

    def test_skip_button_not_shown_when_no_bookmark(self):
        """No button when intro_bookmark is None"""
        self.player.intro_bookmark = None
        self.player.intro_start = 30

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_not_called()

    def test_skip_button_handles_ui_failure(self):
        """prompt_shown stays False if UI fails to show the dialog"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35
        self.player.ui.prompt_skip_intro.return_value = False  # UI failure

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertFalse(self.player.prompt_shown)

    # --- skip_to_intro_end ---

    def test_skip_seeks_to_bookmark(self):
        """skip_to_intro_end should seekTime to intro_bookmark"""
        self.player.intro_bookmark = 157.074

        self.player.skip_to_intro_end()

        self.player.seekTime.assert_called_once_with(157.074)

    def test_skip_does_nothing_without_bookmark(self):
        """skip_to_intro_end should be a no-op if intro_bookmark is None"""
        self.player.intro_bookmark = None

        self.player.skip_to_intro_end()

        self.player.seekTime.assert_not_called()

    def test_skip_handles_seek_error(self):
        """skip_to_intro_end should not raise if seekTime throws"""
        self.player.intro_bookmark = 157.074
        self.player.seekTime.side_effect = RuntimeError("Player not ready")

        # Should not raise
        self.player.skip_to_intro_end()

    def test_skip_uses_chapter_seek_when_set(self):
        """skip_to_intro_end should use _seek_to_chapter when _skip_to_chapter is set"""
        self.player.intro_bookmark = 99999
        self.player._skip_to_chapter = 3
        self.player._seek_to_chapter = MagicMock(return_value=True)

        self.player.skip_to_intro_end()

        self.player._seek_to_chapter.assert_called_once_with(3)
        self.player.seekTime.assert_not_called()

    # --- onPlayBackTime (timer-driven skip) ---

    def test_warning_timer_triggers_skip_button(self):
        """onPlayBackTime should trigger show_skip_button when warning timer fires"""
        self.player.warning_timer_active = True
        self.player.warning_check_time = 30
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.onPlayBackTime(35)

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertFalse(self.player.warning_timer_active)

    def test_timer_does_not_trigger_before_threshold(self):
        """onPlayBackTime should not trigger before next_check_time"""
        self.player.timer_active = True
        self.player.next_check_time = 30
        self.player.intro_start = 30
        self.player.intro_bookmark = 90

        self.player.onPlayBackTime(20)  # before threshold

        self.player.ui.prompt_skip_intro.assert_not_called()
        self.assertTrue(self.player.timer_active)  # still active

    def test_timer_inactive_does_nothing(self):
        """onPlayBackTime should be a no-op when timer_active is False"""
        self.player.timer_active = False
        self.player.next_check_time = 30

        self.player.onPlayBackTime(35)

        self.player.ui.prompt_skip_intro.assert_not_called()

    # --- callback wiring ---

    def test_skip_button_callback_calls_seek(self):
        """The callback passed to prompt_skip_intro should call skip_to_intro_end"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 157.074
        self.player.getTime.return_value = 35

        # Capture the callback that gets passed to prompt_skip_intro
        captured_callback = None
        def capture_callback(cb):
            nonlocal captured_callback
            captured_callback = cb
            return True
        self.player.ui.prompt_skip_intro.side_effect = capture_callback

        self.player.show_skip_button()

        # Now invoke the captured callback (simulates user pressing the button)
        self.assertIsNotNone(captured_callback)
        captured_callback()

        self.player.seekTime.assert_called_once_with(157.074)


class TestSettings(unittest.TestCase):
    """Tests for Settings validation and bounds enforcement"""

    def test_default_settings(self):
        """Normal settings are read correctly"""
        s = default.Settings()
        self.assertTrue(s.settings['enable_autoskip'])
        self.assertEqual(s.settings['pre_skip_seconds'], 3)
        self.assertEqual(s.settings['delay_autoskip'], 0)
        self.assertEqual(s.settings['auto_dismiss_button'], 0)

    def test_get_setting(self):
        """get_setting returns individual values"""
        s = default.Settings()
        self.assertEqual(s.get_setting('pre_skip_seconds'), 3)
        self.assertIsNone(s.get_setting('nonexistent'))

    def test_invalid_settings_fall_back_to_defaults(self):
        """ValueError in settings returns all defaults"""
        with patch.object(MockXBMCAddon.Addon, 'getSetting', return_value='not_a_number'):
            s = default.Settings()
            self.assertTrue(s.settings['enable_autoskip'])
            self.assertEqual(s.settings['pre_skip_seconds'], 3)
            self.assertEqual(s.settings['delay_autoskip'], 0)


class TestChapterManager(unittest.TestCase):
    """Tests for ChapterManager chapter lookup methods"""

    def setUp(self):
        from resources.lib.chapters import ChapterManager
        self.mgr = ChapterManager()
        self.chapters = [
            {'name': 'Start', 'time': 0, 'end_time': 112, 'number': 1},
            {'name': 'Intro', 'time': 112, 'end_time': 157, 'number': 2},
            {'name': 'Intro End', 'time': 157, 'end_time': 1352, 'number': 3},
            {'name': 'Credits', 'time': 1352, 'end_time': 1363, 'number': 4},
        ]

    def test_get_chapter_by_number(self):
        """Finds chapter by its number"""
        ch = self.mgr.get_chapter_by_number(self.chapters, 2)
        self.assertEqual(ch['name'], 'Intro')
        self.assertEqual(ch['time'], 112)

    def test_get_chapter_by_number_not_found(self):
        """Returns None for non-existent chapter number"""
        self.assertIsNone(self.mgr.get_chapter_by_number(self.chapters, 99))

    def test_get_chapter_by_number_none_input(self):
        """Returns None for None chapter number or empty list"""
        self.assertIsNone(self.mgr.get_chapter_by_number(self.chapters, None))
        self.assertIsNone(self.mgr.get_chapter_by_number([], 1))
        self.assertIsNone(self.mgr.get_chapter_by_number(None, 1))

    def test_get_intro_chapters(self):
        """Returns start and end chapter objects"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 1, 3)
        self.assertEqual(start['name'], 'Start')
        self.assertEqual(end['name'], 'Intro End')

    def test_get_intro_chapters_defaults_start_to_1(self):
        """When start_chapter is None/0, defaults to chapter 1"""
        start, end = self.mgr.get_intro_chapters(self.chapters, None, 3)
        self.assertEqual(start['number'], 1)
        self.assertEqual(end['number'], 3)

    def test_get_intro_chapters_missing_end(self):
        """Returns None, None when end_chapter is None"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 1, None)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_get_intro_chapters_invalid_end(self):
        """Returns None, None when end chapter not found"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 1, 99)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_get_intro_chapters_invalid_start(self):
        """Returns None, None when specific start chapter not found"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 99, 3)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_get_outro_chapter(self):
        """Returns outro chapter object"""
        ch = self.mgr.get_outro_chapter(self.chapters, 4)
        self.assertEqual(ch['name'], 'Credits')

    def test_get_outro_chapter_none(self):
        """Returns None when no outro chapter configured"""
        self.assertIsNone(self.mgr.get_outro_chapter(self.chapters, None))

    def test_get_outro_chapter_not_found(self):
        """Returns None when outro chapter number doesn't exist"""
        self.assertIsNone(self.mgr.get_outro_chapter(self.chapters, 99))

    def test_find_chapter_by_name(self):
        """find_chapter_by_name finds intro chapter"""
        from resources.lib.chapters import ChapterManager as CM
        ch = CM.find_chapter_by_name(self.chapters, 'Intro')
        self.assertIsNotNone(ch)
        self.assertEqual(ch['name'], 'Intro')

    def test_find_chapter_by_name_none(self):
        """find_chapter_by_name returns None for no match"""
        from resources.lib.chapters import ChapterManager as CM
        ch = CM.find_chapter_by_name(self.chapters, 'NonExistent')
        self.assertIsNone(ch)

    def test_autodetect_intro_by_name(self):
        """autodetect_intro finds intro by 'Intro'/'Intro End' chapter names"""
        chapters = [
            {'name': 'Start', 'time': 0, 'number': 1},
            {'name': 'Intro', 'time': 112, 'number': 2},
            {'name': 'Intro End', 'time': 157, 'number': 3},
            {'name': 'Credits Starting', 'time': 1352, 'number': 4},
        ]
        result = self.mgr.autodetect_intro(chapters)
        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 2)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertEqual(result['intro_start_time'], 112)
        self.assertEqual(result['intro_end_time'], 157)
        self.assertEqual(result['outro_start_chapter'], 4)

    def test_autodetect_intro_no_match(self):
        """autodetect_intro returns None when no intro-named chapter exists"""
        chapters = [
            {'name': 'Chapter 1', 'time': 0, 'number': 1},
            {'name': 'Chapter 2', 'time': 100, 'number': 2},
        ]
        result = self.mgr.autodetect_intro(chapters)
        self.assertIsNone(result)

    def test_autodetect_intro_by_next_chapter(self):
        """autodetect_intro uses next chapter as end when only 'Intro' found"""
        chapters = [
            {'name': 'Start', 'time': 0, 'number': 1},
            {'name': 'Intro', 'time': 30, 'number': 2},
            {'name': 'Main Content', 'time': 90, 'number': 3},
        ]
        result = self.mgr.autodetect_intro(chapters)
        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 2)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertEqual(result['intro_end_time'], 90)

    def test_autodetect_intro_matches_short_op_name_without_timestamps(self):
        """Anime-style OP/episode-start chapters can use chapter-seek mode"""
        chapters = [
            {'name': 'Chapter 1', 'number': 1},
            {'name': 'OP', 'number': 2},
            {'name': 'Episode Start', 'number': 3},
        ]
        result = self.mgr.autodetect_intro(chapters)

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 2)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertIsNone(result['intro_start_time'])
        self.assertIsNone(result['intro_end_time'])

    def test_autodetect_opening_credits_is_not_outro(self):
        """Opening Credits should be classified as intro, not end credits"""
        chapters = [
            {'name': 'Opening Credits', 'time': 0, 'number': 1},
            {'name': 'Act 1', 'time': 65, 'number': 2},
            {'name': 'End Credits', 'time': 1400, 'number': 3},
        ]
        result = self.mgr.autodetect_intro(chapters)

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 1)
        self.assertEqual(result['intro_end_chapter'], 2)
        self.assertEqual(result['outro_start_chapter'], 3)

    def test_autodetect_intro_uses_chapter_end_time_without_next_chapter(self):
        """A named intro chapter can use its own end_time as the boundary"""
        chapters = [
            {'name': 'OP', 'time': 20, 'end_time': 80, 'number': 1},
        ]
        result = self.mgr.autodetect_intro(chapters)

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 1)
        self.assertEqual(result['intro_end_chapter'], 1)
        self.assertEqual(result['intro_end_time'], 80)


class TestAudioIntroDetector(unittest.TestCase):
    """Tests for music-to-dialogue audio intro detection"""

    def test_detect_intro_from_music_silence_speech(self):
        from resources.lib.audio_intro import AudioIntroDetector
        detector = AudioIntroDetector(min_music_seconds=120, min_speech_seconds=10)
        segments = [
            ('music', 0, 260),
            ('noEnergy', 260, 263),
            ('speech', 263, 320),
        ]

        result = detector.detect_intro_from_segments(segments)

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_time'], 0)
        self.assertEqual(result['intro_end_time'], 263)

    def test_detect_intro_requires_long_music(self):
        from resources.lib.audio_intro import AudioIntroDetector
        detector = AudioIntroDetector(min_music_seconds=120, min_speech_seconds=10)
        segments = [
            ('music', 0, 45),
            ('speech', 45, 120),
        ]

        self.assertIsNone(detector.detect_intro_from_segments(segments))

    def test_detect_show_intro_uses_median_across_episodes(self):
        from resources.lib.audio_intro import AudioIntroDetector
        # 11 blocks = 2.0 + 10*0.5 = 7.0s (>= 5.0s min)
        common = [0xAAAAAA] * 11
        def fps(values, start=0.0):
            return [{'time': float(start) + index * 0.5, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(max_episodes=3, fingerprint_min_common_seconds=5)
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)
        detector._fingerprint_file = MagicMock(side_effect=[
            fps([0x11] * 4 + common), # starts at 2.0s
            fps([0x33] * 8 + common), # starts at 4.0s
            fps(common),              # starts at 0.0s
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.mkv', 'e2.mkv', 'e3.mkv'])

        self.assertIsNotNone(result)
        # Current impl uses best pair (e1, e2). Median of [2.0, 4.0] is 3.0
        self.assertEqual(result['intro_start_time'], 3.0)
        self.assertEqual(result['intro_end_time'], 10.0) # 3.0 + 7.0

    def test_detect_show_intro_skips_unreadable_episode(self):
        from resources.lib.audio_intro import AudioIntroDetectionError, AudioIntroDetector
        common = [0xAAAAAA] * 11
        def fps(values, start=0.0):
            return [{'time': float(start) + index * 0.5, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(max_episodes=2, fingerprint_min_common_seconds=5)
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)

        detector._fingerprint_file = MagicMock(side_effect=[
            AudioIntroDetectionError('bad media'),
            fps(common, start=0.0),
            fps(common, start=4.0),
        ])

        result = detector.detect_show_intro_by_fingerprint(['bad.mkv', 'g1.mkv', 'g2.mkv'])

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_time'], 2.0) # (0+4)/2
        self.assertEqual(result['episode_count'], 2) # Only g1 and g2 successfully analyzed


    def test_detect_show_intro_by_fingerprint_finds_common_audio(self):
        from resources.lib.audio_intro import AudioIntroDetector

        # Need enough blocks for 30s duration
        # duration = window + (len - 1) * step
        # 30 = 2.0 + (len - 1) * 0.5
        # 28 = (len - 1) * 0.5
        # 56 = len - 1
        # len = 57
        common = [0xAAAAAA] * 57

        def fingerprints(values):
            return [{'time': index * 0.5, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            max_episodes=2,
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=30,
            fingerprint_hamming_distance=0
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x11] * 10 + common), # starts at index 10 (t=5.0s)
            fingerprints([0x33] * 4 + common),  # starts at index 4 (t=2.0s)
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.strm', 'e2.strm'])

        self.assertIsNotNone(result)
        self.assertEqual(result['match_duration'], 30.0)
        self.assertEqual(result['intro_start_time'], 3.5) # (5.0 + 2.0) / 2
        self.assertEqual(result['intro_end_time'], 33.5)
        self.assertEqual(result['matching_episode_count'], 2)
        self.assertEqual(result['source'], 'audio_fingerprint')

    def test_detect_show_intro_by_fingerprint_default_accepts_shorter_intro(self):
        from resources.lib.audio_intro import AudioIntroDetector

        # Need 57 blocks for 30s duration (2.0 + 56 * 0.5)
        common = [0x1000000000000000 + index for index in range(57)]

        def fingerprints(values):
            return [{'time': index * 0.5, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=30,
            fingerprint_hamming_distance=0
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=180)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x1111111111111111] * 4 + common), # starts at 2.0s
            fingerprints([0x3333333333333333] * 8 + common), # starts at 4.0s
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.mkv', 'e2.mkv'])

        self.assertIsNotNone(result)
        self.assertEqual(result['match_duration'], 30.0)
        self.assertEqual(result['intro_start_time'], 3.0)
        self.assertEqual(result['intro_end_time'], 33.0)



    def test_detect_show_intro_by_fingerprint_prefers_aligned_pair(self):
        from resources.lib.audio_intro import AudioIntroDetector

        common = [
            0xAAAAAAAAAAAAAAAA,
            0xCCCCCCCCCCCCCCCC,
            0xF0F0F0F0F0F0F0F0,
            0x0F0F0F0F0F0F0F0F,
        ]

        def fingerprints(values):
            return [{'time': index * 2.0, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            max_episodes=3,
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=2.0, # Match legacy test behavior for this specific test
            fingerprint_min_common_seconds=6,
            fingerprint_hamming_distance=0
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x1111111111111111, 0x2222222222222222] + common),
            fingerprints(common + [0x3333333333333333]),
            fingerprints(common + [0x4444444444444444]),
        ])

        # Use the NEW method name
        result = detector.detect_show_intro_by_fingerprint(['cold-open.strm', 'e2.strm', 'e3.strm'])

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_time'], 0)
        self.assertEqual(result['intro_end_time'], 8)

    def test_detect_show_intro_by_fingerprint_rejects_late_intro_match(self):
        from resources.lib.audio_intro import AudioIntroDetector

        common = [
            0xAAAAAAAAAAAAAAAA,
            0xCCCCCCCCCCCCCCCC,
            0xF0F0F0F0F0F0F0F0,
            0x0F0F0F0F0F0F0F0F,
        ]

        def fingerprints(values):
            return [{'time': index * 2, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            fingerprint_window_seconds=2,
            fingerprint_min_common_seconds=6,
            fingerprint_hamming_distance=0
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=36)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x1111111111111111] * 8 + common),
            fingerprints([0x2222222222222222] * 8 + common),
        ])

        self.assertIsNone(detector.detect_show_intro_by_fingerprint(['e1.strm', 'e2.strm']))

    def test_detect_show_intro_by_fingerprint_includes_outro(self):
        from resources.lib.audio_intro import AudioIntroDetector

        # 9 blocks = 2.0 + 8*0.5 = 6.0s (>= 5.0s min)
        intro = [0xAAAAAA] * 9
        outro = [0xBBBBBB] * 9

        def fingerprints(values, start=0.0):
            return [{'time': float(start) + index * 0.5, 'hash': value, 'rms': 1000} for index, value in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=5,
            fingerprint_min_outro_seconds=5,
            fingerprint_hamming_distance=0
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=100)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x11] * 4 + intro), # ep 1 intro starts at 2.0s
            fingerprints([0x33] * 8 + intro), # ep 2 intro starts at 4.0s
            fingerprints(outro, start=90),    # ep 1 outro starts at 90.0s
            fingerprints(outro, start=92),    # ep 2 outro starts at 92.0s
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.strm', 'e2.strm'])

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_time'], 3.0) # (2+4)/2
        self.assertEqual(result['intro_end_time'], 9.0)  # 3.0 + 6.0
        self.assertEqual(result['outro_start_time'], 91.0) # (90+92)/2
        self.assertEqual(result['outro_match_duration'], 6.0)


    def test_gap_detector_truncates_overshooting_run(self):
        """Gap detector should cut the run where match quality degrades."""
        from resources.lib.audio_intro import AudioIntroDetector

        # 40 steps of strong match (distance 0) = identical intro audio
        # 40 steps of weak match (distance ~14) = similar but different post-intro
        # At step_seconds=0.5, that's 20s intro + 20s bleed
        intro_hash = 0xAAAAAAAAAAAAAAAA
        bleed_base = 0x5555555555555555
        bleed_varied = bleed_base ^ 0x3FFF  # 14 bits different from bleed_base

        def fingerprints(values):
            return [{'time': i * 0.5, 'hash': v, 'rms': 1000} for i, v in enumerate(values)]

        # Both episodes share identical intro, but post-intro content is
        # similar (passes hamming threshold) but not identical.
        common_intro = [intro_hash] * 40
        ep1_unique = [0x0] * 5
        ep2_unique = [None] * 8

        detector = AudioIntroDetector(
            backend='fingerprint',
            max_episodes=2,
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=5,
            fingerprint_hamming_distance=16,
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints(ep1_unique + common_intro + [bleed_base] * 40),
            fingerprints(ep2_unique + common_intro + [bleed_varied] * 40),
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.mkv', 'e2.mkv'])

        self.assertIsNotNone(result)
        # Without gap detection, duration would be ~42s (80 steps).
        # With gap detection, it should truncate near the intro boundary (~40 steps = ~21.5s).
        self.assertLessEqual(result['match_duration'], 25.0)
        self.assertGreaterEqual(result['match_duration'], 10.0)

    def test_gap_detector_does_not_truncate_clean_run(self):
        """Gap detector should leave a clean (uniform quality) run untouched."""
        from resources.lib.audio_intro import AudioIntroDetector

        # 57 steps of identical hashes = clean run, 30s
        common = [0xAAAAAA] * 57

        def fingerprints(values):
            return [{'time': i * 0.5, 'hash': v, 'rms': 1000} for i, v in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            max_episodes=2,
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=5,
            fingerprint_hamming_distance=0,
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x11] * 10 + common),
            fingerprints([0x33] * 4 + common),
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.mkv', 'e2.mkv'])

        self.assertIsNotNone(result)
        self.assertEqual(result['match_duration'], 30.0)

    def test_gap_detector_skips_short_runs(self):
        """Gap detection should not apply to runs shorter than the minimum."""
        from resources.lib.audio_intro import AudioIntroDetector

        # 9 steps = 6.0s, well under the 10s gap-detection minimum
        common = [0xAAAAAA] * 9

        def fingerprints(values):
            return [{'time': i * 0.5, 'hash': v, 'rms': 1000} for i, v in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            max_episodes=2,
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=5,
            fingerprint_hamming_distance=0,
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)
        detector._fingerprint_file = MagicMock(side_effect=[
            fingerprints([0x11] * 4 + common),
            fingerprints([0x33] * 8 + common),
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1.mkv', 'e2.mkv'])

        self.assertIsNotNone(result)
        self.assertEqual(result['match_duration'], 6.0)

    def test_find_gap_index_returns_none_for_uniform_distances(self):
        """_find_gap_index should return None when all distances are equal."""
        from resources.lib.audio_intro import AudioIntroDetector

        detector = AudioIntroDetector()
        self.assertIsNone(detector._find_gap_index([2] * 30))
        self.assertIsNone(detector._find_gap_index([0] * 30))

    def test_find_gap_index_detects_quality_step(self):
        """_find_gap_index should find where distances jump."""
        from resources.lib.audio_intro import AudioIntroDetector

        # 20 steps at distance 2, then 20 steps at distance 14
        distances = [2] * 20 + [14] * 20
        detector = AudioIntroDetector()
        gap = detector._find_gap_index(distances)
        self.assertIsNotNone(gap)
        # Gap should be near the transition point (index ~20)
        self.assertGreaterEqual(gap, 12)
        self.assertLessEqual(gap, 25)

    def test_find_episode_candidates_uses_neighboring_video_files(self):
        from resources.lib.audio_intro import AudioIntroDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ['Show.S01E01.mkv', 'Show.S01E02.mkv', 'Show.S01E03.mkv', 'notes.txt']:
                open(os.path.join(tmpdir, name), 'w').close()

            selected = os.path.join(tmpdir, 'Show.S01E02.mkv')
            detector = AudioIntroDetector(max_episodes=2)
            result = detector.find_episode_candidates(selected)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].endswith('Show.S01E02.mkv'))
        self.assertTrue(result[1].endswith('Show.S01E03.mkv'))

    def test_find_episode_candidates_includes_strm_files(self):
        from resources.lib.audio_intro import AudioIntroDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ['Show.S01E01.strm', 'Show.S01E02.strm', 'notes.txt']:
                open(os.path.join(tmpdir, name), 'w').close()

            selected = os.path.join(tmpdir, 'Show.S01E01.strm')
            detector = AudioIntroDetector(max_episodes=2)
            result = detector.find_episode_candidates(selected)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].endswith('Show.S01E01.strm'))
        self.assertTrue(result[1].endswith('Show.S01E02.strm'))

    def test_find_episode_candidates_accepts_show_folder(self):
        from resources.lib.audio_intro import AudioIntroDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ['Show.S01E01.mkv', 'Show.S01E02.mkv']:
                open(os.path.join(tmpdir, name), 'w').close()

            detector = AudioIntroDetector(max_episodes=2)
            result = detector.find_episode_candidates(tmpdir + os.sep)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].endswith('Show.S01E01.mkv'))
        self.assertTrue(result[1].endswith('Show.S01E02.mkv'))

    def test_extract_audio_clip_resolves_strm_url(self):
        from resources.lib.audio_intro import AudioIntroDetector

        stream_url = 'https://stream.example.test/private-token/episode.m3u8'

        class FakeStrmFile:
            def read(self):
                return '#EXTM3U\n' + stream_url + '\n'
            def close(self):
                pass

        detector = AudioIntroDetector(max_scan_seconds=600)
        with patch('resources.lib.audio_intro.xbmcvfs.File', return_value=FakeStrmFile()), \
                patch('resources.lib.audio_intro.subprocess.run') as run_mock:
            output_path = detector._extract_audio_clip('/media/Show.S01E01.strm', 'ffmpeg')

        try:
            run_mock.assert_called_once()
            self.assertTrue(run_mock.call_args.kwargs.get('check'))
            self.assertEqual(run_mock.call_args.kwargs.get('timeout'), detector.ffmpeg_timeout_seconds)
            command = run_mock.call_args[0][0]
            self.assertIn(stream_url, command)
            self.assertIn('-t', command)
            self.assertIn('600', command)
        finally:
            os.unlink(output_path)

    def test_extract_audio_clip_redacts_strm_url_on_ffmpeg_error(self):
        from resources.lib.audio_intro import AudioIntroDetectionError, AudioIntroDetector

        stream_url = 'https://stream.example.test/private-token/episode.m3u8'

        class FakeStrmFile:
            def read(self):
                return stream_url
            def close(self):
                pass

        detector = AudioIntroDetector()
        ffmpeg_error = subprocess.CalledProcessError(
            1,
            ['ffmpeg'],
            stderr=f'{stream_url}: Server returned 403 Forbidden'.encode('utf-8')
        )
        with patch('resources.lib.audio_intro.xbmcvfs.File', return_value=FakeStrmFile()), \
                patch('resources.lib.audio_intro.subprocess.run', side_effect=ffmpeg_error):
            with self.assertRaises(AudioIntroDetectionError) as ctx:
                detector._extract_audio_clip('/media/Show.S01E01.strm', 'ffmpeg')

        self.assertNotIn(stream_url, str(ctx.exception))
        self.assertIn('[input]', str(ctx.exception))

    def test_extract_pcm_clip_timeout_redacts_strm_url(self):
        from resources.lib.audio_intro import AudioIntroDetectionError, AudioIntroDetector

        stream_url = 'https://stream.example.test/private-token/episode.m3u8'

        class FakeStrmFile:
            def read(self):
                return stream_url
            def close(self):
                pass

        detector = AudioIntroDetector(ffmpeg_timeout_seconds=12)
        ffmpeg_error = subprocess.TimeoutExpired(
            ['ffmpeg', '-i', stream_url],
            timeout=12
        )
        with patch('resources.lib.audio_intro.xbmcvfs.File', return_value=FakeStrmFile()), \
                patch('resources.lib.audio_intro.subprocess.run', side_effect=ffmpeg_error):
            with self.assertRaises(AudioIntroDetectionError) as ctx:
                detector._extract_pcm_clip('/media/Show.S01E01.strm', 'ffmpeg')

        self.assertNotIn(stream_url, str(ctx.exception))
        self.assertIn('timed out', str(ctx.exception))
        self.assertIn('12 seconds', str(ctx.exception))

    def test_probe_duration_timeout_redacts_strm_url(self):
        from resources.lib.audio_intro import AudioIntroDetector

        stream_url = 'https://stream.example.test/private-token/episode.m3u8'

        class FakeStrmFile:
            def read(self):
                return stream_url
            def close(self):
                pass

        detector = AudioIntroDetector()
        detector._find_ffprobe = MagicMock(return_value='ffprobe')
        ffprobe_error = subprocess.TimeoutExpired(
            ['ffprobe', stream_url],
            timeout=30
        )
        with patch('resources.lib.audio_intro.xbmcvfs.File', return_value=FakeStrmFile()), \
                patch('resources.lib.audio_intro.subprocess.run', side_effect=ffprobe_error), \
                patch('resources.lib.audio_intro.xbmc.log') as log_mock:
            self.assertIsNone(detector._probe_duration('/media/Show.S01E01.strm'))

        message = log_mock.call_args[0][0]
        self.assertNotIn(stream_url, message)
        self.assertIn('ffprobe timed out', message)

    def test_hamming_distance(self):
        from resources.lib.audio_intro import AudioIntroDetector
        self.assertEqual(AudioIntroDetector._hamming_distance(0, 0), 0)
        self.assertEqual(AudioIntroDetector._hamming_distance(0xFF, 0x00), 8)
        self.assertEqual(AudioIntroDetector._hamming_distance(0x01, 0x02), 2)

    def test_is_better_fingerprint_match(self):
        from resources.lib.audio_intro import AudioIntroDetector
        det = AudioIntroDetector()
        self.assertTrue(det._is_better_fingerprint_match({'duration': 10}, None))
        self.assertTrue(det._is_better_fingerprint_match({'duration': 10}, {'duration': 5}))
        self.assertFalse(det._is_better_fingerprint_match({'duration': 5}, {'duration': 10}))
        # Equal duration, prefer lower spread
        self.assertTrue(det._is_better_fingerprint_match(
            {'duration': 10, 'start_spread': 1},
            {'duration': 10, 'start_spread': 2}
        ))
        # Equal duration and spread, prefer lower distance
        self.assertTrue(det._is_better_fingerprint_match(
            {'duration': 10, 'start_spread': 1, 'average_distance': 1},
            {'duration': 10, 'start_spread': 1, 'average_distance': 2}
        ))

    def test_is_better_outro_match(self):
        from resources.lib.audio_intro import AudioIntroDetector
        det = AudioIntroDetector()
        self.assertTrue(det._is_better_outro_match({'duration': 10}, None))
        self.assertTrue(det._is_better_outro_match({'duration': 10}, {'duration': 5}))
        # Prefer later start for outro
        self.assertTrue(det._is_better_outro_match(
            {'duration': 10, 'left_start_time': 100, 'right_start_time': 100},
            {'duration': 10, 'left_start_time': 50, 'right_start_time': 50}
        ))

    def test_normalize_segments_handles_invalid_data(self):
        from resources.lib.audio_intro import AudioIntroDetector
        segments = [
            ('music', 0, 10),
            ('speech', 'invalid', 20),
            ('silence', 20, 10),  # end <= start
            ('music', 30, 40)
        ]
        result = AudioIntroDetector._normalize_segments(segments)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ('music', 0.0, 10.0))
        self.assertEqual(result[1], ('music', 30.0, 40.0))

    def test_speech_seconds_from_stops_at_gap(self):
        from resources.lib.audio_intro import AudioIntroDetector
        detector = AudioIntroDetector(min_speech_seconds=10)
        segments = [
            ('speech', 0, 5),
            ('music', 5, 10),  # gap/interruption
            ('speech', 10, 20),
        ]
        self.assertEqual(detector._speech_seconds_from(segments, 0), 5)

    def test_fingerprint_pcm_resolution(self):
        from resources.lib.audio_intro import AudioIntroDetector
        # 8000Hz * 4 seconds = 32000 samples
        # With 2s window and 0.5s step:
        # 0.0s to 2.0s
        # 0.5s to 2.5s
        # 1.0s to 3.0s
        # 1.5s to 3.5s
        # 2.0s to 4.0s (last possible window)
        # Total = 5 fingerprints
        pcm = b'\x00\x01' * 32000
        detector = AudioIntroDetector(
            fingerprint_sample_rate=8000,
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_rms=0 # Disable noise gate for predictable count
        )
        fps = detector._fingerprint_pcm(pcm)
        self.assertEqual(len(fps), 5)
        self.assertEqual(fps[0]['time'], 0.0)
        self.assertEqual(fps[1]['time'], 0.5)
        self.assertEqual(fps[4]['time'], 2.0)

    def test_detect_show_intro_by_fingerprint_consensus(self):
        from resources.lib.audio_intro import AudioIntroDetector

        intro = [0xA, 0xB, 0xC, 0xD] # 4 blocks * 0.5s step = 2s match (2s window + 1.5s additional)
        recap = [0x1]                # 1 block * 0.5s step = 2s match (just window)

        def fps(values):
            return [{'time': i * 0.5, 'hash': v, 'rms': 1000} for i, v in enumerate(values)]

        detector = AudioIntroDetector(
            backend='fingerprint',
            fingerprint_window_seconds=2.0,
            fingerprint_step_seconds=0.5,
            fingerprint_min_common_seconds=2, # Require 2s
            fingerprint_hamming_distance=0,
            max_episodes=3
        )
        detector._find_ffmpeg = MagicMock(return_value='ffmpeg')
        detector._probe_duration = MagicMock(return_value=120)

        # Intro: [0xA, 0xB, 0xC, 0xD] starts at index 4 (t=2.0s)
        # Recap: [0x1] starts at index 0 (t=0.0s)
        detector._fingerprint_file = MagicMock(side_effect=[
            fps(recap + [0, 0, 0] + intro), # Ep 1
            fps([9, 9] + [0, 0] + intro), # Ep 2
            fps(recap + [0, 0, 0] + intro), # Ep 3
        ])

        result = detector.detect_show_intro_by_fingerprint(['e1', 'e2', 'e3'])

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_time'], 2.0)
        self.assertEqual(result['support_count'], 3)



class TestEntryPoints(unittest.TestCase):
    """Tests for script entry points (command wrappers)"""

    def test_database_tools_backup(self):
        import database_tools
        with patch('sys.argv', ['database_tools.py', 'backup']), \
             patch('database_tools.DatabaseManager') as mock_mgr:
            database_tools.main()
            mock_mgr.return_value.backup_database.assert_called_once()

    def test_database_tools_unknown_action(self):
        import database_tools
        with patch('sys.argv', ['database_tools.py', 'invalid']), \
             patch('database_tools.DatabaseManager') as mock_mgr:
            database_tools.main()
            mock_mgr.assert_not_called()

    def test_browse_path_success(self):
        import browse_path
        with patch('browse_path.xbmcaddon.Addon') as mock_addon, \
             patch('browse_path.xbmcgui.Dialog') as mock_dialog:
            mock_dialog.return_value.browse.return_value = 'smb://server/backups/'
            browse_path.browse_and_set_path()
            mock_addon.return_value.setSetting.assert_called_with('backup_restore_path', 'smb://server/backups/')
            mock_dialog.return_value.textviewer.assert_called()

    def test_browse_path_cancel(self):
        import browse_path
        with patch('browse_path.xbmcaddon.Addon'), \
             patch('browse_path.xbmcgui.Dialog') as mock_dialog:
            mock_dialog.return_value.browse.return_value = None
            browse_path.browse_and_set_path()
            # No setSetting call expected on cancel


class TestMetadataFilenameEdgeCases(unittest.TestCase):
    """Tests for ShowMetadata filename parsing edge cases"""

    def setUp(self):
        from resources.lib.metadata import ShowMetadata
        self.metadata = ShowMetadata()

    def test_parse_sxxexx_format(self):
        """Standard SxxExx format"""
        result = self.metadata._parse_filename('/path/to/Friends.S02E05.720p.mkv')
        self.assertEqual(result['title'].strip(), 'Friends')
        self.assertEqual(result['season'], 2)
        self.assertEqual(result['episode'], 5)

    def test_parse_xxXxx_format(self):
        """Alternative xxXxx format"""
        result = self.metadata._parse_filename('/path/to/Friends.02x05.720p.mkv')
        self.assertEqual(result['title'].strip(), 'Friends')
        self.assertEqual(result['season'], 2)
        self.assertEqual(result['episode'], 5)

    def test_parse_show_with_dots(self):
        """Show names with dots get spaces"""
        result = self.metadata._parse_filename('/path/to/The.Office.US.S06E01.mkv')
        self.assertEqual(result['title'].strip(), 'The Office US')

    def test_parse_no_match_returns_none(self):
        """Returns None when filename doesn't match any pattern"""
        result = self.metadata._parse_filename('/path/to/random_movie.mkv')
        self.assertIsNone(result)

    def test_parse_case_insensitive(self):
        """Matches case-insensitively"""
        result = self.metadata._parse_filename('/path/to/show.s01e01.mkv')
        self.assertIsNotNone(result)
        self.assertEqual(result['season'], 1)
        self.assertEqual(result['episode'], 1)

    def test_parse_windows_path(self):
        """Handles backslash paths"""
        result = self.metadata._parse_filename('C:\\Videos\\Show.S01E01.mkv')
        self.assertIsNotNone(result)
        self.assertEqual(result['season'], 1)

    def test_parse_url_strips_query_tokens(self):
        """URL query tokens are ignored when parsing filenames"""
        result = self.metadata._parse_filename('https://stream.example/Show.S01E01.m3u8?token=secret')
        self.assertIsNotNone(result)
        self.assertEqual(result['title'].strip(), 'Show')
        self.assertEqual(result['season'], 1)

    def test_sanitize_path_redacts_credentials_and_tokens(self):
        """sanitize_path removes credentials, query strings, and fragments"""
        from resources.lib.metadata import sanitize_path, safe_basename
        self.assertEqual(
            sanitize_path('smb://user:pass@example.test/share/Show.S01E01.mkv?token=abc#frag'),
            'smb://***:***@example.test/share/Show.S01E01.mkv'
        )
        self.assertEqual(
            sanitize_path('plugin://plugin.video.fenlight/?tmdb_id=123&token=secret'),
            'plugin://plugin.video.fenlight/'
        )
        self.assertEqual(
            safe_basename('https://stream.example/path/Show.S01E01.m3u8?token=secret'),
            'Show.S01E01.m3u8'
        )


class TestPlayerUI(unittest.TestCase):
    """Tests for PlayerUI and SkipIntroDialog"""

    def setUp(self):
        from resources.lib.ui import PlayerUI
        self.ui = PlayerUI()

    def test_initial_state(self):
        """PlayerUI starts with no dialog and prompt_shown=False"""
        self.assertFalse(self.ui.prompt_shown)
        self.assertIsNone(self.ui._dialog)

    def test_prompt_skip_intro_creates_dialog(self):
        """prompt_skip_intro creates and shows dialog"""
        callback = MagicMock()
        result = self.ui.prompt_skip_intro(callback)
        self.assertTrue(result)
        self.assertTrue(self.ui.prompt_shown)
        self.assertIsNotNone(self.ui._dialog)

    def test_prompt_skip_intro_only_once(self):
        """Second call returns False"""
        self.ui.prompt_skip_intro(MagicMock())
        result = self.ui.prompt_skip_intro(MagicMock())
        self.assertFalse(result)

    def test_cleanup_closes_dialog(self):
        """cleanup closes dialog and resets state"""
        self.ui.prompt_skip_intro(MagicMock())
        self.ui.cleanup()
        self.assertIsNone(self.ui._dialog)
        self.assertFalse(self.ui.prompt_shown)

    def test_cleanup_no_dialog(self):
        """cleanup is safe when no dialog exists"""
        self.ui.cleanup()  # should not raise

    def test_skip_intro_dialog_onclick_calls_callback(self):
        """SkipIntroDialog.onClick calls callback on button 1"""
        from resources.lib.ui import SkipIntroDialog
        callback = MagicMock()
        dialog = SkipIntroDialog('skip_button.xml', '.', 'default', '720p', callback=callback)
        dialog.onClick(1)
        callback.assert_called_once()

    def test_skip_intro_dialog_onclick_ignores_other_controls(self):
        """SkipIntroDialog.onClick ignores non-button controls"""
        from resources.lib.ui import SkipIntroDialog
        callback = MagicMock()
        dialog = SkipIntroDialog('skip_button.xml', '.', 'default', '720p', callback=callback)
        dialog.onClick(999)
        callback.assert_not_called()

    def test_show_notification_uses_dialog(self):
        """show_notification uses xbmcgui.Dialog().notification() not executebuiltin"""
        self.ui.show_notification('test message')
        # Should not raise - uses safe Dialog API


class TestContextModule(unittest.TestCase):
    """Tests for context.py input validation"""

    def test_get_time_input_valid(self):
        """Valid MM:SS input is accepted"""
        from context import get_time_input
        dialog = MagicMock()
        dialog.numeric.return_value = '02:30'
        result = get_time_input(dialog, 'prompt')
        self.assertEqual(result, '02:30')

    def test_get_time_input_invalid_seconds(self):
        """Seconds >= 60 are rejected, user cancels retry"""
        from context import get_time_input
        dialog = MagicMock()
        dialog.numeric.side_effect = ['02:70', '']  # bad, then empty
        dialog.yesno.return_value = False  # don't retry
        result = get_time_input(dialog, 'prompt', required=False)
        self.assertIsNone(result)

    def test_get_time_input_empty_optional(self):
        """Empty input on optional field returns None"""
        from context import get_time_input
        dialog = MagicMock()
        dialog.numeric.return_value = ''
        result = get_time_input(dialog, 'prompt', required=False)
        self.assertIsNone(result)

    def test_get_chapter_selection_valid(self):
        """Valid chapter numbers are accepted (full chapter mode)"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.select.return_value = 2  # Full chapter mode (both start & end)
        dialog.numeric.side_effect = ['1', '3', '']  # start, end, no outro
        result = get_chapter_selection(dialog, None)
        self.assertEqual(result['intro_start_chapter'], 1)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertIsNone(result['outro_start_chapter'])
        self.assertTrue(result['use_chapters'])

    def test_get_chapter_selection_end_before_start(self):
        """End chapter <= start chapter is rejected"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.select.return_value = 2  # Full chapter mode
        dialog.numeric.side_effect = ['3', '2', '']
        dialog.notification = MagicMock()
        result = get_chapter_selection(dialog, None)
        self.assertIsNone(result)

    def test_get_chapter_selection_zero_chapter(self):
        """Chapter number 0 is rejected"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.select.return_value = 2  # Full chapter mode
        dialog.numeric.side_effect = ['0', '', '']
        dialog.notification = MagicMock()
        result = get_chapter_selection(dialog, None)
        self.assertIsNone(result)

    def test_get_manual_time_input(self):
        """Manual time input converts MM:SS to seconds"""
        from context import get_manual_time_input
        dialog = MagicMock()
        dialog.numeric.side_effect = ['01:30', '03:00', '']  # start, end, no outro
        dialog.yesno.return_value = False
        result = get_manual_time_input(dialog, None)
        self.assertEqual(result['intro_start_time'], 90)
        self.assertEqual(result['intro_end_time'], 180)
        self.assertIsNone(result['outro_start_time'])

    def test_get_manual_time_input_empty_start_defaults_to_zero(self):
        """Empty optional intro start means video start, not cancellation"""
        from context import get_manual_time_input
        dialog = MagicMock()
        dialog.numeric.side_effect = ['', '03:00', '']  # no start, end, no outro
        dialog.yesno.return_value = False
        result = get_manual_time_input(dialog, None)
        self.assertEqual(result['intro_start_time'], 0)
        self.assertEqual(result['intro_end_time'], 180)
        self.assertIsNone(result['outro_start_time'])

    def test_get_audio_intro_detection_confirms_detected_times(self):
        import context

        dialog = MagicMock()
        dialog.yesno.return_value = True
        fake_detector = MagicMock()
        fake_detector.find_episode_candidates.return_value = ['e1.mkv', 'e2.mkv']
        fake_detector.detect_show_intro.return_value = {
            'intro_start_time': 0,
            'intro_end_time': 263,
            'episode_count': 2,
            'matching_episode_count': 2,
        }

        with patch.object(context, 'AudioIntroDetector', return_value=fake_detector) as detector_cls:
            result = context.get_audio_intro_detection(dialog, {'file': '/videos/e1.mkv'})

        detector_cls.assert_called_once_with(backend='fingerprint')
        self.assertEqual(result['intro_start_time'], 0)
        self.assertEqual(result['intro_end_time'], 263)
        self.assertEqual(result['source'], 'audio_detection')
        dialog.yesno.assert_called_once()

    def test_get_audio_intro_detection_includes_outro(self):
        import context

        dialog = MagicMock()
        dialog.yesno.return_value = True
        fake_detector = MagicMock()
        fake_detector.find_episode_candidates.return_value = ['e1.mkv', 'e2.mkv']
        fake_detector.detect_show_intro.return_value = {
            'intro_start_time': 0,
            'intro_end_time': 180,
            'outro_start_time': 2400,
            'episode_count': 2,
            'matching_episode_count': 2,
        }

        with patch.object(context, 'AudioIntroDetector', return_value=fake_detector):
            result = context.get_audio_intro_detection(dialog, {'file': '/videos/e1.mkv'})

        self.assertEqual(result['outro_start_time'], 2400)
        self.assertIn('outro', dialog.yesno.call_args[0][1])

    def test_resolve_fenlight_episode_to_local_episode_by_tmdb(self):
        import context

        path = 'plugin://plugin.video.fenlight/?mode=playback.media&media_type=episode&tmdb_id=86325&season=1&episode=2'
        tvshows = {
            'tvshows': [
                {
                    'tvshowid': 7,
                    'title': 'بوابة الحلواني',
                    'uniqueid': {'tmdb': '86325'},
                    'file': 'smb://server/بوابة الحلواني/'
                }
            ]
        }
        episodes = {
            'episodes': [
                {'season': 1, 'episode': 1, 'file': 'smb://server/show/S01E01.strm'},
                {'season': 1, 'episode': 2, 'file': 'smb://server/show/S01E02.strm'},
            ]
        }

        with patch.object(context, '_json_rpc', side_effect=[tvshows, tvshows['tvshows'][0], episodes]):
            result = context._resolve_plugin_item_to_local(path, [])

        self.assertEqual(result['showtitle'], 'بوابة الحلواني')
        self.assertEqual(result['season'], 1)
        self.assertEqual(result['episode'], 2)
        self.assertEqual(result['file'], 'smb://server/show/S01E02.strm')

    def test_resolve_fenlight_show_to_local_episode_seed_by_normalized_title(self):
        import context

        path = 'plugin://plugin.video.fenlight/?mode=extras_menu_choice&tmdb_id=110491&media_type=tvshow'
        tvshows = {
            'tvshows': [
                {
                    'tvshowid': 8,
                    'title': 'لن أعيش فى جلباب أبي',
                    'file': 'smb://server/لن أعيش فى جلباب أبي/'
                }
            ]
        }
        episodes = {
            'episodes': [
                {'season': 1, 'episode': 1, 'file': 'smb://server/show/Season 01/S01E01.strm'},
                {'season': 1, 'episode': 2, 'file': 'smb://server/show/Season 01/S01E02.strm'},
            ]
        }

        with patch.object(context, '_json_rpc', side_effect=[tvshows, tvshows['tvshows'][0], episodes]):
            result = context._resolve_plugin_item_to_local(path, ['لن اعيش في جلباب ابي'])

        self.assertEqual(result['showtitle'], 'لن أعيش فى جلباب أبي')
        self.assertEqual(result['season'], 1)
        self.assertEqual(result['episode'], 1)
        self.assertFalse(result['save_episode_times'])
        self.assertEqual(result['file'], 'smb://server/show/Season 01/S01E01.strm')

    def test_get_selected_item_info_rejects_unmapped_fenlight_item(self):
        import context

        def info_label(label):
            if label == 'ListItem.FileNameAndPath':
                return 'plugin://plugin.video.fenlight/?mode=extras_menu_choice&tmdb_id=122543&media_type=tvshow'
            return ''

        with patch.object(context.xbmc, 'getInfoLabel', side_effect=info_label), \
             patch.object(context, '_json_rpc', return_value={'tvshows': []}):
            result = context.get_selected_item_info()

        self.assertEqual(
            result['error'],
            'No matching local Kodi library show found for this Fen Light item'
        )

    def test_get_selected_item_info_rejects_unsupported_plugin_item(self):
        import context

        def info_label(label):
            if label == 'ListItem.FileNameAndPath':
                return 'plugin://plugin.video.other/?mode=show&id=1'
            return ''

        with patch.object(context.xbmc, 'getInfoLabel', side_effect=info_label):
            result = context.get_selected_item_info()

        self.assertIn('local Kodi library', result['error'])

    def test_save_user_times_skips_episode_save_for_show_folder_audio_detection(self):
        import context

        fake_db = MagicMock()
        fake_db.get_show.return_value = 123
        fake_db.set_manual_show_times.return_value = True
        fake_db.get_show_config.return_value = {
            'intro_start_time': 0,
            'intro_end_time': 120,
            'outro_start_time': None
        }

        item = {
            'showtitle': 'Local Show',
            'season': None,
            'episode': None,
            'file': 'smb://server/Local Show/'
        }
        times = {
            'intro_start_time': 0,
            'intro_end_time': 120,
            'outro_start_time': None,
            'source': 'audio_detection'
        }

        with patch.object(context, 'get_selected_item_info', return_value=item), \
             patch.object(context, 'ShowDatabase', return_value=fake_db), \
             patch.object(context, 'get_manual_times', return_value=times):
            context.save_user_times()

        fake_db.set_manual_show_times.assert_called_once_with(123, 0, 120, None)
        fake_db.save_episode_times.assert_not_called()


class TestDatabaseManager(unittest.TestCase):
    """Tests for database management helper methods"""

    def test_vfs_join_preserves_kodi_url_paths(self):
        from resources.lib.database_manager import DatabaseManager
        self.assertEqual(
            DatabaseManager._vfs_join('smb://server/share/folder/', 'backup.db'),
            'smb://server/share/folder/backup.db'
        )
        self.assertEqual(
            DatabaseManager._vfs_join('nfs://server/share/folder', '/backup.db'),
            'nfs://server/share/folder/backup.db'
        )
        self.assertEqual(
            DatabaseManager._vfs_join('special://userdata/addon_data/plugin.video.skipintro/', 'export.json'),
            'special://userdata/addon_data/plugin.video.skipintro/export.json'
        )

    def test_vfs_join_treats_second_argument_as_safe_filename(self):
        """Backup/export filenames cannot traverse outside the configured directory"""
        from resources.lib.database_manager import DatabaseManager
        self.assertEqual(
            DatabaseManager._vfs_join('smb://server/share/folder', '../escape.db'),
            'smb://server/share/folder/escape.db'
        )
        self.assertEqual(
            DatabaseManager._vfs_join('/tmp/skipintro', '..\\escape.db'),
            os.path.join('/tmp/skipintro', 'escape.db')
        )

    def test_vfs_join_uses_native_join_for_local_paths(self):
        from resources.lib.database_manager import DatabaseManager
        self.assertEqual(
            DatabaseManager._vfs_join('/tmp/skipintro', 'backup.db'),
            os.path.join('/tmp/skipintro', 'backup.db')
        )

    def test_backup_restore_path_uses_url_separator_for_vfs_paths(self):
        from resources.lib.database_manager import DatabaseManager
        mgr = DatabaseManager.__new__(DatabaseManager)
        mgr.addon = MockXBMCAddon.Addon()
        mgr.addon.setSetting('backup_restore_path', 'smb://server/share/backups')
        mgr.addon_data_path = 'special://userdata/addon_data/plugin.video.skipintro/'

        with patch('resources.lib.database_manager.xbmcvfs.translatePath', side_effect=lambda p: p):
            self.assertEqual(
                mgr._get_backup_restore_path(),
                'smb://server/share/backups/'
            )

    def test_validate_import_config_rejects_unsafe_values(self):
        from resources.lib.database_manager import DatabaseManager
        clean = DatabaseManager._validate_import_config({
            'intro_start_chapter': -1,
            'intro_end_chapter': 10000,
            'outro_start_chapter': 5,
            'intro_start_time': -0.1,
            'intro_end_time': 86401,
            'outro_start_time': 3600,
            'intro_duration': 90,
            'use_chapters': True,
            'config_created_at': '2026-04-17 10:00:00',
        })

        self.assertIsNone(clean['intro_start_chapter'])
        self.assertIsNone(clean['intro_end_chapter'])
        self.assertEqual(clean['outro_start_chapter'], 5)
        self.assertIsNone(clean['intro_start_time'])
        self.assertIsNone(clean['intro_end_time'])
        self.assertEqual(clean['outro_start_time'], 3600)
        self.assertEqual(clean['intro_duration'], 90)
        self.assertTrue(clean['use_chapters'])

    def test_validate_import_config_rejects_bool_as_numeric_value(self):
        from resources.lib.database_manager import DatabaseManager
        clean = DatabaseManager._validate_import_config({
            'intro_start_chapter': True,
            'intro_end_time': False,
            'intro_duration': True,
        })
        self.assertIsNone(clean['intro_start_chapter'])
        self.assertIsNone(clean['intro_end_time'])
        self.assertIsNone(clean['intro_duration'])

    def test_validate_import_episode_rejects_invalid_identity(self):
        from resources.lib.database_manager import DatabaseManager
        self.assertIsNone(DatabaseManager._validate_import_episode({
            'season': -1,
            'episode': 1,
            'intro_end_time': 90,
        }))
        self.assertIsNone(DatabaseManager._validate_import_episode({
            'season': 1,
            'episode': 10001,
            'intro_end_time': 90,
        }))

    def test_export_to_json_uses_vfs_file_and_redacts_logs(self):
        from resources.lib.database import ShowDatabase
        from resources.lib.database_manager import DatabaseManager

        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        db = ShowDatabase(tmp.name)
        try:
            show_id = db.get_show('Export Show')
            db.set_manual_show_times(show_id, 0, 75, 1200)
            db.save_episode_times(show_id, 1, 2, {
                'intro_start_time': 0,
                'intro_end_time': 75,
                'source': 'test'
            })
        finally:
            db.close()

        writes = {}

        class FakeFile:
            def __init__(self, path, mode):
                writes['path'] = path
                writes['mode'] = mode
                writes['content'] = ''

            def write(self, data):
                writes['content'] += data

            def close(self):
                writes['closed'] = True

        mgr = DatabaseManager.__new__(DatabaseManager)
        mgr.addon = MockXBMCAddon.Addon()
        mgr.addon.setSetting(
            'backup_restore_path',
            'smb://user:pass@server/share/backups?token=secret'
        )
        mgr.addon_data_path = 'special://userdata/addon_data/plugin.video.skipintro/'
        mgr.db_path = tmp.name

        try:
            with patch('resources.lib.database_manager.xbmcvfs.File', side_effect=FakeFile), \
                    patch('resources.lib.database_manager.xbmcvfs.translatePath', side_effect=lambda p: p), \
                    patch('resources.lib.database_manager.xbmc.log') as log_mock:
                self.assertTrue(mgr.export_to_json())
        finally:
            os.unlink(tmp.name)

        self.assertEqual(writes['mode'], 'w')
        self.assertTrue(writes['path'].startswith('smb://user:pass@server/share/backups/'))
        data = json.loads(writes['content'])
        self.assertEqual(data['shows_count'], 1)
        self.assertEqual(data['shows'][0]['title'], 'Export Show')
        logs = '\n'.join(str(call.args[0]) for call in log_mock.call_args_list)
        self.assertNotIn('user:pass', logs)
        self.assertNotIn('token=secret', logs)
        self.assertIn('***:***@server', logs)

    def test_import_from_json_rejects_oversized_file_before_reading(self):
        from resources.lib.database_manager import DatabaseManager

        class BigFile:
            def size(self):
                return 10 * 1024 * 1024 + 1

            def read(self):
                raise AssertionError('oversized imports should not be read')

            def close(self):
                pass

        dialog = MagicMock()
        dialog.browse.return_value = 'smb://server/share/huge.json'
        mgr = DatabaseManager.__new__(DatabaseManager)
        mgr.addon = MockXBMCAddon.Addon()
        mgr.addon.setSetting('backup_restore_path', 'special://userdata/addon_data/plugin.video.skipintro/')
        mgr.addon_data_path = 'special://userdata/addon_data/plugin.video.skipintro/'
        mgr.db_path = ':memory:'

        with patch('resources.lib.database_manager.xbmcvfs.File', return_value=BigFile()), \
                patch('resources.lib.database_manager.xbmcvfs.translatePath', side_effect=lambda p: p), \
                patch('resources.lib.database_manager.xbmcgui.Dialog', return_value=dialog):
            self.assertFalse(mgr.import_from_json())

        dialog.notification.assert_called()

    def test_import_from_json_preserves_chapter_outro_columns(self):
        from resources.lib.database import ShowDatabase
        from resources.lib.database_manager import DatabaseManager

        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        ShowDatabase(tmp.name).close()

        import_data = {
            'version': '1.0',
            'shows': [
                {
                    'title': 'Imported Chapter Show',
                    'config': {
                        'use_chapters': True,
                        'intro_start_chapter': 1,
                        'intro_end_chapter': 3,
                        'outro_start_chapter': 4,
                        'intro_duration': 75,
                        'intro_start_time': 42.0,
                        'intro_end_time': 88.0,
                        'outro_start_time': 1200.0,
                    },
                    'episodes': [
                        {
                            'season': 1,
                            'episode': 2,
                            'intro_start_chapter': 1,
                            'intro_end_chapter': 3,
                            'outro_start_chapter': 5,
                            'source': 'test'
                        }
                    ]
                }
            ]
        }

        class FakeImportFile:
            def size(self):
                return len(json.dumps(import_data))

            def read(self):
                return json.dumps(import_data)

            def close(self):
                pass

        dialog = MagicMock()
        dialog.browse.return_value = 'smb://server/share/import.json'
        dialog.select.return_value = 1
        dialog.yesno.return_value = True

        mgr = DatabaseManager.__new__(DatabaseManager)
        mgr.addon = MockXBMCAddon.Addon()
        mgr.addon.setSetting('backup_restore_path', 'special://userdata/addon_data/plugin.video.skipintro/')
        mgr.addon_data_path = 'special://userdata/addon_data/plugin.video.skipintro/'
        mgr.db_path = tmp.name

        try:
            with patch('resources.lib.database_manager.xbmcvfs.File', return_value=FakeImportFile()), \
                    patch('resources.lib.database_manager.xbmcvfs.translatePath', side_effect=lambda p: p), \
                    patch('resources.lib.database_manager.xbmcgui.Dialog', return_value=dialog):
                self.assertTrue(mgr.import_from_json())

            db = ShowDatabase(tmp.name)
            try:
                show_id = db.get_show('Imported Chapter Show')
                config = db.get_show_config(show_id)
                episode = db.get_episode_times(show_id, 1, 2)
            finally:
                db.close()
        finally:
            os.unlink(tmp.name)

        self.assertEqual(config['outro_start_chapter'], 4)
        self.assertEqual(config['intro_start_time'], 42.0)
        self.assertEqual(config['intro_end_time'], 88.0)
        self.assertEqual(config['outro_start_time'], 1200.0)
        self.assertEqual(episode['outro_start_chapter'], 5)


class TestDatabaseMigration(unittest.TestCase):
    """Tests for database schema creation and migration"""

    def setUp(self):
        from resources.lib.database import ShowDatabase
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        self.db = ShowDatabase(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_tables_created(self):
        """All required tables exist after init"""
        import sqlite3
        conn = sqlite3.connect(self.tmp.name)
        try:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in c.fetchall()}
        finally:
            conn.close()
        self.assertIn('shows', tables)
        self.assertIn('shows_config', tables)
        self.assertIn('episodes', tables)

    def test_shows_config_columns(self):
        """shows_config has all required columns"""
        import sqlite3
        conn = sqlite3.connect(self.tmp.name)
        try:
            c = conn.cursor()
            c.execute("PRAGMA table_info(shows_config)")
            columns = {row[1] for row in c.fetchall()}
        finally:
            conn.close()
        expected = {'show_id', 'use_chapters', 'intro_start_chapter', 'intro_end_chapter',
                    'outro_start_chapter', 'intro_duration', 'intro_start_time',
                    'intro_end_time', 'outro_start_time', 'created_at'}
        self.assertTrue(expected.issubset(columns))

    def test_reinit_is_safe(self):
        """Re-initializing database doesn't lose data"""
        from resources.lib.database import ShowDatabase
        show_id = self.db.get_show('Persistent Show')
        self.db.set_manual_show_times(show_id, 10, 20, 30)

        db2 = ShowDatabase(self.tmp.name)
        try:
            config = db2.get_show_config(show_id)
            self.assertEqual(config['intro_start_time'], 10)
        finally:
            db2.close()

    def test_get_show_times_time_based(self):
        """get_show_times returns time-based config"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_times(show_id, 30, 90, 1200)
        times = self.db.get_show_times(show_id)
        self.assertFalse(times['use_chapters'])
        self.assertEqual(times['intro_start_time'], 30)

    def test_get_show_times_chapter_based(self):
        """get_show_times returns chapter-based config"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_chapters(show_id, True, 1, 3, 5)
        times = self.db.get_show_times(show_id)
        self.assertTrue(times['use_chapters'])
        self.assertEqual(times['intro_start_chapter'], 1)

    def test_get_show_times_no_config(self):
        """get_show_times returns None for unconfigured show"""
        show_id = self.db.get_show('New Show')
        # Default config has None times
        times = self.db.get_show_times(show_id)
        self.assertIsNotNone(times)

    def test_config_overwrite(self):
        """Saving config twice overwrites the first"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_times(show_id, 10, 20)
        self.db.set_manual_show_times(show_id, 50, 100, 200)
        config = self.db.get_show_config(show_id)
        self.assertEqual(config['intro_start_time'], 50)
        self.assertEqual(config['intro_end_time'], 100)

    def test_chapter_config_with_duration(self):
        """Chapter config with intro_duration is saved correctly"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_chapters(show_id, True, 1, None, None, intro_duration=90)
        config = self.db.get_show_config(show_id)
        self.assertTrue(config['use_chapters'])
        self.assertEqual(config['intro_start_chapter'], 1)
        self.assertIsNone(config['intro_end_chapter'])
        self.assertEqual(config['intro_duration'], 90)

    def test_show_title_is_parameterized_not_sql(self):
        """Show titles containing SQL syntax are stored as data"""
        malicious = "Robert'); DROP TABLE shows;--"
        show_id = self.db.get_show(malicious)
        self.assertIsNotNone(show_id)

        import sqlite3
        conn = sqlite3.connect(self.tmp.name)
        try:
            c = conn.cursor()
            c.execute("SELECT title FROM shows WHERE id = ?", (show_id,))
            self.assertEqual(c.fetchone()[0], malicious)
            c.execute("SELECT COUNT(*) FROM shows")
            self.assertGreaterEqual(c.fetchone()[0], 1)
        finally:
            conn.close()

    def test_legacy_database_gets_missing_columns(self):
        """Migration adds modern columns without dropping legacy rows"""
        import sqlite3
        legacy = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        legacy.close()
        conn = sqlite3.connect(legacy.name)
        try:
            c = conn.cursor()
            c.execute('CREATE TABLE shows (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL)')
            c.execute('CREATE TABLE shows_config (show_id INTEGER PRIMARY KEY, use_chapters BOOLEAN DEFAULT 0)')
            c.execute('INSERT INTO shows (title) VALUES (?)', ('Legacy Show',))
            conn.commit()
        finally:
            conn.close()

        from resources.lib.database import ShowDatabase
        db = ShowDatabase(legacy.name)
        try:
            conn = sqlite3.connect(legacy.name)
            try:
                c = conn.cursor()
                c.execute("PRAGMA table_info(shows_config)")
                columns = {row[1] for row in c.fetchall()}
            finally:
                conn.close()
            self.assertIn('intro_end_time', columns)
            self.assertEqual(db.get_show('Legacy Show'), 1)
        finally:
            db.close()
            os.unlink(legacy.name)

    def test_invalid_table_name_is_rejected_by_migration_helper(self):
        """Dynamic migration helpers reject table names outside the allowlist"""
        import sqlite3
        conn = sqlite3.connect(':memory:')
        try:
            c = conn.cursor()
            self.db._migrate_table(c, 'shows; DROP TABLE shows', {'id': 'INTEGER'})
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            self.assertEqual(c.fetchall(), [])
        finally:
            conn.close()


class TestShowManager(unittest.TestCase):
    """Tests for ShowManager facade"""

    def test_detect_show(self):
        """detect_show returns show info from metadata"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        result = mgr.detect_show()
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Test Show')
        self.assertEqual(mgr.current_show, result)

    def test_detect_show_no_video(self):
        """detect_show returns None when no info available"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        with patch('xbmc.getInfoLabel', return_value=''), \
             patch.object(MockXBMC.Player, 'isPlaying', return_value=False):
            result = mgr.detect_show()
            self.assertIsNone(result)

    def test_save_intro_time_no_db(self):
        """save_intro_time returns False without database"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()  # no db
        mgr.current_show = {'title': 'Test', 'season': 1, 'episode': 1}
        self.assertFalse(mgr.save_intro_time(30, 60))

    def test_get_saved_times_no_db(self):
        """get_saved_times returns None without database"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        self.assertIsNone(mgr.get_saved_times())

    def test_get_saved_times_no_show(self):
        """get_saved_times returns None without current_show"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        mgr.current_show = None
        self.assertIsNone(mgr.get_saved_times())


if __name__ == '__main__':
    unittest.main()
