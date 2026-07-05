#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Database management tools entry point
Called from addon settings for backup, restore, import, and export operations
"""

import sys
import xbmc
from resources.lib.database_manager import DatabaseManager

ALLOWED_ACTIONS = {'backup', 'restore', 'export', 'import'}


def main():
    """Main entry point for database tools"""
    try:
        # Get the action from command line arguments
        if len(sys.argv) < 2:
            xbmc.log('SkipIntro: No action specified for database tools', xbmc.LOGERROR)
            return

        action = sys.argv[1]
        if action not in ALLOWED_ACTIONS:
            xbmc.log('SkipIntro: Unknown database action', xbmc.LOGERROR)
            return

        xbmc.log(f'SkipIntro: Database tools action: {action}', xbmc.LOGINFO)

        # Pass explicit addon ID since RunScript doesn't set addon context
        manager = DatabaseManager(addon_id='plugin.video.skipintro')

        if action == 'backup':
            manager.backup_database()
        elif action == 'restore':
            manager.restore_database()
        elif action == 'export':
            manager.export_to_json()
        elif action == 'import':
            manager.import_from_json()

    except Exception as e:
        xbmc.log(f'SkipIntro: Database tools error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)


if __name__ == '__main__':
    main()
