import json
import logging

logger = logging.getLogger(__name__)


class ReloadException(Exception):
    pass

class ConfigError(Exception):
    pass

class Config():

    # Singleton stuff
    instance = None
    def __new__(self):
        if not Config.instance:
            Config.instance = Config.__Config()
        return Config.instance

    def __getattr__(self, name):
        return getattr(self.instance, name)

    # Actual class def
    class __Config():
        def __init__(self):
            self._config = {}
            self._load()

        def __contains__(self, key):
            return key in self._config.keys()

        def __getitem__(self, key):
            if key not in self._config.keys():
                logger.info(self._config.keys())
                raise KeyError
            return self._config[key]

        def _load(self):
            try:
                with open('config.json') as f:
                    self._config = json.load(f)
            except:
                raise ConfigError("No config.json found")

            return self