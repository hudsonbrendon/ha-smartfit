"""Entidade base do Smart Fit."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DOCUMENT, DOMAIN
from .coordinator import SmartFitDataUpdateCoordinator


class SmartFitEntity(CoordinatorEntity[SmartFitDataUpdateCoordinator]):
    """Base com device info compartilhado."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartFitDataUpdateCoordinator) -> None:
        """Inicializa a entidade."""
        super().__init__(coordinator)
        document = coordinator.config_entry.data.get(CONF_DOCUMENT, "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, document)},
            manufacturer="Smart Fit",
            model="Smart Fit",
            name=f"Smart Fit {document}",
        )
