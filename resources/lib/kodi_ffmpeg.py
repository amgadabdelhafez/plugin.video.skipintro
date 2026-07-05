"""Extract PCM audio from video files using ctypes to call FFmpeg symbols
loaded in the Kodi process (FFmpeg is statically linked into libkodi.so
on Android).

Falls back gracefully with clear diagnostics when symbols are unavailable.
"""

import ctypes
import ctypes.util
import os
import struct
import sys
import tempfile
from typing import Optional, Tuple

import xbmc

# FFmpeg media types
AVMEDIA_TYPE_AUDIO = 1

# FFmpeg sample formats
AV_SAMPLE_FMT_S16 = 1
AV_SAMPLE_FMT_S16P = 6
AV_SAMPLE_FMT_FLTP = 8

# FFmpeg error codes
AVERROR_EOF = -0x20464F45  # FFERRTAG(0xF8,'E','O','F')

# Channel layout for mono
AV_CH_LAYOUT_MONO = 0x4

# AV_TIME_BASE
AV_TIME_BASE = 1000000

# Seek flags
AVSEEK_FLAG_BACKWARD = 1


def _log(msg, level=xbmc.LOGINFO):
    xbmc.log(f'SkipIntro-FFmpeg: {msg}', level)


class KodiFFmpegError(Exception):
    """Raised when ctypes FFmpeg extraction fails."""


class KodiFFmpegUnavailable(KodiFFmpegError):
    """Raised when FFmpeg symbols cannot be found in the process."""


class _FFmpegLib:
    """Lazy loader for FFmpeg C function symbols via ctypes."""

    _instance = None
    _probed = False
    _available = False
    _probe_log = []

    @classmethod
    def get(cls):
        if not cls._probed:
            cls._probe()
        if not cls._available:
            raise KodiFFmpegUnavailable(
                'FFmpeg ctypes symbols not available. Probe log:\n'
                + '\n'.join(cls._probe_log)
            )
        return cls._instance

    @classmethod
    def probe_log(cls):
        if not cls._probed:
            cls._probe()
        return list(cls._probe_log)

    @classmethod
    def is_available(cls):
        if not cls._probed:
            cls._probe()
        return cls._available

    @classmethod
    def _probe(cls):
        cls._probed = True
        cls._probe_log = []
        log = cls._probe_log.append

        # Strategy 1: ctypes.CDLL(None) — handle to the running process
        # On Android, FFmpeg is statically linked into libkodi.so which is
        # the main binary.  Symbols may still be in the dynamic symbol table.
        strategies = [
            ('CDLL(None)', lambda: ctypes.CDLL(None)),
        ]

        # Strategy 2: Try loading libkodi.so explicitly
        strategies.append(('CDLL("libkodi.so")', lambda: ctypes.CDLL('libkodi.so')))

        # Strategy 3: Try common FFmpeg shared lib names (works on desktop Linux)
        for name in ('libavformat.so', 'libavcodec.so', 'avformat', 'avcodec'):
            strategies.append((f'CDLL("{name}")', lambda n=name: ctypes.CDLL(n)))

        # Strategy 4: find_library
        for name in ('avformat', 'avcodec'):
            path = ctypes.util.find_library(name)
            if path:
                strategies.append((f'find_library("{name}")={path}', lambda p=path: ctypes.CDLL(p)))

        # Log /proc/self/maps for diagnostics
        try:
            with open('/proc/self/maps', 'r') as f:
                seen = set()
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 6:
                        p = parts[-1]
                        if p not in seen and p.endswith('.so') and any(
                            k in p.lower() for k in ('kodi', 'avformat', 'avcodec', 'avutil', 'swresample')
                        ):
                            seen.add(p)
                            log(f'mapped: {p}')
        except Exception as e:
            log(f'/proc/self/maps: {e}')

        # Test symbols
        test_symbols = [
            'avformat_open_input',
            'avformat_find_stream_info',
            'avformat_close_input',
            'av_find_best_stream',
            'avcodec_find_decoder',
            'avcodec_alloc_context3',
            'avcodec_parameters_to_context',
            'avcodec_open2',
            'avcodec_send_packet',
            'avcodec_receive_frame',
            'avcodec_free_context',
            'av_read_frame',
            'av_packet_alloc',
            'av_packet_free',
            'av_frame_alloc',
            'av_frame_free',
            'av_packet_unref',
            'av_frame_unref',
            'swr_alloc',
            'swr_init',
            'swr_convert',
            'swr_free',
            'av_opt_set_int',
            'av_opt_set_sample_fmt',
            'avformat_network_init',
            'av_seek_frame',
        ]

        for strat_name, loader in strategies:
            try:
                lib = loader()
            except OSError as e:
                log(f'{strat_name}: load failed: {e}')
                continue

            found = []
            missing = []
            for sym in test_symbols:
                try:
                    getattr(lib, sym)
                    found.append(sym)
                except AttributeError:
                    missing.append(sym)

            log(f'{strat_name}: {len(found)}/{len(test_symbols)} symbols found')
            if missing:
                log(f'{strat_name}: missing: {", ".join(missing[:10])}')

            if len(found) == len(test_symbols):
                log(f'{strat_name}: ALL symbols found — using this handle')
                try:
                    cls._instance = cls._build(lib)
                    cls._available = True
                    # Log all diagnostics
                    for line in cls._probe_log:
                        _log(line)
                    return
                except AttributeError as e:
                    log(f'{strat_name}: binding failed: {e}')

        # No strategy worked
        log('No strategy found all required FFmpeg symbols')
        for line in cls._probe_log:
            _log(line, xbmc.LOGWARNING)

    @classmethod
    def _build(cls, lib):
        """Set up argtypes/restypes for the FFmpeg functions we need."""
        ff = _FFmpegFunctions()
        vp = ctypes.c_void_p
        ip = ctypes.POINTER(ctypes.c_int)

        ff.avformat_network_init = lib.avformat_network_init
        ff.avformat_network_init.restype = ctypes.c_int

        ff.avformat_open_input = lib.avformat_open_input
        ff.avformat_open_input.argtypes = [ctypes.POINTER(vp), ctypes.c_char_p, vp, vp]
        ff.avformat_open_input.restype = ctypes.c_int

        ff.avformat_find_stream_info = lib.avformat_find_stream_info
        ff.avformat_find_stream_info.argtypes = [vp, vp]
        ff.avformat_find_stream_info.restype = ctypes.c_int

        ff.avformat_close_input = lib.avformat_close_input
        ff.avformat_close_input.argtypes = [ctypes.POINTER(vp)]

        ff.av_find_best_stream = lib.av_find_best_stream
        ff.av_find_best_stream.argtypes = [vp, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(vp), ctypes.c_int]
        ff.av_find_best_stream.restype = ctypes.c_int

        ff.avcodec_find_decoder = lib.avcodec_find_decoder
        ff.avcodec_find_decoder.argtypes = [ctypes.c_int]
        ff.avcodec_find_decoder.restype = vp

        ff.avcodec_alloc_context3 = lib.avcodec_alloc_context3
        ff.avcodec_alloc_context3.argtypes = [vp]
        ff.avcodec_alloc_context3.restype = vp

        ff.avcodec_parameters_to_context = lib.avcodec_parameters_to_context
        ff.avcodec_parameters_to_context.argtypes = [vp, vp]
        ff.avcodec_parameters_to_context.restype = ctypes.c_int

        ff.avcodec_open2 = lib.avcodec_open2
        ff.avcodec_open2.argtypes = [vp, vp, vp]
        ff.avcodec_open2.restype = ctypes.c_int

        ff.avcodec_send_packet = lib.avcodec_send_packet
        ff.avcodec_send_packet.argtypes = [vp, vp]
        ff.avcodec_send_packet.restype = ctypes.c_int

        ff.avcodec_receive_frame = lib.avcodec_receive_frame
        ff.avcodec_receive_frame.argtypes = [vp, vp]
        ff.avcodec_receive_frame.restype = ctypes.c_int

        ff.avcodec_free_context = lib.avcodec_free_context
        ff.avcodec_free_context.argtypes = [ctypes.POINTER(vp)]

        ff.av_read_frame = lib.av_read_frame
        ff.av_read_frame.argtypes = [vp, vp]
        ff.av_read_frame.restype = ctypes.c_int

        ff.av_packet_alloc = lib.av_packet_alloc
        ff.av_packet_alloc.restype = vp

        ff.av_packet_free = lib.av_packet_free
        ff.av_packet_free.argtypes = [ctypes.POINTER(vp)]

        ff.av_packet_unref = lib.av_packet_unref
        ff.av_packet_unref.argtypes = [vp]

        ff.av_frame_alloc = lib.av_frame_alloc
        ff.av_frame_alloc.restype = vp

        ff.av_frame_free = lib.av_frame_free
        ff.av_frame_free.argtypes = [ctypes.POINTER(vp)]

        ff.av_frame_unref = lib.av_frame_unref
        ff.av_frame_unref.argtypes = [vp]

        ff.swr_alloc = lib.swr_alloc
        ff.swr_alloc.restype = vp

        ff.swr_init = lib.swr_init
        ff.swr_init.argtypes = [vp]
        ff.swr_init.restype = ctypes.c_int

        ff.swr_convert = lib.swr_convert
        ff.swr_convert.argtypes = [vp, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
        ff.swr_convert.restype = ctypes.c_int

        ff.swr_free = lib.swr_free
        ff.swr_free.argtypes = [ctypes.POINTER(vp)]

        ff.av_opt_set_int = lib.av_opt_set_int
        ff.av_opt_set_int.argtypes = [vp, ctypes.c_char_p, ctypes.c_int64, ctypes.c_int]
        ff.av_opt_set_int.restype = ctypes.c_int

        ff.av_opt_set_sample_fmt = lib.av_opt_set_sample_fmt
        ff.av_opt_set_sample_fmt.argtypes = [vp, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        ff.av_opt_set_sample_fmt.restype = ctypes.c_int

        ff.av_seek_frame = lib.av_seek_frame
        ff.av_seek_frame.argtypes = [vp, ctypes.c_int, ctypes.c_int64, ctypes.c_int]
        ff.av_seek_frame.restype = ctypes.c_int

        # Try to get avformat_version for diagnostics
        try:
            ff.avformat_version = lib.avformat_version
            ff.avformat_version.restype = ctypes.c_uint
            ver = ff.avformat_version()
            major = (ver >> 16) & 0xFF
            minor = (ver >> 8) & 0xFF
            micro = ver & 0xFF
            _log(f'avformat version: {major}.{minor}.{micro}')
        except Exception:
            pass

        return ff


class _FFmpegFunctions:
    """Container for resolved ctypes function pointers."""
    pass


# ---------- Struct field offsets for FFmpeg 6.0 ----------
# These are architecture-dependent.  We detect pointer size at import.

_PTR = ctypes.sizeof(ctypes.c_void_p)  # 4 on ARM32, 8 on ARM64/x86-64

# AVFormatContext — we need: duration, nb_streams, streams, url
# Layout varies by version. We read nb_streams and streams via a scanning
# approach: open a known-good file and look for expected values.

# AVPacket — on ARM32, int64_t needs 8-byte alignment, so there's 4 bytes
# padding after the buf pointer:
#   buf (ptr, 4) | pad (4) | pts (i64, 8) | dts (i64, 8) | data (ptr, 4) | size (i32, 4) | stream_index (i32, 4)
# On ARM64/x86-64, pointers are 8 bytes so no padding needed.
if _PTR == 4:
    _PKT_STREAM_INDEX_OFFSET = 8 + 8 + 8 + _PTR + 4  # = 32
else:
    _PKT_STREAM_INDEX_OFFSET = _PTR + 8 + 8 + _PTR + 4  # = 28 on 64-bit

# AVFrame layout (AV_NUM_DATA_POINTERS = 8):
#   data[8] (8*PTR) | linesize[8] (8*4=32) | extended_data (PTR) | width (4) | height (4) | nb_samples (4) | format (4)
_AV_NUM_DATA_POINTERS = 8
_FRAME_NB_SAMPLES_OFFSET = _AV_NUM_DATA_POINTERS * _PTR + _AV_NUM_DATA_POINTERS * 4 + _PTR + 4 + 4
_FRAME_FORMAT_OFFSET = _FRAME_NB_SAMPLES_OFFSET + 4


def _read_i32(ptr, offset):
    """Read a 32-bit signed int at ptr+offset."""
    return ctypes.c_int32.from_address(ptr + offset).value


def _read_u32(ptr, offset):
    """Read a 32-bit unsigned int at ptr+offset."""
    return ctypes.c_uint32.from_address(ptr + offset).value


def _read_i64(ptr, offset):
    """Read a 64-bit signed int at ptr+offset."""
    return ctypes.c_int64.from_address(ptr + offset).value


def _read_ptr(ptr, offset):
    """Read a pointer at ptr+offset."""
    return ctypes.c_void_p.from_address(ptr + offset).value or 0


def probe_ffmpeg():
    """Probe whether ctypes FFmpeg is available. Returns (available, log_lines)."""
    return _FFmpegLib.is_available(), _FFmpegLib.probe_log()


def get_duration(path: str) -> Optional[float]:
    """Get media duration in seconds using ctypes FFmpeg."""
    ff = _FFmpegLib.get()
    ff.avformat_network_init()

    fmt_ctx = ctypes.c_void_p(None)
    path_bytes = path.encode('utf-8') if isinstance(path, str) else path

    ret = ff.avformat_open_input(ctypes.byref(fmt_ctx), path_bytes, None, None)
    if ret < 0:
        raise KodiFFmpegError(f'avformat_open_input failed: {ret}')

    try:
        ret = ff.avformat_find_stream_info(fmt_ctx, None)
        if ret < 0:
            raise KodiFFmpegError(f'avformat_find_stream_info failed: {ret}')

        # AVFormatContext.duration is an int64_t.
        # Scan for it — it's after several pointer fields.
        # In FFmpeg 6.0, duration is typically around offset 128-192 depending
        # on pointer size and build config.  We scan a range looking for a
        # plausible duration value (> 1 second, < 24 hours in AV_TIME_BASE units).
        ctx_addr = fmt_ctx.value
        duration = None
        for off in range(0, 512, 8):
            val = _read_i64(ctx_addr, off)
            # Duration in microseconds: > 1s and < 24h
            if AV_TIME_BASE < val < 24 * 3600 * AV_TIME_BASE:
                duration = val / float(AV_TIME_BASE)
                _log(f'Found duration={duration:.1f}s at offset {off}')
                break

        return duration
    finally:
        ff.avformat_close_input(ctypes.byref(fmt_ctx))


def extract_pcm(
    path: str,
    sample_rate: int = 8000,
    start_seconds: Optional[float] = None,
    max_seconds: float = 600.0,
) -> bytes:
    """Extract mono s16le PCM audio from a video file using ctypes FFmpeg.

    Returns raw PCM bytes (16-bit signed little-endian, mono, at sample_rate Hz).
    """
    ff = _FFmpegLib.get()
    ff.avformat_network_init()

    fmt_ctx = ctypes.c_void_p(None)
    codec_ctx = ctypes.c_void_p(None)
    swr_ctx = ctypes.c_void_p(None)
    packet = ctypes.c_void_p(None)
    frame = ctypes.c_void_p(None)

    path_bytes = path.encode('utf-8') if isinstance(path, str) else path

    try:
        # Open input
        ret = ff.avformat_open_input(ctypes.byref(fmt_ctx), path_bytes, None, None)
        if ret < 0:
            raise KodiFFmpegError(f'avformat_open_input failed: {ret}')

        ret = ff.avformat_find_stream_info(fmt_ctx, None)
        if ret < 0:
            raise KodiFFmpegError(f'avformat_find_stream_info failed: {ret}')

        # Find best audio stream
        codec_ptr = ctypes.c_void_p(None)
        stream_idx = ff.av_find_best_stream(
            fmt_ctx, AVMEDIA_TYPE_AUDIO, -1, -1, ctypes.byref(codec_ptr), 0
        )
        if stream_idx < 0:
            raise KodiFFmpegError(f'No audio stream found: {stream_idx}')

        _log(f'Audio stream index: {stream_idx}')

        # Get the stream's codecpar pointer from fmt_ctx->streams[stream_idx]->codecpar
        # AVFormatContext has: streams (AVStream**) and nb_streams (unsigned int)
        # We need to find the streams array pointer.  Scan for it.
        ctx_addr = fmt_ctx.value
        nb_streams = None
        streams_ptr = None

        # nb_streams is a small integer (typically 1-10).  Search for it
        # followed by a valid pointer (streams array).
        for off in range(0, 512 - _PTR, 4):
            ns = _read_u32(ctx_addr, off)
            if 1 <= ns <= 20:
                # Check if next aligned field is a valid pointer
                ptr_off = off + 4
                # Align to pointer size
                ptr_off = (ptr_off + _PTR - 1) & ~(_PTR - 1)
                sp = _read_ptr(ctx_addr, ptr_off)
                if sp > 0x10000:  # looks like a valid pointer
                    # Verify: streams[0] should also be a valid pointer
                    s0 = _read_ptr(sp, 0)
                    if s0 > 0x10000:
                        nb_streams = ns
                        streams_ptr = sp
                        _log(f'nb_streams={ns} at offset {off}, streams at offset {ptr_off}')
                        break

        if streams_ptr is None:
            raise KodiFFmpegError('Could not locate streams array in AVFormatContext')

        # Get AVStream* for our audio stream
        stream_addr = _read_ptr(streams_ptr, stream_idx * _PTR)
        if not stream_addr:
            raise KodiFFmpegError(f'streams[{stream_idx}] is NULL')

        # AVStream.codecpar is a pointer.  In FFmpeg 6.0 it's at a known
        # offset.  Scan for it — codecpar->codec_type should == AVMEDIA_TYPE_AUDIO (1)
        # and codecpar->codec_id should be > 0.
        codecpar = None
        for off in range(0, 256, _PTR):
            cp = _read_ptr(stream_addr, off)
            if cp > 0x10000:
                # AVCodecParameters: codec_type is at offset 4 (after codec_id which is an enum/int)
                # Actually: codec_type (enum, 4 bytes) at offset 0, codec_id (enum, 4 bytes) at offset 4
                ct = _read_i32(cp, 0)
                ci = _read_i32(cp, 4)
                if ct == AVMEDIA_TYPE_AUDIO and ci > 0:
                    codecpar = cp
                    _log(f'codecpar at stream offset {off}, codec_type={ct}, codec_id={ci}')
                    break

        if not codecpar:
            raise KodiFFmpegError('Could not locate codecpar in AVStream')

        # Read codec_id and sample_rate/channels from codecpar
        codec_id = _read_i32(codecpar, 4)

        # Open decoder
        decoder = ff.avcodec_find_decoder(codec_id)
        if not decoder:
            raise KodiFFmpegError(f'No decoder for codec_id {codec_id}')

        codec_ctx = ff.avcodec_alloc_context3(decoder)
        if not codec_ctx:
            raise KodiFFmpegError('avcodec_alloc_context3 failed')

        ret = ff.avcodec_parameters_to_context(codec_ctx, codecpar)
        if ret < 0:
            raise KodiFFmpegError(f'avcodec_parameters_to_context failed: {ret}')

        ret = ff.avcodec_open2(codec_ctx, decoder, None)
        if ret < 0:
            raise KodiFFmpegError(f'avcodec_open2 failed: {ret}')

        # Read sample_rate, sample_fmt, channels from codec context.
        # After avcodec_open2, the codec context has the decoded format.
        # AAC always decodes to FLTP (8). We scan for sample_rate to anchor,
        # then read format from the first decoded frame for accuracy.
        cc_addr = codec_ctx if isinstance(codec_ctx, int) else codec_ctx.value if hasattr(codec_ctx, 'value') else int(codec_ctx)

        src_sample_rate = None
        src_channels = None
        for off in range(0, 512, 4):
            val = _read_i32(cc_addr, off)
            if val in (8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000):
                src_sample_rate = val
                # channels is usually nearby (1-8)
                for ch_off in range(max(0, off - 20), off + 20, 4):
                    cv = _read_i32(cc_addr, ch_off)
                    if 1 <= cv <= 8 and ch_off != off:
                        src_channels = cv
                        break
                break

        if not src_sample_rate:
            _log('Could not find sample_rate, defaulting to 48000')
            src_sample_rate = 48000
        if not src_channels:
            src_channels = 2

        # For sample_fmt, use FLTP (most codecs decode to float planar).
        # We'll verify from the first decoded frame.
        src_sample_fmt = AV_SAMPLE_FMT_FLTP
        _log(f'src: rate={src_sample_rate} ch={src_channels} fmt={src_sample_fmt}(FLTP)')

        # Set up resampler (SwrContext)
        swr_ctx = ff.swr_alloc()
        if not swr_ctx:
            raise KodiFFmpegError('swr_alloc failed')

        swr_addr = swr_ctx if isinstance(swr_ctx, int) else swr_ctx.value if hasattr(swr_ctx, 'value') else int(swr_ctx)

        # Set options via av_opt_set_int
        # AV_OPT_SEARCH_CHILDREN = 1
        ff.av_opt_set_int(swr_addr, b'in_channel_count', src_channels, 0)
        ff.av_opt_set_int(swr_addr, b'out_channel_count', 1, 0)
        ff.av_opt_set_int(swr_addr, b'in_sample_rate', src_sample_rate, 0)
        ff.av_opt_set_int(swr_addr, b'out_sample_rate', sample_rate, 0)
        ff.av_opt_set_sample_fmt(swr_addr, b'in_sample_fmt', src_sample_fmt, 0)
        ff.av_opt_set_sample_fmt(swr_addr, b'out_sample_fmt', AV_SAMPLE_FMT_S16, 0)

        ret = ff.swr_init(swr_addr)
        if ret < 0:
            raise KodiFFmpegError(f'swr_init failed: {ret}')

        # Seek if needed
        if start_seconds and start_seconds > 0:
            ts = int(start_seconds * AV_TIME_BASE)
            ff.av_seek_frame(fmt_ctx, -1, ts, AVSEEK_FLAG_BACKWARD)

        # Allocate packet and frame
        packet = ff.av_packet_alloc()
        frame = ff.av_frame_alloc()
        if not packet or not frame:
            raise KodiFFmpegError('Could not allocate packet/frame')

        # Decode loop
        pcm_chunks = []
        total_samples = 0
        max_samples = int(max_seconds * sample_rate)
        frames_decoded = 0
        swr_initialized = False

        # Temp buffer for resampled output
        out_buf_size = 16384 * 2  # samples * 2 bytes (s16)
        out_buf = ctypes.create_string_buffer(out_buf_size)
        out_ptr = ctypes.cast(out_buf, ctypes.c_void_p)
        out_arr = (ctypes.c_void_p * 1)(out_ptr.value)
        in_arr = (ctypes.c_void_p * 1)()

        _log(f'Decode loop: stream_idx={stream_idx}, pkt_si_offset={_PKT_STREAM_INDEX_OFFSET}, '
             f'frame_nb_samples_offset={_FRAME_NB_SAMPLES_OFFSET}, frame_fmt_offset={_FRAME_FORMAT_OFFSET}')

        packets_read = 0
        packets_matched = 0

        while total_samples < max_samples:
            ret = ff.av_read_frame(fmt_ctx, packet)
            if ret < 0:
                _log(f'av_read_frame returned {ret} after {packets_read} packets')
                break

            packets_read += 1

            # Check stream_index using computed offset
            pkt_addr = packet if isinstance(packet, int) else packet.value if hasattr(packet, 'value') else int(packet)
            pkt_stream = _read_i32(pkt_addr, _PKT_STREAM_INDEX_OFFSET)

            if pkt_stream != stream_idx:
                ff.av_packet_unref(packet)
                continue

            packets_matched += 1
            ret = ff.avcodec_send_packet(codec_ctx, packet)
            ff.av_packet_unref(packet)
            if ret < 0:
                if packets_matched <= 3:
                    _log(f'avcodec_send_packet failed: {ret} (packet #{packets_matched})')
                continue

            while True:
                ret = ff.avcodec_receive_frame(codec_ctx, frame)
                if ret < 0:
                    break

                frames_decoded += 1
                frm_addr = frame if isinstance(frame, int) else frame.value if hasattr(frame, 'value') else int(frame)

                # Read nb_samples and format at known offsets
                nb_samples = _read_i32(frm_addr, _FRAME_NB_SAMPLES_OFFSET)
                frame_fmt = _read_i32(frm_addr, _FRAME_FORMAT_OFFSET)

                # On first frame, detect actual format and reinit resampler if needed
                if frames_decoded == 1:
                    _log(f'First frame: nb_samples={nb_samples} format={frame_fmt}')
                    if frame_fmt != src_sample_fmt and 0 <= frame_fmt <= 11:
                        _log(f'Reinit resampler: fmt {src_sample_fmt} -> {frame_fmt}')
                        src_sample_fmt = frame_fmt
                        # Rebuild resampler with correct format
                        sp = ctypes.c_void_p(swr_addr)
                        ff.swr_free(ctypes.byref(sp))
                        swr_ctx = ff.swr_alloc()
                        swr_addr = swr_ctx if isinstance(swr_ctx, int) else swr_ctx.value if hasattr(swr_ctx, 'value') else int(swr_ctx)
                        ff.av_opt_set_int(swr_addr, b'in_channel_count', src_channels, 0)
                        ff.av_opt_set_int(swr_addr, b'out_channel_count', 1, 0)
                        ff.av_opt_set_int(swr_addr, b'in_sample_rate', src_sample_rate, 0)
                        ff.av_opt_set_int(swr_addr, b'out_sample_rate', sample_rate, 0)
                        ff.av_opt_set_sample_fmt(swr_addr, b'in_sample_fmt', src_sample_fmt, 0)
                        ff.av_opt_set_sample_fmt(swr_addr, b'out_sample_fmt', AV_SAMPLE_FMT_S16, 0)
                        ret2 = ff.swr_init(swr_addr)
                        if ret2 < 0:
                            _log(f'swr_init failed on reinit: {ret2}')
                    swr_initialized = True

                # AVFrame.data[] starts at offset 0 — it's an array of pointers,
                # one per channel for planar formats.  swr_convert expects
                # uint8_t** in, which is exactly &data[0].
                data0 = _read_ptr(frm_addr, 0)

                if nb_samples <= 0 or not data0:
                    ff.av_frame_unref(frame)
                    continue

                # For planar formats, pass pointer to the data[] array itself
                # (frm_addr + 0 is &data[0], which is uint8_t**)
                in_data_ptr = ctypes.cast(frm_addr, ctypes.POINTER(ctypes.c_void_p))
                out_samples = ff.swr_convert(
                    swr_addr,
                    ctypes.cast(out_arr, ctypes.POINTER(ctypes.c_void_p)),
                    16384,
                    in_data_ptr,
                    nb_samples
                )

                if out_samples > 0:
                    chunk_bytes = out_samples * 2  # s16 = 2 bytes per sample
                    pcm_chunks.append(out_buf.raw[:chunk_bytes])
                    total_samples += out_samples

                ff.av_frame_unref(frame)

        _log(f'packets_read={packets_read} packets_matched={packets_matched}')

        _log(f'Decoded {frames_decoded} frames, {total_samples} output samples ({total_samples/sample_rate:.1f}s)')
        return b''.join(pcm_chunks)

    finally:
        if frame:
            fp = ctypes.c_void_p(frame if isinstance(frame, int) else frame.value if hasattr(frame, 'value') else int(frame))
            ff.av_frame_free(ctypes.byref(fp))
        if packet:
            pp = ctypes.c_void_p(packet if isinstance(packet, int) else packet.value if hasattr(packet, 'value') else int(packet))
            ff.av_packet_free(ctypes.byref(pp))
        if swr_ctx:
            sp = ctypes.c_void_p(swr_ctx if isinstance(swr_ctx, int) else swr_ctx.value if hasattr(swr_ctx, 'value') else int(swr_ctx))
            ff.swr_free(ctypes.byref(sp))
        if codec_ctx:
            cp = ctypes.c_void_p(codec_ctx if isinstance(codec_ctx, int) else codec_ctx.value if hasattr(codec_ctx, 'value') else int(codec_ctx))
            ff.avcodec_free_context(ctypes.byref(cp))
        if fmt_ctx:
            ff.avformat_close_input(ctypes.byref(fmt_ctx))
