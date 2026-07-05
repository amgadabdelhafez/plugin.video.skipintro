import json
import re
import xbmc
import xbmcvfs
from typing import List, Dict, Union, Optional

# Try to import enzyme for MKV chapter reading (names + timestamps)
try:
    from . import enzyme
    ENZYME_AVAILABLE = True
except ImportError:
    ENZYME_AVAILABLE = False
    xbmc.log('SkipIntro: enzyme library not available', xbmc.LOGWARNING)

# Chapter name patterns for autodetect (case-insensitive)
INTRO_START_NAMES = [
    'intro',
    'opening',
    'op',
    'opening credits',
    'opening theme',
    'title sequence',
    'main title',
    'theme song',
]
INTRO_END_NAMES = ['intro end', 'intro over', 'after intro', 'post-intro',
                   'opening end', 'end opening', 'episode start',
                   'main content', 'act 1']
OUTRO_START_NAMES = ['credits', 'end credits', 'ending', 'outro',
                     'credits starting', 'ed', 'ending theme']


class ChapterManager:
    """Manages chapter detection using Kodi InfoLabels and enzyme (MKV parser).

    InfoLabels give chapter count (all platforms including Android TV).
    Enzyme reads MKV chapter names and timestamps via Kodi VFS (works with
    SMB/NFS/HTTP sources without ffmpeg).
    """

    def __init__(self):
        self._cached_chapters = {}

    def get_chapters(self) -> List[Dict[str, Union[str, int, float]]]:
        """Get chapter information. Tries enzyme for MKV files (full chapter
        data with names and timestamps), falls back to InfoLabels (count only).
        """
        try:
            if not xbmc.Player().isPlayingVideo():
                return []

            # Get the current file path via JSON-RPC
            result = json.loads(xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetItem",
                "params": {"playerid": 1, "properties": ["file"]},
                "id": 1
            })))

            current_file = None
            if 'result' in result and 'item' in result['result']:
                current_file = result['result']['item'].get('file')

            # Return cached chapters if available
            if current_file and current_file in self._cached_chapters:
                return self._cached_chapters[current_file]

            # Try enzyme for MKV files (gives names + timestamps)
            if current_file and ENZYME_AVAILABLE and self._is_mkv(current_file):
                chapters = self._get_chapters_enzyme(current_file)
                if chapters:
                    self._cached_chapters[current_file] = chapters
                    return chapters

            # Fallback: InfoLabels (count only, no names or timestamps)
            chapters = self._get_chapters_infolabels()
            if current_file and chapters:
                self._cached_chapters[current_file] = chapters
            return chapters

        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting chapters: {str(e)}', xbmc.LOGERROR)
            return []

    def _is_mkv(self, filepath: str) -> bool:
        """Check if a file is an MKV by extension."""
        return filepath.lower().rstrip('/\\').endswith(('.mkv', '.webm'))

    # Limits for enzyme parsing safety
    MAX_CHAPTERS = 100
    MAX_CHAPTER_NAME_LEN = 200

    def _get_chapters_enzyme(self, filepath: str) -> List[Dict]:
        """Parse MKV chapters using enzyme via Kodi VFS (works with SMB/NFS).

        Guarded against malicious MKV files: catches MemoryError (crafted
        element sizes), RecursionError (deeply nested EBML), and general
        exceptions (infinite loops hit the VFS EOF and raise ReadError).
        """
        try:
            xbmc.log('SkipIntro: Attempting enzyme MKV chapter parse', xbmc.LOGINFO)

            class VFSFileWrapper:
                """Wrapper to make xbmcvfs.File compatible with enzyme.
                Includes bounds checking to prevent reads/seeks past EOF.
                """
                def __init__(self, vfs_file):
                    self._file = vfs_file
                    self._size = vfs_file.size()

                def read(self, size=-1):
                    if size == -1:
                        remaining = self._size - self._file.tell()
                        if remaining <= 0:
                            return b''
                        return self._file.readBytes(remaining)
                    # Clamp read size to remaining bytes
                    remaining = self._size - self._file.tell()
                    safe_size = max(0, min(size, remaining))
                    if safe_size == 0:
                        return b''
                    return self._file.readBytes(safe_size)

                def seek(self, offset, whence=0):
                    if whence == 0 and offset > self._size:
                        offset = self._size
                    return self._file.seek(offset, whence)

                def tell(self):
                    return self._file.tell()

            vfs_file = xbmcvfs.File(filepath, 'r')
            try:
                wrapper = VFSFileWrapper(vfs_file)

                try:
                    mkv = enzyme.MKV(wrapper)
                except MemoryError:
                    xbmc.log('SkipIntro: MKV parsing aborted — file triggered memory exhaustion', xbmc.LOGWARNING)
                    return []
                except RecursionError:
                    xbmc.log('SkipIntro: MKV parsing aborted — file structure too deeply nested', xbmc.LOGWARNING)
                    return []

                if not hasattr(mkv, 'chapters') or not mkv.chapters:
                    xbmc.log('SkipIntro: enzyme parsed MKV but found no chapters', xbmc.LOGINFO)
                    return []

                chapters = []
                for i, chapter in enumerate(mkv.chapters[:self.MAX_CHAPTERS], 1):
                    start_seconds = chapter.start.total_seconds()
                    end_seconds = chapter.end.total_seconds() if chapter.end else None
                    name = chapter.string if hasattr(chapter, 'string') and chapter.string else f'Chapter {i}'
                    name = name[:self.MAX_CHAPTER_NAME_LEN]

                    chapters.append({
                        'name': name,
                        'time': start_seconds,
                        'end_time': end_seconds,
                        'number': i
                    })

                xbmc.log(f'SkipIntro: enzyme found {len(chapters)} chapters with names', xbmc.LOGINFO)
                for ch in chapters:
                    xbmc.log(f'  Ch {ch["number"]}: "{ch["name"]}" at {ch["time"]:.1f}s', xbmc.LOGINFO)
                return chapters

            finally:
                vfs_file.close()

        except Exception as e:
            xbmc.log(f'SkipIntro: enzyme chapter parse failed: {str(e)}', xbmc.LOGWARNING)
            return []

    def _get_chapters_infolabels(self) -> List[Dict]:
        """Get chapter count via Kodi InfoLabels (no names or timestamps)."""
        try:
            count_str = xbmc.getInfoLabel('Player.ChapterCount')
            chapter_count = int(count_str) if count_str and count_str.isdigit() else 0

            if chapter_count == 0:
                return []

            xbmc.log(f'SkipIntro: Found {chapter_count} chapters via InfoLabels', xbmc.LOGINFO)
            return [{'number': i + 1, 'name': f'Chapter {i + 1}'} for i in range(chapter_count)]

        except Exception as e:
            xbmc.log(f'SkipIntro: Error reading InfoLabel chapters: {str(e)}', xbmc.LOGERROR)
            return []

    # --- Autodetect methods ---

    def autodetect_intro(self, chapters: List[Dict]) -> Optional[Dict]:
        """Detect intro start/end from chapter names.

        Returns a dict with chapter numbers and timestamps if intro is found:
            {
                'intro_start_chapter': int,
                'intro_end_chapter': int,
                'intro_start_time': float,
                'intro_end_time': float,
                'outro_start_chapter': int or None,
                'outro_start_time': float or None,
                'source': 'autodetect'
            }
        Returns None if no intro pattern is detected.
        """
        if not chapters:
            return None

        intro_start = None
        intro_end = None
        outro_start = None

        for ch in chapters:
            name = ch.get('name', '').lower().strip()
            if not name:
                continue

            is_intro_end = self._matches_any(name, INTRO_END_NAMES)
            is_intro_start = self._matches_any(name, INTRO_START_NAMES) and not is_intro_end

            # Look for intro end first (most reliable signal)
            if not intro_end and is_intro_end:
                intro_end = ch

            # Look for intro start
            if not intro_start and is_intro_start:
                intro_start = ch

            # Look for outro/credits. "Opening Credits" should stay intro-only.
            if not outro_start and not is_intro_start and self._matches_any(name, OUTRO_START_NAMES):
                outro_start = ch

        # Build result
        if intro_end:
            # We have a clear intro end marker
            result = {
                'intro_end_chapter': intro_end['number'],
                'intro_end_time': intro_end.get('time'),
                'source': 'autodetect'
            }

            if intro_start:
                result['intro_start_chapter'] = intro_start['number']
                result['intro_start_time'] = intro_start.get('time')
            else:
                # No explicit start — assume first chapter is intro start
                result['intro_start_chapter'] = 1
                result['intro_start_time'] = chapters[0].get('time', 0)

            if outro_start:
                result['outro_start_chapter'] = outro_start['number']
                result['outro_start_time'] = outro_start.get('time')
            else:
                result['outro_start_chapter'] = None
                result['outro_start_time'] = None

            xbmc.log(f'SkipIntro: Autodetected intro: chapters {result["intro_start_chapter"]}→{result["intro_end_chapter"]}', xbmc.LOGINFO)
            return result

        # No "intro end" found, but if we have an "intro" chapter,
        # the NEXT chapter is likely the end
        if intro_start:
            next_idx = intro_start['number']  # 1-based, so this is the next
            if next_idx < len(chapters):
                next_ch = chapters[next_idx]
                result = {
                    'intro_start_chapter': intro_start['number'],
                    'intro_start_time': intro_start.get('time'),
                    'intro_end_chapter': next_ch['number'],
                    'intro_end_time': next_ch.get('time'),
                    'outro_start_chapter': outro_start['number'] if outro_start else None,
                    'outro_start_time': outro_start.get('time') if outro_start else None,
                    'source': 'autodetect'
                }
                xbmc.log(f'SkipIntro: Autodetected intro (by next chapter): chapters {result["intro_start_chapter"]}→{result["intro_end_chapter"]}', xbmc.LOGINFO)
                return result
            if intro_start.get('end_time') is not None:
                result = {
                    'intro_start_chapter': intro_start['number'],
                    'intro_start_time': intro_start.get('time'),
                    'intro_end_chapter': intro_start['number'],
                    'intro_end_time': intro_start.get('end_time'),
                    'outro_start_chapter': outro_start['number'] if outro_start else None,
                    'outro_start_time': outro_start.get('time') if outro_start else None,
                    'source': 'autodetect'
                }
                xbmc.log(f'SkipIntro: Autodetected intro (by chapter end time): chapter {result["intro_start_chapter"]}', xbmc.LOGINFO)
                return result

        return None

    @staticmethod
    def _matches_any(text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the patterns (case-insensitive)."""
        normalized = re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()
        tokens = set(normalized.split())
        for pattern in patterns:
            normalized_pattern = re.sub(r'[^a-z0-9]+', ' ', pattern.lower()).strip()
            if not normalized_pattern:
                continue
            if len(normalized_pattern) <= 3:
                if normalized_pattern in tokens:
                    return True
                continue
            if f' {normalized_pattern} ' in f' {normalized} ':
                return True
        return False

    # --- Utility methods ---

    def get_chapter_by_number(self, chapters, chapter_number):
        """Get chapter info by chapter number."""
        if not chapters or chapter_number is None:
            return None
        for chapter in chapters:
            if chapter['number'] == chapter_number:
                return chapter
        return None

    def get_intro_chapters(self, chapters, start_chapter, end_chapter):
        """Get intro start and end chapters based on configured chapter numbers."""
        if not chapters or end_chapter is None:
            return None, None

        start = self.get_chapter_by_number(chapters, start_chapter if start_chapter else 1)
        if not start and start_chapter:
            return None, None

        end = self.get_chapter_by_number(chapters, end_chapter)
        if not end:
            return None, None

        return start, end

    def get_outro_chapter(self, chapters, outro_chapter):
        """Get outro chapter based on configured chapter number."""
        if not chapters or outro_chapter is None:
            return None
        return self.get_chapter_by_number(chapters, outro_chapter)

    @staticmethod
    def find_chapter_by_name(chapters, name):
        """Find a chapter by name (case-insensitive partial match)."""
        if not chapters or not name:
            return None
        name_lower = name.lower()
        for chapter in chapters:
            if name_lower in chapter.get('name', '').lower():
                return chapter
        return None
