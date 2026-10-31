"""Tipos compartilhados da integração Smart Fit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import SmartFitApiClient
    from .coordinator import SmartFitDataUpdateCoordinator


type SmartFitConfigEntry = ConfigEntry[SmartFitData]


@dataclass
class SmartFitData:
    """Dados guardados no ConfigEntry."""

    client: SmartFitApiClient
    coordinator: SmartFitDataUpdateCoordinator
    integration: Integration
