"""Local dashboard authentication primitives.

Each module in this package owns a single responsibility:

- ``password_hasher``: bcrypt hash/verify (no I/O, no state).
- ``jwt_session``: JWT issue/decode with ``session_version`` claim.
- ``lockout_tracker``: in-memory failed-login throttling.
- ``dependencies``: FastAPI ``Depends`` shims for routes.

Higher-level orchestration (routes, middleware, server wiring) lives
in ``src.api.routes`` and ``src.api.server`` and consumes these
modules; nothing in this package imports FastAPI app state directly.
"""
