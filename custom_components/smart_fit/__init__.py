"""Integração Smart Fit para Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_loaded_integration

from .api import SmartFitApiClient
from .const import CONF_CORPORATIVE, CONF_DOCUMENT, CONF_SESSION_TOKEN, DOMAIN
from .coordinator import SmartFitDataUpdateCoordinator
from .data import SmartFitConfigEntry, SmartFitData

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Setup YAML-less."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SmartFitConfigEntry) -> bool:
    """Configura a integração a partir de um config entry."""
    client = SmartFitApiClient(
        session=async_get_clientsession(hass),
        document=entry.data[CONF_DOCUMENT],
        session_token=entry.data[CONF_SESSION_TOKEN],
        corporative=entry.data.get(CONF_CORPORATIVE, False),
    )

    coordinator = SmartFitDataUpdateCoordinator(hass, client)
    entry.runtime_data = SmartFitData(
        client=client,
        coordinator=coordinator,
        integration=async_get_loaded_integration(hass, entry.domain),
    )
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartFitConfigEntry) -> bool:
    """Descarrega o config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: SmartFitConfigEntry) -> None:
    """Recarrega o config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
