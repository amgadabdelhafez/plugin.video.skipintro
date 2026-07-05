import sqlite3
import os
import xbmc
import xbmcvfs
import traceback

class ShowDatabase:
    def __init__(self, db_path):
        """Initialize database connection.

        Note: For :memory: databases, we keep a persistent connection.
        For file databases, we use context managers for each operation.
        """
        try:
            self.db_path = db_path
            self._persistent_conn = None
            xbmc.log(f'SkipIntro: Initializing database at: {db_path}', xbmc.LOGINFO)

            # For :memory: databases, create a persistent connection
            if db_path == ':memory:':
                self._persistent_conn = sqlite3.connect(':memory:')
                xbmc.log('SkipIntro: Created persistent in-memory database connection', xbmc.LOGINFO)
            else:
                # Ensure directory exists for file databases
                db_dir = os.path.dirname(db_path)
                if db_dir and not xbmcvfs.exists(db_dir):
                    xbmcvfs.mkdirs(db_dir)
                    xbmc.log(f'SkipIntro: Created database directory', xbmc.LOGINFO)

            # Always create tables and migrate database
            self._create_tables()
            self._migrate_database()
            xbmc.log('SkipIntro: Database initialized and migrated', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log(f'SkipIntro: Database initialization error: {str(e)}', xbmc.LOGERROR)
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
            raise

    def _get_connection(self):
        """Get database connection (persistent for :memory:, new for files)."""
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)

    def _execute_with_conn(self, func):
        """Execute a function with a database connection, handling both persistent and file DBs."""
        conn = self._get_connection()
        needs_close = (not self._persistent_conn)
        try:
            result = func(conn)
            conn.commit()
            return result
        finally:
            if needs_close:
                conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close persistent connection if exists."""
        self.close()
        return False

    def close(self):
        """Close persistent connection if exists."""
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None

    def _migrate_database(self):
        """Migrate database to current schema"""
        try:
            conn = self._get_connection()
            needs_close = (not self._persistent_conn)
            try:
                c = conn.cursor()

                # Migrate shows table (must come first as it's referenced by others)
                self._migrate_table(c, 'shows', {
                    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
                    'title': 'TEXT NOT NULL',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                })

                # Migrate shows_config table
                self._migrate_table(c, 'shows_config', {
                    'show_id': 'INTEGER PRIMARY KEY',
                    'use_chapters': 'BOOLEAN DEFAULT 0',
                    'intro_start_chapter': 'INTEGER',
                    'intro_end_chapter': 'INTEGER',
                    'outro_start_chapter': 'INTEGER',
                    'intro_duration': 'INTEGER',
                    'intro_start_time': 'REAL',
                    'intro_end_time': 'REAL',
                    'outro_start_time': 'REAL',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }, 'FOREIGN KEY (show_id) REFERENCES shows(id)')

                # Migrate episodes table
                self._migrate_table(c, 'episodes', {
                    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
                    'show_id': 'INTEGER',
                    'season': 'INTEGER',
                    'episode': 'INTEGER',
                    'intro_start_chapter': 'INTEGER',
                    'intro_end_chapter': 'INTEGER',
                    'outro_start_chapter': 'INTEGER',
                    'intro_start_time': 'REAL',
                    'intro_end_time': 'REAL',
                    'outro_start_time': 'REAL',
                    'source': 'TEXT',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }, 'FOREIGN KEY (show_id) REFERENCES shows(id), UNIQUE(show_id, season, episode)')

                conn.commit()
                xbmc.log('SkipIntro: Database migration completed successfully', xbmc.LOGINFO)
            finally:
                if needs_close:
                    conn.close()
        except Exception as e:
            xbmc.log(f'SkipIntro: Database migration error: {str(e)}', xbmc.LOGERROR)
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)

    def _migrate_table(self, cursor, table_name, columns, additional_sql=''):
        """Migrate a single table with proper SQL construction."""
        xbmc.log(f'SkipIntro: Migrating {table_name} table', xbmc.LOGINFO)

        # Whitelist of allowed table names for security
        allowed_tables = {'shows', 'shows_config', 'episodes'}
        if table_name not in allowed_tables:
            xbmc.log(f'SkipIntro: Invalid table name: {table_name}', xbmc.LOGERROR)
            return

        # Check if the table exists using parameterized query where possible
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Get existing columns
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {column[1] for column in cursor.fetchall()}

            # Add missing columns
            for col_name, col_type in columns.items():
                if col_name not in existing_columns:
                    # Validate column name contains only safe characters
                    if not col_name.replace('_', '').isalnum():
                        xbmc.log(f'SkipIntro: Invalid column name: {col_name}', xbmc.LOGERROR)
                        continue
                    alter_col_type = col_type
                    if 'DEFAULT CURRENT_TIMESTAMP' in col_type.upper():
                        alter_col_type = col_type.rsplit(' DEFAULT ', 1)[0]
                    # ALTER TABLE doesn't support parameters, but we've validated the inputs
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {alter_col_type}")
                    xbmc.log(f'SkipIntro: Added column {col_name} to {table_name}', xbmc.LOGINFO)
        else:
            # Create the table if it doesn't exist
            columns_sql = ', '.join(f"{col_name} {col_type}" for col_name, col_type in columns.items())

            # Only add additional_sql if it's not empty (fixes trailing comma issue)
            if additional_sql:
                full_sql = f"CREATE TABLE {table_name} ({columns_sql}, {additional_sql})"
            else:
                full_sql = f"CREATE TABLE {table_name} ({columns_sql})"

            cursor.execute(full_sql)
            xbmc.log(f'SkipIntro: Created table {table_name}', xbmc.LOGINFO)

        xbmc.log(f'SkipIntro: {table_name} table migration completed', xbmc.LOGINFO)

    def _create_tables(self):
        """Create database tables - now handled by _migrate_database"""
        # Migration now handles table creation
        pass

    @staticmethod
    def _title_lookup_key(title):
        """Normalize titles for alias lookup while preserving exact storage."""
        normalized = []
        for char in str(title or '').strip().casefold():
            if char in ("'", '\u2019', '`', '\u00b4'):
                continue
            if char.isalnum():
                normalized.append(char)
            else:
                normalized.append(' ')
        return ' '.join(''.join(normalized).split())

    @staticmethod
    def _config_has_intro_markers(config):
        if not config:
            return False
        return (
            config.get('intro_end_time') is not None or
            config.get('intro_end_chapter') is not None or
            (
                config.get('intro_start_chapter') is not None and
                config.get('intro_duration') is not None
            )
        )

    def _get_show_config_from_cursor(self, cursor, show_id):
        cursor.execute('''
            SELECT use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter, intro_duration,
                   intro_start_time, intro_end_time, outro_start_time
            FROM shows_config
            WHERE show_id = ?
        ''', (show_id,))
        result = cursor.fetchone()

        if not result:
            return None

        return {
            'use_chapters': bool(result[0]),
            'intro_start_chapter': result[1],
            'intro_end_chapter': result[2],
            'outro_start_chapter': result[3],
            'intro_duration': result[4],
            'intro_start_time': result[5],
            'intro_end_time': result[6],
            'outro_start_time': result[7]
        }

    def _show_has_saved_markers(self, cursor, show_id):
        config = self._get_show_config_from_cursor(cursor, show_id)
        if self._config_has_intro_markers(config):
            return True

        cursor.execute('''
            SELECT 1
            FROM episodes
            WHERE show_id = ?
              AND (
                intro_end_time IS NOT NULL OR
                intro_end_chapter IS NOT NULL
              )
            LIMIT 1
        ''', (show_id,))
        return cursor.fetchone() is not None

    def _find_show_alias(self, cursor, title, exclude_id=None, require_saved_markers=False):
        lookup_key = self._title_lookup_key(title)
        if not lookup_key:
            return None

        cursor.execute('SELECT id, title FROM shows')
        matches = [
            row for row in cursor.fetchall()
            if row[0] != exclude_id and self._title_lookup_key(row[1]) == lookup_key
        ]
        if not matches:
            return None

        for show_id, existing_title in matches:
            if self._show_has_saved_markers(cursor, show_id):
                return show_id, existing_title

        if require_saved_markers:
            return None
        return matches[0]

    def get_show_config(self, show_id):
        """Get show configuration"""
        try:
            conn = self._get_connection()
            needs_close = (not self._persistent_conn)
            try:
                c = conn.cursor()
                config = self._get_show_config_from_cursor(c, show_id)
                if config:
                    xbmc.log(f'SkipIntro: Found show config: {config}', xbmc.LOGINFO)
                    return config

                return None
            finally:
                if needs_close:
                    conn.close()
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show config: {str(e)}', xbmc.LOGERROR)
            return None

    def save_show_config(self, show_id, config):
        """Save show configuration"""
        try:
            conn = self._get_connection()
            needs_close = (not self._persistent_conn)
            try:
                c = conn.cursor()
                c.execute('''
                    INSERT OR REPLACE INTO shows_config
                    (show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter, intro_duration,
                     intro_start_time, intro_end_time, outro_start_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    show_id,
                    config.get('use_chapters', False),
                    config.get('intro_start_chapter'),
                    config.get('intro_end_chapter'),
                    config.get('outro_start_chapter'),
                    config.get('intro_duration'),
                    config.get('intro_start_time'),
                    config.get('intro_end_time'),
                    config.get('outro_start_time')
                ))
                conn.commit()
                xbmc.log(f'SkipIntro: Successfully saved show config: {config}', xbmc.LOGINFO)
                return True
            finally:
                if needs_close:
                    conn.close()
        except Exception as e:
            xbmc.log(f'SkipIntro: Error saving show config: {str(e)}', xbmc.LOGERROR)
            return False

    def get_show(self, title):
        """Get show by title, create if doesn't exist"""
        try:
            title = title.strip()
            xbmc.log(f'SkipIntro: Looking up show: {title}', xbmc.LOGINFO)
            conn = self._get_connection()
            needs_close = (not self._persistent_conn)
            try:
                c = conn.cursor()
                c.execute('SELECT id FROM shows WHERE TRIM(title) = ?', (title,))
                result = c.fetchone()

                if result:
                    exact_show_id = result[0]
                    alias = self._find_show_alias(
                        c,
                        title,
                        exclude_id=exact_show_id,
                        require_saved_markers=True
                    )
                    if alias and not self._show_has_saved_markers(c, exact_show_id):
                        xbmc.log(
                            f'SkipIntro: Using configured show alias "{alias[1]}" for "{title}"',
                            xbmc.LOGINFO
                        )
                        return alias[0]

                    xbmc.log(f'SkipIntro: Found existing show ID: {exact_show_id}', xbmc.LOGINFO)
                    return exact_show_id

                alias = self._find_show_alias(c, title)
                if alias:
                    xbmc.log(
                        f'SkipIntro: Found existing show alias "{alias[1]}" for "{title}"',
                        xbmc.LOGINFO
                    )
                    return alias[0]

                xbmc.log(f'SkipIntro: Creating new show entry for: {title}', xbmc.LOGINFO)
                c.execute('INSERT INTO shows (title) VALUES (?)', (title,))
                conn.commit()
                show_id = c.lastrowid

                # Create empty show config without default values
                self.save_show_config(show_id, {
                    'use_chapters': False,
                    'intro_start_time': None,
                    'intro_end_time': None,
                    'outro_start_time': None
                })

                xbmc.log(f'SkipIntro: Created show with ID: {show_id}', xbmc.LOGINFO)
                return show_id
            finally:
                if needs_close:
                    conn.close()
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show: {str(e)}', xbmc.LOGERROR)
            return None

    def set_manual_show_times(self, show_id, intro_start, intro_end, outro_start=None):
        """Manually set intro/outro times for a show"""
        try:
            config = {
                'use_chapters': False,
                'intro_start_time': intro_start,
                'intro_end_time': intro_end,
                'outro_start_time': outro_start,
                'intro_start_chapter': None,
                'intro_end_chapter': None,
                'outro_start_chapter': None
            }
            return self.save_show_config(show_id, config)
        except Exception as e:
            xbmc.log(f'SkipIntro: Error setting manual show times: {str(e)}', xbmc.LOGERROR)
            return False

    def set_manual_show_chapters(self, show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter=None, intro_duration=None):
        """Manually set intro/outro chapters for a show"""
        try:
            config = {
                'use_chapters': use_chapters,
                'intro_start_chapter': intro_start_chapter,
                'intro_end_chapter': intro_end_chapter,
                'intro_duration': intro_duration,
                'outro_start_chapter': outro_start_chapter,
                'intro_start_time': None,
                'intro_end_time': None,
                'outro_start_time': None
            }
            return self.save_show_config(show_id, config)
        except Exception as e:
            xbmc.log(f'SkipIntro: Error setting manual show chapters: {str(e)}', xbmc.LOGERROR)
            return False

    def save_episode_times(self, show_id, season, episode, times):
        """Save episode-specific intro/outro times or chapters."""
        try:
            conn = self._get_connection()
            needs_close = (not self._persistent_conn)
            try:
                c = conn.cursor()
                c.execute('''
                    INSERT OR REPLACE INTO episodes
                    (show_id, season, episode, intro_start_chapter, intro_end_chapter, outro_start_chapter,
                     intro_start_time, intro_end_time, outro_start_time, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    show_id,
                    season,
                    episode,
                    times.get('intro_start_chapter'),
                    times.get('intro_end_chapter'),
                    times.get('outro_start_chapter'),
                    times.get('intro_start_time'),
                    times.get('intro_end_time'),
                    times.get('outro_start_time'),
                    times.get('source')
                ))
                conn.commit()
                xbmc.log(f'SkipIntro: Successfully saved episode times: S{season}E{episode} {times}', xbmc.LOGINFO)
                return True
            finally:
                if needs_close:
                    conn.close()
        except Exception as e:
            xbmc.log(f'SkipIntro: Error saving episode times: {str(e)}', xbmc.LOGERROR)
            return False

    def get_episode_times(self, show_id, season, episode):
        """Get episode-specific intro/outro times or chapters."""
        try:
            conn = self._get_connection()
            needs_close = (not self._persistent_conn)
            try:
                c = conn.cursor()
                c.execute('''
                    SELECT intro_start_chapter, intro_end_chapter, outro_start_chapter,
                           intro_start_time, intro_end_time, outro_start_time, source
                    FROM episodes
                    WHERE show_id = ? AND season = ? AND episode = ?
                ''', (show_id, season, episode))
                result = c.fetchone()

                if not result:
                    return None

                config = {
                    'use_chapters': result[0] is not None or result[1] is not None,
                    'intro_start_chapter': result[0],
                    'intro_end_chapter': result[1],
                    'outro_start_chapter': result[2],
                    'intro_start_time': result[3],
                    'intro_end_time': result[4],
                    'outro_start_time': result[5],
                    'source': result[6]
                }
                xbmc.log(f'SkipIntro: Found episode times: {config}', xbmc.LOGINFO)
                return config
            finally:
                if needs_close:
                    conn.close()
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting episode times: {str(e)}', xbmc.LOGERROR)
            return None

    def get_show_times(self, show_id):
        """Get intro/outro times or chapters for a show"""
        try:
            xbmc.log(f'SkipIntro: Getting times/chapters for show {show_id}', xbmc.LOGINFO)

            config = self.get_show_config(show_id)
            if config:
                if config.get('use_chapters'):
                    times = {
                        'use_chapters': True,
                        'intro_start_chapter': config.get('intro_start_chapter'),
                        'intro_end_chapter': config.get('intro_end_chapter'),
                        'outro_start_chapter': config.get('outro_start_chapter'),
                        'intro_start_time': config.get('intro_start_time'),
                        'intro_end_time': config.get('intro_end_time'),
                        'outro_start_time': config.get('outro_start_time')
                    }
                else:
                    times = {
                        'use_chapters': False,
                        'intro_start_time': config.get('intro_start_time'),
                        'intro_end_time': config.get('intro_end_time'),
                        'outro_start_time': config.get('outro_start_time')
                    }
                xbmc.log(f'SkipIntro: Found show times/chapters: {times}', xbmc.LOGINFO)
                return times

            xbmc.log('SkipIntro: No times/chapters found for show', xbmc.LOGINFO)
            return None
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show times/chapters: {str(e)}', xbmc.LOGERROR)
            return None
