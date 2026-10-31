# Engenharia reversa — app Smart Fit

Alvo: **`com.eokoe.smartfitcoach`** v4.9.26 (APK da APKMirror). App **Flutter**
(Dart 3.9.2, `libapp.so` AOT). Decompilado com [blutter] (nunca executado).
No macOS o build do blutter precisou de `ICU_ROOT=/opt/homebrew/opt/icu4c@78` e
`PKG_CONFIG_PATH` apontando para `capstone/lib/pkgconfig`.

## Backend

- REST (academia): **`https://api-mobile.smartfit.com.br/api/`** (Rails).
- Há um 2º backend GraphQL (saúde/nutri, `Authorization: Bearer`) — não usado aqui.
- Base URL e segredos ficam em `LocalAppConfigApplication`
  (`application/src/utils/local_app_config_application.dart`).

## Autenticação

`HttpApiProvider._buildHeader` monta, em toda requisição REST:

| Header | Origem | Valor |
|---|---|---|
| `Authorization` | `serverAuthorization` (estático) | `Token token=Hi6SmkNjLUpbGbdB525CwUQs` |
| `X-Api-Key` | `apiToken` = `SessionEntity.sessionToken` | token do usuário (vazio = público) |
| `User-Agent`, `Accept-Language`, `Locale`, `Content-Type` | config | — |

- O **token estático do app** (`Hi6Smk…`) sozinho já autoriza endpoints públicos
  (`v1/countries`, `v1/states`). Sem `X-Api-Key`, endpoints de usuário dão
  `401 HTTP Token: Access denied`.
- O **token do usuário** vai no `X-Api-Key`, **não** no `Authorization`. Ele é o
  campo **`id`** da resposta do validate — `ApiValidateTokenRepository._saveSession`
  grava `id → SessionEntity.sessionToken`.

## Login (CPF + OTP de 4 dígitos)

Módulo `login`, endpoints em `login/src/features/*/data/endpoints`:

1. `POST v1/tokens` — body `{document, locale:"pt-BR", corporative:false}`.
   Prepara/envia o código; devolve `pin_size` e os métodos de entrega.
   CPF inexistente → `404 {"error_code":"user_not_found","pin_size":4}`.
2. `POST v1/tokens/delivery_methods` — `{document, locale, corporative, method}`.
   Reenvia o OTP por SMS ou e-mail (opcional).
3. `GET v1/tokens/{otp}?document=<cpf>&locale=pt-BR&corporative=false` →
   `{id:<session_token>, registration_id, user_id, email, document, current_plan, brand, ...}`.

## Endpoints de leitura (exigem `X-Api-Key`)

| Recurso | Método / path | Resposta (campos vistos no DTO) |
|---|---|---|
| Unidades (busca) | `GET v1/locations` | lista de `{id, name, acronym, address, ...}` |
| **Lotação por hora** | `GET v1/locations/{id}/occupancy_rates` | `location{name,acronym,address}` + `occupancy_rates[]{hour,total}` |
| **Frequência do mês** | `GET v1/monthly_activity_results` | `results[]`, `cards[]` (`value,label,icon,...`) |
| **Plano atual** | `GET v2/purchases/current` | dados da compra/plano vigente |
| Histórico de treinos/check-ins | `GET v3/training_sessions` | sessões de treino |

A sessão do login já traz `current_plan`, `registration_id` (matrícula) e
`location_acronym`.

## Reprodução

O script `live_login.py` (em `~/RE/smartfit/`, fora deste repo) reexecuta o
fluxo com `urllib` puro: `request <CPF>` → `validate <CPF> <OTP>` →
`dump <CPF>`. O `session_token` fica em `~/RE/smartfit/.session.json` (nunca
commitar).

[blutter]: https://github.com/worawit/blutter
