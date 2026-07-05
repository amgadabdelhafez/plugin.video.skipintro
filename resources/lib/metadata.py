import re
import json
from urllib.parse import urlsplit, urlunsplit
import xbmc
import xbmcvfs


def sanitize_path(path):
    """Remove credentials and URL tokens from paths before logging."""
    value = str(path)
    try:
        parts = urlsplit(value)
    except Exception:
        parts = None

    if parts and parts.scheme and (parts.netloc or value.startswith(parts.scheme + '://')):
        netloc = parts.netloc
        if '@' in netloc:
            host = netloc.rsplit('@', 1)[1]
            netloc = f'***:***@{host}'
        return urlunsplit((parts.scheme, netloc, parts.path, '', ''))

    return re.split(r'[?#]', value, maxsplit=1)[0]


def safe_basename(path):
    """Get filename from a path, handling both native and network (smb://) paths.

    os.path.basename fails on Windows for network URLs because it splits
    on backslash only. This splits on both / and \\ for cross-platform safety.
    """
    safe_path = sanitize_path(path)
    return safe_path.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]

class ShowMetadata:
    def __init__(self):
        self.show_regex = re.compile(r'^(.*?)(?:s(\d{1,2})e(\d{1,2})|(\d{1,2})x(\d{1,2}))', re.IGNORECASE)

    def get_show_info(self):
        """Extract show information from currently playing video"""
        try:
            # Try to get info from Kodi's video info labels first
            title = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
            season = xbmc.getInfoLabel('VideoPlayer.Season')
            episode = xbmc.getInfoLabel('VideoPlayer.Episode')

            xbmc.log(f'SkipIntro: Video info labels - Title: {title}, Season: {season}, Episode: {episode}', xbmc.LOGINFO)

            # If we got all info from Kodi, return it
            if title and season and episode:
                try:
                    season = int(season)
                    episode = int(episode)
                    xbmc.log(f'SkipIntro: Found show info from Kodi labels - {title} S{season:02d}E{episode:02d}', xbmc.LOGINFO)
                    return {'title': title, 'season': season, 'episode': episode}
                except ValueError as e:
                    xbmc.log(f'SkipIntro: Error converting season/episode numbers: {str(e)}', xbmc.LOGWARNING)
                    pass

            # Fall back to filename parsing
            filename = self._get_filename()
            if not filename:
                xbmc.log('SkipIntro: No filename available for parsing', xbmc.LOGWARNING)
                return None

            xbmc.log(f'SkipIntro: Attempting to parse filename: {sanitize_path(filename)}', xbmc.LOGINFO)
            return self._parse_filename(filename)

        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show info: {str(e)}', xbmc.LOGERROR)
            return None

    def _get_filename(self):
        """Get filename of currently playing video"""
        try:
            if xbmc.Player().isPlaying():
                return xbmc.Player().getPlayingFile()
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting filename: {str(e)}', xbmc.LOGERROR)
        return None

    def _parse_filename(self, filename):
        """Parse show information from filename"""
        try:
            # Get just the filename without path — handle both native and network paths
            # Network paths (smb://...) won't translate properly, so split on both separators
            basename = safe_basename(filename)
            xbmc.log(f'SkipIntro: Parsing basename: {basename}', xbmc.LOGINFO)

            # Try to match show pattern
            match = self.show_regex.search(basename)
            if match:
                groups = match.groups()
                title = groups[0].replace('.', ' ').strip()
                
                # Handle both SxxExx and xxXxx formats
                season = int(groups[1] or groups[3])
                episode = int(groups[2] or groups[4])

                result = {
                    'title': title,
                    'season': season,
                    'episode': episode
                }
                xbmc.log(f'SkipIntro: Successfully parsed filename - {title} S{season:02d}E{episode:02d}', xbmc.LOGINFO)
                return result
        except Exception as e:
            xbmc.log(f'SkipIntro: Error parsing filename: {str(e)}', xbmc.LOGERROR)

        return None

    def get_chapters(self):
        """Get chapter information for currently playing video using InfoLabels.

        Works on all platforms including Android TV where JSON-RPC
        Player.GetProperties doesn't expose chapter fields.
        """
        try:
            if not xbmc.Player().isPlayingVideo():
                xbmc.log('SkipIntro: No video playing to get chapters from', xbmc.LOGWARNING)
                return []

            count_str = xbmc.getInfoLabel('Player.ChapterCount')
            chapter_count = int(count_str) if count_str and count_str.isdigit() else 0

            if chapter_count == 0:
                xbmc.log('SkipIntro: Video has no chapters', xbmc.LOGWARNING)
                return []

            xbmc.log(f'SkipIntro: Found {chapter_count} chapters via InfoLabels', xbmc.LOGINFO)
            return [{'number': i + 1} for i in range(chapter_count)]

        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting chapters: {str(e)}', xbmc.LOGERROR)
            return []
