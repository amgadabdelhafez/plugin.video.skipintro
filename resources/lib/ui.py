import xbmc
import xbmcgui
import xbmcaddon

class SkipIntroDialog(xbmcgui.WindowXMLDialog):
    """Dialog that shows the skip intro button"""

    def __init__(self, *args, **kwargs):
        self.callback = kwargs.get('callback')
        xbmcgui.WindowXMLDialog.__init__(self)

    def onInit(self):
        """Called when dialog is initialized"""
        # Auto-focus the button so remote works immediately
        self.setFocusId(1)

    def onClick(self, controlId):
        """Called when a control is clicked"""
        if controlId == 1:  # Skip button
            xbmc.log('SkipIntro: Skip button clicked', xbmc.LOGINFO)
            self.close()
            if self.callback:
                self.callback()

class PlayerUI:
    """UI manager for skip intro functionality"""

    def __init__(self):
        self.prompt_shown = False
        self.warning_shown = False
        self._dialog = None

    def show_skip_button(self, seconds_until_skip=None):
        """
        Show the actual skip button dialog.

        Args:
            seconds_until_skip: Not used, kept for compatibility
        """
        # This method is now just for compatibility with timer logic
        # The actual button is shown via prompt_skip_intro
        return True

    def show_skip_warning(self, seconds_until_skip):
        """
        Show a warning notification X seconds before the skip happens.
        (Deprecated - kept for backward compatibility)

        Args:
            seconds_until_skip: How many seconds until the skip will occur
        """
        return self.show_skip_button(seconds_until_skip)

    def prompt_skip_intro(self, callback):
        """
        Show skip button dialog (non-blocking).

        Args:
            callback: Function to call when user clicks skip button
        """
        xbmc.log('SkipIntro: Showing skip button dialog', xbmc.LOGINFO)
        try:
            if self.prompt_shown:
                xbmc.log('SkipIntro: Skip button already shown', xbmc.LOGDEBUG)
                return False

            # Show the actual button dialog
            addon = xbmcaddon.Addon()
            addon_path = addon.getAddonInfo('path')

            self._dialog = SkipIntroDialog('skip_button.xml', addon_path, 'default', '720p', callback=callback)
            self._dialog.show()  # Non-blocking show

            self.prompt_shown = True
            xbmc.log('SkipIntro: Skip button dialog shown', xbmc.LOGINFO)
            return True

        except Exception as e:
            xbmc.log(f'SkipIntro: Error showing skip button: {str(e)}', xbmc.LOGERROR)
            import traceback
            xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
            return False

    def close_dialog(self):
        """Close the skip button dialog if it's open"""
        if self._dialog:
            try:
                self._dialog.close()
                xbmc.log('SkipIntro: Dialog closed', xbmc.LOGINFO)
            except Exception:
                pass
            self._dialog = None

    def cleanup(self):
        """Clean up resources"""
        self.close_dialog()
        self.prompt_shown = False
        self.warning_shown = False

    def show_notification(self, message, time=5000):
        """Show a notification message"""
        xbmcgui.Dialog().notification('SkipIntro', str(message), xbmcgui.NOTIFICATION_INFO, time)
