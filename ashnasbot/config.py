import json
import logging

logger = logging.getLogger(__name__)


class ReloadException(Exception):
    pass

class ConfigLoader():

    # Singleton stuff
    instance = None
    def __new__(self):
        if not ConfigLoader.instance:
            ConfigLoader.instance = ConfigLoader.__Config()
        return ConfigLoader.instance

    def __getattr__(self, name):
        return getattr(self.instance, name)

    # Actual class def
    class __Config():
        def __init__(self):
            self._config = {}

        def __getitem__(self, key):
            if key not in self._config.keys():
                logger.info(self._config.keys())
                raise KeyError
            return self._config[key]

        def load(self):
            with open('config.json') as f:
                self._config = json.load(f)

            return self