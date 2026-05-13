"""Bcrypt password hashing wrapper.

Single responsibility: turn a plaintext password into a bcrypt hash
and verify a candidate against a stored hash without leaking timing
information. No file or network I/O, no global state -- callers
inject a ``PasswordHasher`` instance so tests can stub the work
factor down for fast unit tests.

Production usage:

    hasher = PasswordHasher()                    # rounds=12 by default
    stored = hasher.hash(plaintext)              # store on /setup
    ok = hasher.verify(candidate, stored)        # check on /login

The class deliberately swallows malformed-hash errors during
``verify`` and returns ``False`` rather than raising. That keeps
callers from leaking "this hash was malformed" vs "wrong password"
through differing exception paths.
"""

from __future__ import annotations

import bcrypt

_MIN_ROUNDS = 4
_MAX_ROUNDS = 16
_DEFAULT_ROUNDS = 12


class PasswordHasher:
    """Stateless bcrypt hash + verify, with a configurable work factor.

    ``rounds`` is the bcrypt cost parameter (work factor = ``2**rounds``).
    Production defaults to 12 (~250ms on modern hardware); tests pass
    ``rounds=4`` to keep the suite fast.
    """

    def __init__(self, rounds: int = _DEFAULT_ROUNDS) -> None:
        if not _MIN_ROUNDS <= rounds <= _MAX_ROUNDS:
            raise ValueError(
                f"rounds must be in [{_MIN_ROUNDS}, {_MAX_ROUNDS}], got {rounds}"
            )
        self._rounds = rounds

    @property
    def rounds(self) -> int:
        return self._rounds

    def hash(self, plaintext: str) -> str:
        """Return a bcrypt hash for ``plaintext`` as an ASCII string."""
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be str")
        if plaintext == "":
            raise ValueError("plaintext password must not be empty")
        salt = bcrypt.gensalt(rounds=self._rounds)
        digest = bcrypt.hashpw(plaintext.encode("utf-8"), salt)
        return digest.decode("ascii")

    def verify(self, candidate: str, stored_hash: str) -> bool:
        """Return True iff ``candidate`` matches ``stored_hash``.

        Returns ``False`` (never raises) if ``stored_hash`` is empty,
        malformed, or otherwise unparseable. Callers should treat
        an empty stored hash as "auth not configured" upstream.
        """
        if not isinstance(candidate, str) or not isinstance(stored_hash, str):
            return False
        if candidate == "" or stored_hash == "":
            return False
        try:
            return bcrypt.checkpw(
                candidate.encode("utf-8"), stored_hash.encode("ascii")
            )
        except (ValueError, TypeError):
            return False
