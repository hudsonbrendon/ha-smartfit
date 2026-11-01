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

## Endpoints extras (confirmados em login real)

| Recurso | Método / path | Campos usados |
|---|---|---|
| Estatísticas de treino | `GET v3/training_session_stats` | `weekly_training_streak.current_weekly_count`, `training_progress.{completed_session,total_session,progress_in_percent}`, `last_training_session` |
| Resultados do mês | `GET v1/monthly_activity_results` | `cards[].metadata.title` (nº de treinos / minutos no texto) |
| Pendências financeiras | `GET v2/debts` | `empty_state` = em dia |
| Convidados (Black) | `GET v1/guests` | `guests[]` (contagem) |
| Bioimpedância | `GET v2/bioimpedances` | `measurements` (vazio se nunca mediu) |

## Marca

Ícone e logo oficiais extraídos do APK (`icon.png` 512×512 do bundle;
`.../app_assets/.../training/smartfit-logo.svg`). Enviados ao
[home-assistant/brands] em `custom_integrations/smart_fit/` para o HA exibir a
logo.

[home-assistant/brands]: https://github.com/home-assistant/brands

## Ficha de treino e aulas (confirmados em login real, 31/10)

| Recurso | Método / path | Campos usados |
|---|---|---|
| **Ficha atual** | `GET v2/trainings` | `weight_training.{frequency,start_date,finish_date(epoch),teacher_name,automatically_generated, groups[]{letter,label,exercises[]{title,series,repetitions[2],interval[2],smartfit_code,intensification_method},data.done_at(epoch)}, weekly_streak.{current_count,current_record}}` |
| Ficha (variante) | `GET v3/current_training` | mesma ficha, exercícios com `video_url`/`image_url` |
| **Aulas coletivas** | `GET v1/classes` | `location{name,acronym}`, `schedule[]{date, classes[]{name,start_at,end_at,teacher,room,duration,classification}}` (5 dias) |
| Conquistas | `GET v1/achievements` | catálogo de medalhas (sem estado do usuário) |
| Sugestões de treino | `GET v1/training_suggestions` / `v3/recommended_trainings` | fichas prontas |
| Parceiros | `GET v1/partner_connections` | apps conectados (GymRats etc.) |
| Home do app | `GET v1/feed` | widgets (training_calendar, smart_spa...) |

Sem dado útil / 404 / 500 para o aluno comum: `v1/purchases`, `v1/purchase_status`,
`v1/marketing/contracts`, `v3/training_calendar`, `v3/group_fitness_classes/*`,
`v1/analytics/activities`, `v1/wifi_coupons`, `v3/anamnesis/current`.

## Financeiro — Espaço do Cliente (web)

O app **não** tem endpoint de histórico de pagamento; ele abre a área web
**`https://espacodocliente.smartfit.com.br`** por um *magic link*
(`training/.../warning_cancel_plan/data/endpoints/magic_link_endpoint.dart`):

1. `POST v1/client_space/magic_link` body `{"destination_path": "/payment"}` (api-mobile,
   com `X-Api-Key`) → `{"client_space_url": ".../pt-BR/auth?t=<JWT HS256, exp 1h>"}`.
2. O site (Next.js) troca o JWT por cookie: `GET /api/v1/auth?t=<jwt>` →
   `Set-Cookie: session/smart-client-space=…` (válido ~21h).
3. Com o cookie, a API própria do site (`js/1546-*.js`, `axios` com `/api/...`):

| Recurso | Path | Campos |
|---|---|---|
| **Cadastro + plano** | `GET /api/v1/user` | `purchase.{membership_price,plan,confirmed_at,limit_guests}`, `plan.status`, `wallet.{masked_card_number,payment_company_name,expires_at}`, `has_pending_payments`, `count_current_guests`, `location{...}`, `bank_slip_url`, `booking_url` |
| **Forma de pagamento** | `GET /api/v1/user-plan` | `payment_method`, `membership_due_date` (dia) |
| Cartão | `GET /api/v3/client_space/wallet` | `data.{payment_company_name,masked_card_number,expires_at}` |
| **Pagamentos** | `GET /api/v3/client_space/payments?status=payed\|scheduled\|overdue&page=1&per_page=50` | `data[]{id,dueDate,value,payed_at,paymentState,startAt,endAt,planName,siteRpsPath (recibo),invoiceDescription{url,params[Numnota,Cdverificacao]},barcode,client_bank_slip_url}` |

`status` aceita **só** `overdue`, `scheduled`, `payed` (`history-installments-*.js`);
`per_page` máx 50; o site pagina até 20 páginas. Outros status → `400 Invalid status`.
Rotas de escrita existentes (não usadas): `POST /api/v1/user/pay-pendency`,
`PUT /api/v2/plan/finalize_suspension`, `POST /api/v3/churn/`, `PUT /api/v1/purchase/`.
