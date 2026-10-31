<p align="center">
  <img src="logo.png" alt="Smart Fit" height="90">
</p>

# Smart Fit — Home Assistant

Integração (não-oficial) que traz dados da sua conta **Smart Fit** para o Home
Assistant, via engenharia reversa do app Flutter `com.eokoe.smartfitcoach`.

> Sem afiliação com a Smart Fit. Use com a sua própria conta.

## Sensores

| Sensor | Descrição |
|---|---|
| **Plano** | Plano/assinatura (ex.: Black) |
| **Matrícula** | Número de matrícula |
| **Unidade** | Academia vinculada ao perfil |
| **Treinos no mês** | Treinos registrados no mês atual |
| **Minutos no mês** | Tempo total treinado no mês |
| **Total de treinos** | Histórico completo de treinos |
| **Sequência semanal** | Semanas seguidas treinando |
| **Progresso do treino** | % do programa atual (sessões no atributo) |
| **Último treino** | Data/hora do último treino (grupo, duração, exercícios) |
| **Lotação da unidade** | Pessoas na academia agora (curva por hora + pico no atributo) |
| **Pendências financeiras** | Situação de débitos |
| **Convidados** | Convidados cadastrados (Black) |

## Instalação (HACS)

1. HACS → Integrações → repositório custom → `hudsonbrendon/ha-smartfit`.
2. Instale e reinicie o Home Assistant.
3. Ajustes → Dispositivos e serviços → Adicionar → **Smart Fit**.
4. Informe o **CPF**, escolha **SMS ou e-mail** e digite o **código** recebido.

A unidade é detectada automaticamente pelo perfil. A sessão não renova sozinha:
quando expirar, o HA pede um novo código (reauth).

## Como funciona

Veja [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).
