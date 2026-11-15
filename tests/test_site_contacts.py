"""3.3.0: the people of the site, the newsletter codes and their campaigns."""

from __future__ import annotations

import pytest

from custom_components.spa_booking import site_contacts as site_mod, wp_shop
from custom_components.spa_booking.exceptions import ValidationError

from .conftest import run

MASSAGE = "trt_massaggio_relax_90"


def test_merge_keeps_one_card_per_person() -> None:
    old = [site_mod.norm_contact({"email": "anna@x.it", "unsubscribed": True, "campaigns_sent": 3})]
    merged = site_mod.merge(
        old,
        [{"email": "Anna@x.it", "first": "Anna", "status": "C", "created": "2026-10-01"}],
        [{"email": "anna@x.it", "first": "Anna", "last": "Rossi", "phone": "333", "orders": 2, "total": 160}],
        [{"email": "", "phone": "347 1234567", "first_name": "Luca", "at": "2026-11-01", "marketing": True}],
    )
    anna = next(c for c in merged if c["email"] == "anna@x.it")
    assert anna["newsletter"] == "C" and anna["shop_orders"] == 2 and anna["last_name"] == "Rossi"
    assert anna["unsubscribed"] and anna["campaigns_sent"] == 3  # what only Spa Booking knows stays
    assert not site_mod.can_mail(anna)
    luca = next(c for c in merged if c["key"] == "tel:393471234567")
    assert luca["web_bookings"] == 1 and luca["web_consent"] and not site_mod.can_mail(luca)  # no e-mail


@pytest.fixture
def site(coordinator, monkeypatch, freeze):
    freeze("2026-11-15 10:00")
    state = {"used": [], "coupons": [
        {"code": "welcomeab12", "email": "giulia@x.it", "type": "percent", "amount": 5, "min_amount": 100,
         "expires": "2026-12-01", "created": "2026-11-01T10:00:00", "used": False},
        {"code": "welcomezz99", "email": "old@x.it", "type": "percent", "amount": 5, "min_amount": 100,
         "expires": "2026-10-01", "created": "2026-09-01T10:00:00", "used": True},
    ]}

    async def contacts(session, base, secret, prefix="welcome"):
        return {"newsletter": [{"email": "giulia@x.it", "first": "Giulia", "last": "Martino", "status": "C"},
                               {"email": "via@x.it", "first": "Via", "status": "U"}],
                "buyers": [{"email": "luca@x.it", "first": "Luca", "orders": 1, "total": 80}],
                "coupons": state["coupons"]}

    async def coupon_use(session, base, secret, code):
        state["used"].append(code)
        return {"ok": True}

    monkeypatch.setattr(wp_shop, "contacts", contacts)
    monkeypatch.setattr(wp_shop, "coupon_use", coupon_use)
    monkeypatch.setattr(coordinator, "_http_session", lambda: None)
    tasks = []
    coordinator.hass.async_create_task = tasks.append
    state["tasks"] = tasks
    run(coordinator.async_update_settings(wp_enabled=True, wp_url="benessere.hotelilmarchese.it"))
    run(coordinator.async_wp_new_secret())
    return state


def test_sync_people_and_codes(coordinator, site) -> None:
    result = run(coordinator.async_site_sync())
    assert result["contacts"] == 3 and result["coupons_added"] == 2
    code = next(v for v in coordinator.promo_vouchers if v["code"] == "WELCOMEAB12")
    assert code["source"] == "newsletter" and code["discount_percent"] == 5 and code["min_spend"] == 100
    assert code["first_name"] == "Giulia" and code["status"] == "sent"
    assert next(v for v in coordinator.promo_vouchers if v["code"] == "WELCOMEZZ99")["status"] == "redeemed"
    targets = {c["email"] for c in coordinator.site_campaign_targets(["newsletter", "shop"])}
    assert targets == {"giulia@x.it", "luca@x.it"}  # "via" left the newsletter
    assert {c["email"] for c in coordinator.site_campaign_targets(["coupon"])} == {"giulia@x.it"}
    # Again: nothing doubled.
    run(coordinator.async_site_sync())
    assert len([v for v in coordinator.promo_vouchers if v.get("source") == "newsletter"]) == 2


def test_code_on_booking_gives_the_discount_and_is_used_on_the_shop(coordinator, site) -> None:
    run(coordinator.async_site_sync())
    next(t for t in coordinator.treatments if t["id"] == MASSAGE)["price"] = 80.0

    ops = [o["id"] for o in coordinator.operators]

    def rows(people):
        return [{"treatment_id": MASSAGE, "entries": [
            {"start": "2026-11-16T10:00:00", "first_name": "Giulia", "phone": "347 1234567", "person": p,
             "operator_ids": ops, "voucher_code": "welcomeab12"} for p in range(people)]}]

    with pytest.raises(ValidationError, match="spesa da"):
        run(coordinator.async_create_bookings(rows(1)))  # 80 € < 100 €
    booked = run(coordinator.async_create_bookings(rows(2)))["appointments"]
    live = [next(a for a in coordinator.appointments if a["id"] == b["id"]) for b in booked]
    assert [a["price"] for a in live] == [76.0, 76.0] and live[0]["promo_code"] == "WELCOMEAB12"
    code = next(v for v in coordinator.promo_vouchers if v["code"] == "WELCOMEAB12")
    assert code["status"] == "redeemed"
    for task in site["tasks"]:
        run(task)
    assert site["used"] == ["welcomeab12"] and code["wp_used"]


def test_web_request_joins_the_list_and_campaign_unsubscribe(coordinator, site) -> None:
    run(coordinator.async_site_sync())
    run(coordinator.async_create_request(first_name="Marco", phone="+39 320 0000003", email="marco@x.it",
                                         date="2026-11-20", entries=[{"treatment_id": MASSAGE, "time": "10:00"}],
                                         source="web", marketing=True))
    marco = next(c for c in coordinator.site_contacts if c["email"] == "marco@x.it")
    assert marco["web_bookings"] == 1 and site_mod.can_mail(marco)
    giulia = next(c for c in coordinator.site_contacts if c["email"] == "giulia@x.it")
    subject, body, _html = coordinator.format_site_campaign("Per te {nome}", "Il tuo codice {codice_sconto} scade il {scadenza_sconto}", giulia)
    assert subject == "Per te Giulia" and "welcomeab12 scade il 01/12/2026" in body
    run(coordinator.async_site_unsubscribe(giulia["unsub_token"]))
    assert not site_mod.can_mail(giulia)
    run(coordinator.async_site_sync())  # the site does not bring her back
    assert next(c for c in coordinator.site_contacts if c["email"] == "giulia@x.it")["unsubscribed"]
