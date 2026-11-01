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

# "Espaço do Cliente" (web). O app abre essa área via magic link
# (`POST v1/client_space/magic_link {destination_path}` → `client_space_url`
# com um JWT `t=` de 1h). O site troca o JWT por um cookie de sessão em
# `GET /api/v1/auth?t=<jwt>` e expõe uma API Next.js própria com os dados
# financeiros (mensalidade, cartão, histórico de pagamentos).
CLIENT_SPACE_URL = "https://espacodocliente.smartfit.com.br"
_CS_COOKIE = "session/smart-client-space"


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
        self._cs_cookie: str | None = None

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

    async def async_get_training_stats(self) -> Any:
        """Estatísticas: last_training_session, weekly_training_streak, training_progress."""
        return await self._request("GET", "v3/training_session_stats")

    async def async_get_monthly_activity(self) -> Any:
        """Resultados do mês: {title, cards:[{tracking, metadata:{title}}]}.

        `tracking` é `training_sessions` (nº de treinos) ou `training_duration`
        (minutos); o número fica no texto de `metadata.title`.
        """
        return await self._request("GET", "v1/monthly_activity_results")

    async def async_get_debts(self) -> Any:
        """Pendências financeiras. Com `empty_state` = sem débitos."""
        return await self._request("GET", "v2/debts")

    async def async_get_guests(self) -> Any:
        """Convidados (Black): {guests:[{id, name, blocked, ...}]}."""
        return await self._request("GET", "v1/guests")

    async def async_get_locations(self) -> Any:
        """Lista de unidades agrupada por UF: [{uf, locations:[{acronym,name,address}]}]."""
        return await self._request("GET", "v1/locations")

    async def async_get_training(self) -> Any:
        """Ficha de treino atual (v2): {weight_training:{frequency, start_date,
        finish_date(epoch), teacher_name, groups:[{letter,label,exercises,data:{done_at}}],
        weekly_streak:{current_count,current_record}}}."""
        return await self._request("GET", "v2/trainings")

    async def async_get_classes(self) -> Any:
        """Grade de aulas coletivas da unidade do aluno:
        {location:{name,acronym}, schedule:[{date, classes:[{name,start_at,end_at,teacher,room,duration}]}]}."""
        return await self._request("GET", "v1/classes")

    # -- Espaço do Cliente (financeiro) ----------------------------------

    async def async_get_magic_link(self, destination_path: str = "/payment") -> str:
        """URL autenticada do Espaço do Cliente (JWT `t=` válido por 1h)."""
        data = await self._request(
            "POST",
            "v1/client_space/magic_link",
            json={"destination_path": destination_path},
        )
        url = (data or {}).get("client_space_url") if isinstance(data, dict) else None
        if not url:
            raise SmartFitApiError("magic_link sem client_space_url")
        return str(url)

    async def _cs_login(self) -> None:
        """Troca o JWT do magic link pelo cookie de sessão do Espaço do Cliente."""
        url = await self.async_get_magic_link()
        token = url.split("t=", 1)[1].split("&", 1)[0]
        try:
            async with self._session.get(
                f"{CLIENT_SPACE_URL}/api/v1/auth",
                params={"t": token},
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT),
            ) as resp:
                cookie = resp.cookies.get(_CS_COOKIE)
                if resp.status != 200 or cookie is None:
                    body = await resp.text()
                    raise SmartFitApiError(
                        f"Espaço do Cliente auth HTTP {resp.status}: {body[:120]}"
                    )
                self._cs_cookie = cookie.value
        except aiohttp.ClientError as err:
            raise SmartFitApiCommunicationError(str(err)) from err
        except TimeoutError as err:
            raise SmartFitApiCommunicationError("timeout") from err

    async def _cs_get(self, path: str, params: dict[str, Any] | None = None, *, _retry: bool = True) -> Any:
        if not self._cs_cookie:
            await self._cs_login()
        try:
            async with self._session.get(
                f"{CLIENT_SPACE_URL}/{path.lstrip('/')}",
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0",
                    "Cookie": f"{_CS_COOKIE}={self._cs_cookie}",
                },
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT),
            ) as resp:
                if resp.status in (401, 405) and _retry:
                    # cookie expirou (~21h): refaz o magic link uma vez
                    self._cs_cookie = None
                    return await self._cs_get(path, params, _retry=False)
                body = await resp.text()
                if resp.status >= 400:
                    raise SmartFitApiError(f"Espaço do Cliente HTTP {resp.status}: {body[:160]}")
                return await resp.json(content_type=None) if body else None
        except aiohttp.ClientError as err:
            raise SmartFitApiCommunicationError(str(err)) from err
        except TimeoutError as err:
            raise SmartFitApiCommunicationError("timeout") from err

    async def async_get_client_space(self) -> dict[str, Any]:
        """Dados financeiros do Espaço do Cliente num dict só.

        - `user`: `/api/v1/user` → purchase.membership_price, plan.status,
          wallet{masked_card_number, payment_company_name, expires_at},
          has_pending_payments, count_current_guests, location{...}.
        - `user_plan`: `/api/v1/user-plan` → payment_method, membership_due_date (dia).
        - `payed`/`scheduled`/`overdue`: `/api/v3/client_space/payments?status=`
          → data:[{id, dueDate, value, payed_at, paymentState, startAt, endAt,
          siteRpsPath (NF-e), invoiceDescription{url,params}, barcode, client_bank_slip_url}].
        Só a página 1 (50 itens) de cada status.
        """
        out: dict[str, Any] = {
            "user": await self._cs_get("api/v1/user"),
            "user_plan": await self._cs_get("api/v1/user-plan"),
        }
        for status in ("payed", "scheduled", "overdue"):
            res = await self._cs_get(
                "api/v3/client_space/payments",
                {"status": status, "page": 1, "per_page": 50},
            )
            items = res.get("data") if isinstance(res, dict) else None
            out[status] = items if isinstance(items, list) else []
        return out


def _only_digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())
