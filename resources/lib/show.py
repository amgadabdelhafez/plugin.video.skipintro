import xbmc
from resources.lib.metadata import ShowMetadata
from resources.lib.database import ShowDatabase

class ShowManager:
    def __init__(self, database_path=None):
        self.metadata = ShowMetadata()
        self.db = ShowDatabase(database_path) if database_path else None
        self.current_show = None

    def detect_show(self):
        """Detect current TV show and episode"""
        xbmc.log('SkipIntro: Attempting to detect show info...', xbmc.LOGINFO)
        self.current_show = self.metadata.get_show_info()
        if self.current_show:
            xbmc.log('SkipIntro: Detected show: {}'.format(self.current_show), xbmc.LOGINFO)
        else:
            xbmc.log('SkipIntro: Could not detect show info', xbmc.LOGWARNING)
        return self.current_show

    def save_intro_time(self, intro_start, intro_duration, source='manual'):
        """Save intro time to database"""
        if not self.db or not self.current_show:
            return False

        try:
            show_id = self.db.get_show(self.current_show['title'])
            times = {
                'intro_start_time': intro_start,
                'intro_end_time': intro_start + intro_duration,
                'intro_start_chapter': None,
                'intro_end_chapter': None,
                'outro_start_chapter': None,
                'outro_start_time': None,
                'source': source
            }
            self.db.save_episode_times(
                show_id,
                self.current_show['season'],
                self.current_show['episode'],
                times
            )
            return True
        except Exception as e:
            xbmc.log('SkipIntro: Error saving intro time: {}'.format(str(e)), xbmc.LOGERROR)
            return False

    def get_saved_times(self):
        """Get saved intro/outro times for current episode"""
        if not self.db or not self.current_show:
            return None

        try:
            show_id = self.db.get_show(self.current_show['title'])
            if not show_id:
                return None

            return self.db.get_episode_times(
                show_id,
                self.current_show['season'],
                self.current_show['episode']
            )
        except Exception as e:
            xbmc.log('SkipIntro: Error getting saved times: {}'.format(str(e)), xbmc.LOGERROR)
            return None
