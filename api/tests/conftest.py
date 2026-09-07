# -*- coding: utf-8 -*-
"""Test-session environment.

Rate limiting is infrastructure, not behaviour under test. Leaving it on makes
the suite order-dependent — the upload tests legitimately post more than ten
files, which is exactly what the limiter exists to stop in production and
exactly the wrong thing for it to stop here.

So it is off for the suite at large, and `test_production.py` turns it back on
deliberately for the tests that are actually about it.
"""

from __future__ import annotations

import os

# Set before anything imports salix.config, so the first Settings() sees them.
os.environ.setdefault("SALIX_RATE_LIMIT_ENABLED", "false")
# No shared key by default: the existing suite asserts the open behaviour a
# fresh clone has, and the auth tests supply their own.
os.environ.pop("SALIX_API_KEY", None)
os.environ.pop("API_KEY", None)

# The developer's own .env is not part of the test environment.
#
# Clearing os.environ above is not enough on its own: Settings also reads
# `.env` at the repository root, and that file is where a real deployment's
# key lives. Anybody who followed the deployment guide and created one got 95
# failures on a clean checkout -- not because anything was broken, but because
# the suite was reading their configuration and asserting against it.
#
# Tests that want a setting say so themselves. Nothing is inherited.
from salix.config import Settings  # noqa: E402

Settings.model_config["env_file"] = ()
