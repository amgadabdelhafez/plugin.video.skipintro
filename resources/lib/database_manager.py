import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import os
import shutil
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from resources.lib.database import ShowDatabase
from resources.lib.metadata import sanitize_path


class DatabaseManager:
    """Handles database backup, restore, import, and export operations"""

    def __init__(self, addon_id=None):
        # Accept explicit addon ID for RunScript context
        if addon_id:
            self.addon = xbmcaddon.Addon(addon_id)
        else:
            self.addon = xbmcaddon.Addon()

        self.addon_data_path = xbmcvfs.translatePath(
            'special://userdata/addon_data/plugin.video.skipintro/'
        )
        # Database path is now fixed (not user-configurable)
        self.db_path = xbmcvfs.translatePath(
            'special://userdata/addon_data/plugin.video.skipintro/shows.db'
        )

        # Ensure addon data directory exists
        if not xbmcvfs.exists(self.addon_data_path):
            xbmcvfs.mkdirs(self.addon_data_path)

    @staticmethod
    def _vfs_join(directory, filename):
        """Join paths without breaking Kodi URL-style VFS paths."""
        directory = str(directory or '')
        filename = str(filename or '').replace('\\', '/').rsplit('/', 1)[-1]
        if '://' in directory:
            return directory.rstrip('/\\') + '/' + filename
        return os.path.join(directory, filename)

    @staticmethod
    def _is_safe_int(value):
        return isinstance(value, int) and not isinstance(value, bool)

    @staticmethod
    def _is_safe_number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @staticmethod
    def _validate_import_config(config):
        """Validate and sanitize imported config values to prevent bad data in DB."""
        if not isinstance(config, dict):
            return None
        clean = {}
        for key in ['intro_start_chapter', 'intro_end_chapter', 'outro_start_chapter']:
            val = config.get(key)
            if val is not None:
                if DatabaseManager._is_safe_int(val) and 0 < val < 10000:
                    clean[key] = val
                else:
                    clean[key] = None
            else:
                clean[key] = None
        for key in ['intro_start_time', 'intro_end_time', 'outro_start_time']:
            val = config.get(key)
            if val is not None:
                if DatabaseManager._is_safe_number(val) and 0 <= val <= 86400:
                    clean[key] = float(val)
                else:
                    clean[key] = None
            else:
                clean[key] = None
        intro_duration = config.get('intro_duration')
        if intro_duration is not None:
            if DatabaseManager._is_safe_number(intro_duration) and 0 <= intro_duration <= 86400:
                clean['intro_duration'] = int(intro_duration)
            else:
                clean['intro_duration'] = None
        else:
            clean['intro_duration'] = None
        clean['use_chapters'] = bool(config.get('use_chapters', False))
        clean['config_created_at'] = config.get('config_created_at')
        return clean

    @staticmethod
    def _validate_import_episode(episode):
        """Validate and sanitize imported episode override values."""
        if not isinstance(episode, dict):
            return None
        season = episode.get('season')
        episode_number = episode.get('episode')
        if not DatabaseManager._is_safe_int(season) or season < 0 or season > 10000:
            return None
        if not DatabaseManager._is_safe_int(episode_number) or episode_number < 0 or episode_number > 10000:
            return None

        clean = {
            'season': season,
            'episode': episode_number,
            'source': episode.get('source') if isinstance(episode.get('source'), str) else None,
            'created_at': episode.get('created_at')
        }
        for key in ['intro_start_chapter', 'intro_end_chapter', 'outro_start_chapter']:
            val = episode.get(key)
            if val is not None:
                clean[key] = val if DatabaseManager._is_safe_int(val) and 0 < val < 10000 else None
            else:
                clean[key] = None
        for key in ['intro_start_time', 'intro_end_time', 'outro_start_time']:
            val = episode.get(key)
            if val is not None:
                clean[key] = float(val) if DatabaseManager._is_safe_number(val) and 0 <= val <= 86400 else None
            else:
                clean[key] = None
        return clean

    def _get_backup_restore_path(self):
        """Get backup/restore path from settings, with fallback to default"""
        custom_path = self.addon.getSetting('backup_restore_path')
        xbmc.log(f'SkipIntro: backup_restore_path setting = "{sanitize_path(custom_path)}"', xbmc.LOGINFO)

        if custom_path and custom_path.strip():
            path = xbmcvfs.translatePath(custom_path)
            if '://' in path:
                parts = urlsplit(path)
                path = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
            xbmc.log(f'SkipIntro: Using custom backup path: {sanitize_path(path)}', xbmc.LOGINFO)
            # Ensure path ends with separator
            if not path.endswith(('/', '\\')):
                path += '/' if '://' in path else os.sep
            return path

        xbmc.log(f'SkipIntro: Using default backup path: {sanitize_path(self.addon_data_path)}', xbmc.LOGINFO)
        return self.addon_data_path

    def backup_database(self):
        """Create a backup of the database with timestamp"""
        try:
            if not xbmcvfs.exists(self.db_path):
                xbmcgui.Dialog().notification(
                    'Skip Intro',
                    'No database found to backup',
                    xbmcgui.NOTIFICATION_WARNING
                )
                return False

            # Get backup/restore directory from settings
            backup_dir = self._get_backup_restore_path()

            # Create backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'shows_backup_{timestamp}.db'
            backup_path = self._vfs_join(backup_dir, backup_filename)

            # Copy database file
            if xbmcvfs.copy(self.db_path, backup_path):
                xbmc.log(f'SkipIntro: Database backed up to {sanitize_path(backup_path)}', xbmc.LOGINFO)
                xbmcgui.Dialog().notification(
                    'Skip Intro',
                    f'Database backed up successfully',
                    xbmcgui.NOTIFICATION_INFO,
                    5000
                )
                return True
            else:
                raise Exception('Failed to copy database file')

        except Exception as e:
            xbmc.log(f'SkipIntro: Backup failed: {str(e)}', xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                'Skip Intro',
                f'Backup failed: {str(e)}',
                xbmcgui.NOTIFICATION_ERROR
            )
            return False

    def restore_database(self):
        """Restore database from a backup file"""
        try:
            dialog = xbmcgui.Dialog()

            # Get backup/restore directory from settings
            restore_dir = self._get_backup_restore_path()

            # Let user browse for backup file (type 1 = ShowAndGetFile, 'files' allows SMB/NFS)
            backup_file = dialog.browse(
                1,  # Type: ShowAndGetFile
                'Select backup file to restore',
                'files',
                '.db',
                False,
                False,
                restore_dir
            )

            if not backup_file:
                return False

            # Confirm restore action
            if not dialog.yesno(
                'Restore Database',
                'This will replace your current database.',
                'All current show configurations will be lost.',
                'Are you sure you want to continue?'
            ):
                return False

            # Backup current database before restoring
            if xbmcvfs.exists(self.db_path):
                current_backup = self.db_path + '.before_restore'
                xbmcvfs.copy(self.db_path, current_backup)
                xbmc.log(f'SkipIntro: Current database backed up to {sanitize_path(current_backup)}', xbmc.LOGINFO)

            # Restore from backup
            if xbmcvfs.copy(backup_file, self.db_path):
                xbmc.log(f'SkipIntro: Database restored from {sanitize_path(backup_file)}', xbmc.LOGINFO)
                dialog.notification(
                    'Skip Intro',
                    'Database restored successfully',
                    xbmcgui.NOTIFICATION_INFO,
                    5000
                )
                return True
            else:
                raise Exception('Failed to copy backup file')

        except Exception as e:
            xbmc.log(f'SkipIntro: Restore failed: {str(e)}', xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                'Skip Intro',
                f'Restore failed: {str(e)}',
                xbmcgui.NOTIFICATION_ERROR
            )
            return False

    def export_to_json(self):
        """Export database contents to JSON file"""
        try:
            if not xbmcvfs.exists(self.db_path):
                xbmcgui.Dialog().notification(
                    'Skip Intro',
                    'No database found to export',
                    xbmcgui.NOTIFICATION_WARNING
                )
                return False

            # Get all data from database
            db = ShowDatabase(self.db_path)

            # Query all shows and their configurations
            conn = db._get_connection()
            cursor = conn.cursor()

            # Get shows with their configurations
            cursor.execute("""
                SELECT
                    s.id, s.title, s.created_at,
                    c.use_chapters, c.intro_start_chapter, c.intro_end_chapter, c.outro_start_chapter,
                    c.intro_duration, c.intro_start_time, c.intro_end_time, c.outro_start_time,
                    c.created_at as config_created_at
                FROM shows s
                LEFT JOIN shows_config c ON s.id = c.show_id
                ORDER BY s.title
            """)

            shows_data = []
            for row in cursor.fetchall():
                show_data = {
                    'id': row[0],
                    'title': row[1],
                    'created_at': row[2],
                    'config': {
                        'use_chapters': bool(row[3]) if row[3] is not None else None,
                        'intro_start_chapter': row[4],
                        'intro_end_chapter': row[5],
                        'outro_start_chapter': row[6],
                        'intro_duration': row[7],
                        'intro_start_time': row[8],
                        'intro_end_time': row[9],
                        'outro_start_time': row[10],
                        'config_created_at': row[11]
                    } if row[3] is not None else None
                }

                cursor.execute("""
                    SELECT season, episode, intro_start_chapter, intro_end_chapter, outro_start_chapter,
                           intro_start_time, intro_end_time, outro_start_time, source, created_at
                    FROM episodes
                    WHERE show_id = ?
                    ORDER BY season, episode
                """, (row[0],))
                show_data['episodes'] = [
                    {
                        'season': ep[0],
                        'episode': ep[1],
                        'intro_start_chapter': ep[2],
                        'intro_end_chapter': ep[3],
                        'outro_start_chapter': ep[4],
                        'intro_start_time': ep[5],
                        'intro_end_time': ep[6],
                        'outro_start_time': ep[7],
                        'source': ep[8],
                        'created_at': ep[9]
                    }
                    for ep in cursor.fetchall()
                ]
                shows_data.append(show_data)

            conn.close()

            # Get backup/restore directory from settings
            export_dir = self._get_backup_restore_path()

            # Create export filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_filename = f'skipintro_export_{timestamp}.json'
            export_path = self._vfs_join(export_dir, export_filename)

            # Write JSON file
            json_data = {
                'version': '1.0',
                'exported_at': timestamp,
                'shows_count': len(shows_data),
                'shows': shows_data
            }

            # Use xbmcvfs.File for SMB/NFS support
            json_content = json.dumps(json_data, indent=2, ensure_ascii=False)
            vfs_file = xbmcvfs.File(export_path, 'w')
            try:
                vfs_file.write(json_content)
            finally:
                vfs_file.close()

            xbmc.log(f'SkipIntro: Database exported to {sanitize_path(export_path)}', xbmc.LOGINFO)
            xbmcgui.Dialog().notification(
                'Skip Intro',
                f'Exported {len(shows_data)} shows to JSON',
                xbmcgui.NOTIFICATION_INFO,
                5000
            )
            return True

        except Exception as e:
            xbmc.log(f'SkipIntro: Export failed: {str(e)}', xbmc.LOGERROR)
            import traceback
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                'Skip Intro',
                f'Export failed: {str(e)}',
                xbmcgui.NOTIFICATION_ERROR
            )
            return False

    def import_from_json(self):
        """Import database contents from JSON file"""
        try:
            dialog = xbmcgui.Dialog()

            # Get backup/restore directory from settings
            import_dir = self._get_backup_restore_path()

            # Let user browse for JSON file (type 1 = ShowAndGetFile, 'files' allows SMB/NFS)
            json_file = dialog.browse(
                1,  # Type: ShowAndGetFile
                'Select JSON file to import',
                'files',
                '.json',
                False,
                False,
                import_dir
            )

            if not json_file:
                return False

            # Read JSON file with size limit to prevent memory exhaustion
            MAX_IMPORT_SIZE = 10 * 1024 * 1024  # 10MB
            MAX_IMPORT_SHOWS = 5000

            vfs_file = xbmcvfs.File(json_file, 'r')
            try:
                file_size = vfs_file.size()
                if file_size > MAX_IMPORT_SIZE:
                    dialog.notification('Skip Intro', 'Import file too large (max 10MB)', xbmcgui.NOTIFICATION_ERROR)
                    return False
                json_content = vfs_file.read()
                # xbmcvfs.File.read() may return bytes on some Kodi versions
                if isinstance(json_content, bytes):
                    json_content = json_content.decode('utf-8')
                json_data = json.loads(json_content)
            finally:
                vfs_file.close()

            shows_data = json_data.get('shows', [])
            if len(shows_data) > MAX_IMPORT_SHOWS:
                dialog.notification(
                    'Skip Intro',
                    f'Import rejected: {len(shows_data)} shows exceeds {MAX_IMPORT_SHOWS} limit',
                    xbmcgui.NOTIFICATION_ERROR
                )
                xbmc.log(f'SkipIntro: Import rejected — {len(shows_data)} shows exceeds limit of {MAX_IMPORT_SHOWS}', xbmc.LOGWARNING)
                return False
            if not shows_data:
                dialog.notification(
                    'Skip Intro',
                    'No show data found in JSON file',
                    xbmcgui.NOTIFICATION_WARNING
                )
                return False

            # Ask user about import mode
            import_mode = dialog.select(
                'Import Mode',
                [
                    'Merge (keep existing, add new)',
                    'Replace (clear database, import all)'
                ]
            )

            if import_mode == -1:
                return False

            # Confirm import action
            action_text = 'merge with' if import_mode == 0 else 'replace'
            if not dialog.yesno(
                'Import Database',
                f'This will {action_text} your current database.',
                f'Import {len(shows_data)} shows from JSON?'
            ):
                return False

            # Perform import
            db = ShowDatabase(self.db_path)

            if import_mode == 1:  # Replace mode
                # Clear existing data
                conn = db._get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM episodes')
                cursor.execute('DELETE FROM shows_config')
                cursor.execute('DELETE FROM shows')
                conn.commit()
                conn.close()
                xbmc.log('SkipIntro: Cleared existing database for replace mode', xbmc.LOGINFO)

            # Import shows
            imported_count = 0
            skipped_count = 0

            conn = db._get_connection()
            cursor = conn.cursor()

            for show_data in shows_data:
                try:
                    title = show_data.get('title', '')
                    if not isinstance(title, str) or not title.strip() or len(title) > 500:
                        xbmc.log('SkipIntro: Skipping import entry - invalid title', xbmc.LOGWARNING)
                        skipped_count += 1
                        continue
                    title = title.strip()

                    config = show_data.get('config')
                    if config:
                        config = self._validate_import_config(config)
                    show_created_at = show_data.get('created_at')

                    if not config:
                        xbmc.log(f'SkipIntro: Skipping {title} - no config', xbmc.LOGDEBUG)
                        skipped_count += 1
                        continue

                    # Check if show exists (in merge mode)
                    if import_mode == 0:  # Merge mode
                        cursor.execute('SELECT id FROM shows WHERE title = ?', (title,))
                        existing_show = cursor.fetchone()
                        if existing_show:
                            show_id = existing_show[0]
                            cursor.execute('SELECT show_id FROM shows_config WHERE show_id = ?', (show_id,))
                            if cursor.fetchone():
                                xbmc.log(f'SkipIntro: Skipping {title} - already configured', xbmc.LOGDEBUG)
                                skipped_count += 1
                                continue

                    # Insert or update show with original timestamp
                    cursor.execute('SELECT id FROM shows WHERE title = ?', (title,))
                    existing_show = cursor.fetchone()

                    if existing_show:
                        show_id = existing_show[0]
                        # Update existing show timestamp if provided
                        if show_created_at:
                            cursor.execute(
                                'UPDATE shows SET created_at = ? WHERE id = ?',
                                (show_created_at, show_id)
                            )
                    else:
                        # Insert new show with original timestamp
                        if show_created_at:
                            cursor.execute(
                                'INSERT INTO shows (title, created_at) VALUES (?, ?)',
                                (title, show_created_at)
                            )
                        else:
                            cursor.execute(
                                'INSERT INTO shows (title) VALUES (?)',
                                (title,)
                            )
                        show_id = cursor.lastrowid

                    # Save configuration with original timestamp
                    config_created_at = config.get('config_created_at')

                    if config.get('use_chapters'):
                        if config_created_at:
                            cursor.execute('''
                                INSERT OR REPLACE INTO shows_config
                                (show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter, intro_duration,
                                 intro_start_time, intro_end_time, outro_start_time, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                show_id,
                                True,
                                config.get('intro_start_chapter'),
                                config.get('intro_end_chapter'),
                                config.get('outro_start_chapter'),
                                config.get('intro_duration'),
                                config.get('intro_start_time'),
                                config.get('intro_end_time'),
                                config.get('outro_start_time'),
                                config_created_at
                            ))
                        else:
                            cursor.execute('''
                                INSERT OR REPLACE INTO shows_config
                                (show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter, intro_duration,
                                 intro_start_time, intro_end_time, outro_start_time)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                show_id,
                                True,
                                config.get('intro_start_chapter'),
                                config.get('intro_end_chapter'),
                                config.get('outro_start_chapter'),
                                config.get('intro_duration'),
                                config.get('intro_start_time'),
                                config.get('intro_end_time'),
                                config.get('outro_start_time')
                            ))
                    else:
                        if config_created_at:
                            cursor.execute('''
                                INSERT OR REPLACE INTO shows_config
                                (show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter,
                                 intro_start_time, intro_end_time, outro_start_time, created_at)
                                VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
                            ''', (
                                show_id,
                                False,
                                config.get('intro_start_time'),
                                config.get('intro_end_time'),
                                config.get('outro_start_time'),
                                config_created_at
                            ))
                        else:
                            cursor.execute('''
                                INSERT OR REPLACE INTO shows_config
                                (show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter,
                                 intro_start_time, intro_end_time, outro_start_time)
                                VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?)
                            ''', (
                                show_id,
                                False,
                                config.get('intro_start_time'),
                                config.get('intro_end_time'),
                                config.get('outro_start_time')
                            ))

                    episodes = show_data.get('episodes', [])
                    if isinstance(episodes, list):
                        for episode_data in episodes[:5000]:
                            episode_config = self._validate_import_episode(episode_data)
                            if not episode_config:
                                skipped_count += 1
                                continue
                            if episode_config.get('created_at'):
                                cursor.execute('''
                                    INSERT OR REPLACE INTO episodes
                                    (show_id, season, episode, intro_start_chapter, intro_end_chapter, outro_start_chapter,
                                     intro_start_time, intro_end_time, outro_start_time, source, created_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    show_id,
                                    episode_config.get('season'),
                                    episode_config.get('episode'),
                                    episode_config.get('intro_start_chapter'),
                                    episode_config.get('intro_end_chapter'),
                                    episode_config.get('outro_start_chapter'),
                                    episode_config.get('intro_start_time'),
                                    episode_config.get('intro_end_time'),
                                    episode_config.get('outro_start_time'),
                                    episode_config.get('source'),
                                    episode_config.get('created_at')
                                ))
                            else:
                                cursor.execute('''
                                    INSERT OR REPLACE INTO episodes
                                    (show_id, season, episode, intro_start_chapter, intro_end_chapter, outro_start_chapter,
                                     intro_start_time, intro_end_time, outro_start_time, source)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    show_id,
                                    episode_config.get('season'),
                                    episode_config.get('episode'),
                                    episode_config.get('intro_start_chapter'),
                                    episode_config.get('intro_end_chapter'),
                                    episode_config.get('outro_start_chapter'),
                                    episode_config.get('intro_start_time'),
                                    episode_config.get('intro_end_time'),
                                    episode_config.get('outro_start_time'),
                                    episode_config.get('source')
                                ))

                    imported_count += 1
                    xbmc.log(f'SkipIntro: Imported {title}', xbmc.LOGDEBUG)

                except Exception as e:
                    xbmc.log(f'SkipIntro: Failed to import show {show_data.get("title")}: {str(e)}', xbmc.LOGERROR)
                    import traceback
                    xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
                    continue

            conn.commit()
            conn.close()

            xbmc.log(f'SkipIntro: Import complete - {imported_count} imported, {skipped_count} skipped', xbmc.LOGINFO)
            dialog.notification(
                'Skip Intro',
                f'Imported {imported_count} shows ({skipped_count} skipped)',
                xbmcgui.NOTIFICATION_INFO,
                5000
            )
            return True

        except Exception as e:
            xbmc.log(f'SkipIntro: Import failed: {str(e)}', xbmc.LOGERROR)
            import traceback
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
            xbmcgui.Dialog().notification(
                'Skip Intro',
                f'Import failed: {str(e)}',
                xbmcgui.NOTIFICATION_ERROR
            )
            return False
