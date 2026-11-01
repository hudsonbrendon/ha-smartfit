"""Coordinator de atualização do Smart Fit."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartFitApiAuthenticationError, SmartFitApiError
from .const import DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import SmartFitApiClient
    from .data import SmartFitConfigEntry


class SmartFitDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Puxa perfil, treinos, ficha, aulas, lotação e financeiro a cada ciclo."""

    config_entry: SmartFitConfigEntry

    def __init__(self, hass: HomeAssistant, client: SmartFitApiClient) -> None:
        """Inicializa o coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Busca os dados. O session_token não renova sozinho (precisa novo OTP):
        401 vira ConfigEntryAuthFailed e dispara o reauth."""
        try:
            return await self._fetch_all()
        except SmartFitApiAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SmartFitApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch_all(self) -> dict[str, Any]:
        # O perfil é obrigatório (plano + unidade); o resto é complementar.
        profile = await self.client.async_get_profile()
        acronym = (profile.get("profile") or {}).get("location_acronym")

        tasks: dict[str, Any] = {
            "training_sessions": self.client.async_get_training_sessions(),
            "training_stats": self.client.async_get_training_stats(),
            "monthly_activity": self.client.async_get_monthly_activity(),
            "debts": self.client.async_get_debts(),
            "guests": self.client.async_get_guests(),
            "training": self.client.async_get_training(),
            "classes": self.client.async_get_classes(),
            # Espaço do Cliente (web): mensalidade, cartão, histórico de pagamentos
            "client_space": self.client.async_get_client_space(),
        }
        if acronym:
            tasks["occupancy"] = self.client.async_get_occupancy(acronym)

        data: dict[str, Any] = {"profile": profile}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks, results, strict=True):
            if isinstance(result, SmartFitApiAuthenticationError):
                raise result
            if isinstance(result, Exception):
                LOGGER.debug("%s indisponível: %s", key, result)
                data[key] = None
            else:
                data[key] = result
        return data
