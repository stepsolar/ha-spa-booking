"""The WordPress shop's vouchers (2.7.0)."""

from __future__ import annotations

import pytest

from custom_components.spa_booking import wp_shop
from custom_components.spa_booking.exceptions import NotFoundError

from .conftest import run


def _item(code="filippo-ISYM-10208-5118-4180", **extra):
    return {"code": code, "order_id": 10208, "order_status": "completed", "order_date": "2026-11-12T19:13:38+01:00",
            "product_id": 4097, "variation_id": 5118, "product_name": "Ingresso SPA You&Me - senza Wellness Kit",
            "value": 80, "expires": "2027-05-11 19:13:38", "buyer_first": "Filippo", "buyer_last": "Rossi",
            "buyer_email": "f@example.com", "buyer_phone": "333 1234567", "recipient_name": "Nicoletta",
            "recipient_email": "f@example.com", "message": "Auguri", "used": False, "used_at": "", **extra}


@pytest.fixture
def shop(coordinator, monkeypatch, freeze):
    freeze("2026-11-13 10:00")
    state = {"items": [_item()], "redeemed": []}

    async def vouchers(session, base, secret, days=200):
        return state["items"]

    async def redeem(session, base, secret, code, note=""):
        state["redeemed"].append(code)
        return {"ok": True}

    monkeypatch.setattr(wp_shop, "vouchers", vouchers)
    monkeypatch.setattr(wp_shop, "redeem", redeem)
    monkeypatch.setattr(coordinator, "_http_session", lambda: None)
    run(coordinator.async_update_settings(wp_enabled=True, wp_url="benessere.hotelilmarchese.it",
                                          wp_product_map={"4097:0": {"people": 2, "treatment_ids": ["trt_ingresso_90"]}}))
    run(coordinator.async_wp_new_secret())
    return state


def test_sync_pairs_and_redeems_on_arrival(coordinator, shop) -> None:
    result = run(coordinator.async_wp_sync())
    assert result["added"] == 1
    voucher = next(v for v in coordinator.vouchers if v["source"] == "wordpress")
    assert voucher["code"] == "FILIPPO-ISYM-10208-5118-4180" and voucher["wp_code"] == "filippo-ISYM-10208-5118-4180"
    assert voucher["expires_on"] == "2027-05-11" and voucher["value"] == 80.0
    assert [p["treatment_ids"] for p in voucher["people"]] == [["trt_ingresso_90"], ["trt_ingresso_90"]]
    # Twice: no duplicate.
    assert run(coordinator.async_wp_sync())["added"] == 0
    # Booked with the code (two people, the paired treatment): redeemed here, not yet on the site.
    booked = run(coordinator.async_create_bookings([{
        "treatment_id": "trt_ingresso_90",
        "entries": [{"start": "2026-11-14 10:00", "first_name": "Nicoletta", "phone": "333 7654321", "person": 0,
                     "payment": {"voucher_code": voucher["code"]}},
                    {"start": "2026-11-14 10:00", "first_name": "Ospite", "phone": "333 7654321", "person": 1,
                     "payment": {"voucher_code": voucher["code"]}}],
    }]))
    assert voucher["status"] == "redeemed" and not voucher["wp_redeemed"] and shop["redeemed"] == []
    first = booked["appointments"][0]["id"]
    run(coordinator.async_check_in_appointment(first))
    assert shop["redeemed"] == ["filippo-ISYM-10208-5118-4180"] and voucher["wp_redeemed"]


def test_used_on_site_expired_and_cancelled(coordinator, shop) -> None:
    shop["items"] = [_item(), _item("old-X-1", expires="2026-01-01"), _item("used-X-2", used=True)]
    assert run(coordinator.async_wp_sync())["added"] == 1  # the expired and the used ones are not imported
    voucher = next(v for v in coordinator.vouchers if v["source"] == "wordpress")
    shop["items"] = [_item(used=True, used_at="2026-11-13 11:00:00")]
    run(coordinator.async_wp_sync())
    assert voucher["status"] == "redeemed" and voucher["wp_redeemed"] and voucher["wp_note"] == "riscattato sul sito"


def test_unpaired_product_books_freely_and_errors(coordinator, shop, monkeypatch) -> None:
    run(coordinator.async_update_settings(wp_product_map={}))
    run(coordinator.async_wp_sync())
    voucher = next(v for v in coordinator.vouchers if v["source"] == "wordpress")
    assert voucher["people"] == []
    run(coordinator.async_create_bookings([{
        "treatment_id": "trt_ingresso_120",
        "entries": [{"start": "2026-11-14 12:00", "first_name": "Nicoletta", "phone": "333 7654321", "person": 0,
                     "payment": {"voucher_code": voucher["code"]}}],
    }]))
    assert voucher["status"] == "redeemed"

    async def broken(*args, **kwargs):
        raise wp_shop.WpShopError("Sito non raggiungibile: prova")

    monkeypatch.setattr(wp_shop, "vouchers", broken)
    assert "error" in run(coordinator.async_wp_sync())
    assert coordinator._data["settings"]["wp_last_error"].startswith("Sito non raggiungibile")
    with pytest.raises(NotFoundError):
        run(coordinator.async_wp_redeem("nope"))


def test_mapping_helpers() -> None:
    mapping = {"4097:5118": {"people": 1, "treatment_ids": ["a", "b"]}, "4097:0": {"people": 2, "treatment_ids": ["c"]}}
    assert wp_shop.mapping_for(mapping, 4097, 5118)["treatment_ids"] == ["a", "b"]
    assert wp_shop.mapping_for(mapping, 4097, 9999)["people"] == 2
    assert wp_shop.mapping_for(mapping, 1, 0) is None
    assert len(wp_shop.people_of({"people": 3, "treatment_ids": ["a"]})) == 3


def test_pairing_again_updates_unused_vouchers(coordinator, shop) -> None:
    """2.7.1: a package paired later, with accessories and a note, updates the vouchers received."""
    run(coordinator.async_update_settings(wp_product_map={}))
    run(coordinator.async_wp_sync())
    voucher = next(v for v in coordinator.vouchers if v["source"] == "wordpress")
    assert voucher["people"] == []
    run(coordinator.async_update_settings(wp_product_map={"4097:5118": {
        "people": 2, "treatment_ids": ["trt_ingresso_90"], "extras": ["kit"], "note": "calice di prosecco"}}))
    assert [p["extras"] for p in voucher["people"]] == [["kit"], ["kit"]]
    assert voucher["package_note"] == "calice di prosecco"
    # Unpaired again: back to «book what was bought».
    run(coordinator.async_update_settings(wp_product_map={}))
    assert voucher["people"] == [] and voucher["package_note"] == ""
    # Accessories only: the voucher records them but does not force treatments.
    run(coordinator.async_update_settings(wp_product_map={"4097:0": {"people": 1, "extras": ["kit"]}}))
    assert voucher["people"][0]["treatment_ids"] == [] and voucher["people"][0]["extras"] == ["kit"]
