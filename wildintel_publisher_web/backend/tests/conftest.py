"""Shared pytest fixtures and path setup for the backend test suite."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Make backend/src/ importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# wildintel_publisher.config (imported by services.trapper_service)
# auto-creates settings.toml in the user's real app-config dir the first time
# it's imported. Redirect HOME/XDG_CONFIG_HOME to a throwaway temp dir before
# any test module gets a chance to import it, so the test suite never reads
# or writes the developer's real ~/.config/wildintel-publisher/settings.toml —
# same guard wildintel_publisher's own CLI test suite uses.
_FAKE_HOME = Path(tempfile.mkdtemp(prefix="wildintel-publisher-web-test-home-"))
os.environ["HOME"] = str(_FAKE_HOME)
os.environ["XDG_CONFIG_HOME"] = str(_FAKE_HOME / ".config")
os.environ["APPDATA"] = str(_FAKE_HOME / "AppData" / "Roaming")
atexit.register(shutil.rmtree, _FAKE_HOME, True)
