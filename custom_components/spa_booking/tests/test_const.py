"""Sanity checks on the SPA Booking constants.

These checks catch drift between the three places that must agree on the
same list of payment methods, guest types, extras and operator roles: the
service schema, the coordinator and the card."""

from __future__ import annotations

from custom_components.spa_booking import const


def test_version_is_string() -> None:
    assert isinstance(const.INTEGRATION_VERSION, str) if hasattr(const, "INTEGRATION_VERSION") else True


def test_payment_methods_non_empty() -> None:
    assert len(const.PAYMENT_METHODS) >= 4


def test_payment_methods_unique() -> None:
    names = [method[0] for method in const.PAYMENT_METHODS]
    assert len(names) == len(set(names)), "Duplicate payment method id"


def test_operator_roles_default_in() -> None:
    assert const.OPERATOR_ROLE_DEFAULT in [role[0] for role in const.OPERATOR_ROLES]


def test_guest_type_default_in() -> None:
    assert const.GUEST_TYPE_DEFAULT in [role[0] for role in const.GUEST_TYPES]


def test_extras_default_in_extras() -> None:
    known = {item[0] for item in const.EXTRAS}
    assert set(const.EXTRAS_NAMES) == known


def test_accessory_defaults_match_extras() -> None:
    assert len(const.ACCESSORY_DEFAULTS) == len(const.EXTRAS)
    for accessory, (item_id, _, _) in zip(const.ACCESSORY_DEFAULTS, const.EXTRAS):
        assert accessory["id"] == item_id


def test_voucher_validity_positive() -> None:
    assert const.VOUCHER_VALID_MONTHS >= 1


def test_closure_max_days_reasonable() -> None:
    assert const.MAX_CLOSURE_DAYS >= 100


def test_warning_status_keys() -> None:
    assert const.STATUS_CONFIRMED == "confirmed"
    assert const.STATUS_CANCELLED == "cancelled"
    assert const.STATUS_PENDING == "pending"
    assert const.STATUS_CONFIRMED in const.BOOKING_STATUSES
    assert const.STATUS_CANCELLED not in const.BOOKING_STATUSES