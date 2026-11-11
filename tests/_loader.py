"""Import the plugin exactly the way Hermes' loader does.

Hermes imports a directory plugin as a package named ``hermes_plugins.<slug>``
with ``__path__`` pointing at the plugin directory. This lets ``__init__.py``
use relative imports (``from .core import ...``) and keeps the tests independent
of what the checkout directory happens to be named.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

_NS_PARENT = "hermes_plugins"


def load_plugin(root: Path):
    name = f"{_NS_PARENT}.phoenix"
    init = Path(root) / "__init__.py"
    if not init.exists():
        raise FileNotFoundError(f"No __init__.py in {root}")
    # Register the parent namespace package — exactly what Hermes' loader does.
    if _NS_PARENT not in sys.modules:
        ns_pkg = types.ModuleType(_NS_PARENT)
        ns_pkg.__path__ = []
        ns_pkg.__package__ = _NS_PARENT
        sys.modules[_NS_PARENT] = ns_pkg
    spec = importlib.util.spec_from_file_location(
        name, init, submodule_search_locations=[str(root)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {init}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = name
    module.__path__ = [str(root)]
    sys.modules[name] = module
    spec.loader.exec_module(module)
    # Eagerly import the submodules so callers can use `module.core`, etc.
    for sub in ("core", "journal", "keys", "middleware", "commands", "tools", "windtunnel"):
        sub_mod = importlib.import_module(f"{name}.{sub}")
        setattr(module, sub, sub_mod)

    # App.close() must close SQLite connections to release Windows file locks
    # while preserving the journal instance so demo.py can read app.journal.db_path.
    # It also closes the module singleton get_app() so that no unclosed connections lock demo/test directories.
    def _app_close(self):
        if self.journal is not None:
            try:
                self.journal.close()
            except Exception:
                pass
        try:
            singleton = module.core.get_app()
            if singleton is not self and singleton.journal is not None:
                singleton.journal.close()
        except Exception:
            pass

    module.core.App.close = _app_close
    return module
