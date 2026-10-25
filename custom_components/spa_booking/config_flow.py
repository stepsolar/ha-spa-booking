"""Config flow for the SPA Booking integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN


def split_names(value: str) -> list[str]:
    """Return comma or semicolon separated names."""
    parts: list[str] = []
    for chunk in value.replace(";", ",").split(","):
        name = chunk.strip()
        if name:
            parts.append(name)
    return parts


class SpaBookingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a single config entry and seed the first dataset."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for a name for this installation."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title=user_input["name"],
                data={"operator_names": split_names(user_input.get("operator_names", ""))},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Spa Booking"): str,
                    vol.Optional("operator_names", default=""): str,
                }
            ),
        )