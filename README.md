<p align="center">
  <img src="logo.png" alt="Smart Fit" height="90">
</p>

# Smart Fit — Home Assistant

Integração (não-oficial) que traz dados da sua conta **Smart Fit** para o Home
Assistant, via engenharia reversa do app Flutter `com.eokoe.smartfitcoach`.

> Sem afiliação com a Smart Fit. Use com a sua própria conta.

## Entidades

Uma conta vira **três dispositivos** no HA: **Smart Fit Conta** (cadastro e
financeiro), **Smart Fit Treino** e **Smart Fit Unidade**. Datas nos atributos
ficam em `dd/mm/aaaa`; os estados de data usam o formato do seu perfil do HA.

### Smart Fit Conta

| Entidade | Descrição |
|---|---|
| **Perfil** | Nome (com foto); e-mail, telefone, nascimento, endereço, acessos liberados |
| **Plano** / **Matrícula** | Plano (ex.: Black) e nº de matrícula |
| **Mensalidade** | Valor (plano, status, dia de vencimento, forma de pagamento, cliente desde, anuidade, boleto) |
| **Cartão cadastrado** | Bandeira e final do cartão (validade) |
| **Próximo pagamento** | Data do próximo vencimento (valor, período, agendados até 12 meses) |
| **Último pagamento** | Data do último pagamento (valor, nº da nota fiscal, links da NF-e e do recibo) |
| **Total pago** | Soma de tudo que já foi pago (histórico dos últimos 36) |
| **Pagamentos em atraso** | Faturas vencidas (valor, boleto, código de barras) |
| **Pendências financeiras** | Situação de débitos segundo o app |
| **Convidados** | Convidados cadastrados (Black): nomes, usados/máximo, renovação |
| **Seguidores** | Perfil social (seguindo, amigos, "cliente há X anos", link) |
| **Apps conectados** | Parceiros ligados à conta (GymRats etc.) |
| 📅 **Pagamentos** | Calendário com cada mensalidade (paga/agendada/em atraso) no dia do vencimento |

### Smart Fit Treino

| Entidade | Descrição |
|---|---|
| **Ficha de treino** | Grupos da ficha (A/B/C/D), frequência, professor, início, validade, última vez de cada grupo |
| **Próximo treino** | Grupo feito há mais tempo, com os exercícios (séries, repetições, intervalo, máquina, método) |
| **Validade do treino** | Data em que a ficha vence |
| **Treinos na semana** | Feitos × esperados, semanas consecutivas, total de sessões |
| **Treinos no mês** / **Minutos no mês** | Volume do mês atual |
| **Total de treinos** | Histórico completo (últimos 30 nos atributos: data, grupo, duração, exercícios) |
| **Sequência semanal** / **Recorde semanal** | Semanas seguidas treinando e o recorde |
| **Progresso do treino** | % do programa atual |
| **Último treino** | Data/hora do último treino (grupo, duração, exercícios) |
| **Anamnese** | Objetivo/ênfase do treino e as demais respostas (horário, duração, peso/altura) |
| 📅 **Treinos** | Calendário com cada treino feito (duração real, grupo, exercícios) |

### Smart Fit Unidade

| Entidade | Descrição |
|---|---|
| **Unidade** | Academia do plano: endereço, cidade, CEP, inauguração, categoria, PIX/boleto |
| **Lotação da unidade** | Pessoas agora (curva por hora + pico) |
| **Próxima aula coletiva** | Próxima aula (nome, professor, sala, aulas de hoje) |
| 📅 **Aulas coletivas** | Calendário com a grade dos próximos 5 dias |

Os dados financeiros vêm do **Espaço do Cliente** (web); a integração entra
lá sozinha com um *magic link* gerado pela sessão do app, sem senha extra.

## Instalação (HACS)

1. HACS → Integrações → repositório custom → `hudsonbrendon/ha-smartfit`.
2. Instale e reinicie o Home Assistant.
3. Ajustes → Dispositivos e serviços → Adicionar → **Smart Fit**.
4. Informe o **CPF**, escolha **SMS ou e-mail** e digite o **código** recebido.

A unidade é detectada automaticamente pelo perfil. A sessão não renova sozinha:
quando expirar, o HA pede um novo código (reauth).

## Como funciona

Veja [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).
