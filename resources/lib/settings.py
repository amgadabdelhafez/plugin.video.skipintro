import xbmc
import xbmcaddon

class Settings:
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.settings = self.validate_settings()

    def validate_settings(self):
        """Validate and sanitize addon settings"""
        try:
            enable_autoskip = self.addon.getSettingBool('enable_autoskip')
            pre_skip_seconds = int(self.addon.getSetting('pre_skip_seconds'))
            delay_autoskip = int(self.addon.getSetting('delay_autoskip'))
            auto_dismiss_button = int(self.addon.getSetting('auto_dismiss_button'))

            # Ensure pre-skip seconds within reasonable bounds
            if pre_skip_seconds < 0:
                pre_skip_seconds = 3
                self.addon.setSetting('pre_skip_seconds', '3')
            elif pre_skip_seconds > 10:
                pre_skip_seconds = 10
                self.addon.setSetting('pre_skip_seconds', '10')

            # Ensure delay autoskip within reasonable bounds
            if delay_autoskip < 0:
                delay_autoskip = 0
                self.addon.setSetting('delay_autoskip', '0')
            elif delay_autoskip > 30:
                delay_autoskip = 30
                self.addon.setSetting('delay_autoskip', '30')

            # Ensure auto dismiss button within reasonable bounds
            if auto_dismiss_button < 0:
                auto_dismiss_button = 0
                self.addon.setSetting('auto_dismiss_button', '0')
            elif auto_dismiss_button > 30:
                auto_dismiss_button = 30
                self.addon.setSetting('auto_dismiss_button', '30')

            return {
                'enable_autoskip': enable_autoskip,
                'pre_skip_seconds': pre_skip_seconds,
                'delay_autoskip': delay_autoskip,
                'auto_dismiss_button': auto_dismiss_button
            }
        except ValueError as e:
            xbmc.log(f'SkipIntro: Error reading settings: {str(e)} - using defaults', xbmc.LOGERROR)
            return {
                'enable_autoskip': True,
                'pre_skip_seconds': 3,
                'delay_autoskip': 0,
                'auto_dismiss_button': 0
            }

    def get_setting(self, key):
        return self.settings.get(key)
