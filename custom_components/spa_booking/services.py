"""Services exposed by the SPA Booking integration.

Handlers read the coordinator from `hass.data[DOMAIN]`, so they always act on
the loaded dataset and raise `HomeAssistantError` subclasses (SpaBookingError)
that Home Assistant surfaces as a readable error in the UI.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import time
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import config_validation as cv

from .const import (
    APPEARANCE_MODES,
    CLOSURE_SCOPES,
    ATTR_APPOINTMENT_ID,
    ATTR_APPOINTMENT_IDS,
    ATTR_CATEGORY_ID,
    ATTR_CHANNEL,
    ATTR_CHECKED_IN,
    ATTR_CHAT_ID,
    ATTR_CLIENT_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DATE,
    ATTR_EXTRAS,
    ATTR_FORCE_NEW,
    ATTR_GUEST_TYPE,
    ATTR_KIND,
    ATTR_LIMIT,
    ATTR_MONTH,
    ATTR_NOTIFY,
    ATTR_OPERATOR_ID,
    ATTR_OPERATOR_IDS,
    ATTR_PAYLOAD,
    ATTR_PAYMENT,
    ATTR_QUERY,
    ATTR_REASON,
    ATTR_RESPONSE,
    ATTR_ROWS,
    ATTR_SOURCE,
    ATTR_STATE,
    ATTR_TREATMENT_ID,
    ATTR_USER_ID,
    ATTR_LEVEL,
    ATTR_REQUEST_ID,
    ATTR_PEOPLE,
    ATTR_ENTRIES,
    ATTR_METHOD,
    ATTR_AMOUNT,
    ATTR_PAYMENT_ID,
    ATTR_TIME,
    DEFAULT_CATEGORY_PAUSE_MIN,
    DOMAIN,
    GUEST_TYPE_DEFAULT,
    GUEST_TYPES,
    OPERATOR_ROLE_DEFAULT,
    OPERATOR_ROLES,
    PAYMENT_METHODS,
    KEY_PROFILES,
    PERMISSION_LEVELS,
)
from .coordinator import ACTOR, FORCE_RULES, INTEGRATION_VERSION, SpaBookingCoordinator
from .normalize import as_date
from . import access, messaging, updates
from .exceptions import SpaBookingError, ValidationError
from .waha import WahaError

#: The accepted method names, taken from the single place they are declared.
PAYMENT_METHOD_NAMES = tuple(name for name, _, _ in PAYMENT_METHODS)

#: The accepted operator roles, from the same single place.
OPERATOR_ROLE_NAMES = tuple(role for role, _, _ in OPERATOR_ROLES)

#: The accepted guest types, from the same single place.
GUEST_TYPE_NAMES = tuple(name for name, _, _ in GUEST_TYPES)

SERVICE_CREATE_APPOINTMENT = "create_appointment"
SERVICE_CANCEL_APPOINTMENT = "cancel_appointment"
SERVICE_DELETE_APPOINTMENT = "delete_appointment"
SERVICE_UPDATE_APPOINTMENT = "update_appointment"
SERVICE_CHECK_IN_APPOINTMENT = "check_in_appointment"
SERVICE_CHECK_OUT_APPOINTMENT = "check_out_appointment"
SERVICE_SAVE_CLIENT = "save_client"
SERVICE_SEARCH_CLIENTS = "search_clients"
SERVICE_DELETE_CLIENT = "delete_client"
SERVICE_MERGE_CLIENTS = "merge_clients"
SERVICE_GET_CLIENT_HISTORY = "get_client_history"
SERVICE_GET_DAILY_AGENDA = "get_daily_agenda"
SERVICE_GET_CONFIG = "get_config"
SERVICE_ADD_CATEGORY = "add_category"
SERVICE_UPDATE_CATEGORY = "update_category"
SERVICE_DELETE_CATEGORY = "delete_category"
SERVICE_ADD_TREATMENT = "add_treatment"
SERVICE_UPDATE_TREATMENT = "update_treatment"
SERVICE_DELETE_TREATMENT = "delete_treatment"
SERVICE_ADD_OPERATOR = "add_operator"
SERVICE_UPDATE_OPERATOR = "update_operator"
SERVICE_DELETE_OPERATOR = "delete_operator"
SERVICE_EXPORT_DATA = "export_data"
SERVICE_IMPORT_DATA = "import_data"
SERVICE_EXPORT_CLIENTS_CSV = "export_clienti_csv"
SERVICE_IMPORT_CLIENTS_CSV = "import_clienti_csv"
SERVICE_GET_MONTHLY_REPORT = "get_monthly_report"
SERVICE_UPDATE_SETTINGS = "update_settings"
SERVICE_CHECK_WAHA = "check_waha"
SERVICE_RESPOND_TO_OFFER = "respond_to_offer"
SERVICE_CREATE_BOOKINGS = "create_bookings"
SERVICE_CLEAR_SLOT_BLOCK = "clear_slot_block"
SERVICE_ADD_CLOSURE = "add_closure"
SERVICE_DELETE_CLOSURE = "delete_closure"
SERVICE_RESIZE_APPOINTMENT_GROUP = "resize_appointment_group"
SERVICE_EXPIRE_OFFERS = "expire_offers"
SERVICE_RELOAD_CARD = "reload_card"
SERVICE_SEND_TEST_MESSAGE = "send_test_message"
SERVICE_SET_OFFER_STATE = "set_offer_state"
SERVICE_MANUAL_CONFIRM_OFFER = "manual_confirm_offer"
SERVICE_CREATE_VOUCHER = "create_voucher"
SERVICE_EXTEND_VOUCHER = "extend_voucher"
SERVICE_DELETE_VOUCHER = "delete_voucher"
SERVICE_REDEEM_PROMO_VOUCHER = "redeem_promo_voucher"
SERVICE_DELETE_PROMO_VOUCHER = "delete_promo_voucher"
SERVICE_LOYALTY_REWARD = "loyalty_reward"
SERVICE_LOYALTY_ADJUST = "loyalty_adjust"
SERVICE_SAVE_PARTNER = "save_partner"
SERVICE_PARTNER_POINTS_ADJUST = "partner_points_adjust"
SERVICE_SET_APPOINTMENT_PARTNER = "set_appointment_partner"
SERVICE_SEND_PARTNER_CAMPAIGN = "send_partner_campaign"
SERVICE_DELETE_PARTNER = "delete_partner"
SERVICE_IMPORT_PARTNERS = "import_partners"
SERVICE_DELETE_ALL_PARTNERS = "delete_all_partners"
SERVICE_PARTNER_DETAIL = "partner_detail"
SERVICE_SEND_LOYALTY_VOUCHER = "send_loyalty_voucher"
SERVICE_TELEGRAM_STATUS = "telegram_status"
SERVICE_SPLIT_FROM_GROUP = "split_from_group"
SERVICE_JOIN_GROUP = "join_group"
SERVICE_PARTNER_REWARD = "partner_reward"
SERVICE_WP_SYNC = "wp_sync"
SERVICE_WP_TEST = "wp_test"
SERVICE_WP_NEW_SECRET = "wp_new_secret"
SERVICE_WP_REDEEM = "wp_redeem"
SERVICE_PROMO_VOUCHER_TICK = "promo_voucher_tick"
SERVICE_SEND_OPERATOR_MESSAGE = "send_operator_message"
SERVICE_SEND_GUEST_SUMMARY = "send_guest_summary"
SERVICE_SEND_DEPOSIT_REQUEST = "send_deposit_request"
SERVICE_SEND_PROMO = "send_promo"
SERVICE_PROMO_AUTOMATIC = "promo_automatico"
SERVICE_SEND_REMINDERS = "send_reminders"
SERVICE_SEND_REVIEW_REQUESTS = "send_review_requests"
SERVICE_VOUCHER_EXPIRY_REMINDER = "voucher_expiry_reminder"
SERVICE_GET_USERS = "get_users"
SERVICE_SET_USER_PERMISSIONS = "set_user_permissions"
SERVICE_WHOAMI = "whoami"
SERVICE_UPDATE_STATUS = "update_status"
SERVICE_INSTALL_UPDATE = "install_update"
SERVICE_RESTART_HOME_ASSISTANT = "restart_home_assistant"
SERVICE_PIN_LOGIN = "pin_login"
SERVICE_PIN_LOGOUT = "pin_logout"
SERVICE_SET_USER_PROFILE = "set_user_profile"
SERVICE_CREATE_USER = "create_user"
SERVICE_SET_USER_PASSWORD = "set_user_password"
SERVICE_SET_USER_ACTIVE = "set_user_active"
SERVICE_CREATE_REQUEST = "create_request"
SERVICE_DELETE_REQUEST = "delete_request"
SERVICE_CONFIRM_REQUEST = "confirm_request"
SERVICE_SEND_REQUEST_MESSAGE = "send_request_message"
SERVICE_PROPOSE_REQUEST_DATE = "propose_request_date"
SERVICE_TEST_WEB_NOTICE = "test_web_notice"
SERVICE_SEND_EMAIL = "send_email"
SERVICE_GOOGLE_AUTH_URL = "google_auth_url"
SERVICE_GOOGLE_DISCONNECT = "google_disconnect"
SERVICE_GDRIVE_BACKUP = "gdrive_backup"
SERVICE_GDRIVE_LIST = "gdrive_list"
SERVICE_GDRIVE_RESTORE = "gdrive_restore"
SERVICE_TEST_EMAIL = "test_email"
SERVICE_WHATSAPP_CHATS = "whatsapp_chats"
SERVICE_DELETE_WHATSAPP_CHATS = "delete_whatsapp_chats"
SERVICE_ADD_PAYMENT = "add_payment"
SERVICE_DELETE_PAYMENT = "delete_payment"
#: The card's bell (clear it once the desk has read the web requests) and the
#: website's shared secret (rotated the moment it is thought to be leaked).
SERVICE_MARK_REQUESTS_SEEN = "mark_requests_seen"
SERVICE_REGENERATE_PUBLIC_TOKEN = "regenerate_public_token"
SERVICE_WEB_SNIPPET = "web_snippet"
SERVICE_SEND_EXTERNAL_MESSAGE = "send_external_message"
SERVICE_UPDATE_BOOKING_BATCH = "update_booking_batch"
SERVICE_EXPORT_ALL = "export_all"
SERVICE_EXPORT_DASHBOARD_YAML = "export_dashboard_yaml"
SERVICE_IMPORT_ALL = "import_all"
SERVICE_GET_DASHBOARD_CONFIG = "get_dashboard_config"
SERVICE_RUN_SCHEDULED_JOBS = "run_scheduled_jobs"
SERVICE_WHATSAPP_STATUS = "whatsapp_status"
SERVICE_WHATSAPP_PAIR = "whatsapp_pair"
SERVICE_WHATSAPP_PAIR_CODE = "whatsapp_pair_code"
SERVICE_WHATSAPP_LOGOUT = "whatsapp_logout"

ALL_SERVICES = (
    SERVICE_CREATE_APPOINTMENT,
    SERVICE_CANCEL_APPOINTMENT,
    SERVICE_DELETE_APPOINTMENT,
    SERVICE_UPDATE_APPOINTMENT,
    SERVICE_CHECK_IN_APPOINTMENT,
    SERVICE_CHECK_OUT_APPOINTMENT,
    SERVICE_SAVE_CLIENT,
    SERVICE_SEARCH_CLIENTS,
    SERVICE_DELETE_CLIENT,
    SERVICE_MERGE_CLIENTS,
    SERVICE_GET_CLIENT_HISTORY,
    SERVICE_GET_DAILY_AGENDA,
    SERVICE_GET_CONFIG,
    SERVICE_ADD_CATEGORY,
    SERVICE_UPDATE_CATEGORY,
    SERVICE_DELETE_CATEGORY,
    SERVICE_ADD_TREATMENT,
    SERVICE_UPDATE_TREATMENT,
    SERVICE_DELETE_TREATMENT,
    SERVICE_ADD_OPERATOR,
    SERVICE_UPDATE_OPERATOR,
    SERVICE_DELETE_OPERATOR,
    SERVICE_EXPORT_DATA,
    SERVICE_IMPORT_DATA,
    SERVICE_EXPORT_CLIENTS_CSV,
    SERVICE_IMPORT_CLIENTS_CSV,
    SERVICE_GET_MONTHLY_REPORT,
    SERVICE_UPDATE_SETTINGS,
    SERVICE_CHECK_WAHA,
    SERVICE_RESPOND_TO_OFFER,
    SERVICE_CREATE_BOOKINGS,
    SERVICE_CLEAR_SLOT_BLOCK,
    SERVICE_ADD_CLOSURE,
    SERVICE_DELETE_CLOSURE,
    SERVICE_RESIZE_APPOINTMENT_GROUP,
    SERVICE_EXPIRE_OFFERS,
    SERVICE_RELOAD_CARD,
    SERVICE_SEND_TEST_MESSAGE,
    SERVICE_SET_OFFER_STATE,
    SERVICE_MANUAL_CONFIRM_OFFER,
    SERVICE_CREATE_VOUCHER,
    SERVICE_EXTEND_VOUCHER,
    SERVICE_DELETE_VOUCHER,
    SERVICE_REDEEM_PROMO_VOUCHER,
    SERVICE_DELETE_PROMO_VOUCHER,
    SERVICE_LOYALTY_REWARD,
    SERVICE_LOYALTY_ADJUST,
    SERVICE_SAVE_PARTNER,
    SERVICE_PARTNER_POINTS_ADJUST,
    SERVICE_SET_APPOINTMENT_PARTNER,
    SERVICE_SEND_PARTNER_CAMPAIGN,
    SERVICE_DELETE_PARTNER,
    SERVICE_IMPORT_PARTNERS,
    SERVICE_DELETE_ALL_PARTNERS,
    SERVICE_PARTNER_DETAIL,
    SERVICE_SEND_LOYALTY_VOUCHER,
    SERVICE_TELEGRAM_STATUS,
    SERVICE_PARTNER_REWARD,
    SERVICE_SPLIT_FROM_GROUP,
    SERVICE_JOIN_GROUP,
    SERVICE_WP_SYNC,
    SERVICE_WP_TEST,
    SERVICE_WP_NEW_SECRET,
    SERVICE_WP_REDEEM,
    SERVICE_PROMO_VOUCHER_TICK,
    SERVICE_SEND_OPERATOR_MESSAGE,
    SERVICE_SEND_GUEST_SUMMARY,
    SERVICE_SEND_DEPOSIT_REQUEST,
    SERVICE_SEND_REMINDERS,
    SERVICE_SEND_REVIEW_REQUESTS,
    SERVICE_VOUCHER_EXPIRY_REMINDER,
    SERVICE_SEND_PROMO,
    SERVICE_PROMO_AUTOMATIC,
    SERVICE_GET_USERS,
    SERVICE_SET_USER_PERMISSIONS,
    SERVICE_WHOAMI,
    SERVICE_UPDATE_STATUS,
    SERVICE_INSTALL_UPDATE,
    SERVICE_RESTART_HOME_ASSISTANT,
    SERVICE_PIN_LOGIN,
    SERVICE_PIN_LOGOUT,
    SERVICE_SET_USER_PROFILE,
    SERVICE_CREATE_USER,
    SERVICE_SET_USER_PASSWORD,
    SERVICE_SET_USER_ACTIVE,
    SERVICE_CREATE_REQUEST,
    SERVICE_DELETE_REQUEST,
    SERVICE_CONFIRM_REQUEST,
    SERVICE_SEND_REQUEST_MESSAGE,
    SERVICE_PROPOSE_REQUEST_DATE,
    SERVICE_TEST_WEB_NOTICE,
    SERVICE_SEND_EMAIL,
    SERVICE_GOOGLE_AUTH_URL,
    SERVICE_GOOGLE_DISCONNECT,
    SERVICE_TEST_EMAIL,
    SERVICE_WHATSAPP_CHATS,
    SERVICE_DELETE_WHATSAPP_CHATS,
    SERVICE_ADD_PAYMENT,
    SERVICE_DELETE_PAYMENT,
    SERVICE_MARK_REQUESTS_SEEN,
    SERVICE_REGENERATE_PUBLIC_TOKEN,
    SERVICE_WEB_SNIPPET,
    SERVICE_SEND_EXTERNAL_MESSAGE,
    SERVICE_EXPORT_ALL,
    SERVICE_IMPORT_ALL,
    SERVICE_GET_DASHBOARD_CONFIG,
    SERVICE_EXPORT_DASHBOARD_YAML,
    SERVICE_UPDATE_BOOKING_BATCH,
    SERVICE_RUN_SCHEDULED_JOBS,
    SERVICE_WHATSAPP_STATUS,
    SERVICE_WHATSAPP_PAIR,
    SERVICE_WHATSAPP_PAIR_CODE,
    SERVICE_WHATSAPP_LOGOUT,
)

_CLIENT_FIELDS = {
    vol.Optional("first_name"): cv.string,
    vol.Optional("last_name"): cv.string,
    vol.Optional("phone"): cv.string,
    vol.Optional("email"): cv.string,
    vol.Optional("client_notes"): cv.string,
}

#: How the guest pays. The four flags are independent on purpose: a deposit
#: and the balance still owed are both true at once. "Paid" carries its own
#: amount rather than meaning "every other flag is off".
PAYMENT_SCHEMA = vol.Schema(
    {
        vol.Optional("paid"): cv.boolean,
        vol.Optional("paid_amount"): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("deposit"): cv.boolean,
        vol.Optional("deposit_amount"): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional("voucher"): cv.boolean,
        vol.Optional("voucher_code"): cv.string,
        vol.Optional("balance_due"): cv.boolean,
        vol.Optional("balance_due_amount"): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        #: The ways of paying, several at once. Unknown names are refused here
        #: so a typo cannot quietly become an empty method.
        vol.Optional("methods"): vol.All(cv.ensure_list, [vol.In(PAYMENT_METHOD_NAMES)]),
    },
    extra=vol.PREVENT_EXTRA,
)

CREATE_APPOINTMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TREATMENT_ID): cv.string,
        vol.Required("start"): cv.datetime,
        vol.Optional(ATTR_CLIENT_ID): vol.Any(cv.string, None),
        **_CLIENT_FIELDS,
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        #: The candidates to offer, in order. Leave it out and the operator_id
        #: alone is used, so the form's "automatica" is just the full list.
        vol.Optional(ATTR_OPERATOR_IDS): vol.All(
            cv.ensure_list, [cv.string]
        ),
        #: The guest would like a woman ("F") or a man ("M"); "" = anybody.
        vol.Optional("therapist_preference"): vol.Any(vol.In(("", "F", "M")), None),
        #: The partner who brought the booking (id or code, 2.5.0).
        vol.Optional("partner_id"): vol.Any(cv.string, None),
        vol.Optional("notes"): cv.string,
        vol.Optional(ATTR_PAYMENT): vol.Any(PAYMENT_SCHEMA, None),
        #: Take the booking and leave it waiting. Any money on it confirms it
        #: anyway, so pending + payment comes out confirmed.
        vol.Optional("pending", default=False): cv.boolean,
        #: Hotel guest or from outside. No business rule uses it: it only
        #: labels the booking for the agenda and its filters.
        vol.Optional(ATTR_GUEST_TYPE, default=GUEST_TYPE_DEFAULT): vol.In(
            GUEST_TYPE_NAMES
        ),
        #: The accessories this person gets with the booking, unknown ones
        #: dropped by the coordinator. Leave it out for none.
        vol.Optional(ATTR_EXTRAS): vol.All(cv.ensure_list, [cv.string]),
        #: Per-row price overrides, both editable from the card: the list
        #: price and the discounted one. Leave them out for catalogue price.
        vol.Optional("list_price"): vol.Any(vol.Coerce(float), None),
        vol.Optional("price"): vol.Any(vol.Coerce(float), None),
        #: The shop package this treatment belongs to (2.8.9) and which copy
        #: of it (two couples, two packages): its price is shared out.
        vol.Optional("package_key"): vol.Any(cv.string, None),
        vol.Optional("package_group"): vol.Any(cv.string, None),
        #: The desk saw the overlap warning and books anyway: skips only the
        #: same-person client refusal, never an operator double-booking.
        vol.Optional("batch_id"): vol.Any(cv.string, None),
        vol.Optional("force_client_overlap", default=False): cv.boolean,
        #: The desk saw the category warning (days, time windows,
        #: exclusions) and books anyway. Reception and above only.
        vol.Optional("force_rules", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

CANCEL_APPOINTMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Optional(ATTR_REASON): cv.string,
        # 2.8.7: the whole party at once, and the message to the guest.
        vol.Optional("whole_group", default=False): cv.boolean,
        vol.Optional("notify_guest", default=False): cv.boolean,
    }
)

SAVE_CLIENT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CLIENT_ID): vol.Any(cv.string, None),
        vol.Optional("first_name"): cv.string,
        vol.Optional("last_name"): cv.string,
        vol.Optional("phone"): cv.string,
        vol.Optional("email"): cv.string,
        vol.Optional("notes"): cv.string,
        vol.Optional("promo_opt_in"): vol.Any(cv.boolean, None),
    }
)

SEARCH_CLIENTS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_QUERY, default=""): cv.string,
        vol.Optional(ATTR_LIMIT, default=20): cv.positive_int,
    }
)

GET_CLIENT_HISTORY_SCHEMA = vol.Schema({vol.Required(ATTR_CLIENT_ID): cv.string})
DELETE_CLIENT_SCHEMA = vol.Schema({vol.Required(ATTR_CLIENT_ID): cv.string})

MERGE_CLIENTS_SCHEMA = vol.Schema(
    {
        vol.Required("target_client_id"): cv.string,
        vol.Required("source_client_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)
DELETE_APPOINTMENT_SCHEMA = vol.Schema({vol.Required(ATTR_APPOINTMENT_ID): cv.string})

UPDATE_APPOINTMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        #: The guest would like a woman ("F") or a man ("M"); "" = anybody.
        vol.Optional("therapist_preference"): vol.Any(vol.In(("", "F", "M")), None),

        vol.Optional(ATTR_TREATMENT_ID): vol.Any(cv.string, None),
        vol.Optional("start"): vol.Any(cv.string, None),
        vol.Optional(ATTR_CLIENT_ID): vol.Any(cv.string, None),
        vol.Optional("first_name"): vol.Any(cv.string, None),
        vol.Optional("last_name"): vol.Any(cv.string, None),
        vol.Optional("phone"): vol.Any(cv.string, None),
        vol.Optional("email"): vol.Any(cv.string, None),
        vol.Optional("client_notes"): vol.Any(cv.string, None),
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        vol.Optional(ATTR_OPERATOR_IDS): vol.Any(cv.ensure_list, [cv.string], None),
        vol.Optional("notes"): vol.Any(cv.string, None),
        #: Omit to keep the payment the appointment already has; send it to
        #: replace the whole set, which is what makes clearing a flag work.
        vol.Optional(ATTR_PAYMENT): vol.Any(PAYMENT_SCHEMA, None),
        #: Omit to leave the status alone. True puts it back to waiting, false
        #: confirms it — and payment alone confirms it too.
        vol.Optional("pending"): vol.Any(cv.boolean, None),
        #: Who confirms it. Recorded with the moment of the confirmation.
        vol.Optional("confirmed_by"): vol.Any(cv.string, None),
        #: Omit to keep the hotel/external flag the appointment already has;
        #: send it to change it.
        vol.Optional(ATTR_GUEST_TYPE): vol.Any(vol.In(GUEST_TYPE_NAMES), None),
        #: Omit to keep the accessories the appointment already has; send a
        #: list to replace them, an empty one to clear them all.
        vol.Optional(ATTR_EXTRAS): vol.Any(
            vol.All(cv.ensure_list, [cv.string]), None
        ),
        #: Omit to keep the agreed prices; send a number to change one.
        vol.Optional("list_price"): vol.Any(vol.Coerce(float), None),
        vol.Optional("price"): vol.Any(vol.Coerce(float), None),
        #: The desk saw the overlap warning and confirms anyway: skips only
        #: the same-person client refusal, never an operator double-booking.
        vol.Optional("force_client_overlap", default=False): cv.boolean,
        #: The desk saw the category warning (days, time windows,
        #: exclusions) and books anyway. Reception and above only.
        vol.Optional("force_rules", default=False): cv.boolean,
        #: Apply the same edit to every appointment of the group (same client,
        #: treatment and slot) instead of only this one.
        vol.Optional("whole_group", default=False): cv.boolean,
    }
)

ADD_CLOSURE_SCHEMA = vol.Schema(
    {
        vol.Optional("scope", default="facility"): vol.In(CLOSURE_SCOPES),
        vol.Optional(ATTR_OPERATOR_ID, default=""): cv.string,
        vol.Optional(ATTR_CATEGORY_ID, default=""): cv.string,
        vol.Required("date_from"): cv.string,
        vol.Optional("date_to", default=""): cv.string,
        vol.Optional("start", default=""): cv.string,
        vol.Optional("end", default=""): cv.string,
        vol.Optional("label", default=""): cv.string,
        vol.Optional("skip_weekdays", default=list): vol.All(
            cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))]
        ),
    }
)

DELETE_CLOSURE_SCHEMA = vol.Schema({vol.Required("closure_id"): cv.string})

RESIZE_APPOINTMENT_GROUP_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Required("persons"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
    }
)

CHECK_IN_APPOINTMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Optional(ATTR_CHECKED_IN, default=True): cv.boolean,
        # 2.9.0: other people of the group entering (or leaving) together.
        vol.Optional("appointment_ids"): [cv.string],
    }
)
CHECK_OUT_APPOINTMENT_SCHEMA = vol.Schema(
    {vol.Required(ATTR_APPOINTMENT_ID): cv.string, vol.Optional("appointment_ids"): [cv.string]}
)

RELOAD_CARD_SCHEMA = vol.Schema({vol.Optional("version", default=""): cv.string})

GET_USERS_SCHEMA = vol.Schema({})

SET_USER_PERMISSIONS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_USER_ID): cv.string,
        vol.Required(ATTR_LEVEL): vol.In(PERMISSION_LEVELS),
    }
)

GET_DAILY_AGENDA_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DATE): vol.Any(cv.date, cv.string),
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        vol.Optional(ATTR_CATEGORY_ID): vol.Any(cv.string, None),
    }
)

GET_CONFIG_SCHEMA = vol.Schema({})

SEND_TEST_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CHANNEL): vol.In(("telegram", "whatsapp")),
        vol.Required(ATTR_CHAT_ID): cv.string,
        vol.Optional(ATTR_CONFIG_ENTRY_ID, default=""): cv.string,
        #: Text to send instead of the generic one, so the reception can read
        #: her own message (the review request) on her phone before guests do.
        vol.Optional("message", default=""): cv.string,
    }
)

_WEEKDAYS = vol.All(
    cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))]
)

ADD_CATEGORY_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("requires_operator", default=False): cv.boolean,
        vol.Optional("color", default=""): cv.string,
        vol.Optional("pause_min", default=DEFAULT_CATEGORY_PAUSE_MIN): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=120)
        ),
        vol.Optional("days", default=list): _WEEKDAYS,
        vol.Optional("morning_days"): _WEEKDAYS,
        vol.Optional("afternoon_days"): _WEEKDAYS,
        vol.Optional("morning_start", default=""): cv.string,
        vol.Optional("morning_end", default=""): cv.string,
        vol.Optional("afternoon_start", default=""): cv.string,
        vol.Optional("afternoon_end", default=""): cv.string,
        vol.Optional("exclusive_with", default=list): vol.All(
            cv.ensure_list, [cv.string]
        ),
    }
)

UPDATE_CATEGORY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CATEGORY_ID): cv.string,
        vol.Optional("name"): vol.Any(cv.string, None),
        vol.Optional("requires_operator"): vol.Any(cv.boolean, None),
        vol.Optional("color"): vol.Any(cv.string, None),
        vol.Optional("pause_min"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=0, max=120)), None
        ),
        vol.Optional("days"): vol.Any(_WEEKDAYS, None),
        vol.Optional("morning_days"): vol.Any(_WEEKDAYS, None),
        vol.Optional("afternoon_days"): vol.Any(_WEEKDAYS, None),
        vol.Optional("morning_start"): vol.Any(cv.string, None),
        vol.Optional("morning_end"): vol.Any(cv.string, None),
        vol.Optional("afternoon_start"): vol.Any(cv.string, None),
        vol.Optional("afternoon_end"): vol.Any(cv.string, None),
        vol.Optional("exclusive_with"): vol.Any(
            vol.All(cv.ensure_list, [cv.string]), None
        ),
    }
)

DELETE_CATEGORY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CATEGORY_ID): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    }
)

_PARALLEL = vol.All(vol.Coerce(int), vol.Range(min=0, max=1000))

ADD_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional(ATTR_CATEGORY_ID): vol.Any(cv.string, None),
        vol.Optional("duration_min", default=90): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=600)
        ),
        vol.Optional("price"): vol.Any(vol.Coerce(float), None),
        vol.Optional("active", default=True): cv.boolean,
        #: Shown on the public website. Separate from ``active``: something
        #: may be sold at the desk every day without belonging on the site.
        vol.Optional("web_visible", default=True): cv.boolean,
        vol.Optional("min_parallel", default=0): _PARALLEL,
        vol.Optional("max_parallel", default=0): _PARALLEL,
        #: VAT rate in percent (2.5.1); absent = the default rate.
        vol.Optional("vat_rate"): vol.Any(vol.Coerce(float), None),
        #: Which operators may perform it, like in the update: synced onto
        #: each operator card so the two never disagree.
        vol.Optional("operator_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)

UPDATE_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TREATMENT_ID): cv.string,
        vol.Optional("name"): vol.Any(cv.string, None),
        vol.Optional(ATTR_CATEGORY_ID): vol.Any(cv.string, None),
        vol.Optional("duration_min"): vol.All(vol.Coerce(int), vol.Range(min=5, max=600)),
        vol.Optional("price"): vol.Any(vol.Coerce(float), None),
        vol.Optional("active"): vol.Any(cv.boolean, None),
        vol.Optional("web_visible"): vol.Any(cv.boolean, None),
        vol.Optional("min_parallel"): vol.Any(_PARALLEL, None),
        vol.Optional("max_parallel"): vol.Any(_PARALLEL, None),
        #: VAT rate in percent (2.5.1); -1 = back to the default rate.
        vol.Optional("vat_rate"): vol.Any(vol.Coerce(float), None),
        #: Which operators may perform this treatment, selectable right from the
        #: treatment form. An empty list clears every operator.
        vol.Optional("operator_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)

DELETE_TREATMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TREATMENT_ID): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    }
)

ADD_OPERATOR_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        # The role classifies, it does not restrict: defaulting keeps an
        # operator created without one perfectly usable.
        vol.Optional("role", default=OPERATOR_ROLE_DEFAULT): vol.In(OPERATOR_ROLE_NAMES),
        vol.Optional("phone", default=""): cv.string,
        vol.Optional("whatsapp_chat_id", default=""): cv.string,
        vol.Optional("telegram_chat_id", default=""): cv.string,
        vol.Optional("treatment_ids", default=list): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional("notify_whatsapp", default=True): cv.boolean,
        vol.Optional("notify_telegram", default=True): cv.boolean,
        vol.Optional("notify_service", default=""): cv.string,
        vol.Optional("notify_on_create", default=True): cv.boolean,
        # Lower priority = asked sooner. Zero means "no particular order".
        vol.Optional("priority", default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=999)
        ),
        vol.Optional("active", default=True): cv.boolean,
        #: "F" (massaggiatrice), "M" (massaggiatore) or "" (not said).
        vol.Optional("gender", default=""): vol.In(("", "F", "M")),
    }
)

UPDATE_OPERATOR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_OPERATOR_ID): cv.string,
        vol.Optional("name"): vol.Any(cv.string, None),
        # None means "leave it as it is", which is why it is not an enum here.
        vol.Optional("role"): vol.Any(vol.In(OPERATOR_ROLE_NAMES), None),
        vol.Optional("phone"): vol.Any(cv.string, None),
        vol.Optional("whatsapp_chat_id"): vol.Any(cv.string, None),
        vol.Optional("telegram_chat_id"): vol.Any(cv.string, None),
        vol.Optional("treatment_ids"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("notify_whatsapp"): vol.Any(cv.boolean, None),
        vol.Optional("notify_telegram"): vol.Any(cv.boolean, None),
        vol.Optional("notify_service"): vol.Any(cv.string, None),
        vol.Optional("notify_on_create"): vol.Any(cv.boolean, None),
        vol.Optional("priority"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=0, max=999)), None
        ),
        vol.Optional("active"): vol.Any(cv.boolean, None),
        vol.Optional("gender"): vol.Any(vol.In(("", "F", "M")), None),
    }
)

DELETE_OPERATOR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_OPERATOR_ID): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    }
)

GET_MONTHLY_REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_MONTH): vol.Any(cv.string, None),
        vol.Optional(ATTR_NOTIFY, default=False): cv.boolean,
    }
)

#: One Spa-tab tile: the entity shown plus its own display options (name and
#: icon overrides, three visibility flags, and how many columns it spans). The
#: bare entity-id string is still accepted so a card saved before the tiles
#: existed keeps saving without error.
SPA_TILE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.string,
        vol.Optional("name"): vol.Any(cv.string, None),
        vol.Optional("icon"): vol.Any(cv.string, None),
        vol.Optional("show_name"): vol.Any(cv.boolean, None),
        vol.Optional("show_icon"): vol.Any(cv.boolean, None),
        vol.Optional("show_state"): vol.Any(cv.boolean, None),
        vol.Optional("span"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=1, max=4)), None
        ),
        vol.Optional("card_type"): vol.Any(
            vol.In(["auto", "tile", "button", "switch", "climate", "sensor", "entity", "thermostat", "gauge"]), None
        ),
        vol.Optional("tap_action"): vol.Any(
            vol.In(["toggle", "more-info", "none", "brightness"]), None
        ),
        vol.Optional("hold_action"): vol.Any(
            vol.In(["toggle", "more-info", "none", "brightness"]), None
        ),
        vol.Optional("features"): vol.Any(
            vol.All(cv.ensure_list, [cv.string]), None
        ),
    },
    extra=vol.PREVENT_EXTRA,
)

ACCESSORY_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Optional("label"): vol.Any(cv.string, None),
        vol.Optional("icon"): vol.Any(cv.string, None),
        # Informational only: it never enters a total. A number, a numeric
        # string (comma or dot) or a blank; the coordinator keeps only a number.
        vol.Optional("price"): vol.Any(None, vol.Coerce(float), cv.string),
        vol.Optional("description"): vol.Any(cv.string, None),
        vol.Optional("vat_rate"): vol.Any(None, vol.Coerce(float), cv.string),
    },
    extra=vol.PREVENT_EXTRA,
)

UPDATE_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("telegram_config_entry_id"): vol.Any(cv.string, None),
        vol.Optional("report_telegram_chats"): vol.Any(cv.string, None),
        vol.Optional("report_whatsapp_chat"): vol.Any(cv.string, None),
        vol.Optional("report_per_operator"): vol.Any(cv.boolean, None),
        vol.Optional("report_enabled"): vol.Any(cv.boolean, None),
        vol.Optional("report_time"): vol.Any(cv.string, None),
        vol.Optional("offer_timeout_hours"): vol.Any(cv.positive_int, None),
        vol.Optional("offer_reminder_hours"): vol.Any(int, None),
        vol.Optional("appearance"): vol.Any(vol.In(APPEARANCE_MODES), None),
        # Titolo in testata della card, scritto dalla reception in Impostazioni.
        vol.Optional("card_title"): vol.Any(cv.string, None),
        vol.Optional("pin_idle_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
        # Telecamere tab: one flat, user-ordered tile list (each camera carries
        # its name/icon/visibility/span). A bare entity-id string is accepted
        # too, so a client that predates the tiles keeps saving without error.
        vol.Optional("camera_entities"): vol.All(
            cv.ensure_list, [vol.Any(SPA_TILE_SCHEMA, cv.string)]
        ),
        # Spa tab: one flat, user-ordered tile list (each tile carries the
        # entity plus its name/icon/visibility/span).
        vol.Optional("spa_entities"): vol.All(
            cv.ensure_list, [vol.Any(SPA_TILE_SCHEMA, cv.string)]
        ),
        vol.Optional("spa_grouped"): cv.boolean,
        # Accessori tab: the accessories offered with a booking, in user order
        # (each one with label, icon, price and description). A bare id string
        # is accepted too, so a client that predates the tab keeps saving.
        vol.Optional("accessories"): vol.All(
            cv.ensure_list, [vol.Any(ACCESSORY_SCHEMA, cv.string)]
        ),
        # "Nuovo appuntamento" form layout: the block order of each column.
        # Unknown blocks are dropped by the coordinator, defaults fill gaps.
        vol.Optional("form_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # Notifications tab: its own two-column layout, the review request text
        # and the number the test goes to.
        vol.Optional("notifiche_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # Impostazioni tab: its four boxes, movable between the two columns.
        vol.Optional("impostazioni_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # Batch editor sheet: its own block order.
        vol.Optional("batch_form_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # Modifica appuntamento sheet: its own block order.
        vol.Optional("edit_form_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # One operator's card: its own block order.
        vol.Optional("operator_form_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # How many columns each tab lays its blocks out in: 1 (stacked) or 2.
        # The key is the tab, the value the number of columns. The coordinator
        # keeps only the tabs with a valid number and drops the rest.
        vol.Optional("tab_cols"): vol.Any(dict, None),
        vol.Optional("review_request_message"): vol.Any(cv.string, None),
        vol.Optional("cancel_message"): vol.Any(cv.string, None),
        vol.Optional("review_request_test_phone"): vol.Any(cv.string, None),
        # Appointment reminder: the text, automatic or not, and how many hours
        # before (2.3.7: the card always sent them, the schema refused them).
        vol.Optional("appointment_reminder_message"): vol.Any(cv.string, None),
        vol.Optional("appointment_reminder_auto"): vol.Any(cv.boolean, None),
        vol.Optional("appointment_reminder_hours"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=1, max=168)), None
        ),
        # Automatic review requests on/off, and the hours after a treatment
        # before the request goes out on its own.
        vol.Optional("review_request_auto"): vol.Any(cv.boolean, None),
        vol.Optional("review_request_after_hours"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=1, max=168)), None
        ),
        # Deposit request: bank details, the message the guest receives and the
        # number a test send goes to.
        vol.Optional("deposit_intestatario"): vol.Any(cv.string, None),
        vol.Optional("deposit_iban"): vol.Any(cv.string, None),
        vol.Optional("deposit_message"): vol.Any(cv.string, None),
        vol.Optional("deposit_test_phone"): vol.Any(cv.string, None),
        # Guest-facing summary headline (hotel name after the title).
        vol.Optional("guest_header"): vol.Any(cv.string, None),
        # The guest-facing appointment summary itself, plus the number a test
        # send goes to.
        vol.Optional("summary_message"): vol.Any(cv.string, None),
        vol.Optional("summary_test_phone"): vol.Any(cv.string, None),
        # Acknowledgement to a guest whose appointment request was taken.
        vol.Optional("request_message"): vol.Any(cv.string, None),
        vol.Optional("request_propose_message"): vol.Any(cv.string, None),
        vol.Optional("request_propose_alt_intro"): vol.Any(cv.string, None),
        vol.Optional("request_propose_alt_line"): vol.Any(cv.string, None),
        # Promo broadcast: the message, the daily send time and the delay
        # between one send and the next.
        vol.Optional("promo_message"): vol.Any(cv.string, None),
        vol.Optional("promo_time"): vol.Any(cv.string, None),
        vol.Optional("promo_interval_sec"): vol.Any(cv.positive_int, None),
        vol.Optional("promo_max_sends"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=1000)), None),
        vol.Optional("promo_window_min"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)), None),
        vol.Optional("promo_date"): vol.Any(cv.string, None),
        vol.Optional("promo_code"): vol.Any(cv.string, None),
        vol.Optional("promo_expiry"): vol.Any(cv.string, None),
        # The saved campaigns (2.3.9); each is checked by _norm_promo.
        vol.Optional("promos"): vol.Any(vol.All(cv.ensure_list, [dict]), None),
        vol.Optional("promo_voucher_message"): vol.Any(cv.string, None),
        vol.Optional("promo_voucher_days"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)), None),
        vol.Optional("promo_voucher_discount"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=1, max=100)), None),
        vol.Optional("promo_voucher_min_spend"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=100000)), None),
        vol.Optional("promo_voucher_max_spend"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=100000)), None),
        vol.Optional("promo_voucher_after_hours"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=8760)), None),
        vol.Optional("promo_voucher_auto"): vol.Any(cv.boolean, None),
        # Email sending (2.4.1). An empty password keeps the saved one.
        vol.Optional("email_enabled"): vol.Any(cv.boolean, None),
        vol.Optional("smtp_provider"): vol.Any(vol.In(["gmail", "outlook", "aruba", "libero", "altro"]), None),
        vol.Optional("smtp_host"): vol.Any(cv.string, None),
        vol.Optional("smtp_port"): vol.Any(vol.Coerce(int), None),
        vol.Optional("smtp_security"): vol.Any(vol.In(["", "starttls", "ssl", "none"]), None),
        vol.Optional("smtp_username"): vol.Any(cv.string, None),
        vol.Optional("smtp_password"): vol.Any(cv.string, None),
        vol.Optional("email_from"): vol.Any(cv.string, None),
        vol.Optional("email_from_name"): vol.Any(cv.string, None),
        vol.Optional("email_reply_to"): vol.Any(cv.string, None),
        vol.Optional("email_method"): vol.Any(vol.In(["smtp", "google"]), None),
        vol.Optional("google_client_id"): vol.Any(cv.string, None),
        vol.Optional("google_client_secret"): vol.Any(cv.string, None),
        vol.Optional("email_aliases"): vol.Any(vol.All(cv.ensure_list, [cv.string]), None),
        # VAT (2.5.1).
        vol.Optional("vat_default"): vol.Any(vol.Coerce(float), None),
        vol.Optional("wp_enabled"): vol.Any(cv.boolean, None),
        vol.Optional("gdrive_enabled"): vol.Any(cv.boolean, None),
        vol.Optional("gdrive_time"): vol.Any(cv.string, None),
        vol.Optional("wp_url"): vol.Any(cv.string, None),
        vol.Optional("wp_product_map"): vol.Any(dict, None),
        vol.Optional("billing_company"): vol.Any(cv.string, None),
        vol.Optional("billing_vat_number"): vol.Any(cv.string, None),
        vol.Optional("billing_tax_code"): vol.Any(cv.string, None),
        vol.Optional("billing_address"): vol.Any(cv.string, None),
        vol.Optional("billing_zip"): vol.Any(cv.string, None),
        vol.Optional("billing_city"): vol.Any(cv.string, None),
        vol.Optional("billing_province"): vol.Any(cv.string, None),
        vol.Optional("billing_country"): vol.Any(cv.string, None),
        vol.Optional("billing_phone"): vol.Any(cv.string, None),
        vol.Optional("billing_email"): vol.Any(cv.string, None),
        vol.Optional("billing_pec"): vol.Any(cv.string, None),
        vol.Optional("billing_sdi"): vol.Any(cv.string, None),
        vol.Optional("billing_receipt_note"): vol.Any(cv.string, None),
        # Partners (2.5.0).
        vol.Optional("partner_points_per_euro"): vol.Any(vol.Coerce(float), None),
        vol.Optional("partner_booking_url"): vol.Any(cv.string, None),
        vol.Optional("package_hidden_web"): vol.Any([cv.string], None),
        vol.Optional("package_hidden_desk"): vol.Any([cv.string], None),
        vol.Optional("package_order"): vol.Any([cv.string], None),
        vol.Optional("partner_discount_pct"): vol.Any(vol.Coerce(float), None),
        vol.Optional("partner_reward_points"): vol.Any(vol.Coerce(int), None),
        vol.Optional("partner_reward_value"): vol.Any(vol.Coerce(int), None),
        vol.Optional("partner_reward_message"): vol.Any(cv.string, None),
        vol.Optional("partner_campaigns"): vol.Any(vol.All(cv.ensure_list, [dict]), None),
        # Loyalty points (2.4.0).
        vol.Optional("loyalty_enabled"): vol.Any(cv.boolean, None),
        vol.Optional("loyalty_points_per_euro"): vol.Any(vol.Coerce(float), None),
        vol.Optional("loyalty_threshold"): vol.Any(vol.Coerce(int), None),
        vol.Optional("loyalty_reward"): vol.Any(vol.Coerce(int), None),
        vol.Optional("loyalty_auto"): vol.Any(cv.boolean, None),
        vol.Optional("loyalty_message"): vol.Any(cv.string, None),
        vol.Optional("promo_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            None,
        ),
        # Sito web: the switch, the shared token the site sends, the hours the
        # site may offer (a break may cut the day in two) and the minutes
        # between one offer and the next, and how far ahead it may look. The
        # token is normally written by regenerate_public_token, not by hand.
        vol.Optional("web_enabled"): vol.Any(cv.boolean, None),
        vol.Optional("web_token"): vol.Any(cv.string, None),
        vol.Optional("web_open_time"): vol.Any(cv.string, None),
        vol.Optional("web_close_time"): vol.Any(cv.string, None),
        vol.Optional("web_break_start"): vol.Any(cv.string, None),
        vol.Optional("web_break_end"): vol.Any(cv.string, None),
        vol.Optional("web_step_min"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=5, max=240)), None
        ),
        vol.Optional("web_max_days_ahead"): vol.Any(
            vol.All(vol.Coerce(int), vol.Range(min=1, max=365)), None
        ),
        # Numero WhatsApp della reception per l'avviso di una nuova richiesta
        # dal sito (vuoto = nessun avviso).
        vol.Optional("web_notify_whatsapp"): vol.Any(cv.string, None),
        vol.Optional("web_show_prices"): cv.boolean,
        vol.Optional("web_accent"): vol.Any(cv.string, None),
        vol.Optional("web_public_url"): vol.Any(cv.string, None),
        vol.Optional("whatsapp_engine"): vol.In(["integrated"]),
        vol.Optional("telegram_bot_token"): vol.Any(cv.string, None),
        # Configuration tab: the order of the treatments, as dragged.
        vol.Optional("treatments_order"): vol.Any(
            vol.All(cv.ensure_list, [cv.string]), None
        ),
        # ...and the place of their category groups: which column and which
        # row inside it, as dragged. A plain list is still accepted.
        vol.Optional("categories_order"): vol.Any(
            {
                vol.Optional("left"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("right"): vol.All(cv.ensure_list, [cv.string]),
            },
            vol.All(cv.ensure_list, [cv.string]),
            None,
        ),
        # Internal timers and the quiet window for guest messages.
        vol.Optional("scheduler_enabled"): cv.boolean,
        vol.Optional("quiet_hours_start"): vol.Any(cv.string, None),
        vol.Optional("quiet_hours_end"): vol.Any(cv.string, None),
    },
    extra=vol.PREVENT_EXTRA,
)

CHECK_WAHA_SCHEMA = vol.Schema({})


EXPORT_DATA_SCHEMA = vol.Schema({})
EXPORT_ALL_SCHEMA = vol.Schema({})

IMPORT_DATA_SCHEMA = vol.Schema({vol.Required(ATTR_PAYLOAD): dict})
IMPORT_ALL_SCHEMA = vol.Schema({vol.Required(ATTR_PAYLOAD): dict})
UPDATE_BOOKING_BATCH_SCHEMA = vol.Schema(
    {
        vol.Required("appointment_id"): cv.string,
        vol.Required(ATTR_ROWS): vol.All(cv.ensure_list, [dict]),
        vol.Optional("force_rules", default=False): cv.boolean,
    }
)

EXPORT_CLIENTS_CSV_SCHEMA = vol.Schema({})

IMPORT_CLIENTS_CSV_SCHEMA = vol.Schema(
    {vol.Required("csv"): cv.string},
    extra=vol.PREVENT_EXTRA,
)

BOOKING_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("start"): cv.datetime,
        vol.Optional(ATTR_CLIENT_ID): vol.Any(cv.string, None),
        **_CLIENT_FIELDS,
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        vol.Optional(ATTR_OPERATOR_IDS): vol.All(cv.ensure_list, [cv.string]),
        #: The guest would like a woman ("F") or a man ("M"); "" = anybody.
        vol.Optional("therapist_preference"): vol.Any(vol.In(("", "F", "M")), None),
        vol.Optional("notes"): cv.string,
        #: The accessories this person gets with the booking, unknown ones
        #: dropped by the coordinator. Leave it out for none.
        vol.Optional(ATTR_EXTRAS): vol.All(cv.ensure_list, [cv.string]),
        #: Which person of the party this entry is: 0 is the one written on the
        #: card — the leader — and 1.. are her guests. Two people of one party
        #: share the leader's card and may share the hour; the same person
        #: twice in the same hour is still refused.
        vol.Optional("person"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1000)),
        #: Force a brand new client card even when a name or number matches an
        #: existing one, so two people who share a name get their own id.
        vol.Optional(ATTR_FORCE_NEW, default=False): cv.boolean,
        #: Per-row price overrides, both editable from the card: the list
        #: price and the discounted one. Leave them out for catalogue price.
        vol.Optional("list_price"): vol.Any(vol.Coerce(float), None),
        vol.Optional("price"): vol.Any(vol.Coerce(float), None),
        #: The shop package this treatment belongs to (2.8.9) and which copy
        #: of it (two couples, two packages): its price is shared out.
        vol.Optional("package_key"): vol.Any(cv.string, None),
        vol.Optional("package_group"): vol.Any(cv.string, None),
        #: The desk saw the overlap warning and books anyway: skips only the
        #: same-person client refusal, never an operator double-booking.
        vol.Optional("force_client_overlap", default=False): cv.boolean,
        #: One payment for the whole booking reaches every entry, so each
        #: appointment ends up carrying the same detail.
        vol.Optional(ATTR_PAYMENT): vol.Any(PAYMENT_SCHEMA, None),
    },
    extra=vol.PREVENT_EXTRA,
)

BOOKING_ROW_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TREATMENT_ID): cv.string,
        vol.Required("entries"): vol.All(cv.ensure_list, [BOOKING_ENTRY_SCHEMA]),
        #: Waiting or confirmed, for every row: a party is confirmed together
        #: or waits together, never one half of it.
        vol.Optional("pending", default=False): cv.boolean,
        #: Hotel or outside, one value for the whole row.
        vol.Optional(ATTR_GUEST_TYPE, default=GUEST_TYPE_DEFAULT): vol.In(
            GUEST_TYPE_NAMES
        ),
        #: The partner who brought the party (id or code, 2.5.0).
        vol.Optional("partner_id"): vol.Any(cv.string, None),
    },
    extra=vol.PREVENT_EXTRA,
)

CREATE_BOOKINGS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ROWS): vol.All(cv.ensure_list, [BOOKING_ROW_SCHEMA]),
        vol.Optional("force_rules", default=False): cv.boolean,
        # 2.8.3: the request these appointments confirm, marked confirmed
        # together with the booking.
        vol.Optional("request_id"): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

RESPOND_TO_OFFER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_APPOINTMENT_ID): vol.Any(cv.string, None),
        vol.Required(ATTR_RESPONSE): cv.string,
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        vol.Optional(ATTR_CHAT_ID): vol.Any(cv.string, None),
        vol.Optional(ATTR_CHANNEL): vol.Any(cv.string, None),
        vol.Optional(ATTR_SOURCE, default=""): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

SET_OFFER_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Required(ATTR_STATE): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

MANUAL_CONFIRM_OFFER_SCHEMA = vol.Schema(
    {vol.Required(ATTR_APPOINTMENT_ID): cv.string},
    extra=vol.PREVENT_EXTRA,
)

ADD_PAYMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Required(ATTR_METHOD): vol.In(PAYMENT_METHOD_NAMES),
        vol.Required(ATTR_AMOUNT): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
        vol.Optional(ATTR_DATE, default=""): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

DELETE_PAYMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Required(ATTR_PAYMENT_ID): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

#: One treatment of a request: which one, at what time, with which accessories.
REQUEST_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TREATMENT_ID): cv.string,
        vol.Required(ATTR_TIME): cv.string,
        vol.Optional(ATTR_EXTRAS): vol.All(cv.ensure_list, [cv.string]),
        # Which person of the party (0 = the one booking); website requests
        # carry it, desk requests leave it out (each entry is for everybody).
        vol.Optional("person"): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=0))),
        #: This person would like a woman ("F") or a man ("M") (2.3.4).
        vol.Optional("therapist_preference"): vol.Any(vol.In(("", "F", "M")), None),
        vol.Optional("package_key"): vol.Any(cv.string, None),
        vol.Optional("package_group"): vol.Any(cv.string, None),
    },
    extra=vol.PREVENT_EXTRA,
)

CREATE_REQUEST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CLIENT_ID): vol.Any(cv.string, None),
        **_CLIENT_FIELDS,
        vol.Optional(ATTR_FORCE_NEW, default=False): cv.boolean,
        vol.Required(ATTR_DATE): cv.string,
        vol.Optional(ATTR_PEOPLE, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Required(ATTR_ENTRIES): vol.All(cv.ensure_list, [REQUEST_ENTRY_SCHEMA]),
        vol.Optional("notes"): cv.string,
        #: A gift voucher code the guest mentioned, if any. Checked if it is a
        #: real one; an unknown code is recorded for the desk to verify.
        vol.Optional("voucher_code"): cv.string,
        vol.Optional(ATTR_GUEST_TYPE, default=GUEST_TYPE_DEFAULT): vol.In(
            GUEST_TYPE_NAMES
        ),
        #: Rewrite this request instead of adding a new one (card "Modifica").
        vol.Optional(ATTR_REQUEST_ID): vol.Any(cv.string, None),
        #: The guest would like a woman ("F") or a man ("M"); "" = anybody.
        vol.Optional("therapist_preference"): vol.Any(vol.In(("", "F", "M")), None),
        #: The partner who brought the request (id or code, 2.5.0); None keeps it.
        vol.Optional("partner"): vol.Any(cv.string, None),
    },
    extra=vol.PREVENT_EXTRA,
)

REQUEST_ID_SCHEMA = vol.Schema(
    {vol.Required(ATTR_REQUEST_ID): cv.string},
    extra=vol.PREVENT_EXTRA,
)

MARK_REQUESTS_SEEN_SCHEMA = vol.Schema({})

REGENERATE_PUBLIC_TOKEN_SCHEMA = vol.Schema({})

#: No fields: the snippet is read from the published file.
WEB_SNIPPET_SCHEMA = vol.Schema({vol.Optional("base_url", default=""): cv.string})

SEND_EXTERNAL_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CHAT_ID): cv.string,
        vol.Required("text"): cv.string,
    }
)

VOUCHER_PERSON_SCHEMA = vol.Schema(
    {
        vol.Optional("name", default=""): cv.string,
        vol.Required("treatment_ids"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("extras", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("gift_card_amount"): vol.Any(vol.Coerce(float), None),
    },
    extra=vol.PREVENT_EXTRA,
)

CREATE_VOUCHER_SCHEMA = vol.Schema(
    {
        vol.Optional("buyer_name", default=""): cv.string,
        vol.Optional("buyer_phone", default=""): cv.string,
        vol.Optional("recipient_name", default=""): cv.string,
        vol.Optional("recipient_phone", default=""): cv.string,
        vol.Required("people"): vol.All(cv.ensure_list, [VOUCHER_PERSON_SCHEMA]),
        #: Who made it. Ignored for a signed-in person: her own name is used.
        vol.Optional("created_by", default=""): cv.string,
        #: The PIN of whoever sells it: the voucher is signed with her name.
        vol.Optional("pin", default=""): vol.All(cv.string, vol.Match(r"^(\d{4})?$")),
    },
    extra=vol.PREVENT_EXTRA,
)

EXTEND_VOUCHER_SCHEMA = vol.Schema(
    {vol.Required("voucher_id"): cv.string, vol.Required("expires_on"): cv.string},
    extra=vol.PREVENT_EXTRA,
)

DELETE_VOUCHER_SCHEMA = vol.Schema(
    {vol.Required("voucher_id"): cv.string},
    extra=vol.PREVENT_EXTRA,
)

REDEEM_PROMO_VOUCHER_SCHEMA = vol.Schema(
    {vol.Required("voucher_id"): cv.string},
    extra=vol.PREVENT_EXTRA,
)

LOYALTY_REWARD_SCHEMA = vol.Schema(
    {vol.Required("client_id"): cv.string, vol.Optional("send", default=True): cv.boolean},
    extra=vol.PREVENT_EXTRA,
)

LOYALTY_ADJUST_SCHEMA = vol.Schema(
    {
        vol.Required("client_id"): cv.string,
        vol.Required("points"): vol.Coerce(int),
        vol.Optional("note", default=""): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

SAVE_PARTNER_SCHEMA = vol.Schema(
    {
        vol.Optional("id"): vol.Any(cv.string, None),
        vol.Optional("first_name"): vol.Any(cv.string, None),
        vol.Optional("last_name"): vol.Any(cv.string, None),
        vol.Optional("company"): vol.Any(cv.string, None),
        vol.Optional("phone"): vol.Any(cv.string, None),
        vol.Optional("email"): vol.Any(cv.string, None),
        vol.Optional("code"): vol.Any(cv.string, None),
        vol.Optional("notes"): vol.Any(cv.string, None),
        vol.Optional("active"): vol.Any(cv.boolean, None),
        vol.Optional("city"): vol.Any(cv.string, None),
        vol.Optional("structure_type"): vol.Any(cv.string, None),
        vol.Optional("whatsapp"): vol.Any(cv.boolean, None),
        vol.Optional("subscribed"): vol.Any(cv.boolean, None),
        # Her own discount for her guests (2.8.6); empty = the general one.
        vol.Optional("discount_pct"): vol.Any(vol.Coerce(float), None, ""),
    },
    extra=vol.PREVENT_EXTRA,
)

WP_EMPTY_SCHEMA = vol.Schema({}, extra=vol.PREVENT_EXTRA)
WP_REDEEM_SCHEMA = vol.Schema({vol.Required("voucher_id"): cv.string}, extra=vol.PREVENT_EXTRA)

IMPORT_PARTNERS_SCHEMA = vol.Schema(
    {vol.Required("partners"): vol.All(cv.ensure_list, [dict])}, extra=vol.PREVENT_EXTRA
)

PARTNER_POINTS_ADJUST_SCHEMA = vol.Schema(
    {
        vol.Required("partner_id"): cv.string,
        vol.Required("points"): vol.Coerce(int),
        vol.Optional("note", default=""): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

SPLIT_FROM_GROUP_SCHEMA = vol.Schema({vol.Required(ATTR_APPOINTMENT_ID): cv.string}, extra=vol.PREVENT_EXTRA)
JOIN_GROUP_SCHEMA = vol.Schema(
    {vol.Required(ATTR_APPOINTMENT_ID): cv.string, vol.Required("code"): cv.string}, extra=vol.PREVENT_EXTRA
)

SEND_LOYALTY_VOUCHER_SCHEMA = vol.Schema(
    {
        vol.Optional("client_id"): cv.string,
        vol.Optional("partner_id"): cv.string,
        vol.Optional("discount_percent"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional("days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
        vol.Optional("min_spend"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100000)),
    },
    extra=vol.PREVENT_EXTRA,
)

PARTNER_DETAIL_SCHEMA = vol.Schema({vol.Required("partner_id"): cv.string}, extra=vol.PREVENT_EXTRA)
PARTNER_REWARD_SCHEMA = vol.Schema(
    {vol.Required("partner_id"): cv.string, vol.Optional("send", default=True): cv.boolean},
    extra=vol.PREVENT_EXTRA,
)

SET_APPOINTMENT_PARTNER_SCHEMA = vol.Schema(
    {vol.Required(ATTR_APPOINTMENT_ID): cv.string, vol.Optional("partner_id", default=""): vol.Any(cv.string, None)},
    extra=vol.PREVENT_EXTRA,
)

SEND_PARTNER_CAMPAIGN_SCHEMA = vol.Schema(
    {vol.Required("campaign_id"): cv.string, vol.Optional("test_to"): vol.Any(cv.string, None)},
    extra=vol.PREVENT_EXTRA,
)

DELETE_PARTNER_SCHEMA = vol.Schema(
    {vol.Required("partner_id"): cv.string}, extra=vol.PREVENT_EXTRA
)

DELETE_PROMO_VOUCHER_SCHEMA = vol.Schema(
    {vol.Required("voucher_id"): cv.string},
    extra=vol.PREVENT_EXTRA,
)

SEND_OPERATOR_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_OPERATOR_ID): cv.string,
        vol.Required(ATTR_KIND): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

SEND_GUEST_SUMMARY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_APPOINTMENT_ID): cv.string,
        vol.Optional(ATTR_APPOINTMENT_IDS): vol.All(cv.ensure_list, [cv.string]),
        # 3.0.1: only the appointments named, not the rest of the party
        # (a partial confirmation tells the guest only what was confirmed).
        vol.Optional("only", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

SEND_DEPOSIT_REQUEST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        #: Send it again (the guest lost it, or the amount changed).
        vol.Optional("resend", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

SEND_PROMO_SCHEMA = vol.Schema(
    {
        vol.Optional("client_ids"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("message"): vol.Any(cv.string, None),
        vol.Optional("promo_id"): vol.Any(cv.string, None),
    },
    extra=vol.PREVENT_EXTRA,
)

PROMO_AUTOMATIC_SCHEMA = vol.Schema(
    {},
    extra=vol.PREVENT_EXTRA,
)

SEND_REMINDERS_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_APPOINTMENT_ID): vol.Any(cv.string, None)}
)

SEND_REVIEW_REQUESTS_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_APPOINTMENT_ID): vol.Any(cv.string, None)}
)

VOUCHER_EXPIRY_REMINDER_SCHEMA = vol.Schema(
    {},
    extra=vol.PREVENT_EXTRA,
)

CLEAR_SLOT_BLOCK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_OPERATOR_ID): cv.string,
        vol.Optional(ATTR_APPOINTMENT_ID, default=""): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

EXPIRE_OFFERS_SCHEMA = vol.Schema({})



async def _async_get_dashboard_config(call: ServiceCall) -> ServiceResponse:
    """Return the structured dashboard configuration (read-only)."""
    coordinator = _coordinator(call)
    settings = coordinator.export_data().get("settings", {})
    return {
        "dashboard": {
            "appearance": settings.get("appearance"),
            "card_title": settings.get("card_title"),
            "spa_entities": settings.get("spa_entities"),
            "spa_grouped": settings.get("spa_grouped", True),
            "camera_entities": settings.get("camera_entities"),
            "accessories": settings.get("accessories"),
        }
    }



async def _async_export_dashboard_yaml(call: ServiceCall) -> ServiceResponse:
    """Generate a ready-to-import Lovelace YAML dashboard for the Spa tiles."""
    return await _coordinator(call).async_export_dashboard_yaml()


def _coordinator(call: ServiceCall) -> SpaBookingCoordinator:
    """Return the loaded coordinator."""
    return call.hass.data[DOMAIN]


#: Order of the access levels of the card's Accessi tab.
_LEVEL_RANK = {level: rank for rank, level in enumerate(PERMISSION_LEVELS)}

#: The settings an operator may change: only the layout of her own screens
#: and the Spa tab tiles. Everything else is configuration (admin).
OPERATOR_SETTINGS = frozenset(
    {
        "appearance",
        "tab_cols",
        "form_order",
        "edit_form_order",
        "batch_form_order",
        "operator_form_order",
        "camera_entities",
        "spa_entities",
        "spa_grouped",
    }
)


async def _caller_is_ha_admin(call: ServiceCall) -> bool:
    """Whether the caller is a Home Assistant administrator or the owner."""
    user_id = call.context.user_id if call.context else None
    if not user_id:
        return False
    user = await call.hass.auth.async_get_user(user_id)
    return bool(user is not None and (user.is_admin or user.is_owner))


@dataclass
class Caller:
    """Who is acting: a person, the shared tablet waiting for a PIN, or the system."""

    user_id: str | None
    name: str
    level: str
    operator_id: str = ""
    #: The shared reception tablet the call came from, if any.
    device: str | None = None
    system: bool = False


#: The caller of the service being run, set by ``_guarded``.
_ACTING: ContextVar[Caller | None] = ContextVar("spa_booking_caller", default=None)


async def caller_identity(
    call: ServiceCall, coordinator: SpaBookingCoordinator, *, refresh: bool = False
) -> Caller:
    """Return who made the call and with which SPA level.

    The level chosen in Accessi wins; a Home Assistant admin or owner who is
    not listed is an administrator; anybody else has no access. A call
    without a user (an automation, a script, the integration itself) acts as
    the system and is an administrator. A call from the shared reception
    tablet acts as the person who typed her PIN, or has no access while
    nobody did. ``refresh`` keeps that person's session alive.
    """
    user_id = call.context.user_id if call.context else None
    if not user_id:
        return Caller(None, "Sistema", "admin", system=True)
    device: str | None = None
    if coordinator.profile(user_id).get("shared"):
        device = user_id
        sessions = coordinator.pin_sessions
        now = time.monotonic()
        acting = (
            sessions.current(device, now, coordinator.pin_idle_minutes)
            if refresh
            else sessions.peek(device, now, coordinator.pin_idle_minutes)
        )
        if not acting:
            return Caller(None, "", "none", device=device)
        user_id = acting
    user = await call.hass.auth.async_get_user(user_id)
    if user is None or not user.is_active:
        return Caller(None, "", "none", device=device)
    stored = coordinator.permissions_payload().get(user_id)
    level = stored if stored in _LEVEL_RANK else "none"
    # A Home Assistant administrator can edit the storage file anyway:
    # refusing her here would protect nothing.
    if user.is_admin or user.is_owner:
        level = "admin"
    return Caller(
        user_id,
        user.name or "",
        level,
        coordinator.profile(user_id).get("operator_id") or "",
        device,
    )


async def caller_level(call: ServiceCall, coordinator: SpaBookingCoordinator) -> str:
    """Return the SPA access level of whoever made the call."""
    acting = _ACTING.get()
    if acting is not None:
        return acting.level
    return (await caller_identity(call, coordinator)).level


def _acting_user_id(call: ServiceCall) -> str | None:
    """The person behind the call: on the shared tablet, who typed her PIN."""
    acting = _ACTING.get()
    if acting is not None and not acting.system:
        return acting.user_id
    return call.context.user_id if call.context else None


async def _require_level(
    call: ServiceCall, coordinator: SpaBookingCoordinator, needed: str
) -> str:
    """Refuse the call unless the caller has at least ``needed``."""
    level = await caller_level(call, coordinator)
    if _LEVEL_RANK.get(level, 0) < _LEVEL_RANK.get(needed, len(_LEVEL_RANK)):
        raise ValidationError(
            f"Accesso negato: questa operazione richiede il livello '{needed}' "
            f"(il tuo è '{level}')."
        )
    return level


async def _require_admin(call: ServiceCall, coordinator: SpaBookingCoordinator) -> None:
    """Refuse the call unless the caller is an administrator."""
    await _require_level(call, coordinator, "admin")


#: Secrets that only an administrator may read back from the dataset.
_SECRET_SETTINGS = (
    "web_token", "smtp_password", "telegram_bot_token",
    "google_client_secret", "google_refresh_token", "wp_secret",
)


def _without_secrets(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the settings with the gateway and website secrets blanked."""
    return {
        **settings,
        **{key: "" for key in _SECRET_SETTINGS if key in settings},
        KEY_PROFILES: access.public_profiles(settings.get(KEY_PROFILES) or {}),
    }


async def _async_create_appointment(call: ServiceCall) -> ServiceResponse:
    """Create an appointment."""
    data = call.data
    appointment = await _coordinator(call).async_create_appointment(
        treatment_id=data[ATTR_TREATMENT_ID],
        start=data["start"],
        client_id=data.get(ATTR_CLIENT_ID),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        client_notes=data.get("client_notes", ""),
        operator_id=data.get(ATTR_OPERATOR_ID),
        operator_ids=data.get(ATTR_OPERATOR_IDS),
        notes=data.get("notes", ""),
        payment=data.get(ATTR_PAYMENT),
        pending=data.get("pending", False),
        guest_type=data.get(ATTR_GUEST_TYPE, GUEST_TYPE_DEFAULT),
        extras=data.get(ATTR_EXTRAS),
        list_price=data.get("list_price"),
        price=data.get("price"),
        force_client_overlap=data.get("force_client_overlap", False),
        batch_id=data.get("batch_id"),
        therapist_preference=data.get("therapist_preference") or "",
        partner_id=data.get("partner_id") or "",
    )
    return {"appointment": appointment}


async def _async_create_bookings(call: ServiceCall) -> ServiceResponse:
    """Create every appointment of a multi-row booking."""
    user_id = _acting_user_id(call)
    coordinator = _coordinator(call)
    request_id = call.data.get("request_id")
    if request_id:
        return await coordinator.async_confirm_request_with(request_id, call.data[ATTR_ROWS], user_id)
    return await coordinator.async_create_bookings(call.data[ATTR_ROWS], user_id)


async def _async_create_request(call: ServiceCall) -> ServiceResponse:
    """Take a guest's appointment request and acknowledge it."""
    data = call.data
    user_id = _acting_user_id(call)
    return await _coordinator(call).async_create_request(
        client_id=data.get(ATTR_CLIENT_ID),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        client_notes=data.get("client_notes", ""),
        force_new=data.get(ATTR_FORCE_NEW, False),
        date=data[ATTR_DATE],
        people=data.get(ATTR_PEOPLE, 1),
        entries=data[ATTR_ENTRIES],
        notes=data.get("notes", ""),
        voucher_code=data.get("voucher_code", ""),
        guest_type=data.get(ATTR_GUEST_TYPE, GUEST_TYPE_DEFAULT),
        user_id=user_id,
        request_id=data.get(ATTR_REQUEST_ID),
        therapist_preference=data.get("therapist_preference") or "",
        partner=data.get("partner"),
    )


async def _async_delete_request(call: ServiceCall) -> ServiceResponse:
    """Drop a request the desk no longer needs."""
    return await _coordinator(call).async_delete_request(
        call.data[ATTR_REQUEST_ID]
    )


async def _async_confirm_request(call: ServiceCall) -> ServiceResponse:
    """Turn a request into real appointments."""
    return await _coordinator(call).async_confirm_request(
        call.data[ATTR_REQUEST_ID]
    )


async def _async_propose_request_date(call: ServiceCall) -> ServiceResponse:
    """Offer the guest another date on WhatsApp (or just write the text)."""
    data = call.data
    acting = _ACTING.get()
    return await _coordinator(call).async_propose_request_date(
        data["request_id"],
        data["date"].isoformat() if hasattr(data["date"], "isoformat") else str(data["date"]),
        str(data.get("time") or "")[:5],
        data.get("text") or None,
        alternatives=[dict(item) for item in data.get("alternatives") or []],
        dry_run=data.get("dry_run", False),
        by_name=(acting.name if acting is not None and acting.user_id else ""),
    )


PROPOSE_REQUEST_DATE_SCHEMA = vol.Schema(
    {
        vol.Required("request_id"): cv.string,
        vol.Required("date"): cv.date,
        vol.Optional("time", default=""): vol.Any(
            vol.All(cv.string, vol.Match(r"^(\d{2}:\d{2})?$")), None
        ),
        vol.Optional("text"): vol.Any(cv.string, None),
        vol.Optional("alternatives", default=list): vol.All(
            cv.ensure_list,
            vol.Length(max=6),
            [
                vol.Schema(
                    {
                        vol.Required("treatment_id"): cv.string,
                        vol.Optional("price"): vol.Any(vol.Coerce(float), None, ""),
                        vol.Optional("time", default=""): vol.Any(
                            vol.All(cv.string, vol.Match(r"^(\d{2}:\d{2})?$")), None
                        ),
                        vol.Optional("day", default="asked"): vol.Any(
                            "asked", "proposed", vol.All(cv.string, vol.Match(r"^\d{4}-\d{2}-\d{2}$"))
                        ),
                    }
                )
            ],
        ),
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)


async def _async_send_request_message(call: ServiceCall) -> ServiceResponse:
    """Resend a request's acknowledgement to the guest."""
    return await _coordinator(call).async_send_request_message(
        call.data[ATTR_REQUEST_ID]
    )


async def _async_respond_to_offer(call: ServiceCall) -> ServiceResponse:
    """Apply an operator's answer to an open offer."""
    data = call.data
    return await _coordinator(call).async_answer_from_operator(
        data[ATTR_RESPONSE],
        operator_id=data.get(ATTR_OPERATOR_ID),
        chat_id=data.get(ATTR_CHAT_ID),
        channel=data.get(ATTR_CHANNEL),
        appointment_id=data.get(ATTR_APPOINTMENT_ID),
        source=data.get(ATTR_SOURCE, ""),
    )


async def _async_set_offer_state(call: ServiceCall) -> ServiceResponse:
    """Move an appointment between waiting and confirmed from the desk."""
    data = call.data
    return await _coordinator(call).async_set_offer_state(
        data[ATTR_APPOINTMENT_ID], data[ATTR_STATE]
    )


async def _async_create_voucher(call: ServiceCall) -> ServiceResponse:
    """Sell a gift voucher, signed by whoever is signed in."""
    data = call.data
    coordinator = _coordinator(call)
    acting = _ACTING.get()
    # From 2.3.0 a person signs every voucher with her own PIN, whoever is
    # signed in on the device: the voucher carries the name of whoever typed
    # it. Only an automation (no user) may still say who made it in words.
    human = acting is not None and not acting.system
    if data.get("pin"):
        user_id, name = await _pin_signer(call, coordinator, data["pin"])
    elif human:
        raise ValidationError("Inserisci il tuo PIN per firmare il voucher")
    else:
        user_id = call.context.user_id if call.context else None
        name = data.get("created_by", "")
    voucher = await coordinator.async_create_voucher(
        data["buyer_name"],
        data["buyer_phone"],
        data["recipient_name"],
        data["recipient_phone"],
        data["people"],
        user_id,
        name,
    )
    return {"voucher": voucher}


async def _async_extend_voucher(call: ServiceCall) -> ServiceResponse:
    """Give a voucher a new expiry date."""
    voucher = await _coordinator(call).async_extend_voucher(
        call.data["voucher_id"], call.data["expires_on"]
    )
    return {"voucher": voucher}


async def _async_delete_voucher(call: ServiceCall) -> ServiceResponse:
    """Remove a voucher. Admin can delete redeemed vouchers."""
    coordinator = _coordinator(call)
    is_admin = await caller_level(call, coordinator) == "admin"
    return await coordinator.async_delete_voucher(
        call.data["voucher_id"], _acting_user_id(call), is_admin, False
    )


async def _async_redeem_promo_voucher(call: ServiceCall) -> ServiceResponse:
    """Mark a loyalty voucher ("Voucher fedelta") as used."""
    voucher = await _coordinator(call).async_redeem_promo_voucher(
        call.data["voucher_id"]
    )
    return {"voucher": voucher}


def _acting_name() -> str:
    """Who is acting, for the logs of points (2.4.0)."""
    acting = _ACTING.get()
    return acting.name if acting is not None else ""


async def _async_loyalty_reward(call: ServiceCall) -> ServiceResponse:
    """Give a client her reward voucher for the points, and send it on WhatsApp."""
    return await _coordinator(call).async_loyalty_reward(
        call.data["client_id"], _acting_name(), call.data.get("send", True)
    )


async def _async_loyalty_adjust(call: ServiceCall) -> ServiceResponse:
    """Add or take points by hand, with a reason."""
    return await _coordinator(call).async_loyalty_adjust(
        call.data["client_id"], call.data["points"], call.data.get("note", ""), _acting_name()
    )


async def _async_save_partner(call: ServiceCall) -> ServiceResponse:
    """Add or change a partner."""
    data = {k: v for k, v in call.data.items() if v is not None}
    return await _coordinator(call).async_save_partner(data)


async def _async_partner_points_adjust(call: ServiceCall) -> ServiceResponse:
    """Add or take a partner's points by hand."""
    return await _coordinator(call).async_partner_points_adjust(
        call.data["partner_id"], call.data["points"], call.data.get("note", ""), _acting_name()
    )


async def _async_split_from_group(call: ServiceCall) -> ServiceResponse:
    """Take a person out of her group: a booking of her own (2.8.8)."""
    return await _coordinator(call).async_split_from_group(call.data[ATTR_APPOINTMENT_ID])


async def _async_join_group(call: ServiceCall) -> ServiceResponse:
    """Add another booking, by its code, to this group (2.8.8)."""
    return await _coordinator(call).async_join_group(call.data[ATTR_APPOINTMENT_ID], call.data["code"])


async def _async_telegram_status(call: ServiceCall) -> ServiceResponse:
    """The bot built into Spa Booking: name, state, who wrote to it (2.9.0)."""
    return await _coordinator(call).async_telegram_status()


async def _async_send_loyalty_voucher(call: ServiceCall) -> ServiceResponse:
    """A loyalty voucher sent by hand to a client or a partner (2.8.11)."""
    data = dict(call.data)
    return await _coordinator(call).async_send_loyalty_voucher(
        client_id=data.get("client_id", ""), partner_id=data.get("partner_id", ""),
        discount_percent=data.get("discount_percent"), days=data.get("days"),
        min_spend=data.get("min_spend"), by=_acting_name(),
    )


async def _async_partner_detail(call: ServiceCall) -> ServiceResponse:
    """A partner's bookings, points and prizes (2.8.6)."""
    return _coordinator(call).partner_detail(call.data["partner_id"])


async def _async_partner_reward(call: ServiceCall) -> ServiceResponse:
    """Turn a partner's points into a voucher and send it (2.8.6)."""
    return await _coordinator(call).async_partner_reward(
        call.data["partner_id"], _acting_name(), call.data.get("send", True)
    )


async def _async_set_appointment_partner(call: ServiceCall) -> ServiceResponse:
    """Name or clear the partner of a booking (and its party)."""
    return await _coordinator(call).async_set_appointment_partner(
        call.data[ATTR_APPOINTMENT_ID], call.data.get("partner_id") or ""
    )


async def _async_send_partner_campaign(call: ServiceCall) -> ServiceResponse:
    """Send a partner campaign now, or a test to one address."""
    return await _coordinator(call).async_send_partner_campaign(
        call.data["campaign_id"], call.data.get("test_to") or ""
    )


async def _async_delete_all_partners(call: ServiceCall) -> ServiceResponse:
    """Empty the partner list (2.7.3)."""
    return await _coordinator(call).async_delete_all_partners()


async def _async_wp_sync(call: ServiceCall) -> ServiceResponse:
    """Read the vouchers sold on the WordPress shop now (2.7.0)."""
    return await _coordinator(call).async_wp_sync(reason="a mano")


async def _async_wp_test(call: ServiceCall) -> ServiceResponse:
    """Check the shop's plugin and read its products."""
    return await _coordinator(call).async_wp_test()


async def _async_wp_new_secret(call: ServiceCall) -> ServiceResponse:
    """A new key for the shop's plugin."""
    return await _coordinator(call).async_wp_new_secret()


async def _async_wp_redeem(call: ServiceCall) -> ServiceResponse:
    """Send a voucher's redemption to the shop again."""
    return await _coordinator(call).async_wp_redeem(call.data["voucher_id"])


async def _async_import_partners(call: ServiceCall) -> ServiceResponse:
    """Add many partners at once, from the file the card read (2.6.0)."""
    return await _coordinator(call).async_import_partners(call.data["partners"])


async def _async_delete_partner(call: ServiceCall) -> ServiceResponse:
    """Remove a partner."""
    return await _coordinator(call).async_delete_partner(call.data["partner_id"])


async def _async_delete_promo_voucher(call: ServiceCall) -> ServiceResponse:
    """Remove a loyalty voucher ("Voucher fedelta") from the list."""
    return await _coordinator(call).async_delete_promo_voucher(
        call.data["voucher_id"]
    )


def _bridge(call: ServiceCall) -> Any:
    """The built-in WhatsApp connection, or a clear error when it is off."""
    bridge = _coordinator(call).wa_bridge
    if bridge is None:
        raise ValidationError(
            "WhatsApp integrato non attivo: sceglilo in Configurazione › WhatsApp"
        )
    return bridge


async def _async_whatsapp_status(call: ServiceCall) -> ServiceResponse:
    """State of the built-in WhatsApp connection, with the QR code if linking."""
    coordinator = _coordinator(call)
    if coordinator.wa_bridge is None:
        return {"engine": coordinator.whatsapp_engine, "state": "off", "label": "Non attivo"}
    status = await coordinator.wa_bridge.async_status()
    return {"engine": coordinator.whatsapp_engine, **status}


async def _async_whatsapp_pair(call: ServiceCall) -> ServiceResponse:
    """Start linking the number: the QR code appears in whatsapp_status."""
    try:
        return await _bridge(call).async_pair_start()
    except WahaError as err:
        raise ValidationError(str(err)) from err


async def _async_whatsapp_pair_code(call: ServiceCall) -> ServiceResponse:
    """A code to type on the phone, for when the QR code cannot be scanned."""
    phone = messaging.international_digits(str(call.data.get("phone") or ""))
    if not phone:
        raise ValidationError("Indica il numero di telefono da collegare")
    try:
        return {"code": await _bridge(call).async_pair_code(phone)}
    except WahaError as err:
        raise ValidationError(str(err)) from err


async def _async_whatsapp_logout(call: ServiceCall) -> ServiceResponse:
    """Unlink the number from Spa Booking."""
    try:
        await _bridge(call).async_logout()
    except WahaError as err:
        raise ValidationError(str(err)) from err
    return {"state": "not_linked"}


async def _async_run_scheduled_jobs(call: ServiceCall) -> ServiceResponse:
    """Run every timed job now (reminders, offers, vouchers, report...)."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    if coordinator.scheduler is None:
        raise ValidationError("Pianificatore non avviato")
    from homeassistant.util import dt as dt_util

    return await coordinator.scheduler.async_run(dt_util.now(), force=True)


async def _async_promo_voucher_tick(call: ServiceCall) -> ServiceResponse:
    """Send due loyalty-voucher messages and drop the expired unused ones."""
    return await _coordinator(call).async_promo_voucher_tick()


async def _async_manual_confirm_offer(call: ServiceCall) -> ServiceResponse:
    """Conferma manualmente l'offerta di un appuntamento."""
    return await _coordinator(call).async_manual_confirm_offer(
        call.data[ATTR_APPOINTMENT_ID]
    )


async def _async_add_payment(call: ServiceCall) -> ServiceResponse:
    """Register one taking on an appointment."""
    data = call.data
    return await _coordinator(call).async_add_payment(
        data[ATTR_APPOINTMENT_ID],
        data[ATTR_METHOD],
        data[ATTR_AMOUNT],
        data.get(ATTR_DATE, ""),
    )


async def _async_delete_payment(call: ServiceCall) -> ServiceResponse:
    """Remove one registered taking from an appointment."""
    data = call.data
    return await _coordinator(call).async_delete_payment(
        data[ATTR_APPOINTMENT_ID], data[ATTR_PAYMENT_ID]
    )


async def _async_send_operator_message(call: ServiceCall) -> ServiceResponse:
    """Send an informational message to one operator."""
    data = call.data
    return await _coordinator(call).async_send_operator_message(
        data[ATTR_OPERATOR_ID], data[ATTR_KIND]
    )


async def _async_send_guest_summary(call: ServiceCall) -> ServiceResponse:
    """Send the guest a WhatsApp summary of one or more appointments."""
    return await _coordinator(call).async_send_guest_summary(
        call.data.get(ATTR_APPOINTMENT_ID),
        call.data.get(ATTR_APPOINTMENT_IDS),
        only=bool(call.data.get("only")),
    )


async def _async_send_deposit_request(call: ServiceCall) -> ServiceResponse:
    """Ask one guest, by WhatsApp, to pay her deposit."""
    return await _coordinator(call).async_send_deposit_request(
        call.data[ATTR_APPOINTMENT_ID], resend=call.data.get("resend", False)
    )


async def _async_send_promo(call: ServiceCall) -> ServiceResponse:
    """Broadcast the promotional message to the chosen clients."""
    data = call.data
    return await _coordinator(call).async_send_promo(
        data.get("client_ids"),
        message=data.get("message"),
        promo_id=data.get("promo_id") or None,
    )


async def _async_promo_automatic(call: ServiceCall) -> ServiceResponse:
    """Daily automatic broadcast of the promotional message."""
    return await _coordinator(call).async_scheduled_promo()


async def _async_whatsapp_chats(call: ServiceCall) -> ServiceResponse:
    """The WhatsApp conversations of the WhatsApp tab."""
    return {"chats": _coordinator(call).whatsapp_chats()}


async def _async_delete_whatsapp_chats(call: ServiceCall) -> ServiceResponse:
    """Delete one conversation (chat_id) or all of them (all: true)."""
    chat_id = call.data.get("chat_id")
    if not chat_id and not call.data.get("all"):
        raise ValidationError("Indica la chat da eliminare, oppure all: true per tutte")
    removed = await _coordinator(call).async_delete_chats(None if call.data.get("all") else chat_id)
    return {"removed": removed}


SEND_EMAIL_SCHEMA = vol.Schema(
    {
        vol.Required("to"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("subject"): cv.string,
        vol.Required("message"): cv.string,
        vol.Optional("html"): vol.Any(cv.string, None),
    },
    extra=vol.PREVENT_EXTRA,
)

TEST_EMAIL_SCHEMA = vol.Schema(
    {vol.Optional("to"): vol.Any(cv.string, None)}, extra=vol.PREVENT_EXTRA
)


GOOGLE_AUTH_URL_SCHEMA = vol.Schema(
    {vol.Required("redirect_uri"): cv.string, vol.Optional("purpose", default="email"): vol.In(["email", "drive"])},
    extra=vol.PREVENT_EXTRA,
)
GDRIVE_EMPTY_SCHEMA = vol.Schema({}, extra=vol.PREVENT_EXTRA)
GDRIVE_RESTORE_SCHEMA = vol.Schema({vol.Required("file_id"): cv.string}, extra=vol.PREVENT_EXTRA)


async def _async_google_auth_url(call: ServiceCall) -> ServiceResponse:
    """The Google page for «Accedi con Google», for this card's address."""
    return await _coordinator(call).async_google_auth_url(call.data["redirect_uri"], call.data.get("purpose", "email"))


async def _async_gdrive_backup(call: ServiceCall) -> ServiceResponse:
    """Write today's backup to Google Drive now (2.8.0)."""
    return await _coordinator(call).async_gdrive_backup(reason="a mano")


async def _async_gdrive_list(call: ServiceCall) -> ServiceResponse:
    """The backups on Google Drive."""
    return await _coordinator(call).async_gdrive_list()


async def _async_gdrive_restore(call: ServiceCall) -> ServiceResponse:
    """Replace the data with a backup from Google Drive."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_gdrive_restore(call.data["file_id"])


async def _async_google_disconnect(call: ServiceCall) -> ServiceResponse:
    """Forget the Google account (and withdraw the permission on Google)."""
    return await _coordinator(call).async_google_disconnect()


async def _async_send_email(call: ServiceCall) -> ServiceResponse:
    """Send an email with the mailbox set in Configurazione › Email."""
    return await _coordinator(call).async_send_email(
        call.data["to"], call.data["subject"], call.data["message"], call.data.get("html")
    )


async def _async_test_email(call: ServiceCall) -> ServiceResponse:
    """A test email, to the sender itself unless told otherwise."""
    return await _coordinator(call).async_test_email(call.data.get("to") or "")


async def _async_test_web_notice(call: ServiceCall) -> ServiceResponse:
    """Send the web-request notice to every number, as a test."""
    return await _coordinator(call).async_test_web_notice()


async def _async_send_reminders(call: ServiceCall) -> ServiceResponse:
    """Send the guest reminders that are due, or one chosen appointment."""
    return await _coordinator(call).async_send_reminders(
        call.data.get(ATTR_APPOINTMENT_ID), manual=True
    )


async def _async_send_review_requests(call: ServiceCall) -> ServiceResponse:
    """Ask the guests whose visit is over for a review, or one chosen guest."""
    return await _coordinator(call).async_send_review_requests(
        call.data.get(ATTR_APPOINTMENT_ID)
    )


async def _async_voucher_expiry_reminder(call: ServiceCall) -> ServiceResponse:
    """Send voucher expiration reminders to recipients whose vouchers are expiring soon."""
    return await _coordinator(call).async_send_voucher_expiry_reminders()


async def _async_clear_slot_block(call: ServiceCall) -> ServiceResponse:
    """Reopen a refused time window."""
    data = call.data
    return await _coordinator(call).async_clear_slot_blocks(
        data[ATTR_OPERATOR_ID], data.get(ATTR_APPOINTMENT_ID, "")
    )


async def _async_expire_offers(call: ServiceCall) -> ServiceResponse:
    """Move on from offers nobody answered."""
    return await _coordinator(call).async_expire_offers()


async def _async_cancel_appointment(call: ServiceCall) -> ServiceResponse:
    """Cancel an appointment."""
    coordinator = _coordinator(call)
    appointment = await coordinator.async_cancel_appointment(
        call.data[ATTR_APPOINTMENT_ID], call.data.get(ATTR_REASON, ""),
        whole_group=call.data.get("whole_group", False),
    )
    ids = appointment.get("cancelled_ids") or [appointment["id"]]
    guest = None
    if call.data.get("notify_guest"):
        guest = await coordinator.async_send_cancel_message(ids)
    return {"appointment": appointment, "cancelled_ids": ids, "guest": guest}


async def _async_save_client(call: ServiceCall) -> ServiceResponse:
    """Create or update a client."""
    data = call.data
    client = await _coordinator(call).async_save_client(
        client_id=data.get(ATTR_CLIENT_ID),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        notes=data.get("notes", ""),
        promo_opt_in=data.get("promo_opt_in"),
    )
    return {"client": client}


async def _async_search_clients(call: ServiceCall) -> ServiceResponse:
    """Search clients."""
    clients = _coordinator(call).search_clients(
        call.data.get(ATTR_QUERY, ""), call.data.get(ATTR_LIMIT, 20)
    )
    return {"clients": clients, "count": len(clients)}


async def _async_get_client_history(call: ServiceCall) -> ServiceResponse:
    """Return every appointment of a client."""
    coordinator = _coordinator(call)
    client_id = call.data[ATTR_CLIENT_ID]
    client = coordinator.get_client(client_id)
    history = coordinator.client_history(client_id)
    return {"client": client, "appointments": history, "count": len(history)}


async def _async_delete_client(call: ServiceCall) -> ServiceResponse:
    """Delete a client record."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_delete_client(call.data[ATTR_CLIENT_ID])


async def _async_merge_clients(call: ServiceCall) -> ServiceResponse:
    """Fold duplicate client cards into the one the reception chooses."""
    return await _coordinator(call).async_merge_clients(
        call.data["target_client_id"], call.data["source_client_ids"]
    )


async def _async_delete_appointment(call: ServiceCall) -> ServiceResponse:
    """Delete a cancelled appointment for good."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_delete_appointment(
        call.data[ATTR_APPOINTMENT_ID]
    )


async def _async_update_appointment(call: ServiceCall) -> ServiceResponse:
    """Update an existing appointment, or a whole group of them."""
    data = call.data
    coordinator = _coordinator(call)
    fields = {
        "treatment_id": data.get(ATTR_TREATMENT_ID),
        "start": data.get("start"),
        "client_id": data.get(ATTR_CLIENT_ID),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "client_notes": data.get("client_notes", ""),
        "operator_id": data.get(ATTR_OPERATOR_ID),
        "operator_ids": data.get(ATTR_OPERATOR_IDS),
        "notes": data.get("notes", ""),
        "payment": data.get(ATTR_PAYMENT),
        "pending": data.get("pending"),
        "confirmed_by": data.get("confirmed_by"),
        "guest_type": data.get(ATTR_GUEST_TYPE),
        "extras": data.get(ATTR_EXTRAS),
        "list_price": data.get("list_price"),
        "price": data.get("price"),
        "force_client_overlap": data.get("force_client_overlap", False),
        "therapist_preference": data.get("therapist_preference"),
    }
    if data.get("whole_group"):
        return await coordinator.async_update_appointment_group(
            data[ATTR_APPOINTMENT_ID], **fields
        )
    appointment = await coordinator.async_update_appointment(
        data[ATTR_APPOINTMENT_ID], **fields
    )
    return {"appointment": appointment}


async def _async_add_closure(call: ServiceCall) -> ServiceResponse:
    """Create a closure from the dashboard."""
    data = call.data
    closure = await _coordinator(call).async_add_closure(
        scope=data["scope"],
        operator_id=data[ATTR_OPERATOR_ID],
        category_id=data[ATTR_CATEGORY_ID],
        date_from=data["date_from"],
        date_to=data["date_to"],
        start=data["start"],
        end=data["end"],
        label=data["label"],
        skip_weekdays=data["skip_weekdays"],
    )
    return {"closure": closure}


async def _async_delete_closure(call: ServiceCall) -> ServiceResponse:
    """Delete a closure."""
    return await _coordinator(call).async_delete_closure(call.data["closure_id"])


async def _async_resize_appointment_group(call: ServiceCall) -> ServiceResponse:
    """Set how many people share an appointment's slot."""
    return await _coordinator(call).async_resize_appointment_group(
        call.data[ATTR_APPOINTMENT_ID], call.data["persons"]
    )


async def _async_check_in_appointment(call: ServiceCall) -> ServiceResponse:
    """Record the client entering the spa, or undo it."""
    coordinator = _coordinator(call)
    ids = list(dict.fromkeys([call.data[ATTR_APPOINTMENT_ID], *call.data.get("appointment_ids", [])]))
    done = [await coordinator.async_check_in_appointment(item, call.data.get(ATTR_CHECKED_IN, True)) for item in ids]
    return {"appointment": done[0], "appointments": done}


async def _async_check_out_appointment(call: ServiceCall) -> ServiceResponse:
    """Record the client leaving the spa."""
    coordinator = _coordinator(call)
    ids = list(dict.fromkeys([call.data[ATTR_APPOINTMENT_ID], *call.data.get("appointment_ids", [])]))
    done = [await coordinator.async_check_out_appointment(item) for item in ids]
    return {"appointment": done[0], "appointments": done}


async def _async_reload_card(call: ServiceCall) -> ServiceResponse:
    """Re-register the card URL, optionally under a new version."""
    return await _coordinator(call).async_reload_card(
        call.data.get("version", "")
    )


async def _async_mark_requests_seen(call: ServiceCall) -> ServiceResponse:
    """Clear the bell: every web request is now considered opened."""
    return await _coordinator(call).async_mark_requests_seen()


async def _async_regenerate_public_token(call: ServiceCall) -> ServiceResponse:
    """Issue a fresh website token and stop honouring the previous one."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_regenerate_public_token()


async def _async_web_snippet(call: ServiceCall) -> ServiceResponse:
    """Return the code to paste into the site's page, token included."""
    return await _coordinator(call).async_web_snippet(call.data.get("base_url", ""))


async def _async_send_external_message(call: ServiceCall) -> ServiceResponse:
    """Send a WhatsApp message to an external number (non-operator)."""
    data = call.data
    return await _coordinator(call).async_send_external_message(
        data.get("chat_id", ""),
        data.get("text", ""),
    )


async def _async_send_test_message(call: ServiceCall) -> ServiceResponse:
    """Send a test message to one chat, so the desk can check a channel."""
    result = await _coordinator(call).async_send_test_message(
        call.data[ATTR_CHANNEL],
        call.data[ATTR_CHAT_ID],
        call.data.get(ATTR_CONFIG_ENTRY_ID, ""),
        call.data.get("message", ""),
    )
    return {"result": result}


async def _async_get_daily_agenda(call: ServiceCall) -> ServiceResponse:
    """Return the agenda of a day, grouped by operator and category."""
    agenda = _coordinator(call).agenda(
        as_date(call.data[ATTR_DATE]),
        operator_id=call.data.get(ATTR_OPERATOR_ID),
        category_id=call.data.get(ATTR_CATEGORY_ID),
    )
    return {"agenda": agenda}


async def _async_get_config(call: ServiceCall) -> ServiceResponse:
    """Return categories, treatments and operators."""
    coordinator = _coordinator(call)
    config = coordinator.config_payload()
    if await caller_level(call, coordinator) != "admin":
        config["settings"] = _without_secrets(config["settings"])
    return {"config": config}


async def _async_add_category(call: ServiceCall) -> ServiceResponse:
    """Create a category."""
    data = call.data
    category = await _coordinator(call).async_add_category(
        data["name"],
        data["requires_operator"],
        color=data.get("color", ""),
        pause_min=data["pause_min"],
        days=data["days"],
        morning_days=data.get("morning_days"),
        afternoon_days=data.get("afternoon_days"),
        morning_start=data.get("morning_start", ""),
        morning_end=data.get("morning_end", ""),
        afternoon_start=data.get("afternoon_start", ""),
        afternoon_end=data.get("afternoon_end", ""),
        exclusive_with=data["exclusive_with"],
    )
    return {"category": category}


async def _async_update_category(call: ServiceCall) -> ServiceResponse:
    """Update a category."""
    data = call.data
    category = await _coordinator(call).async_update_category(
        data[ATTR_CATEGORY_ID],
        name=data.get("name"),
        requires_operator=data.get("requires_operator"),
        color=data.get("color"),
        pause_min=data.get("pause_min"),
        days=data.get("days"),
        morning_days=data.get("morning_days"),
        afternoon_days=data.get("afternoon_days"),
        morning_start=data.get("morning_start"),
        morning_end=data.get("morning_end"),
        afternoon_start=data.get("afternoon_start"),
        afternoon_end=data.get("afternoon_end"),
        exclusive_with=data.get("exclusive_with"),
    )
    return {"category": category}


async def _async_delete_category(call: ServiceCall) -> ServiceResponse:
    """Delete a category."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_delete_category(
        call.data[ATTR_CATEGORY_ID], call.data["force"]
    )


async def _async_add_treatment(call: ServiceCall) -> ServiceResponse:
    """Create a treatment."""
    data = call.data
    treatment = await _coordinator(call).async_add_treatment(
        data["name"],
        category_id=data.get(ATTR_CATEGORY_ID),
        duration_min=data["duration_min"],
        price=data.get("price"),
        active=data["active"],
        web_visible=data["web_visible"],
        min_parallel=data["min_parallel"],
        max_parallel=data["max_parallel"],
        vat_rate=data.get("vat_rate"),
        operator_ids=data.get("operator_ids"),
    )
    return {"treatment": treatment}


async def _async_update_treatment(call: ServiceCall) -> ServiceResponse:
    """Update a treatment."""
    data = call.data
    treatment = await _coordinator(call).async_update_treatment(
        data[ATTR_TREATMENT_ID],
        name=data.get("name"),
        category_id=data.get(ATTR_CATEGORY_ID),
        duration_min=data.get("duration_min"),
        price=data.get("price"),
        active=data.get("active"),
        web_visible=data.get("web_visible"),
        min_parallel=data.get("min_parallel"),
        max_parallel=data.get("max_parallel"),
        vat_rate=data.get("vat_rate"),
        operator_ids=data.get("operator_ids"),
    )
    return {"treatment": treatment}


async def _async_delete_treatment(call: ServiceCall) -> ServiceResponse:
    """Delete a treatment."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_delete_treatment(
        call.data[ATTR_TREATMENT_ID], call.data["force"]
    )


async def _async_add_operator(call: ServiceCall) -> ServiceResponse:
    """Create an operator."""
    operator = await _coordinator(call).async_add_operator(
        call.data["name"],
        role=call.data["role"],
        phone=call.data["phone"],
        whatsapp_chat_id=call.data["whatsapp_chat_id"],
        telegram_chat_id=call.data["telegram_chat_id"],
        treatment_ids=call.data["treatment_ids"],
        notify_whatsapp=call.data["notify_whatsapp"],
        notify_telegram=call.data["notify_telegram"],
        notify_service=call.data["notify_service"],
        notify_on_create=call.data["notify_on_create"],
        priority=call.data["priority"],
        gender=call.data.get("gender", ""),
        active=call.data["active"],
    )
    return {"operator": operator}


async def _async_update_operator(call: ServiceCall) -> ServiceResponse:
    """Update an operator."""
    data = call.data
    operator = await _coordinator(call).async_update_operator(
        data[ATTR_OPERATOR_ID],
        name=data.get("name"),
        role=data.get("role"),
        phone=data.get("phone"),
        whatsapp_chat_id=data.get("whatsapp_chat_id"),
        telegram_chat_id=data.get("telegram_chat_id"),
        treatment_ids=data.get("treatment_ids"),
        notify_whatsapp=data.get("notify_whatsapp"),
        notify_telegram=data.get("notify_telegram"),
        notify_service=data.get("notify_service"),
        notify_on_create=data.get("notify_on_create"),
        priority=data.get("priority"),
        gender=data.get("gender"),
        active=data.get("active"),
    )
    return {"operator": operator}


async def _async_delete_operator(call: ServiceCall) -> ServiceResponse:
    """Delete an operator."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_delete_operator(
        call.data[ATTR_OPERATOR_ID], call.data["force"]
    )


async def _async_export_data(call: ServiceCall) -> ServiceResponse:
    """Return the whole dataset (what the card loads)."""
    coordinator = _coordinator(call)
    data = coordinator.export_data()
    settings = data.get("settings") or {}
    if await caller_level(call, coordinator) != "admin":
        settings = _without_secrets(settings)
        # The change history of the bookings is for the administrator only.
        data = {
            **data,
            "appointments": [
                {key: value for key, value in item.items() if key != "history"}
                for item in data.get("appointments") or []
            ],
        }
    # The card never needs the PIN hashes (the full backup keeps them), nor
    # the mailbox password: it only learns whether one is saved (2.4.1).
    settings = {
        **settings,
        KEY_PROFILES: access.public_profiles(settings.get(KEY_PROFILES) or {}),
        "smtp_password": "",
        "smtp_password_set": bool(((coordinator.data or {}).get("settings") or {}).get("smtp_password")),
        "google_client_secret": "",
        "google_refresh_token": "",
        "google_secret_set": bool(((coordinator.data or {}).get("settings") or {}).get("google_client_secret")),
        "google_connected": bool(((coordinator.data or {}).get("settings") or {}).get("google_refresh_token")),
    }
    # The points of each client (2.4.0), worked out here once for the card.
    data = {
        **data,
        "settings": settings,
        "loyalty": coordinator.loyalty_summary(),
        "partner_points": coordinator.partner_points_summary(),
    }
    return {
        "data": data,
        "integration_version": INTEGRATION_VERSION,
    }


async def _async_export_all(call: ServiceCall) -> ServiceResponse:
    """Return the whole dataset as JSON."""
    return {"data": _coordinator(call).export_data()}


async def _async_import_data(call: ServiceCall) -> ServiceResponse:
    """Replace the dataset with the given payload."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_import_data(call.data[ATTR_PAYLOAD])


async def _async_import_all(call: ServiceCall) -> ServiceResponse:
    """Replace the dataset with the given payload."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.async_import_data(call.data[ATTR_PAYLOAD])


async def _async_update_booking_batch(call: ServiceCall) -> ServiceResponse:
    """Update or rebuild a batch of appointments."""
    data = call.data
    return await _coordinator(call).async_update_booking_batch(
        data["appointment_id"], data[ATTR_ROWS], _acting_user_id(call)
    )


async def _async_export_clients_csv(call: ServiceCall) -> ServiceResponse:
    """Export the client list as a CSV string."""
    return {"csv": _coordinator(call).export_clients_csv()}


async def _async_import_clients_csv(call: ServiceCall) -> ServiceResponse:
    """Create clients from a CSV string."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    return await coordinator.import_clients_csv(call.data["csv"])


async def _async_get_monthly_report(call: ServiceCall) -> ServiceResponse:
    """Return the monthly massage report, optionally sending it."""
    coordinator = _coordinator(call)
    month = call.data.get(ATTR_MONTH)
    if call.data[ATTR_NOTIFY]:
        return await coordinator.async_send_monthly_report(month)
    return {"report": coordinator.monthly_report(month)}


async def _async_update_settings(call: ServiceCall) -> ServiceResponse:
    """Update the settings: layout for operators, the rest for admins only."""
    coordinator = _coordinator(call)
    if set(call.data) - OPERATOR_SETTINGS:
        await _require_admin(call, coordinator)
    settings = await coordinator.async_update_settings(**call.data)
    if await caller_level(call, coordinator) != "admin":
        settings = _without_secrets(settings)
    else:
        settings = {
            **settings,
            KEY_PROFILES: access.public_profiles(settings.get(KEY_PROFILES) or {}),
        }
    return {"settings": settings}


async def _async_check_waha(call: ServiceCall) -> ServiceResponse:
    """Ask the WhatsApp connection built into Spa Booking how it is."""
    return await _coordinator(call).async_check_waha()


async def _async_get_users(call: ServiceCall) -> ServiceResponse:
    """Return the Home Assistant users for the Accessi tab."""
    users = await _coordinator(call).async_users_payload()
    return {"users": users}


async def _async_set_user_permissions(call: ServiceCall) -> ServiceResponse:
    """Save the access level for a user."""
    coordinator = _coordinator(call)
    await _require_admin(call, coordinator)
    permissions = await coordinator.async_set_user_permissions(
        call.data[ATTR_USER_ID], call.data[ATTR_LEVEL]
    )
    return {"permissions": permissions}


# ------------------------------------------------------------------ logins


async def _async_whoami(call: ServiceCall) -> ServiceResponse:
    """Who the card is acting as, and on the shared tablet who may sign in.

    Called by the card when it opens and while somebody uses it, so it also
    keeps the PIN session of the tablet alive.
    """
    coordinator = _coordinator(call)
    acting = await caller_identity(call, coordinator, refresh=True)
    result: dict[str, Any] = {
        "user_id": acting.user_id,
        "name": acting.name,
        "level": acting.level,
        "operator_id": acting.operator_id,
        "shared": acting.device is not None,
        "idle_minutes": coordinator.pin_idle_minutes,
    }
    if acting.device is not None:
        result["locked_for"] = coordinator.pin_sessions.locked_for(
            acting.device, time.monotonic()
        )
        result["people"] = await _pin_people(call, coordinator)
    return result


async def _pin_people(
    call: ServiceCall, coordinator: SpaBookingCoordinator
) -> list[dict[str, Any]]:
    """The people who can sign in on the tablet: an active user with a PIN."""
    people = []
    permissions = coordinator.permissions_payload()
    for user_id, profile in coordinator.profiles().items():
        if profile.get("shared") or not profile.get("pin_hash"):
            continue
        user = await call.hass.auth.async_get_user(user_id)
        if user is None or not user.is_active:
            continue
        level = "admin" if (user.is_admin or user.is_owner) else permissions.get(user_id, "none")
        if level == "none":
            continue
        people.append({"user_id": user_id, "name": user.name or "", "level": level})
    return sorted(people, key=lambda person: person["name"].lower())


async def _async_pin_login(call: ServiceCall) -> ServiceResponse:
    """On the shared tablet: the person picks her face and types her PIN."""
    coordinator = _coordinator(call)
    device = call.context.user_id if call.context else None
    if not device or not coordinator.profile(device).get("shared"):
        raise ValidationError("Il PIN si usa solo sul tablet condiviso della reception")
    sessions = coordinator.pin_sessions
    now = time.monotonic()
    wait = sessions.locked_for(device, now)
    if wait:
        raise ValidationError(f"Troppi PIN sbagliati: riprova tra {wait} secondi")
    user_id = call.data[ATTR_USER_ID]
    profile = coordinator.profile(user_id)
    people = {person["user_id"] for person in await _pin_people(call, coordinator)}
    ok = user_id in people and await call.hass.async_add_executor_job(
        access.check_pin,
        call.data["pin"],
        profile.get("pin_salt", ""),
        profile.get("pin_hash", ""),
    )
    if not ok:
        wait = sessions.failure(device, now)
        if wait:
            raise ValidationError(f"PIN sbagliato. Tablet bloccato per {wait} secondi")
        raise ValidationError("PIN sbagliato")
    sessions.start(device, user_id, now)
    return await _async_whoami(call)


async def _pin_signer(
    call: ServiceCall, coordinator: SpaBookingCoordinator, pin: str
) -> tuple[str, str]:
    """Who owns ``pin``: the person signing a voucher (reception or above).

    Wrong PINs count like on the tablet: five in a row lock the signature
    for a minute on that device.
    """
    sessions = coordinator.pin_sessions
    key = f"sign:{call.context.user_id if call.context else 'system'}"
    now = time.monotonic()
    wait = sessions.locked_for(key, now)
    if wait:
        raise ValidationError(f"Troppi PIN sbagliati: riprova tra {wait} secondi")
    profiles = coordinator.profiles()
    matches = []
    for person in await _pin_people(call, coordinator):
        profile = profiles.get(person["user_id"]) or {}
        if await call.hass.async_add_executor_job(
            access.check_pin, pin, profile.get("pin_salt", ""), profile.get("pin_hash", "")
        ):
            matches.append(person)
    if len(matches) > 1:
        raise ValidationError(
            "Questo PIN è usato da più persone: cambiatelo in Configurazione › Accessi"
        )
    if not matches:
        wait = sessions.failure(key, now)
        if wait:
            raise ValidationError(f"PIN sbagliato. Firma bloccata per {wait} secondi")
        raise ValidationError("PIN sbagliato")
    signer = matches[0]
    if _LEVEL_RANK.get(signer["level"], 0) < _LEVEL_RANK["operator"]:
        raise ValidationError(f"{signer['name']} non può creare voucher (serve il ruolo Reception)")
    sessions.start(key, signer["user_id"], now)
    sessions.end(key)
    return signer["user_id"], signer["name"]


async def _async_pin_logout(call: ServiceCall) -> ServiceResponse:
    """Sign the shared tablet out (the next person types her own PIN)."""
    device = call.context.user_id if call.context else None
    if device:
        _coordinator(call).pin_sessions.end(device)
    return {"ok": True}


async def _target_user(call: ServiceCall, user_id: str) -> Any:
    """A Home Assistant user an administrator of the card may manage."""
    user = await call.hass.auth.async_get_user(user_id)
    if user is None or user.system_generated:
        raise ValidationError("Utente non trovato")
    if (user.is_owner or user.is_admin) and not await _caller_is_ha_admin(call):
        raise ValidationError(
            "Solo un amministratore di Home Assistant può modificare un altro amministratore"
        )
    return user


async def _async_set_user_profile(call: ServiceCall) -> ServiceResponse:
    """Link a user to an operator, set her PIN or mark the shared tablet."""
    coordinator = _coordinator(call)
    data = call.data
    user = await _target_user(call, data[ATTR_USER_ID])
    shared = data.get("shared")
    if shared and (user.is_admin or user.is_owner):
        raise ValidationError(
            "Un amministratore di Home Assistant non può essere il tablet condiviso"
        )
    try:
        profile = await coordinator.async_set_user_profile(
            user.id,
            operator_id=data.get(ATTR_OPERATOR_ID),
            shared=shared,
            pin=data.get("pin"),
            clear_pin=data.get("clear_pin", False),
        )
    except SpaBookingError as err:
        raise ValidationError(str(err)) from err
    return {"profile": profile}


def _ha_auth_provider(call: ServiceCall) -> Any:
    """The username-and-password provider of Home Assistant."""
    provider = call.hass.auth.get_auth_provider("homeassistant", None)
    if provider is None:
        raise ValidationError("Gli utenti con password non sono attivi in Home Assistant")
    return provider


def _username_of(user: Any) -> str:
    for credential in getattr(user, "credentials", None) or []:
        if credential.auth_provider_type == "homeassistant":
            return str(credential.data.get("username") or "")
    return ""


async def _async_create_user(call: ServiceCall) -> ServiceResponse:
    """Create a Home Assistant user for an operator, with her role.

    The user is an ordinary (non administrator) Home Assistant user: what she
    may do in Spa Booking is the level chosen here.
    """
    coordinator = _coordinator(call)
    data = call.data
    provider = _ha_auth_provider(call)
    username = data["username"].strip().lower()
    if len(data["password"]) < 6:
        raise ValidationError("La password deve avere almeno 6 caratteri")
    for existing in await call.hass.auth.async_get_users():
        if _username_of(existing) == username:
            raise ValidationError(f"Il nome utente «{username}» esiste già")
    user = await call.hass.auth.async_create_user(
        data["name"].strip(), group_ids=["system-users"], local_only=data.get("local_only", False)
    )
    try:
        await provider.async_add_auth(username, data["password"])
        credentials = await provider.async_get_or_create_credentials({"username": username})
        await call.hass.auth.async_link_user(user, credentials)
    except Exception as err:  # noqa: BLE001 - undo the half-made user
        await call.hass.auth.async_remove_user(user)
        raise ValidationError(f"Utente non creato: {err}") from err
    await coordinator.async_set_user_permissions(user.id, data[ATTR_LEVEL])
    if data.get(ATTR_OPERATOR_ID) or data.get("pin") or data.get("shared"):
        try:
            await coordinator.async_set_user_profile(
                user.id,
                operator_id=data.get(ATTR_OPERATOR_ID) or "",
                shared=data.get("shared", False),
                pin=data.get("pin") or None,
            )
        except SpaBookingError as err:
            raise ValidationError(f"Utente creato, ma: {err}") from err
    return {"user": {"id": user.id, "name": user.name, "username": username}}


async def _async_set_user_password(call: ServiceCall) -> ServiceResponse:
    """Give a user a new password (she forgot hers)."""
    user = await _target_user(call, call.data[ATTR_USER_ID])
    username = _username_of(user)
    if not username:
        raise ValidationError("Questo utente non accede con nome utente e password")
    if len(call.data["password"]) < 6:
        raise ValidationError("La password deve avere almeno 6 caratteri")
    await _ha_auth_provider(call).async_change_password(username, call.data["password"])
    return {"ok": True}


async def _async_set_user_active(call: ServiceCall) -> ServiceResponse:
    """Disable a user who left (or enable her again)."""
    user = await _target_user(call, call.data[ATTR_USER_ID])
    if user.is_owner:
        raise ValidationError("Il proprietario di Home Assistant non si può disattivare")
    active = call.data["active"]
    await call.hass.auth.async_update_user(user, is_active=active)
    if not active:
        _coordinator(call).pin_sessions.end_user(user.id)
    return {"ok": True}


_PIN = vol.All(cv.string, vol.Match(r"^\d{4}$", msg="Il PIN deve essere di 4 cifre"))

PIN_LOGIN_SCHEMA = vol.Schema(
    {vol.Required(ATTR_USER_ID): cv.string, vol.Required("pin"): _PIN}
)
SET_USER_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_USER_ID): cv.string,
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        vol.Optional("shared"): cv.boolean,
        vol.Optional("pin"): _PIN,
        vol.Optional("clear_pin", default=False): cv.boolean,
    }
)
CREATE_USER_SCHEMA = vol.Schema(
    {
        vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=60)),
        vol.Required("username"): vol.All(
            cv.string, vol.Match(r"^[A-Za-z0-9._-]{3,32}$",
                                 msg="Nome utente: 3-32 lettere, numeri, punto o trattino")
        ),
        vol.Required("password"): cv.string,
        vol.Required(ATTR_LEVEL): vol.In(PERMISSION_LEVELS),
        vol.Optional(ATTR_OPERATOR_ID): vol.Any(cv.string, None),
        vol.Optional("pin"): vol.Any(_PIN, ""),
        vol.Optional("shared", default=False): cv.boolean,
        vol.Optional("local_only", default=False): cv.boolean,
    }
)
SET_USER_PASSWORD_SCHEMA = vol.Schema(
    {vol.Required(ATTR_USER_ID): cv.string, vol.Required("password"): cv.string}
)
SET_USER_ACTIVE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_USER_ID): cv.string, vol.Required("active"): cv.boolean}
)


# ----------------------------------------------------------------- updates


async def _async_update_status(call: ServiceCall) -> ServiceResponse:
    """Installed, running and available versions, and whether to restart."""
    coordinator = _coordinator(call)
    hass = call.hass
    on_disk = await hass.async_add_executor_job(updates.disk_version)
    fingerprint = await hass.async_add_executor_job(updates.code_fingerprint)
    running_print = getattr(coordinator, "code_fingerprint", "") or fingerprint
    restart = fingerprint != running_print
    entity = updates.find_update_entity(hass.states.async_all("update"))
    return {
        "running_version": INTEGRATION_VERSION,
        "disk_version": on_disk,
        "restart_needed": restart,
        # Only the card or the form changed: a page reload is enough.
        "reload_only": (not restart) and bool(on_disk) and on_disk != INTEGRATION_VERSION,
        "update": entity,
    }


async def _async_install_update(call: ServiceCall) -> ServiceResponse:
    """Install the new version through the HACS update entity."""
    entity = updates.find_update_entity(call.hass.states.async_all("update"))
    if entity is None:
        raise ValidationError(
            "Aggiornamento non trovato: Spa Booking va installato da HACS per aggiornarsi dalla card"
        )
    if not entity["available"]:
        raise ValidationError("Spa Booking è già all'ultima versione")
    # Not blocking: the download takes a while and the card follows the
    # progress on the entity itself.
    await call.hass.services.async_call(
        "update", "install", {"entity_id": entity["entity_id"]}, blocking=False
    )
    return {"entity_id": entity["entity_id"], "version": entity["latest_version"]}


async def _async_restart_home_assistant(call: ServiceCall) -> ServiceResponse:
    """Restart Home Assistant to load the new version of the integration."""
    await call.hass.services.async_call("homeassistant", "restart", {}, blocking=False)
    return {"ok": True}


_HANDLERS: dict[str, tuple[Any, Any, SupportsResponse]] = {
    SERVICE_CREATE_APPOINTMENT: (
        _async_create_appointment,
        CREATE_APPOINTMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CANCEL_APPOINTMENT: (
        _async_cancel_appointment,
        CANCEL_APPOINTMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_APPOINTMENT: (
        _async_delete_appointment,
        DELETE_APPOINTMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_UPDATE_APPOINTMENT: (
        _async_update_appointment,
        UPDATE_APPOINTMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_ADD_CLOSURE: (
        _async_add_closure,
        ADD_CLOSURE_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_CLOSURE: (
        _async_delete_closure,
        DELETE_CLOSURE_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_RESIZE_APPOINTMENT_GROUP: (
        _async_resize_appointment_group,
        RESIZE_APPOINTMENT_GROUP_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CHECK_IN_APPOINTMENT: (
        _async_check_in_appointment,
        CHECK_IN_APPOINTMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CHECK_OUT_APPOINTMENT: (
        _async_check_out_appointment,
        CHECK_OUT_APPOINTMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SAVE_CLIENT: (
        _async_save_client,
        SAVE_CLIENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEARCH_CLIENTS: (
        _async_search_clients,
        SEARCH_CLIENTS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_CLIENT: (
        _async_delete_client,
        DELETE_CLIENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_MERGE_CLIENTS: (
        _async_merge_clients,
        MERGE_CLIENTS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_GET_CLIENT_HISTORY: (
        _async_get_client_history,
        GET_CLIENT_HISTORY_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_GET_DAILY_AGENDA: (
        _async_get_daily_agenda,
        GET_DAILY_AGENDA_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_GET_CONFIG: (
        _async_get_config,
        GET_CONFIG_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_ADD_CATEGORY: (
        _async_add_category,
        ADD_CATEGORY_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_UPDATE_CATEGORY: (
        _async_update_category,
        UPDATE_CATEGORY_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_CATEGORY: (
        _async_delete_category,
        DELETE_CATEGORY_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_EXPORT_CLIENTS_CSV: (
        _async_export_clients_csv,
        EXPORT_CLIENTS_CSV_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_IMPORT_CLIENTS_CSV: (
        _async_import_clients_csv,
        IMPORT_CLIENTS_CSV_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_ADD_TREATMENT: (
        _async_add_treatment,
        ADD_TREATMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_UPDATE_TREATMENT: (
        _async_update_treatment,
        UPDATE_TREATMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_TREATMENT: (
        _async_delete_treatment,
        DELETE_TREATMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_ADD_OPERATOR: (
        _async_add_operator,
        ADD_OPERATOR_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_UPDATE_OPERATOR: (
        _async_update_operator,
        UPDATE_OPERATOR_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_OPERATOR: (
        _async_delete_operator,
        DELETE_OPERATOR_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_EXPORT_DATA: (_async_export_data, EXPORT_DATA_SCHEMA, SupportsResponse.ONLY),
    SERVICE_EXPORT_ALL: (_async_export_all, EXPORT_ALL_SCHEMA, SupportsResponse.ONLY),
    SERVICE_IMPORT_DATA: (_async_import_data, IMPORT_DATA_SCHEMA, SupportsResponse.ONLY),
    SERVICE_IMPORT_ALL: (_async_import_all, IMPORT_ALL_SCHEMA, SupportsResponse.ONLY),
    SERVICE_GET_MONTHLY_REPORT: (
        _async_get_monthly_report,
        GET_MONTHLY_REPORT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_UPDATE_SETTINGS: (
        _async_update_settings,
        UPDATE_SETTINGS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CHECK_WAHA: (
        _async_check_waha,
        CHECK_WAHA_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_RESPOND_TO_OFFER: (
        _async_respond_to_offer,
        RESPOND_TO_OFFER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SET_OFFER_STATE: (
        _async_set_offer_state,
        SET_OFFER_STATE_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_MANUAL_CONFIRM_OFFER: (
        _async_manual_confirm_offer,
        MANUAL_CONFIRM_OFFER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_ADD_PAYMENT: (
        _async_add_payment,
        ADD_PAYMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_PAYMENT: (
        _async_delete_payment,
        DELETE_PAYMENT_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CREATE_VOUCHER: (
        _async_create_voucher,
        CREATE_VOUCHER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_EXTEND_VOUCHER: (
        _async_extend_voucher,
        EXTEND_VOUCHER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_VOUCHER: (
        _async_delete_voucher,
        DELETE_VOUCHER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_REDEEM_PROMO_VOUCHER: (
        _async_redeem_promo_voucher,
        REDEEM_PROMO_VOUCHER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_LOYALTY_REWARD: (_async_loyalty_reward, LOYALTY_REWARD_SCHEMA, SupportsResponse.ONLY),
    SERVICE_LOYALTY_ADJUST: (_async_loyalty_adjust, LOYALTY_ADJUST_SCHEMA, SupportsResponse.ONLY),
    SERVICE_SAVE_PARTNER: (_async_save_partner, SAVE_PARTNER_SCHEMA, SupportsResponse.ONLY),
    SERVICE_DELETE_PARTNER: (_async_delete_partner, DELETE_PARTNER_SCHEMA, SupportsResponse.ONLY),
    SERVICE_IMPORT_PARTNERS: (_async_import_partners, IMPORT_PARTNERS_SCHEMA, SupportsResponse.ONLY),
    SERVICE_WP_SYNC: (_async_wp_sync, WP_EMPTY_SCHEMA, SupportsResponse.ONLY),
    SERVICE_GDRIVE_BACKUP: (_async_gdrive_backup, GDRIVE_EMPTY_SCHEMA, SupportsResponse.ONLY),
    SERVICE_GDRIVE_LIST: (_async_gdrive_list, GDRIVE_EMPTY_SCHEMA, SupportsResponse.ONLY),
    SERVICE_GDRIVE_RESTORE: (_async_gdrive_restore, GDRIVE_RESTORE_SCHEMA, SupportsResponse.ONLY),
    SERVICE_DELETE_ALL_PARTNERS: (_async_delete_all_partners, WP_EMPTY_SCHEMA, SupportsResponse.ONLY),
    SERVICE_WP_TEST: (_async_wp_test, WP_EMPTY_SCHEMA, SupportsResponse.ONLY),
    SERVICE_WP_NEW_SECRET: (_async_wp_new_secret, WP_EMPTY_SCHEMA, SupportsResponse.ONLY),
    SERVICE_WP_REDEEM: (_async_wp_redeem, WP_REDEEM_SCHEMA, SupportsResponse.ONLY),
    SERVICE_PARTNER_POINTS_ADJUST: (_async_partner_points_adjust, PARTNER_POINTS_ADJUST_SCHEMA, SupportsResponse.ONLY),
    SERVICE_PARTNER_DETAIL: (_async_partner_detail, PARTNER_DETAIL_SCHEMA, SupportsResponse.ONLY),
    SERVICE_SEND_LOYALTY_VOUCHER: (_async_send_loyalty_voucher, SEND_LOYALTY_VOUCHER_SCHEMA, SupportsResponse.ONLY),
    SERVICE_TELEGRAM_STATUS: (_async_telegram_status, vol.Schema({}), SupportsResponse.ONLY),
    SERVICE_SPLIT_FROM_GROUP: (_async_split_from_group, SPLIT_FROM_GROUP_SCHEMA, SupportsResponse.ONLY),
    SERVICE_JOIN_GROUP: (_async_join_group, JOIN_GROUP_SCHEMA, SupportsResponse.ONLY),
    SERVICE_PARTNER_REWARD: (_async_partner_reward, PARTNER_REWARD_SCHEMA, SupportsResponse.ONLY),
    SERVICE_SET_APPOINTMENT_PARTNER: (_async_set_appointment_partner, SET_APPOINTMENT_PARTNER_SCHEMA, SupportsResponse.ONLY),
    SERVICE_SEND_PARTNER_CAMPAIGN: (_async_send_partner_campaign, SEND_PARTNER_CAMPAIGN_SCHEMA, SupportsResponse.ONLY),
    SERVICE_DELETE_PROMO_VOUCHER: (
        _async_delete_promo_voucher,
        DELETE_PROMO_VOUCHER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_PROMO_VOUCHER_TICK: (
        _async_promo_voucher_tick,
        None,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_OPERATOR_MESSAGE: (
        _async_send_operator_message,
        SEND_OPERATOR_MESSAGE_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_GUEST_SUMMARY: (
        _async_send_guest_summary,
        SEND_GUEST_SUMMARY_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_DEPOSIT_REQUEST: (
        _async_send_deposit_request,
        SEND_DEPOSIT_REQUEST_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_REMINDERS: (
        _async_send_reminders,
        SEND_REMINDERS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_REVIEW_REQUESTS: (
        _async_send_review_requests,
        SEND_REVIEW_REQUESTS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_VOUCHER_EXPIRY_REMINDER: (
        _async_voucher_expiry_reminder,
        VOUCHER_EXPIRY_REMINDER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_PROMO: (
        _async_send_promo,
        SEND_PROMO_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_PROMO_AUTOMATIC: (
        _async_promo_automatic,
        PROMO_AUTOMATIC_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CREATE_BOOKINGS: (
        _async_create_bookings,
        CREATE_BOOKINGS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CREATE_REQUEST: (
        _async_create_request,
        CREATE_REQUEST_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_REQUEST: (
        _async_delete_request,
        REQUEST_ID_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CONFIRM_REQUEST: (
        _async_confirm_request,
        REQUEST_ID_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_REQUEST_MESSAGE: (
        _async_send_request_message,
        REQUEST_ID_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_PROPOSE_REQUEST_DATE: (
        _async_propose_request_date, PROPOSE_REQUEST_DATE_SCHEMA, SupportsResponse.ONLY,
    ),
    SERVICE_TEST_WEB_NOTICE: (
        _async_test_web_notice, vol.Schema({}), SupportsResponse.ONLY,
    ),
    SERVICE_GOOGLE_AUTH_URL: (
        _async_google_auth_url, GOOGLE_AUTH_URL_SCHEMA, SupportsResponse.ONLY,
    ),
    SERVICE_GOOGLE_DISCONNECT: (
        _async_google_disconnect, vol.Schema({}), SupportsResponse.ONLY,
    ),
    SERVICE_SEND_EMAIL: (
        _async_send_email, SEND_EMAIL_SCHEMA, SupportsResponse.ONLY,
    ),
    SERVICE_TEST_EMAIL: (
        _async_test_email, TEST_EMAIL_SCHEMA, SupportsResponse.ONLY,
    ),
    SERVICE_WHATSAPP_CHATS: (
        _async_whatsapp_chats, vol.Schema({}), SupportsResponse.ONLY,
    ),
    SERVICE_DELETE_WHATSAPP_CHATS: (
        _async_delete_whatsapp_chats,
        vol.Schema({
            vol.Optional("chat_id"): cv.string,
            vol.Optional("all", default=False): cv.boolean,
        }),
        SupportsResponse.ONLY,
    ),
    SERVICE_MARK_REQUESTS_SEEN: (
        _async_mark_requests_seen,
        MARK_REQUESTS_SEEN_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_REGENERATE_PUBLIC_TOKEN: (
        _async_regenerate_public_token,
        REGENERATE_PUBLIC_TOKEN_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_WEB_SNIPPET: (
        _async_web_snippet,
        WEB_SNIPPET_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_RUN_SCHEDULED_JOBS: (
        _async_run_scheduled_jobs,
        None,
        SupportsResponse.ONLY,
    ),
    SERVICE_WHATSAPP_STATUS: (_async_whatsapp_status, None, SupportsResponse.ONLY),
    SERVICE_WHATSAPP_PAIR: (_async_whatsapp_pair, None, SupportsResponse.OPTIONAL),
    SERVICE_WHATSAPP_PAIR_CODE: (
        _async_whatsapp_pair_code,
        vol.Schema({vol.Required("phone"): cv.string}),
        SupportsResponse.ONLY,
    ),
    SERVICE_WHATSAPP_LOGOUT: (_async_whatsapp_logout, None, SupportsResponse.OPTIONAL),
    SERVICE_GET_DASHBOARD_CONFIG: (
        _async_get_dashboard_config,
        EXPORT_ALL_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_EXPORT_DASHBOARD_YAML: (
        _async_export_dashboard_yaml,
        EXPORT_ALL_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_UPDATE_BOOKING_BATCH: (
        _async_update_booking_batch,
        UPDATE_BOOKING_BATCH_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_EXTERNAL_MESSAGE: (
        _async_send_external_message,
        SEND_EXTERNAL_MESSAGE_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_CLEAR_SLOT_BLOCK: (
        _async_clear_slot_block,
        CLEAR_SLOT_BLOCK_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_EXPIRE_OFFERS: (
        _async_expire_offers,
        EXPIRE_OFFERS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_RELOAD_CARD: (
        _async_reload_card,
        RELOAD_CARD_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SEND_TEST_MESSAGE: (
        _async_send_test_message,
        SEND_TEST_MESSAGE_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_GET_USERS: (
        _async_get_users,
        GET_USERS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_SET_USER_PERMISSIONS: (
        _async_set_user_permissions,
        SET_USER_PERMISSIONS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    SERVICE_WHOAMI: (_async_whoami, None, SupportsResponse.ONLY),
    SERVICE_UPDATE_STATUS: (_async_update_status, None, SupportsResponse.ONLY),
    SERVICE_INSTALL_UPDATE: (_async_install_update, None, SupportsResponse.ONLY),
    SERVICE_RESTART_HOME_ASSISTANT: (
        _async_restart_home_assistant, None, SupportsResponse.OPTIONAL,
    ),
    SERVICE_PIN_LOGIN: (_async_pin_login, PIN_LOGIN_SCHEMA, SupportsResponse.ONLY),
    SERVICE_PIN_LOGOUT: (_async_pin_logout, None, SupportsResponse.OPTIONAL),
    SERVICE_SET_USER_PROFILE: (
        _async_set_user_profile, SET_USER_PROFILE_SCHEMA, SupportsResponse.ONLY,
    ),
    SERVICE_CREATE_USER: (_async_create_user, CREATE_USER_SCHEMA, SupportsResponse.ONLY),
    SERVICE_SET_USER_PASSWORD: (
        _async_set_user_password, SET_USER_PASSWORD_SCHEMA, SupportsResponse.ONLY,
    ),
    SERVICE_SET_USER_ACTIVE: (
        _async_set_user_active, SET_USER_ACTIVE_SCHEMA, SupportsResponse.ONLY,
    ),
}


#: Minimum access level for each service, mirroring the card: what the
#: Agenda, Nuovo, Spa, Clienti, Voucher and WhatsApp tabs do is "operator",
#: the management actions the card reserves to "manage_clients" are
#: "manager", and everything in Configurazione is "admin" (the default for any
#: service not listed). Calls from automations act as the system.
SERVICE_LEVELS: dict[str, str] = {
    # Reading the day.
    SERVICE_EXPORT_DATA: "read",
    SERVICE_GET_CONFIG: "read",
    SERVICE_GET_DAILY_AGENDA: "read",
    SERVICE_GET_DASHBOARD_CONFIG: "read",
    # Layout keys are checked again inside the handler.
    SERVICE_UPDATE_SETTINGS: "read",
    # Signing in: anybody, the tablet before a PIN included.
    SERVICE_WHOAMI: "none",
    SERVICE_PIN_LOGIN: "none",
    SERVICE_PIN_LOGOUT: "none",
    # A masseuse books, moves and checks in her own appointments only
    # (THERAPIST_OWN_SERVICES); the reception does it for everybody.
    SERVICE_CREATE_APPOINTMENT: "therapist",
    SERVICE_CREATE_BOOKINGS: "therapist",
    SERVICE_UPDATE_APPOINTMENT: "therapist",
    SERVICE_UPDATE_BOOKING_BATCH: "therapist",
    SERVICE_RESIZE_APPOINTMENT_GROUP: "therapist",
    SERVICE_CANCEL_APPOINTMENT: "therapist",
    SERVICE_CHECK_IN_APPOINTMENT: "therapist",
    SERVICE_CHECK_OUT_APPOINTMENT: "therapist",
    SERVICE_SEARCH_CLIENTS: "therapist",
    SERVICE_GET_CLIENT_HISTORY: "therapist",
    # Running the day at the desk.
    SERVICE_ADD_PAYMENT: "operator",
    SERVICE_DELETE_PAYMENT: "operator",
    SERVICE_SAVE_CLIENT: "operator",
    SERVICE_RESPOND_TO_OFFER: "operator",
    SERVICE_SET_OFFER_STATE: "operator",
    SERVICE_MANUAL_CONFIRM_OFFER: "operator",
    SERVICE_CREATE_REQUEST: "operator",
    SERVICE_CONFIRM_REQUEST: "operator",
    SERVICE_DELETE_REQUEST: "operator",
    SERVICE_SEND_REQUEST_MESSAGE: "operator",
    SERVICE_PROPOSE_REQUEST_DATE: "operator",
    SERVICE_TEST_WEB_NOTICE: "manager",
    SERVICE_WHATSAPP_CHATS: "operator",
    SERVICE_DELETE_WHATSAPP_CHATS: "manager",
    SERVICE_MARK_REQUESTS_SEEN: "operator",
    SERVICE_SEND_GUEST_SUMMARY: "operator",
    SERVICE_SEND_DEPOSIT_REQUEST: "operator",
    SERVICE_SEND_REVIEW_REQUESTS: "operator",
    SERVICE_SEND_REMINDERS: "operator",
    SERVICE_SEND_EXTERNAL_MESSAGE: "operator",
    SERVICE_CREATE_VOUCHER: "operator",
    # What the card reserves to "manage_clients".
    SERVICE_EXTEND_VOUCHER: "manager",
    SERVICE_DELETE_VOUCHER: "manager",
    SERVICE_REDEEM_PROMO_VOUCHER: "manager",
    SERVICE_DELETE_PROMO_VOUCHER: "manager",
    SERVICE_SEND_EMAIL: "manager",
    SERVICE_GOOGLE_AUTH_URL: "admin",
    SERVICE_GOOGLE_DISCONNECT: "admin",
    SERVICE_TEST_EMAIL: "admin",
    SERVICE_LOYALTY_REWARD: "operator",
    SERVICE_LOYALTY_ADJUST: "manager",
    SERVICE_SAVE_PARTNER: "operator",
    SERVICE_DELETE_PARTNER: "manager",
    SERVICE_IMPORT_PARTNERS: "manager",
    SERVICE_WP_SYNC: "operator",
    SERVICE_GDRIVE_BACKUP: "admin",
    SERVICE_GDRIVE_LIST: "admin",
    SERVICE_GDRIVE_RESTORE: "admin",
    SERVICE_DELETE_ALL_PARTNERS: "manager",
    SERVICE_WP_TEST: "admin",
    SERVICE_WP_NEW_SECRET: "admin",
    SERVICE_WP_REDEEM: "operator",
    SERVICE_PARTNER_POINTS_ADJUST: "manager",
    SERVICE_PARTNER_DETAIL: "operator",
    SERVICE_SEND_LOYALTY_VOUCHER: "manager",
    SERVICE_TELEGRAM_STATUS: "admin",
    SERVICE_SPLIT_FROM_GROUP: "operator",
    SERVICE_JOIN_GROUP: "operator",
    SERVICE_PARTNER_REWARD: "manager",
    SERVICE_SET_APPOINTMENT_PARTNER: "operator",
    SERVICE_SEND_PARTNER_CAMPAIGN: "manager",
    SERVICE_MERGE_CLIENTS: "manager",
}


#: What a masseuse may do only on her own appointments.
THERAPIST_OWN_SERVICES = frozenset(
    {
        SERVICE_CREATE_APPOINTMENT,
        SERVICE_CREATE_BOOKINGS,
        SERVICE_UPDATE_APPOINTMENT,
        SERVICE_UPDATE_BOOKING_BATCH,
        SERVICE_RESIZE_APPOINTMENT_GROUP,
        SERVICE_CANCEL_APPOINTMENT,
        SERVICE_CHECK_IN_APPOINTMENT,
        SERVICE_CHECK_OUT_APPOINTMENT,
    }
)
_THERAPIST_CREATES = frozenset({SERVICE_CREATE_APPOINTMENT, SERVICE_CREATE_BOOKINGS})


def _check_own_appointment(
    service: str, call: ServiceCall, coordinator: SpaBookingCoordinator, acting: Caller
) -> None:
    """A masseuse touches only her own appointments and takes no money."""
    mine = acting.operator_id
    if not mine:
        raise ValidationError(
            "Il tuo utente non è collegato a un'operatrice: chiedi all'amministratore "
            "(Configurazione › Accessi)."
        )
    data = dict(call.data)
    named = access.operator_ids_in(data)
    if named - {mine}:
        raise ValidationError("Puoi prenotare e modificare solo i tuoi appuntamenti")
    if service in _THERAPIST_CREATES and not named:
        raise ValidationError("Scegli te stessa come operatrice")
    if access.has_payment(data):
        raise ValidationError("Gli incassi li registra la reception")
    appointment_id = data.get(ATTR_APPOINTMENT_ID)
    if appointment_id:
        appointment = next(
            (a for a in coordinator.appointments if a.get("id") == appointment_id), None
        )
        if appointment is not None and appointment.get("operator_id") != mine:
            raise ValidationError("Puoi modificare solo i tuoi appuntamenti")


def _guarded(service: str, handler: Any) -> Any:
    """Wrap a handler so it first checks who is calling and her level."""
    needed = SERVICE_LEVELS.get(service, "admin")

    async def _handler(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(call)
        acting = await caller_identity(
            call, coordinator, refresh=needed not in ("none", "read")
        )
        if _LEVEL_RANK.get(acting.level, 0) < _LEVEL_RANK.get(needed, len(_LEVEL_RANK)):
            if acting.device is not None and acting.user_id is None:
                raise ValidationError("Tablet della reception: inserisci il tuo PIN")
            raise ValidationError(
                f"Accesso negato: questa operazione richiede il livello '{needed}' "
                f"(il tuo è '{acting.level}')."
            )
        if acting.level == "therapist" and service in THERAPIST_OWN_SERVICES:
            _check_own_appointment(service, call, coordinator, acting)
        force = bool((call.data or {}).get("force_rules"))
        if force and _LEVEL_RANK.get(acting.level, 0) < _LEVEL_RANK["operator"]:
            raise ValidationError("Solo la reception può prenotare fuori dalle regole della categoria")
        token = _ACTING.set(acting)
        force_token = FORCE_RULES.set(force)
        actor_token = ACTOR.set(
            None if acting.system else (acting.user_id or "", acting.name or "")
        )
        try:
            return await handler(call)
        finally:
            ACTOR.reset(actor_token)
            FORCE_RULES.reset(force_token)
            _ACTING.reset(token)

    _handler.__name__ = getattr(handler, "__name__", service)
    _handler.__doc__ = handler.__doc__
    return _handler


def async_register_services(hass: HomeAssistant) -> None:
    """Register every service once, regardless of the entry count."""
    # Incremental registration: a reload keeps old service names loaded, so
    # only register the services that are still missing.
    for service, (handler, schema, response) in _HANDLERS.items():
        if hass.services.has_service(DOMAIN, service):
            continue
        hass.services.async_register(
            DOMAIN,
            service,
            _guarded(service, handler),
            schema=schema,
            supports_response=response,
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove every service of this domain."""
    for service in ALL_SERVICES:
        hass.services.async_remove(DOMAIN, service)