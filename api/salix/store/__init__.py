"""Persistence.

`db` owns the engine and sessions, `models` the tables, `repo` the typed
Pydantic-in/Pydantic-out API that the rest of the system uses, and `vectors`
the embedding encoding and similarity search.
"""

from . import repo, vectors
from .db import dispose, get_session, init_db, session_scope

__all__ = ["dispose", "get_session", "init_db", "repo", "session_scope", "vectors"]
