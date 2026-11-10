"""Personal logins, roles and the PIN of the shared reception tablet.

Every operator signs in to Home Assistant with her own user; the level chosen
in the Accessi tab says what she may do (the four roles of the card are
``therapist``, ``operator``, ``manager`` and ``admin``). A user can be linked
to one operator of the agenda: a masseuse may then only book and change her
own appointments.

A tablet at the reception is signed in once with a *shared* user. Nobody acts
as that user: the person in front of it picks her face and types her 4-digit
PIN, and from then on every call from the tablet acts as her, with her level
and her name, until she signs out or the tablet stays idle for a while.

The sessions live in memory only: a restart of Home Assistant signs everybody
out of the tablet, which is the safe direction.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from typing import Any

#: Default minutes of inactivity after which the tablet signs out.
PIN_IDLE_DEFAULT = 10
#: Wrong PINs in a row before the tablet locks for PIN_LOCK_SECONDS.
PIN_MAX_FAILURES = 5
PIN_LOCK_SECONDS = 60
_PBKDF2_ROUNDS = 120_000


def valid_pin(pin: str) -> bool:
    """A PIN is exactly four digits."""
    return len(pin) == 4 and pin.isdigit()


def hash_pin(pin: str, salt: str | None = None) -> tuple[str, str]:
    """Return ``(salt, hash)`` of a PIN, both hex."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS
    )
    return salt, digest.hex()


def check_pin(pin: str, salt: str, expected: str) -> bool:
    """Whether ``pin`` matches the stored salt and hash."""
    if not (salt and expected and valid_pin(pin)):
        return False
    try:
        _, digest = hash_pin(pin, salt)
    except ValueError:
        return False
    return hmac.compare_digest(digest, expected)


def public_profiles(profiles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The profiles without the PIN secrets, as the card sees them."""
    return {
        user_id: {
            "operator_id": profile.get("operator_id") or "",
            "shared": bool(profile.get("shared")),
            "has_pin": bool(profile.get("pin_hash")),
        }
        for user_id, profile in (profiles or {}).items()
    }


@dataclass
class _Session:
    user_id: str
    last_seen: float


class PinSessions:
    """Who is using each shared tablet right now, and wrong-PIN locks."""

    def __init__(self) -> None:
        self._active: dict[str, _Session] = {}
        self._failures: dict[str, tuple[int, float]] = {}

    def start(self, device: str, user_id: str, now: float) -> None:
        """``user_id`` is now acting on ``device``."""
        self._active[device] = _Session(user_id, now)
        self._failures.pop(device, None)

    def current(self, device: str, now: float, idle_minutes: int) -> str | None:
        """The person acting on ``device``, refreshing her idle timer."""
        session = self._active.get(device)
        if session is None:
            return None
        if now - session.last_seen > max(1, idle_minutes) * 60:
            del self._active[device]
            return None
        session.last_seen = now
        return session.user_id

    def peek(self, device: str, now: float, idle_minutes: int) -> str | None:
        """Like ``current`` but without refreshing the timer."""
        session = self._active.get(device)
        if session is None or now - session.last_seen > max(1, idle_minutes) * 60:
            return None
        return session.user_id

    def end(self, device: str) -> None:
        """Sign the tablet out."""
        self._active.pop(device, None)

    def end_user(self, user_id: str) -> None:
        """Sign a person out of every tablet (her PIN or role changed)."""
        for device, session in list(self._active.items()):
            if session.user_id == user_id:
                del self._active[device]

    def locked_for(self, device: str, now: float) -> int:
        """Seconds the tablet still refuses PINs after too many wrong ones."""
        count, until = self._failures.get(device, (0, 0.0))
        if count >= PIN_MAX_FAILURES and until > now:
            return int(until - now) + 1
        return 0

    def failure(self, device: str, now: float) -> int:
        """Record a wrong PIN; return the lock in seconds (0 = not locked)."""
        count, until = self._failures.get(device, (0, 0.0))
        if until and until <= now and count >= PIN_MAX_FAILURES:
            count = 0
        count += 1
        until = now + PIN_LOCK_SECONDS if count >= PIN_MAX_FAILURES else 0.0
        self._failures[device] = (count, until)
        return self.locked_for(device, now)


def operator_ids_in(data: Any) -> set[str]:
    """Every operator id named anywhere in a service call's data."""
    found: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "operator_id" and value:
                found.add(str(value))
            elif key == "operator_ids" and isinstance(value, (list, tuple)):
                found.update(str(item) for item in value if item)
            else:
                found |= operator_ids_in(value)
    elif isinstance(data, (list, tuple)):
        for item in data:
            found |= operator_ids_in(item)
    return found


def has_payment(data: Any) -> bool:
    """Whether a call takes money (a masseuse does not handle payments).

    A payment block that only redeems a voucher or notes a balance due is
    not money taken at the desk.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("payment", "payments") and _takes_money(value):
                return True
            if isinstance(value, (dict, list, tuple)) and has_payment(value):
                return True
    elif isinstance(data, (list, tuple)):
        return any(has_payment(item) for item in data)
    return False


def _takes_money(payment: Any) -> bool:
    if isinstance(payment, (list, tuple)):
        return any(_takes_money(item) for item in payment)
    if not isinstance(payment, dict):
        return False
    if payment.get("paid") or payment.get("deposit"):
        return True
    for key in ("paid_amount", "deposit_amount", "amount"):
        try:
            if float(payment.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False
