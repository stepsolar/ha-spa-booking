"""Calendar platform for the SPA Booking integration.

One calendar entity per operator, so automations can react to a single
therapist's schedule ("switch on the massage room lights when Maria's first
appointment starts"). All entities also show up in the standard calendar views.
"""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STATUS_CONFIRMED
from .coordinator import SpaBookingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the operator calendars and keep them in sync."""
    coordinator: SpaBookingCoordinator = entry.runtime_data
    known: dict[str, SpaOperatorCalendar] = {}

    @callback
    def _schedule_sync() -> None:
        """Run the sync from the event loop on every coordinator update."""
        entry.async_create_task(
            hass,
            _async_sync(),
            name=f"{DOMAIN} sync calendars",
        )

    async def _async_sync() -> None:
        """Add calendars for new operators and drop removed ones."""
        wanted = {operator["id"]: operator["name"] for operator in coordinator.operators}

        for operator_id in list(known):
            if operator_id not in wanted:
                entity = known.pop(operator_id)
                try:
                    await entity.async_remove(force_remove=True)
                except HomeAssistantError:
                    _LOGGER.debug("Calendar %s gia' rimossa", operator_id)

        new_entities: list[SpaOperatorCalendar] = []
        for operator_id, name in wanted.items():
            if operator_id not in known:
                entity = SpaOperatorCalendar(coordinator, operator_id, name)
                known[operator_id] = entity
                new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

        # Creation, update and cancellation do not change a calendar state, so
        # subscribers have to be pushed explicitly.
        for entity in known.values():
            entity.async_update_event_listeners()

    await _async_sync()
    entry.async_on_unload(coordinator.async_add_listener(_schedule_sync))


class SpaOperatorCalendar(CoordinatorEntity[SpaBookingCoordinator], CalendarEntity):
    """The confirmed appointments of a single operator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, coordinator: SpaBookingCoordinator, operator_id: str, operator_name: str
    ) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self.operator_id = operator_id
        self._operator_name = operator_name
        self._attr_name = f"Appuntamenti {operator_name}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_calendar_{operator_id}"
        self._attr_device_info = coordinator.device_info
        self._attr_initial_color = "#0f9d58"

    @property
    def available(self) -> bool:
        """Return whether the coordinator has data."""
        return self.coordinator.data is not None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the running appointment, or the next one."""
        now = dt_util.utcnow()
        upcoming = [
            self._to_event(appointment)
            for appointment in self._operator_appointments()
            if (dt_util.parse_datetime(appointment["end"]) or now) > now
        ]
        if not upcoming:
            return None
        return upcoming[0]

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the appointments of this operator inside the given range."""
        start_utc = dt_util.as_utc(start_date)
        end_utc = dt_util.as_utc(end_date)

        events: list[CalendarEvent] = []
        for appointment in self._operator_appointments():
            start = dt_util.parse_datetime(appointment["start"])
            end = dt_util.parse_datetime(appointment["end"])
            if start is None or end is None:
                continue
            if start < end_utc and end > start_utc:
                events.append(self._to_event(appointment))
        events.sort(key=lambda event: event.start)
        return events

    def _operator_appointments(self) -> list[dict]:
        """Return the confirmed appointments of this operator, sorted by start."""
        appointments = [
            appointment
            for appointment in self.coordinator.appointments
            if appointment["operator_id"] == self.operator_id
            and appointment["status"] == STATUS_CONFIRMED
        ]
        return sorted(appointments, key=lambda a: a["start"])

    def _to_event(self, appointment: dict) -> CalendarEvent:
        """Return the calendar event for an appointment."""
        payload = self.coordinator.appointment_payload(appointment)
        client = payload["client"]
        treatment = payload.get("treatment")
        start = dt_util.parse_datetime(appointment["start"])
        end = dt_util.parse_datetime(appointment["end"])

        description_lines = [
            f"Cliente: {client['full_name']}",
            f"Trattamento: {treatment['name'] if treatment else 'n/d'}"
            f" ({payload.get('duration_min')} min)",
            f"Categoria: {payload['category']['name'] if payload.get('category') else 'n/d'}",
        ]
        if client.get("phone"):
            description_lines.append(f"Telefono: {client['phone']}")
        if client.get("notes"):
            description_lines.append(f"Note cliente: {client['notes']}")
        if appointment.get("notes"):
            description_lines.append(f"Note: {appointment['notes']}")

        return CalendarEvent(
            uid=appointment["id"],
            summary=f"{client['full_name']} - {treatment['name'] if treatment else 'Appuntamento'}",
            start=dt_util.as_local(start),
            end=dt_util.as_local(end),
            location="Spa",
            description="\n".join(description_lines),
        )