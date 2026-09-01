"""The dormant per-picker PIN path (#60).

Nothing calls `pins.py` today; the site signs in with one shared passphrase.
These tests exist so the code still works the day it is wired back up, rather
than rotting quietly in the dark.
"""

import json

import pytest

from g_nfl.api import pins

PIN = "1234"


@pytest.fixture(scope="module")
def stored():
    """One hash for the module: PBKDF2 at 600k iterations is not free."""
    return pins.hash_pin(PIN)


def test_a_pin_verifies_against_its_own_hash(stored):
    assert pins.verify_pin(PIN, stored)


def test_a_wrong_pin_does_not(stored):
    assert not pins.verify_pin("9999", stored)


def test_two_hashes_of_one_pin_differ(stored):
    """Salted, so the env var does not reveal that two people share a PIN."""
    assert pins.hash_pin(PIN) != stored


def test_a_malformed_hash_is_refused_rather_than_raising():
    assert not pins.verify_pin(PIN, "not-a-hash")


def test_pins_load_from_the_environment(monkeypatch, stored):
    monkeypatch.setenv("PICKER_PINS", json.dumps({"Griffin": stored}))
    assert pins.check_pin("Griffin", PIN)
    assert not pins.check_pin("Griffin", "9999")
    assert not pins.check_pin("Mallory", PIN)


def test_an_unset_variable_fails_closed(monkeypatch):
    monkeypatch.delenv("PICKER_PINS", raising=False)
    assert not pins.check_pin("Griffin", PIN)


def test_a_malformed_variable_fails_closed(monkeypatch):
    monkeypatch.setenv("PICKER_PINS", "{not json")
    assert pins.load_pins() == {}
    assert not pins.check_pin("Griffin", PIN)
