# Smart Fit — Home Assistant

Integração (não-oficial) que traz dados da sua conta **Smart Fit** para o Home
Assistant, via engenharia reversa do app Flutter `com.eokoe.smartfitcoach`.

> Sem afiliação com a Smart Fit. Use com a sua própria conta.

## Sensores

- **Plano** — plano/assinatura vigente.
- **Treinos no mês** — frequência do mês atual.
- **Lotação da unidade** — ocupação da academia escolhida (atributo
  `lotacao_por_hora` com a previsão por horário).

## Instalação (HACS)

1. HACS → Integrações → repositório custom → `hudsonbrendon/ha-smartfit`.
2. Instale e reinicie o Home Assistant.
3. Ajustes → Dispositivos e serviços → Adicionar → **Smart Fit**.
4. Informe o **CPF**, digite o **código** recebido por SMS/e-mail e escolha a
   **unidade** para acompanhar a lotação.

A sessão não renova sozinha: quando expirar, o HA pede um novo código (reauth).

## Como funciona

Veja [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).
