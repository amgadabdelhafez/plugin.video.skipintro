#!/usr/bin/env python3
"""Kodi JSON-RPC E2E checks for the Skip Intro addon.

The suite generates tiny deterministic media fixtures at runtime, seeds the
addon database, then verifies real Kodi playback behavior over JSON-RPC.
It is intended to run inside the Kodi test container via:

    docker compose -f test-container/docker-compose.yml run --rm kodi-e2e-arm64
"""

import base64
import json
import os
import sqlite3
import subprocess
import time
import unittest
from pathlib import Path
from urllib import error, request


ROOT = Path(os.environ.get('ADDON_UNDER_TEST', '/addon'))
MEDIA_DIR = Path(os.environ.get('SKIPINTRO_E2E_MEDIA', '/tmp/skipintro-e2e-media'))
KODI_DATA = Path(os.environ.get('KODI_DATA', '/root/.kodi'))
DB_PATH = KODI_DATA / 'userdata' / 'addon_data' / 'plugin.video.skipintro' / 'shows.db'
JSONRPC_URL = os.environ.get('KODI_JSONRPC_URL', 'http://127.0.0.1:8080/jsonrpc')
JSONRPC_USER = os.environ.get('KODI_JSONRPC_USER', 'kodi')
JSONRPC_PASSWORD = os.environ.get('KODI_JSONRPC_PASSWORD', 'kodi')


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def generate_fixture(path, duration=24, chapters=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return

    base = [
        'ffmpeg',
        '-y',
        '-hide_banner',
        '-loglevel',
        'error',
        '-f',
        'lavfi',
        '-i',
        f'testsrc2=size=320x180:rate=24:duration={duration}',
        '-f',
        'lavfi',
        '-i',
        f'sine=frequency=880:duration={duration}',
        '-t',
        str(duration),
    ]

    if chapters:
        metadata = path.with_suffix('.ffmetadata')
        metadata.write_text(
            ';FFMETADATA1\n'
            '[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=5000\ntitle=Intro\n'
            '[CHAPTER]\nTIMEBASE=1/1000\nSTART=5000\nEND=10000\ntitle=Main Content\n'
            '[CHAPTER]\nTIMEBASE=1/1000\nSTART=10000\nEND=24000\ntitle=Act 1\n',
            encoding='utf-8',
        )
        command = base + [
            '-i',
            str(metadata),
            '-map',
            '0:v',
            '-map',
            '1:a',
            '-map_metadata',
            '2',
            '-c:v',
            'mpeg4',
            '-c:a',
            'aac',
            str(path),
        ]
    else:
        command = base + [
            '-map',
            '0:v',
            '-map',
            '1:a',
            '-c:v',
            'mpeg4',
            '-c:a',
            'aac',
            str(path),
        ]

    run(command)


def seed_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS shows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS shows_config (
                show_id INTEGER PRIMARY KEY,
                use_chapters BOOLEAN DEFAULT 0,
                intro_start_chapter INTEGER,
                intro_end_chapter INTEGER,
                intro_duration INTEGER,
                intro_start_time REAL,
                intro_end_time REAL,
                outro_start_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id INTEGER,
                season INTEGER,
                episode INTEGER,
                intro_start_chapter INTEGER,
                intro_end_chapter INTEGER,
                intro_start_time REAL,
                intro_end_time REAL,
                outro_start_time REAL,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(show_id, season, episode)
            )
        ''')
        c.execute('DELETE FROM episodes')
        c.execute('DELETE FROM shows_config')
        c.execute('DELETE FROM shows')

        def insert_show(title, config):
            c.execute('INSERT INTO shows (title) VALUES (?)', (title,))
            show_id = c.lastrowid
            c.execute('''
                INSERT INTO shows_config (
                    show_id, use_chapters, intro_start_chapter, intro_end_chapter,
                    intro_duration, intro_start_time, intro_end_time, outro_start_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                show_id,
                config.get('use_chapters', False),
                config.get('intro_start_chapter'),
                config.get('intro_end_chapter'),
                config.get('intro_duration'),
                config.get('intro_start_time'),
                config.get('intro_end_time'),
                config.get('outro_start_time'),
            ))

        insert_show('SkipIntro E2E', {
            'intro_start_time': 0,
            'intro_end_time': 10,
            'outro_start_time': None,
        })
        insert_show('Chapter E2E', {
            'use_chapters': True,
            'intro_start_chapter': 1,
            'intro_end_chapter': 3,
            'intro_duration': None,
            'outro_start_time': None,
        })
        conn.commit()
    finally:
        conn.close()


class KodiRPC:
    def __init__(self, url):
        self.url = url
        token = f'{JSONRPC_USER}:{JSONRPC_PASSWORD}'.encode('utf-8')
        self.auth_header = 'Basic ' + base64.b64encode(token).decode('ascii')
        self.request_id = 0

    def call(self, method, params=None, timeout=10):
        self.request_id += 1
        payload = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params or {},
            'id': self.request_id,
        }
        req = request.Request(
            self.url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': self.auth_header,
                'Content-Type': 'application/json',
            },
        )
        with request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
        if 'error' in result:
            raise AssertionError(f'{method} failed: {result["error"]}')
        return result.get('result')

    def wait(self, timeout=60):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                self.call('JSONRPC.Ping', timeout=2)
                return
            except (error.URLError, TimeoutError, ConnectionError, AssertionError) as exc:
                last_error = exc
                time.sleep(1)
        raise AssertionError(f'Kodi JSON-RPC did not become ready: {last_error}')


class KodiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rpc = KodiRPC(JSONRPC_URL)
        cls.rpc.wait()
        cls.media = {
            'manual': MEDIA_DIR / 'SkipIntro.E2E.S01E01.mkv',
            'plain': MEDIA_DIR / 'NoSkip.E2E.S01E01.mp4',
            'chapter': MEDIA_DIR / 'Chapter.E2E.S01E01.mkv',
        }
        generate_fixture(cls.media['manual'])
        generate_fixture(cls.media['plain'])
        generate_fixture(cls.media['chapter'], chapters=True)
        seed_database()
        cls.rpc.call('Addons.SetAddonEnabled', {
            'addonid': 'plugin.video.skipintro',
            'enabled': True,
        })

    def tearDown(self):
        try:
            self.rpc.call('Player.Stop', {'playerid': 1})
        except Exception:
            pass
        time.sleep(1)

    def open_video(self, path):
        self.rpc.call('Player.Open', {'item': {'file': str(path)}})
        deadline = time.time() + 20
        while time.time() < deadline:
            players = self.rpc.call('Player.GetActivePlayers')
            if any(player.get('playerid') == 1 for player in players):
                return
            time.sleep(0.5)
        raise AssertionError(f'Kodi did not start playback for {path}')

    def current_seconds(self):
        props = self.rpc.call('Player.GetProperties', {
            'playerid': 1,
            'properties': ['time'],
        })
        current = props['time']
        return current['hours'] * 3600 + current['minutes'] * 60 + current['seconds']

    def wait_for_time_at_least(self, seconds, timeout=12):
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = self.current_seconds()
            if current >= seconds:
                return current
            time.sleep(0.5)
        return self.current_seconds()

    def test_01_jsonrpc_and_addon_available(self):
        details = self.rpc.call('Addons.GetAddonDetails', {
            'addonid': 'plugin.video.skipintro',
            'properties': ['enabled', 'name'],
        })
        self.assertEqual(details['addon']['addonid'], 'plugin.video.skipintro')
        self.assertTrue(details['addon']['enabled'])

    def test_02_manual_time_config_skips_intro(self):
        self.open_video(self.media['manual'])
        current = self.wait_for_time_at_least(8)
        self.assertGreaterEqual(current, 8)

    def test_03_unconfigured_video_does_not_jump_to_intro_end(self):
        self.open_video(self.media['plain'])
        time.sleep(3)
        self.assertLess(self.current_seconds(), 8)

    def test_04_chapter_config_skips_intro(self):
        self.open_video(self.media['chapter'])
        current = self.wait_for_time_at_least(8)
        self.assertGreaterEqual(current, 8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
