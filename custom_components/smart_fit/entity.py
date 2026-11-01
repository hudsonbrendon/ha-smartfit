"""Entidade base do Smart Fit."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DOCUMENT, DOMAIN
from .coordinator import SmartFitDataUpdateCoordinator

# Três "dispositivos" por conta, para separar conta/financeiro, treino e unidade.
DEVICE_ACCOUNT = "account"
DEVICE_TRAINING = "training"
DEVICE_UNIT = "unit"
_DEVICE_NAMES = {
    DEVICE_ACCOUNT: "Smart Fit Conta",
    DEVICE_TRAINING: "Smart Fit Treino",
    DEVICE_UNIT: "Smart Fit Unidade",
}


class SmartFitEntity(CoordinatorEntity[SmartFitDataUpdateCoordinator]):
    """Base com device info compartilhado."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SmartFitDataUpdateCoordinator, device: str = DEVICE_ACCOUNT
    ) -> None:
        """Inicializa a entidade e a prende ao dispositivo do grupo."""
        super().__init__(coordinator)
        document = coordinator.config_entry.data.get(CONF_DOCUMENT, "")
        # A conta mantém o identificador antigo (DOMAIN, document) para não
        # quebrar entidades já criadas; os outros ficam "atrás" dela.
        ident = document if device == DEVICE_ACCOUNT else f"{document}_{device}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ident)},
            manufacturer="Smart Fit",
            model=_DEVICE_NAMES[device].removeprefix("Smart Fit "),
            name=_DEVICE_NAMES[device],
            via_device=None if device == DEVICE_ACCOUNT else (DOMAIN, document),
        )
