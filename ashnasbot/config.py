import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE = 'config.json'
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


class ConfigError(Exception):
    pass


class Config():

    # Singleton stuff
    instance: "Config.__Config" = None

    def __new__(self):
        if not Config.instance:
            Config.instance = Config.__Config()
        return Config.instance

    def __getattr__(self, name) -> Any:
        return getattr(self.instance, name)

    def __getitem__(self, name) -> Any:
        assert self.instance is not None
        return self.instance[name]

    # Actual class def
    class __Config():
        def __init__(self):
            self._config = {}
            self._load()

        def __contains__(self, key):
            return key in self._config.keys()

        def __getitem__(self, key) -> Any:
            if key not in self._config.keys():
                raise ValueError(f"{key} not configured")
            logger.log(0, "Config access: %s : %s", key, self._config[key])
            return self._config[key]

        def _load(self):
            try:
                logger.info("Reading config from %s", CONFIG_FILE)
                with open(CONFIG_FILE) as f:
                    self._config = json.load(f)
            except Exception:
                with open(CONFIG_FILE, 'w') as f:
                    f.write(DEFAULT_CFG)
                raise ConfigError(f"{CONFIG_FILE} not found")
            logger.debug("Config loaded")

            return self

        def get(self, key, default=_no_default):
            if key not in self._config.keys():
                if default is _no_default:
                    raise ValueError(f"{key} not configured")
                else:
                    return default
            logger.log(0, "Config access: %s : %s", key, self._config[key])
            return self._config[key]
