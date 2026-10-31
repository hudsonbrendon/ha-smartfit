"""Config flow do Smart Fit (CPF -> OTP -> escolha da unidade)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import (
    SmartFitApiAuthenticationError,
    SmartFitApiClient,
    SmartFitApiCommunicationError,
    SmartFitApiError,
    SmartFitUserNotFoundError,
)
from .const import (
    CONF_CORPORATIVE,
    CONF_DOCUMENT,
    CONF_SESSION_TOKEN,
    DOMAIN,
)


class SmartFitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Fluxo de configuração via UI."""

    VERSION = 1

    def __init__(self) -> None:
        """Estado entre passos."""
        self._client: SmartFitApiClient | None = None
        self._document: str | None = None
        self._corporative: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Passo 1: CPF. Dispara o OTP."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"error": ""}
        if user_input is not None:
            document = "".join(c for c in user_input[CONF_DOCUMENT] if c.isdigit())
            corporative = user_input.get(CONF_CORPORATIVE, False)
            delivery_method = user_input.get("delivery_method", "sms")
            client = SmartFitApiClient(
                session=async_get_clientsession(self.hass),
                document=document,
                corporative=corporative,
            )
            try:
                await client.async_request_otp(delivery_method)
            except SmartFitUserNotFoundError:
                errors["base"] = "user_not_found"
            except SmartFitApiCommunicationError:
                errors["base"] = "cannot_connect"
            except SmartFitApiError as err:
                errors["base"] = "unknown"
                placeholders["error"] = str(err)
            else:
                self._client = client
                self._document = document
                self._corporative = corporative
                await self.async_set_unique_id(document)
                self._abort_if_unique_id_configured()
                return await self.async_step_otp()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DOCUMENT): str,
                    vol.Required("delivery_method", default="sms"): vol.In(
                        {"sms": "SMS", "email": "E-mail"}
                    ),
                    vol.Optional(CONF_CORPORATIVE, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Passo 2: código recebido por SMS/e-mail."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"error": ""}
        assert self._client is not None
        if user_input is not None:
            try:
                await self._client.async_validate_otp(user_input["code"])
            except SmartFitApiAuthenticationError as err:
                errors["base"] = "invalid_code"
                placeholders["error"] = str(err)
            except SmartFitApiError as err:
                errors["base"] = "unknown"
                placeholders["error"] = str(err)
            else:
                # A unidade (location_acronym) vem do perfil; sem passo extra.
                return self.async_create_entry(
                    title=f"Smart Fit {self._document}",
                    data={
                        CONF_DOCUMENT: self._document,
                        CONF_CORPORATIVE: self._corporative,
                        CONF_SESSION_TOKEN: self._client.session_token,
                    },
                )

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Reauth: sessão expirou, refaz CPF->OTP."""
        self._document = entry_data.get(CONF_DOCUMENT)
        self._corporative = entry_data.get(CONF_CORPORATIVE, False)
        return await self.async_step_user()
