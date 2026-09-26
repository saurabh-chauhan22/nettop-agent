import os
from configparser import ConfigParser
from pathlib import Path

from base import SETTINGS_INIT


class ConfigIniReader:
    """Read an .ini or .env-style file into {section: {key: value}}."""

    def __init__(self, config_file=None):
        if config_file:
            self.config_file = Path(config_file)
        else:
            self.config_file = SETTINGS_INIT
        self.config = {}

    def read(self):
        parser = ConfigParser(interpolation=None)  # API keys may contain '%'
        parser.optionxform = str  # preserve case of keys
        path = Path(self.config_file)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if not any(line.lstrip().startswith("[") for line in text.splitlines()):
                text = "[DEFAULT]\n" + text  # .env-style: no section headers
            parser.read_string(text)
        self.config = {s: dict(parser.items(s)) for s in parser.sections()}
        self.config["DEFAULT"] = dict(parser.defaults())
        return self.config

    def get(self, section, key, default=None):
        if not self.config:
            self.read()
        for name in (section, "DEFAULT"):
            if key in self.config.get(name, {}):
                return self.config[name][key]
        return default


def load_env(config_file=None):
    """Export non-empty settings.ini keys to the environment. Real environment variables win."""
    for key, value in ConfigIniReader(config_file).read()["DEFAULT"].items():
        if value:
            os.environ.setdefault(key, value)
