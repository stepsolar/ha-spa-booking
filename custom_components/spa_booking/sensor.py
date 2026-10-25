"""Sensor platform for the SPA Booking integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import STATUS_CONFIRMED
from .coordinator import SpaBookingCoordinator

KIND_TODAY = "appointments_today"
KIND_TOMORROW = "appointments_tomorrow"
KIND_CLIENTS = "clients"
KIND_NEXT = "next_appointment"
KIND_EXTERNAL = "external_whatsapp"

_KINDS: dict[str, tuple[str, str]] = {
    KIND_TODAY: ("Appuntamenti oggi", "mdi:calendar-today"),
    KIND_TOMORROW: ("Appuntamenti domani", "mdi:calendar-arrow-right"),
    KIND_CLIENTS: ("Clienti registrati", "mdi:account-group"),
    KIND_NEXT: ("Prossimo appuntamento", "mdi:timer-clock-outline"),
    KIND_EXTERNAL: ("Messaggi WhatsApp esterni", "mdi:whatsapp"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sensor per counter."""
    coordinator: SpaBookingCoordinator = entry.runtime_data
    async_add_entities(
        SpaBookingSensor(coordinator, kind) for kind in _KINDS
    )


class SpaBookingSensor(CoordinatorEntity[SpaBookingCoordinator], SensorEntity):
    """A counter or lookup sensor backed by the coordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SpaBookingCoordinator, kind: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._kind = kind
        name, icon = _KINDS[kind]
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{kind}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int | None:
        """Return the sensor state."""
        if self._kind == KIND_CLIENTS:
            return len(self.coordinator.clients)
        if self._kind == KIND_NEXT:
            upcoming = self._upcoming()
            if not upcoming:
                return None
            start = dt_util.parse_datetime(upcoming["start"])
            if start is None:
                return None
            delta = dt_util.as_local(start) - dt_util.now()
            return max(int(delta.total_seconds() // 60), 0)
        if self._kind == KIND_EXTERNAL:
            return len(self.coordinator.external_messages)
        return len(self._agenda(self._kind)["items"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the agenda or client list behind the counter."""
        if self._kind == KIND_CLIENTS:
            clients = self.coordinator.clients
            return {
                "clients": [
                    {
                        "id": client["id"],
                        "full_name": self.coordinator.full_name(client),
                        "phone": client["phone"],
                        "email": client["email"],
                    }
                    for client in clients
                ],
                "count": len(clients),
            }

        if self._kind == KIND_NEXT:
            upcoming = self._upcoming()
            return {"appointment": upcoming} if upcoming else {}

        if self._kind == KIND_EXTERNAL:
            messages = self.coordinator.external_messages
            return {
                "messages": messages,
                "count": len(messages),
                "last": messages[0] if messages else None,
            }

        agenda = self._agenda(self._kind)
        return {
            "date": agenda["date"],
            "total": agenda["total"],
            "appointments": agenda["items"],
            "by_operator": agenda["by_operator"],
            "by_category": agenda["by_category"],
        }

    @property
    def available(self) -> bool:
        """Return whether the coordinator has data."""
        return self.coordinator.data is not None

    def _agenda(self, kind: str) -> dict[str, Any]:
        """Return today's or tomorrow's agenda."""
        day = dt_util.now().date()
        if kind == KIND_TOMORROW:
            day += timedelta(days=1)
        return self.coordinator.agenda(day)

    def _upcoming(self) -> dict[str, Any] | None:
        """Return the next confirmed appointment that has not ended."""
        now = dt_util.utcnow()
        upcoming = [
            self.coordinator.appointment_payload(appointment)
            for appointment in self.coordinator.appointments
            if appointment["status"] == STATUS_CONFIRMED
            and (dt_util.parse_datetime(appointment["end"]) or now) > now
        ]
        if not upcoming:
            return None
        return min(upcoming, key=lambda a: a["start_local"])