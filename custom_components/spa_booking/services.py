"""Services exposed by the SPA Booking integration.

Handlers read the coordinator from `hass.data[DOMAIN]`, so they always act on
the loaded dataset and raise `HomeAssistantError` subclasses (SpaBookingError)
that Home Assistant surfaces as a readable error in the UI.
"""

from __future__ import annotations

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
    ATTR_ANSWER,
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
    PERMISSION_LEVELS,
)
from .coordinator import INTEGRATION_VERSION, SpaBookingCoordinator, as_date
from .exceptions import ValidationError

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
SERVICE_SETUP_WAHA_WEBHOOK = "waha_webhook"
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
SERVICE_CREATE_REQUEST = "create_request"
SERVICE_DELETE_REQUEST = "delete_request"
SERVICE_CONFIRM_REQUEST = "confirm_request"
SERVICE_SEND_REQUEST_MESSAGE = "send_request_message"
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
SERVICE_IMPORT_ALL = "import_all"

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
    SERVICE_SETUP_WAHA_WEBHOOK,
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
    SERVICE_CREATE_REQUEST,
    SERVICE_DELETE_REQUEST,
    SERVICE_CONFIRM_REQUEST,
    SERVICE_SEND_REQUEST_MESSAGE,
    SERVICE_ADD_PAYMENT,
    SERVICE_DELETE_PAYMENT,
    SERVICE_MARK_REQUESTS_SEEN,
    SERVICE_REGENERATE_PUBLIC_TOKEN,
    SERVICE_WEB_SNIPPET,
    SERVICE_SEND_EXTERNAL_MESSAGE,
    SERVICE_EXPORT_ALL,
    SERVICE_IMPORT_ALL,
    SERVICE_UPDATE_BOOKING_BATCH,
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
        #: The desk saw the overlap warning and books anyway: skips only the
        #: same-person client refusal, never an operator double-booking.
        vol.Optional("batch_id"): vol.Any(cv.string, None),
        vol.Optional("force_client_overlap", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

CANCEL_APPOINTMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_APPOINTMENT_ID): cv.string,
        vol.Optional(ATTR_REASON): cv.string,
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
    }
)
CHECK_OUT_APPOINTMENT_SCHEMA = vol.Schema(
    {vol.Required(ATTR_APPOINTMENT_ID): cv.string}
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
        vol.Optional("review_request_test_phone"): vol.Any(cv.string, None),
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
        vol.Optional("promo_voucher_message"): vol.Any(cv.string, None),
        vol.Optional("promo_voucher_days"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)), None),
        vol.Optional("promo_voucher_discount"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=1, max=100)), None),
        vol.Optional("promo_voucher_min_spend"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=100000)), None),
        vol.Optional("promo_voucher_max_spend"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=100000)), None),
        vol.Optional("promo_voucher_after_hours"): vol.Any(vol.All(vol.Coerce(int), vol.Range(min=0, max=8760)), None),
        vol.Optional("promo_voucher_auto"): vol.Any(cv.boolean, None),
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
        # WAHA gateway: with an URL set, WhatsApp goes straight to the add-on
        # instead of through the rest_command fallback.
        vol.Optional("waha_url"): vol.Any(cv.string, None),
        vol.Optional("waha_api_key"): vol.Any(cv.string, None),
        vol.Optional("waha_session"): vol.Any(cv.string, None),
        # How the WAHA add-on reaches Home Assistant, used to build the webhook
        # URL it posts the operators' answers to. Empty = Supervisor network.
        vol.Optional("waha_ha_url"): vol.Any(cv.string, None),
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
    },
    extra=vol.PREVENT_EXTRA,
)

CHECK_WAHA_SCHEMA = vol.Schema({})

SETUP_WAHA_WEBHOOK_SCHEMA = vol.Schema({})

EXPORT_DATA_SCHEMA = vol.Schema({})
EXPORT_ALL_SCHEMA = vol.Schema({})

IMPORT_DATA_SCHEMA = vol.Schema({vol.Required(ATTR_PAYLOAD): dict})
IMPORT_ALL_SCHEMA = vol.Schema({vol.Required(ATTR_PAYLOAD): dict})
UPDATE_BOOKING_BATCH_SCHEMA = vol.Schema({vol.Required("appointment_id"): cv.string, vol.Required(ATTR_ROWS): vol.All(cv.ensure_list, [dict])})

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
    },
    extra=vol.PREVENT_EXTRA,
)

CREATE_BOOKINGS_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ROWS): vol.All(cv.ensure_list, [BOOKING_ROW_SCHEMA])},
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
WEB_SNIPPET_SCHEMA = vol.Schema({})

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
    },
    extra=vol.PREVENT_EXTRA,
)

SEND_DEPOSIT_REQUEST_SCHEMA = vol.Schema(
    {vol.Required(ATTR_APPOINTMENT_ID): cv.string},
    extra=vol.PREVENT_EXTRA,
)

SEND_PROMO_SCHEMA = vol.Schema(
    {
        vol.Optional("client_ids"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("message"): vol.Any(cv.string, None),
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


def _coordinator(call: ServiceCall) -> SpaBookingCoordinator:
    """Return the loaded coordinator."""
    return call.hass.data[DOMAIN]


async def _require_admin(call: ServiceCall, coordinator: SpaBookingCoordinator) -> None:
    """Reject the call unless the caller is a Home Assistant or SPA admin.

    System/internal callers (no user context, e.g. automations) pass through
    to preserve backward compat. End users must have either HA admin/owner
    rights or the SPA permission level "admin".
    """
    user_id = call.context.user_id if getattr(call, "context", None) else None
    if not user_id:
        return
    if call.hass:
        try:
            user = await call.hass.auth.async_get_user(user_id)
            if user is not None and (user.is_admin or user.is_owner):
                return
        except Exception as exc:  # noqa: BLE001 - never raise from auth lookup
            import logging

            logging.getLogger(__name__).debug("Auth lookup fallito: %s", exc)
    if coordinator.user_level(user_id) == "admin":
        return
    raise ValidationError(
        "Accesso negato: questa operazione richiede i permessi di amministratore."
    )


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
    )
    return {"appointment": appointment}


async def _async_create_bookings(call: ServiceCall) -> ServiceResponse:
    """Create every appointment of a multi-row booking."""
    user_id = call.context.user_id if call.context else None
    return await _coordinator(call).async_create_bookings(call.data[ATTR_ROWS], user_id)


async def _async_create_request(call: ServiceCall) -> ServiceResponse:
    """Take a guest's appointment request and acknowledge it."""
    data = call.data
    user_id = call.context.user_id if call.context else None
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
    """Sell a gift voucher."""
    data = call.data
    user_id = call.context.user_id if call.context else None
    voucher = await _coordinator(call).async_create_voucher(
        data["buyer_name"],
        data["buyer_phone"],
        data["recipient_name"],
        data["recipient_phone"],
        data["people"],
        user_id,
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
    user_id = call.context.user_id if call.context else None
    is_admin = False
    is_owner = False
    if user_id and call.hass:
        user = await call.hass.auth.async_get_user(user_id)
        if user:
            is_admin = user.is_admin
            is_owner = user.is_owner
    return await _coordinator(call).async_delete_voucher(call.data["voucher_id"], user_id, is_admin, is_owner)


async def _async_redeem_promo_voucher(call: ServiceCall) -> ServiceResponse:
    """Mark a loyalty voucher ("Voucher fedelta") as used."""
    voucher = await _coordinator(call).async_redeem_promo_voucher(
        call.data["voucher_id"]
    )
    return {"voucher": voucher}


async def _async_delete_promo_voucher(call: ServiceCall) -> ServiceResponse:
    """Remove a loyalty voucher ("Voucher fedelta") from the list."""
    return await _coordinator(call).async_delete_promo_voucher(
        call.data["voucher_id"]
    )


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
    )


async def _async_send_deposit_request(call: ServiceCall) -> ServiceResponse:
    """Ask one guest, by WhatsApp, to pay her deposit."""
    return await _coordinator(call).async_send_deposit_request(
        call.data[ATTR_APPOINTMENT_ID]
    )


async def _async_send_promo(call: ServiceCall) -> ServiceResponse:
    """Broadcast the promotional message to the chosen clients."""
    data = call.data
    return await _coordinator(call).async_send_promo(
        data.get("client_ids"),
        message=data.get("message"),
    )


async def _async_promo_automatic(call: ServiceCall) -> ServiceResponse:
    """Daily automatic broadcast of the promotional message."""
    return await _coordinator(call).async_scheduled_promo()


async def _async_send_reminders(call: ServiceCall) -> ServiceResponse:
    """Send the guest reminders that are due, or one chosen appointment."""
    return await _coordinator(call).async_send_reminders(
        call.data.get(ATTR_APPOINTMENT_ID)
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
    appointment = await _coordinator(call).async_cancel_appointment(
        call.data[ATTR_APPOINTMENT_ID], call.data.get(ATTR_REASON, "")
    )
    return {"appointment": appointment}


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
    appointment = await _coordinator(call).async_check_in_appointment(
        call.data[ATTR_APPOINTMENT_ID], call.data.get(ATTR_CHECKED_IN, True)
    )
    return {"appointment": appointment}


async def _async_check_out_appointment(call: ServiceCall) -> ServiceResponse:
    """Record the client leaving the spa."""
    appointment = await _coordinator(call).async_check_out_appointment(
        call.data[ATTR_APPOINTMENT_ID]
    )
    return {"appointment": appointment}


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
    return await _coordinator(call).async_web_snippet()


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
    return {"config": _coordinator(call).config_payload()}


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
    """Return the whole dataset."""
    return {
        "data": _coordinator(call).export_data(),
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
        data["appointment_id"], data[ATTR_ROWS], call.context.user_id if call.context else None
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
    """Update the notification settings."""
    settings = await _coordinator(call).async_update_settings(**call.data)
    return {"settings": settings}


async def _async_check_waha(call: ServiceCall) -> ServiceResponse:
    """Ask the configured WAHA gateway who it is."""
    return await _coordinator(call).async_check_waha()


async def _async_setup_waha_webhook(call: ServiceCall) -> ServiceResponse:
    """Subscribe the WAHA session to this integration's webhook."""
    return await _coordinator(call).async_setup_waha_webhook()


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
    SERVICE_SETUP_WAHA_WEBHOOK: (
        _async_setup_waha_webhook,
        SETUP_WAHA_WEBHOOK_SCHEMA,
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
}


def async_register_services(hass: HomeAssistant) -> None:
    """Register every service once, regardless of the entry count."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_CONFIG):
        return
    for service, (handler, schema, response) in _HANDLERS.items():
        hass.services.async_register(
            DOMAIN, service, handler, schema=schema, supports_response=response
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove every service of this domain."""
    for service in ALL_SERVICES:
        hass.services.async_remove(DOMAIN, service)