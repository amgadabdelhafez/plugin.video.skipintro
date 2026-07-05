#!/usr/bin/env python3
"""Synthetic harness for the context-menu audio auto-detection flow.

This does not require Kodi. It creates deterministic MKV fixtures with a shared
intro audio block, runs the same candidate discovery and fingerprint detector
used by context.py, and exits non-zero if the detected boundary is off.
"""

import argparse
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import wave


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_RATE = 16000
WINDOW_SECONDS = 2
AMPLITUDE = 12000


def install_kodi_mocks():
    xbmc = types.SimpleNamespace(
        LOGDEBUG=0,
        LOGINFO=1,
        LOGERROR=2,
        LOGWARNING=3,
        log=lambda msg, level=1: None,
    )

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

    xbmcvfs = types.SimpleNamespace(
        translatePath=lambda path: path,
        listdir=listdir,
    )
    sys.modules.setdefault('xbmc', xbmc)
    sys.modules.setdefault('xbmcvfs', xbmcvfs)


def random_window(seed, sample_count):
    rng = random.Random(seed)
    return [rng.randint(-AMPLITUDE, AMPLITUDE) for _ in range(sample_count)]


def tone_window(frequency, sample_count):
    samples = []
    for index in range(sample_count):
        t = index / float(SAMPLE_RATE)
        samples.append(int(math.sin(2 * math.pi * frequency * t) * AMPLITUDE))
    return samples


def append_noise_windows(samples, seconds, seed_prefix):
    window_samples = SAMPLE_RATE * WINDOW_SECONDS
    windows = int(seconds // WINDOW_SECONDS)
    for window in range(windows):
        samples.extend(random_window(f'{seed_prefix}-{window}', window_samples))


def append_tone_remainder(samples, seconds, frequency):
    remainder = seconds % WINDOW_SECONDS
    if remainder:
        samples.extend(tone_window(frequency, int(SAMPLE_RATE * remainder)))


def write_fixture_wav(path, episode_index, cold_open_seconds, intro_seconds, body_seconds):
    samples = []
    append_noise_windows(samples, cold_open_seconds, f'cold-{episode_index}')
    append_tone_remainder(samples, cold_open_seconds, 220 + episode_index * 30)

    # The intro block is byte-identical across episodes, which is what the
    # production fingerprint matcher is expected to recover.
    append_noise_windows(samples, intro_seconds, 'shared-intro')
    append_tone_remainder(samples, intro_seconds, 440)

    append_noise_windows(samples, body_seconds, f'body-{episode_index}')
    append_tone_remainder(samples, body_seconds, 660 + episode_index * 40)

    with wave.open(path, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b''.join(struct.pack('<h', sample) for sample in samples))


def convert_wav_to_mkv(ffmpeg, wav_path, mkv_path):
    subprocess.run(
        [
            ffmpeg,
            '-y',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', wav_path,
            '-c:a', 'pcm_s16le',
            mkv_path,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_fixtures(directory, ffmpeg, episodes, cold_open_seconds, intro_seconds, body_seconds):
    paths = []
    for index in range(1, episodes + 1):
        wav_path = os.path.join(directory, f'Harness.Show.S01E{index:02d}.wav')
        mkv_path = os.path.join(directory, f'Harness.Show.S01E{index:02d}.mkv')
        write_fixture_wav(wav_path, index, cold_open_seconds, intro_seconds, body_seconds)
        convert_wav_to_mkv(ffmpeg, wav_path, mkv_path)
        paths.append(mkv_path)
    return paths


def run_harness(args):
    install_kodi_mocks()
    sys.path.insert(0, REPO_ROOT)

    from resources.lib.audio_intro import AudioIntroDetector

    ffmpeg = args.ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg was not found in PATH')

    keep_fixtures = args.keep_dir is not None
    workdir = args.keep_dir or tempfile.mkdtemp(prefix='skipintro-audio-harness-')
    os.makedirs(workdir, exist_ok=True)
    try:
        paths = build_fixtures(
            workdir,
            ffmpeg,
            args.episodes,
            args.cold_open_seconds,
            args.intro_seconds,
            args.body_seconds,
        )

        detector = AudioIntroDetector(
            backend='fingerprint',
            max_scan_seconds=args.max_scan_seconds,
            fingerprint_window_seconds=WINDOW_SECONDS,
            fingerprint_min_common_seconds=args.min_common_seconds,
            ffmpeg_path=ffmpeg,
        )
        candidates = detector.find_episode_candidates(paths[0])
        result = detector.detect_show_intro(candidates)

        expected = {
            'intro_start_time': float(args.cold_open_seconds),
            'intro_end_time': float(args.cold_open_seconds + args.intro_seconds),
        }
        payload = {
            'workdir': workdir,
            'fixtures_kept': keep_fixtures,
            'candidates': candidates,
            'expected': expected,
            'detected': result,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))

        if not result:
            return 1
        start_delta = abs(result.get('intro_start_time', -9999) - expected['intro_start_time'])
        end_delta = abs(result.get('intro_end_time', -9999) - expected['intro_end_time'])
        return 0 if start_delta <= args.tolerance and end_delta <= args.tolerance else 1
    finally:
        if not keep_fixtures:
            shutil.rmtree(workdir, ignore_errors=True)


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Run synthetic SkipIntro audio detection harness')
    parser.add_argument('--episodes', type=int, default=3)
    parser.add_argument('--cold-open-seconds', type=int, default=12)
    parser.add_argument('--intro-seconds', type=int, default=48)
    parser.add_argument('--body-seconds', type=int, default=150)
    parser.add_argument('--max-scan-seconds', type=int, default=120)
    parser.add_argument('--min-common-seconds', type=int, default=30)
    parser.add_argument('--tolerance', type=float, default=2.0)
    parser.add_argument('--ffmpeg')
    parser.add_argument('--keep-dir')
    return parser.parse_args(argv)


if __name__ == '__main__':
    raise SystemExit(run_harness(parse_args(sys.argv[1:])))
