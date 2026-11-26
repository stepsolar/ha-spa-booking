"""Which menus each user sees (3.21.0): Configurazione › Accessi › Menu visibili.

The role gives the starting menus; the administrator turns each menu on or
off per user with the eye. A configuration tab that is on is also usable: the
services and the settings behind it are allowed to that user, nothing else
of the configuration. «Accessi» stays with the administrators, who always see
everything.
"""

from __future__ import annotations

from typing import Any

#: The menus, in the card's order: top level, then «parent.child».
MAIN = ("agenda", "nuovo", "spa", "clienti", "voucher", "whatsapp", "config")
SUB = {
    "nuovo": ("appuntamento", "nuova", "lista"),
    "spa": ("controlli", "telecamere"),
    "config": (
        "categorie", "trattamenti", "pacchetti", "accessori", "shop", "contabilita",
        "operatori", "blocchi", "notifiche", "promo", "email", "impostazioni",
    ),
}
#: Never given by the eye: only the administrators manage users.
ADMIN_ONLY = ("config.accessi",)

ALL_IDS: tuple[str, ...] = tuple(
    [*MAIN] + [f"{parent}.{child}" for parent, children in SUB.items() for child in children]
)

#: What each role sees before any eye is touched (the card's 3.20 menus).
_ROLE_MAIN = {
    "none": (),
    "read": ("agenda",),
    "therapist": ("agenda", "nuovo", "spa"),
    "operator": ("agenda", "nuovo", "spa", "clienti", "voucher", "whatsapp"),
    "manager": ("agenda", "nuovo", "spa", "clienti", "voucher", "whatsapp"),
}
_ROLE_SUB = {
    "none": (),
    "read": (),
    "therapist": ("nuovo.appuntamento", "spa.controlli"),
    "operator": ("nuovo.appuntamento", "nuovo.nuova", "nuovo.lista", "spa.controlli", "spa.telecamere"),
    "manager": ("nuovo.appuntamento", "nuovo.nuova", "nuovo.lista", "spa.controlli", "spa.telecamere"),
}


def role_menus(level: str) -> set[str]:
    """The menus a role sees on its own."""
    if level == "admin":
        return set(ALL_IDS) | set(ADMIN_ONLY)
    return set(_ROLE_MAIN.get(level, ())) | set(_ROLE_SUB.get(level, ()))


def clean_overrides(raw: Any) -> dict[str, bool]:
    """Keep only known menus with a yes or no: a bad edit grants nothing."""
    if not isinstance(raw, dict):
        return {}
    return {str(key): bool(value) for key, value in raw.items() if key in ALL_IDS and isinstance(value, bool)}


def visible_menus(level: str, overrides: Any = None) -> set[str]:
    """The menus a user sees: her role, then the administrator's eyes.

    A sub-menu needs its parent; a parent with sub-menus is shown only while
    at least one of them is on. Nobody without a role sees anything, and
    the administrators always see everything.
    """
    if level == "admin":
        return role_menus("admin")
    if level not in _ROLE_MAIN or level == "none":
        return set()
    menus = role_menus(level)
    for key, value in clean_overrides(overrides).items():
        if value:
            menus.add(key)
        else:
            menus.discard(key)
    for parent, children in SUB.items():
        kids = {f"{parent}.{child}" for child in children}
        if parent not in menus:
            menus -= kids
        elif not menus & kids:
            menus.discard(parent)
    return menus


def config_tabs(menus: set[str]) -> set[str]:
    """The configuration tabs among the visible menus («trattamenti», …)."""
    return {key.split(".", 1)[1] for key in menus if key.startswith("config.")}


#: The administrator's services behind each configuration tab. Not listed
#: (users, restore, updates, restart, AI keys…) stays with the administrators.
TAB_SERVICES: dict[str, frozenset[str]] = {
    "categorie": frozenset({"add_category", "update_category", "delete_category"}),
    "trattamenti": frozenset({"add_treatment", "update_treatment", "delete_treatment"}),
    "pacchetti": frozenset({"wp_product", "wp_product_update"}),
    "accessori": frozenset(),
    "shop": frozenset({"wp_test", "wp_product", "wp_product_update", "wp_orders", "wp_order", "wp_order_update"}),
    "contabilita": frozenset({"get_monthly_report"}),
    "operatori": frozenset({"add_operator", "update_operator", "delete_operator", "send_operator_message"}),
    "blocchi": frozenset({"add_closure", "delete_closure", "clear_slot_block"}),
    "notifiche": frozenset({"send_test_message", "voucher_expiry_reminder"}),
    "promo": frozenset({"send_promo", "promo_automatico", "promo_voucher_tick"}),
    "email": frozenset({"test_email", "google_auth_url", "google_disconnect"}),
    "impostazioni": frozenset({
        "check_waha", "whatsapp_status", "whatsapp_pair", "whatsapp_pair_code", "whatsapp_logout",
        "telegram_status", "export_all", "export_clienti_csv", "import_clienti_csv", "web_snippet",
        "export_dashboard_yaml", "reload_card",
    }),
}


def service_allowed(service: str, menus: set[str]) -> bool:
    """Whether a visible configuration tab opens this administrator's service."""
    return any(service in TAB_SERVICES.get(tab, ()) for tab in config_tabs(menus))


#: Settings only an administrator changes, whatever the eyes say.
ADMIN_SETTINGS = frozenset({"web_token", "pin_idle_minutes", "telegram_bot_token"})
#: Secrets: a user who is not an administrator reads them blank, so a blank
#: one coming back is dropped instead of wiping the stored value.
SECRET_SETTINGS = frozenset({"smtp_password", "google_client_secret", "telegram_bot_token", "web_token"})

_NOTIFY_PREFIXES = (
    "appointment_reminder_", "review_request_", "offer_", "report_", "low_spa_", "deposit_",
    "op_", "request_",
)
_NOTIFY_KEYS = frozenset({
    "cancel_message", "change_message", "summary_message", "summary_test_phone", "move_proposal_message",
    "quiet_hours_start", "quiet_hours_end", "notifiche_order", "guest_header", "chat_in_cards",
})


def setting_tab(key: str) -> str:
    """The configuration tab a setting belongs to («impostazioni» by default)."""
    if key.startswith("ai_"):
        return "accessi"  # the AI keys: administrators only
    if key == "categories_order":
        return "categorie"
    if key in ("treatments_order", "vat_default"):
        return "trattamenti"
    if key in ("wp_product_map", "package_order") or key.startswith("package_hidden_"):
        return "pacchetti"
    if key == "accessories":
        return "accessori"
    if key.startswith("wp_") or key == "site_coupon_prefix":
        return "shop"
    if key.startswith(("promo", "loyalty_", "partner_")) or key == "voucher_points_message":
        return "promo"
    if key.startswith(("email_", "smtp_", "google_")):
        return "email"
    if key in _NOTIFY_KEYS or key.startswith(_NOTIFY_PREFIXES):
        return "notifiche"
    return "impostazioni"


def settings_refused(keys: set[str], menus: set[str]) -> set[str]:
    """The settings among ``keys`` that the visible tabs do not open."""
    tabs = config_tabs(menus)
    return {key for key in keys if key in ADMIN_SETTINGS or setting_tab(key) not in tabs}
