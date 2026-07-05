#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
from resources.lib.metadata import sanitize_path
import xbmcaddon


def browse_and_set_path():
    """Browse for a directory and save it to the backup_restore_path setting"""
    try:
        # Get addon instance
        addon = xbmcaddon.Addon('plugin.video.skipintro')

        # Get current path as starting point
        current_path = addon.getSetting('backup_restore_path')
        if not current_path or current_path.strip() == '':
            current_path = 'special://userdata/addon_data/plugin.video.skipintro/'

        # Open browse dialog for folder selection (type 0 = ShowAndGetDirectory)
        dialog = xbmcgui.Dialog()
        selected_path = dialog.browse(
            0,  # Type: ShowAndGetDirectory
            'Select Backup/Restore Location',
            'files',  # shares: 'files' allows access to all sources including SMB/NFS
            '',
            False,
            False,
            current_path
        )

        # If user selected a path (didn't cancel)
        if selected_path:
            xbmc.log(f'SkipIntro: Selected backup path: {sanitize_path(selected_path)}', xbmc.LOGINFO)

            # Show path in a text dialog so user can verify and copy if needed
            dialog.textviewer(
                'Selected Path - Click OK to save',
                f'Selected path:\n\n{selected_path}\n\n'
                f'This will be saved to your addon settings.\n'
                f'The settings will be updated when you close the settings dialog.'
            )

            # Save to settings
            addon.setSetting('backup_restore_path', selected_path)

            xbmc.log(f'SkipIntro: Backup path saved to settings: {sanitize_path(selected_path)}', xbmc.LOGINFO)
        else:
            xbmc.log('SkipIntro: Browse path cancelled by user', xbmc.LOGINFO)

    except Exception as e:
        xbmc.log(f'SkipIntro: Browse path failed: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            'Skip Intro',
            f'Browse failed: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR
        )


if __name__ == '__main__':
    browse_and_set_path()
