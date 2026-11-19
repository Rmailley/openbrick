import difflib
import hmac
import time

import pyotp

MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60


class _TOTP(pyotp.TOTP):
    # Plenty of real services still issue 16-character (80-bit) setup keys; pyotp's default rejects them.
    min_secret_length_bits = 80


class TwoFA:
    def __init__(self, pin: str, accounts: dict[str, str], clock=time.time):
        self._pin = pin
        self._accounts = accounts
        self._clock = clock
        self._failures = 0
        self._locked_until = 0.0

    def handle(self, pin: str, account: str | None) -> str:
        now = self._clock()
        if now < self._locked_until:
            return "2FA is locked after too many wrong PINs. Try again later."

        if not hmac.compare_digest(pin.encode(), self._pin.encode()):
            self._failures += 1
            if self._failures >= MAX_FAILURES:
                self._failures = 0
                self._locked_until = now + LOCKOUT_SECONDS
                return "Wrong PIN. 2FA is locked for 15 minutes."
            return "Wrong PIN."
        self._failures = 0

        if account is None:
            return "2FA accounts: " + ", ".join(self.accounts())

        name = account.lower()
        if name not in self._accounts:
            close = difflib.get_close_matches(name, self._accounts, n=1, cutoff=0.6)
            if not close:
                return f"No 2FA account named {account}. Text 2fa PIN to list them."
            name = close[0]

        totp = _TOTP(self._accounts[name])
        remaining = totp.interval - int(now) % totp.interval
        return f"{name}: {totp.at(int(now))} ({remaining}s left)"

    def accounts(self) -> list[str]:
        return sorted(self._accounts)
