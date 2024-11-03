"""Config flow for Sector Alarm integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback

from .client import SectorAlarmAPI, AuthenticationError
from .const import CONF_PANEL_CODE, CONF_PANEL_ID, DOMAIN
from .const import LOGGER

_LOGGER = logging.getLogger(__name__)


class SectorAlarmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sector Alarm."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            panel_id = user_input[CONF_PANEL_ID]
            panel_code = user_input[CONF_PANEL_CODE]

            api = SectorAlarmAPI(email, password, panel_id, panel_code)
            try:
                await api.login()
                await api.retrieve_all_data()
                await api.close()
                return self.async_create_entry(
                    title="Sector Alarm",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_PANEL_ID: panel_id,
                        CONF_PANEL_CODE: panel_code,
                    },
                )
            except AuthenticationError:
                errors["base"] = "authentication_failed"
            except Exception as e:
                errors["base"] = "unknown_error"
                _LOGGER.exception("Unexpected exception during authentication: %s", e)
            finally:
                await api.close()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_PANEL_ID): str,
                vol.Required(CONF_PANEL_CODE): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
