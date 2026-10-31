"""Cliente da API do Smart Fit (engenharia reversa do app com.eokoe.smartfitcoach).

Reimplementa, em Python puro, o fluxo de login e as chamadas de leitura que o
app Flutter faz contra o backend REST `https://api-mobile.smartfit.com.br/api/`.

Autenticação (dois headers, descobertos em `HttpApiProvider._buildHeader` e
`LocalAppConfigApplication`):

- `Authorization: Token token=<APP_TOKEN>` — token **estático do app**
  (`serverAuthorization`). Sozinho já autoriza endpoints públicos
  (countries/states).
- `X-Api-Key: <session_token>` — token **do usuário**, obtido no login. É o
  campo `id` da resposta do validate (`ApiValidateTokenRepository._saveSession`
  grava em `SessionEntity.sessionToken`). Vazio = acesso só público.

Login por CPF + OTP de 4 dígitos (módulo `login`):

1. `POST v1/tokens {document, locale, corporative}` → prepara/envia o código e
   devolve `pin_size` e os métodos de entrega (SMS/e-mail).
2. (opcional) `POST v1/tokens/delivery_methods {document, locale, corporative,
   method}` → reenvia por outro canal.
3. `GET v1/tokens/{otp}?document=<cpf>&locale=pt-BR&corporative=false` →
   `{id: <session_token>, registration_id, user_id, email, current_plan, ...}`.

Nenhuma lib nativa é necessária; o backend é Rails puro e não há pinning
aplicável a um cliente próprio.
"""

from __future__ import annotations

from typing import Any

import aiohttp

BASE_URL = "https://api-mobile.smartfit.com.br/api"

# Token estático do app (config.serverAuthorization), v4.9.26.
APP_TOKEN = "Hi6SmkNjLUpbGbdB525CwUQs"

DEFAULT_LOCALE = "pt-BR"
_TIMEOUT = 20


class SmartFitApiError(Exception):
    """Erro geral da API."""


class SmartFitApiCommunicationError(SmartFitApiError):
    """Falha de comunicação/timeout."""


class SmartFitApiAuthenticationError(SmartFitApiError):
    """Sessão inválida/expirada ou OTP incorreto."""


class SmartFitUserNotFoundError(SmartFitApiError):
    """CPF não encontrado na base da Smart Fit."""


class SmartFitApiClient:
    """Cliente REST da Smart Fit.

    Pode ser criado só com `document` (para o fluxo de login/OTP) ou já com um
    `session_token` persistido (para as leituras).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        document: str | None = None,
        session_token: str | None = None,
        corporative: bool = False,
    ) -> None:
        """Inicializa o cliente."""
        self._session = session
        self.document = _only_digits(document) if document else None
        self.session_token = session_token
        self.corporative = corporative

    # -- Headers ---------------------------------------------------------

    def _headers(self, authed: bool = True) -> dict[str, str]:
        headers = {
            "Authorization": f"Token token={APP_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": DEFAULT_LOCALE,
            "Locale": DEFAULT_LOCALE,
        }
        if authed and self.session_token:
            # X-Api-Key carrega o token do usuário (config.apiToken).
            headers["X-Api-Key"] = self.session_token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        authed: bool = True,
    ) -> Any:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(authed=authed),
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT),
            ) as resp:
                body = await resp.text()
                if resp.status == 401:
                    raise SmartFitApiAuthenticationError(
                        "Sessão expirada ou inválida (401)."
                    )
                if resp.status == 404 and "user_not_found" in body:
                    raise SmartFitUserNotFoundError("CPF não encontrado.")
                if resp.status >= 400:
                    raise SmartFitApiError(f"HTTP {resp.status}: {body[:200]}")
                if not body:
                    return None
                try:
                    return await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    return body
        except aiohttp.ClientError as err:
            raise SmartFitApiCommunicationError(str(err)) from err
        except TimeoutError as err:
            raise SmartFitApiCommunicationError("Timeout na API da Smart Fit.") from err

    # -- Login (CPF + OTP) ----------------------------------------------

    async def async_request_otp(self, delivery_method: str = "sms") -> dict[str, Any]:
        """Passo 1: dispara o código por `sms` ou `email`.

        Retorna `pin_size` e `recipient` (destino mascarado). `delivery_method`
        é obrigatório no body — sem ele a API responde 422.
        """
        if not self.document:
            raise SmartFitApiError("CPF não informado.")
        return await self._request(
            "POST",
            "v1/tokens",
            json={
                "document": self.document,
                "locale": DEFAULT_LOCALE,
                "delivery_method": delivery_method,
                "corporative": self.corporative,
            },
            authed=False,
        )

    async def async_resend_otp(self, method: str) -> dict[str, Any]:
        """Passo 2 (opcional): reenvia o código pelo canal escolhido."""
        return await self._request(
            "POST",
            "v1/tokens/delivery_methods",
            json={
                "document": self.document,
                "locale": DEFAULT_LOCALE,
                "corporative": self.corporative,
                "method": method,
            },
            authed=False,
        )

    async def async_validate_otp(self, code: str) -> dict[str, Any]:
        """Passo 3: valida o OTP e guarda o session_token (campo `id`)."""
        data = await self._request(
            "GET",
            f"v1/tokens/{code.strip()}",
            params={
                "document": self.document,
                "locale": DEFAULT_LOCALE,
                "corporative": "true" if self.corporative else "false",
            },
            authed=False,
        )
        if not isinstance(data, dict) or not data.get("id"):
            raise SmartFitApiAuthenticationError("Código inválido ou expirado.")
        self.session_token = str(data["id"])
        return data

    # -- Leituras --------------------------------------------------------

    async def async_get_profile(self) -> dict[str, Any]:
        """Perfil completo: {profile:{name, plan, location_acronym, ...}, access:{...}}."""
        return await self._request("GET", "v1/users/user")

    async def async_get_occupancy(self, acronym: str) -> Any:
        """Lotação por hora de uma unidade.

        `{location:{acronym,name,address}, occupancy_rates:[{hour:"4"..."23", total:int}]}`.
        O path aceita o **acronym** da unidade (não um id numérico).
        """
        return await self._request("GET", f"v1/locations/{acronym}/occupancy_rates")

    async def async_get_training_sessions(self) -> Any:
        """Histórico de treinos / check-ins: {training_sessions:[{done_at, group, ...}]}."""
        return await self._request("GET", "v3/training_sessions")

    async def async_get_locations(self) -> Any:
        """Lista de unidades agrupada por UF: [{uf, locations:[{acronym,name,address}]}]."""
        return await self._request("GET", "v1/locations")


def _only_digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())
