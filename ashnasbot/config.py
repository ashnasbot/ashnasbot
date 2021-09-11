import json
import logging

logger = logging.getLogger(__name__)

DEFAULT_CFG = """{
    "client_id": "",
    "oauth": "oauth:",
    "username": "BOT_USERNAME",
    "secret": "",
    "user_id": 123456789,
    "log_level":"INFO",
    "bttv": true
}
"""
_no_default = object()


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
                raise ValueError(f"{key} not configured")
            return self._config[key]

        def _load(self):
            try:
                with open('config.json') as f:
                    self._config = json.load(f)
            except Exception:
                with open('config.json', 'w') as f:
                    f.write(DEFAULT_CFG)
                raise ConfigError("No config.json found")

            return self

        def get(self, key, default=_no_default):
            if key not in self._config.keys():
                if default is _no_default:
                    raise ValueError(f"{key} not configured")
                else:
                    return default
            return self._config[key]
