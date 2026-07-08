"""Shared test setup: hermetic config so tests never touch config.json or the network."""
import os

os.makedirs("db", exist_ok=True)

from ashnasbot import config  # noqa: E402


class FakeConfig(dict):
    """Stands in for the Config singleton (same access API, no file IO)."""

    def __getitem__(self, key):
        if key not in self:
            raise ValueError(f"{key} not configured")
        return dict.__getitem__(self, key)

    def get(self, key, default=config._no_default):
        if key not in self:
            if default is config._no_default:
                raise ValueError(f"{key} not configured")
            return default
        return dict.__getitem__(self, key)

    def update(self, key, value=None):
        dict.__setitem__(self, key, value)

    def update_many(self, values):
        dict.update(self, values)

    def reload(self):
        pass


DEFAULTS = {
    "client_id": "test_client_id",
    "secret": "test_secret",
    "username": "ashnasbot",
    "user_id": 123456789,
    "log_level": "INFO",
    "bttv": False,
}


def install_config(**overrides):
    """Reset the FakeConfig singleton contents.

    Mutates the existing instance in place (modules keep references to it),
    creating it only on first use.
    """
    cfg = config.Config.instance
    if not isinstance(cfg, FakeConfig):
        cfg = FakeConfig()
        config.Config.instance = cfg
    cfg.clear()
    dict.update(cfg, {**DEFAULTS, **overrides})
    return cfg


# Install immediately: any ashnasbot import after `import helpers` sees the fake.
install_config()
