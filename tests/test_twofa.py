from openbrick.twofa import LOCKOUT_SECONDS, MAX_FAILURES, TwoFA, _TOTP

SECRET = "JBSWY3DPEHPK3PXP"


def test_returns_current_code():
    now = 1_800_000_015
    tf = TwoFA("0421", {"github": SECRET}, clock=lambda: now)
    expected = _TOTP(SECRET).at(now)
    assert tf.handle("0421", "GitHub") == f"github: {expected} (15s left)"


def test_lists_accounts():
    tf = TwoFA("0421", {"github": SECRET, "aws": SECRET})
    assert tf.handle("0421", None) == "2FA accounts: aws, github"


def test_unknown_account():
    tf = TwoFA("0421", {"github": SECRET})
    assert "No 2FA account named bank" in tf.handle("0421", "bank")


def test_misspelled_account_still_works():
    tf = TwoFA("0421", {"github": SECRET, "aws": SECRET})
    assert tf.handle("0421", "gihub").startswith("github: ")


def test_locks_after_repeated_wrong_pins():
    now = [1_800_000_000.0]
    tf = TwoFA("0421", {"github": SECRET}, clock=lambda: now[0])
    for _ in range(MAX_FAILURES - 1):
        assert tf.handle("0000", "github") == "Wrong PIN."
    assert "locked for 15 minutes" in tf.handle("0000", "github")
    assert "locked" in tf.handle("0421", "github")
    now[0] += LOCKOUT_SECONDS + 1
    assert tf.handle("0421", "github").startswith("github: ")
