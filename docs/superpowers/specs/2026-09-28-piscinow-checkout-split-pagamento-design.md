# Piscinow — Checkout, Split de Pagamento e Retenção por Etapas (Sub-projeto 5)

**Data:** 2026-09-28
**Status:** Aprovado para virar plano de implementação
**Branch:** `piscinow-landing-clube-agente` (continuação dos sub-projetos 1, 2, 3 e 4, ainda sem merge no `main`)

## Contexto

Este é o **sub-projeto 5** de 7 do Clube Piscinow (ver decomposição completa em
[`2026-09-06-piscinow-landing-clube-agente-design.md`](2026-09-06-piscinow-landing-clube-agente-design.md)).

Os sub-projetos 1 a 4 já entregam: landing page, Clube por indicação/fila,
agente de atendimento, catálogos de produto (loja) e serviço (prestador),
e um configurador de projeto onde o comprador monta e confirma um projeto
(um produto principal + N serviços). Este sub-projeto cobre o que a spec
original chama de reter "o pagamento por etapa da obra": o comprador paga
o valor total de um projeto confirmado de uma vez, o dinheiro fica retido,
e o admin libera o repasse pra loja/prestadores conforme cada fase física
da obra é concluída.

Não inclui o acompanhamento visual da obra em si (isso é o sub-projeto 6)
nem um adaptador real de provedor de pagamento — este sub-projeto entrega
a interface `PaymentProvider` e uma implementação fake para testes; a
implementação real de Mercado Pago fica para quando houver conta/sandbox
configurados, sem exigir mudança no resto do sistema.

## Requisitos levantados com o usuário

- **Provedor de pagamento**: abstração `PaymentProvider` (mesmo espírito
  do `LLMProvider` já existente), trocável — só a implementação fake é
  construída agora; Mercado Pago é o provedor-alvo eventual (split nativo,
  Pix, KYC resolvido pelo provedor), mas o adaptador real fica fora de
  escopo desta fase.
- **Momento do pagamento**: cobrança única no checkout do projeto
  confirmado — o valor fica retido e é repassado por fase, não cobrado de
  novo a cada fase.
- **Fases**: quatro fases fixas de obra de piscina — terraplanagem,
  estrutura, revestimento, acabamento (mesmas já mencionadas na landing
  page).
- **Split entre loja e prestador**: cada parte recebe o valor do seu item
  (produto ou serviço) numa fase específica, não uma fração em cada fase.
- **Atribuição de fase e valor**: o admin monta o cronograma manualmente —
  atribui cada item (o produto, e cada serviço) a uma das quatro fases e
  digita o valor final. Para serviços (que só têm uma faixa `price_min`/
  `price_max` cadastrada), o valor digitado não é validado contra essa
  faixa — é só o registro do que foi negociado fora do sistema.
- **Liberação de fase**: manual pelo admin (mesmo padrão de aprovação
  manual já usado em todo o projeto) — libera todas as alocações de uma
  fase de uma vez.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                  FastAPI monolito (existente)              │
│                                                              │
│  Comprador (sub-proj. 4, estendido)                          │
│    → projeto confirmado → NOVO: /comprador/projeto/pagamento │
│      → vê cronograma (montado pelo admin) → paga uma vez     │
│                                                              │
│  Admin (estendido)                                           │
│    → NOVO: /admin/pagamentos                                 │
│      → monta cronograma (fase + valor por item)              │
│      → libera cada fase conforme a obra avança                │
│                                                              │
│  NOVO: src/piscinow/payment/                                 │
│    ├─ payment_provider.py (interface PaymentProvider,        │
│    │    espelha LLMProvider: charge() + release())            │
│    └─ providers/fake_provider.py (FakePaymentProvider,        │
│         em memória, mesmo espírito do FakeLLMProvider)         │
│    (adaptador real de Mercado Pago fica pra depois)            │
│                                                              │
│  Banco: Payment (1:1 com Project confirmado) +                 │
│         PaymentAllocation (1 por item: produto ou serviço,      │
│         com fase, valor, destinatário, status)                  │
└─────────────────────────────────────────────────────────┘
```

### Abordagens consideradas (provedor de pagamento)

1. **Mercado Pago (recomendação de longo prazo)** — API de "Divisão de
   pagamentos" já desenhada pra este caso (múltiplos recebedores,
   retenção), suporte nativo a Pix, KYC de loja/prestador resolvido pelo
   provedor. Documentação em português, ampla adoção em marketplaces
   brasileiros.
2. **Stripe Connect** — split maduro internacionalmente, mas exige mais
   trabalho de compliance (KYC via Stripe Identity, onboarding de
   "connected accounts") pra operar no Brasil, com Pix ainda menos
   maduro que no Mercado Pago.

**Escolhida nesta fase: nenhuma diretamente** — constrói-se a interface
`PaymentProvider` (Abordagem trocável, mesmo padrão de `LLMProvider`) com
uma implementação fake para desenvolvimento e testes. A escolha entre
Mercado Pago e Stripe Connect (recomendação: Mercado Pago) fica para
quando o adaptador real for implementado, sem impacto no resto do
sistema graças à interface.

## Componentes

### `src/piscinow/payment/payment_provider.py` (novo)
Interface abstrata `PaymentProvider`, espelhando `LLMProvider`:
- `async def charge(self, *, amount: Decimal, external_reference: str) -> str`
  — cobra o valor total do comprador, retorna um id de cobrança externo.
- `async def release(self, *, charge_id: str, amount: Decimal, external_reference: str) -> str`
  — libera/repassa uma fatia retida de uma cobrança já paga, retorna um
  id de repasse externo.

### `src/piscinow/payment/providers/fake_provider.py` (novo)
`FakePaymentProvider` — implementação em memória para desenvolvimento e
testes, mesmo espírito do `FakeLLMProvider`: gera ids fake determinísticos
e guarda um histórico de chamadas (`charges`, `releases`) que os testes
podem inspecionar. Suporta ser configurado para simular falha (ex.:
`should_fail_charge=True`) para testar o caminho de erro.

### `src/piscinow/models/payment.py` (novo)
- `PaymentStage` (enum `str`): `TERRAPLANAGEM`, `ESTRUTURA`, `REVESTIMENTO`,
  `ACABAMENTO`.
- `PaymentStatus` (enum `str`): `PENDENTE`, `PAGO`.
- `AllocationStatus` (enum `str`): `RETIDO`, `LIBERADO`.
- `Payment`: `id`, `project_id` (FK para `projects`, `unique=True` — um
  pagamento por projeto confirmado), `total_amount`, `status` (default
  `PENDENTE`), `external_charge_id` (nulo até pago), `created_at`,
  `paid_at` (nulo até pago).
- `PaymentAllocation`: `id`, `payment_id` (FK), `stage`,
  `recipient_member_id` (FK para `members` — a loja ou o prestador dono
  do item), `product_id` (FK, nulo se for alocação de serviço),
  `service_id` (FK, nulo se for alocação de produto — exatamente um dos
  dois preenchido), `amount`, `status` (default `RETIDO`), `released_at`
  (nulo até liberado), `released_by` (e-mail do admin, nulo até
  liberado), `external_transfer_id` (nulo até liberado).

### Admin (extensão)
- `GET /admin/pagamentos` — lista projetos com `status == CONFIRMADO` que
  ainda não têm `Payment` associado.
- `GET/POST /admin/pagamentos/{project_id}/cronograma` — monta o
  cronograma: formulário com uma linha por item (produto + cada serviço
  vinculado ao projeto), cada linha com seletor de fase e campo de valor.
  Ao salvar, cria o `Payment` (`status=PENDENTE`, `total_amount` = soma
  das alocações) e uma `PaymentAllocation` por item.
- `GET /admin/pagamentos/{payment_id}` — mostra o cronograma e o status
  de cada alocação (retido/liberado); se `Payment.status == PAGO`, cada
  fase (com alocações ainda retidas) tem um botão "Liberar fase".
- `POST /admin/pagamentos/{payment_id}/fases/{stage}/liberar` — libera
  todas as alocações `RETIDO` daquela fase de uma vez: para cada uma,
  chama `PaymentProvider.release(...)`, grava `external_transfer_id`,
  `released_at`, `released_by`, muda `status` para `LIBERADO`.

### Comprador (extensão de `comprador_projeto.py`)
- `GET /comprador/projeto/pagamento` — mostra o cronograma (somente
  leitura: fase, item, destinatário, valor) e o total; só acessível se
  já existir um `Payment` para o projeto (o admin já montou o
  cronograma). Se `Payment.status == PENDENTE`, mostra o botão "Pagar".
- `POST /comprador/projeto/pagamento/pagar` — só permitido se
  `Payment.status == PENDENTE`; chama
  `PaymentProvider.charge(amount=total_amount, external_reference=str(payment.id))`;
  se a chamada tiver sucesso, grava `external_charge_id`, `paid_at`, muda
  `status` para `PAGO`; se falhar, mantém `PENDENTE` e reexibe com
  mensagem genérica de erro.

## Fluxo de dados

1. **Projeto confirmado → montar cronograma**: admin acessa
   `/admin/pagamentos`, escolhe um projeto confirmado sem pagamento
   ainda, monta o cronograma (fase + valor por item). Isso cria o
   `Payment` e suas `PaymentAllocation`s.
2. **Comprador paga**: `/comprador/projeto/pagamento` mostra o
   cronograma e o total. Ao clicar "Pagar", a rota chama
   `PaymentProvider.charge(...)`. Sucesso muda `Payment.status` para
   `PAGO`; todas as alocações continuam `RETIDO`.
3. **Admin libera por fase**: conforme a obra avança (tela detalhada
   fica pro sub-projeto 6 — aqui só a ação de liberar já existe), o
   admin libera uma fase inteira de uma vez; cada alocação `RETIDO`
   daquela fase vira `LIBERADO` via `PaymentProvider.release(...)`.
4. Não há liberação parcial de uma fase — libera todo mundo daquela fase
   junto.

## Tratamento de erros

- **Montar cronograma para projeto não confirmado**: 404/400 — só
  projetos `CONFIRMADO` aparecem em `/admin/pagamentos`.
- **Cronograma incompleto** (item sem fase ou sem valor válido):
  validação no backend, reexibe com erro — nunca cria `Payment` com
  alocação incompleta.
- **Montar cronograma duas vezes pro mesmo projeto**: 400 —
  `Payment.project_id` é `unique=True`; a rota checa se já existe antes
  de criar outro.
- **Comprador tentando pagar duas vezes**: 400 — só permite `charge()`
  se `Payment.status == PENDENTE`.
- **`PaymentProvider.charge()` falha** (rejeição, erro de rede/provedor):
  `Payment` continua `PENDENTE`, mensagem genérica pro comprador tentar
  de novo — nunca marca como `PAGO` sem confirmação real do provedor.
- **Admin tentando liberar fase de pagamento não pago**: 400 — só libera
  alocações de um `Payment` com `status == PAGO`.
- **Liberar fase já liberada**: 400/idempotente — não libera de novo uma
  alocação já `LIBERADO`, evitando repasse duplicado.
- **Comprador ou terceiro tentando acessar cronograma/pagamento de outro
  projeto**: 404 — mesma regra de posse já estabelecida (via
  `require_comprador` + checagem de `project.member_id`).

## Estratégia de testes

Mesmo padrão TDD dos sub-projetos anteriores:
- **`PaymentProvider`/`FakePaymentProvider`**: testado isoladamente, sem
  banco — confirma que `charge()`/`release()` retornam ids únicos e
  registram o histórico de chamadas; confirma o caminho de falha
  configurável. Real GREEN, sem Docker.
- **Integração (precisa de `db_session`)**: fluxo completo montar
  cronograma → comprador paga → admin libera fase; isolamento (um
  comprador não acessa pagamento de outro projeto); erro ao pagar quando
  `PaymentProvider.charge()` falha; idempotência de liberação de fase
  (liberar duas vezes não libera duas vezes nem duplica o repasse).
- Mesma ressalva de sempre: sem Docker nesta máquina de desenvolvimento,
  os testes que tocam banco são escritos e revisados com cuidado, mas só
  confirmados de fato quando rodados num ambiente com Postgres.

## Fora de escopo nesta fase

- Adaptador real de Mercado Pago (ou qualquer provedor real) — só a
  interface e o fake nesta fase.
- Tela de acompanhamento visual da obra (nasce no sub-projeto 6); aqui
  só a ação de "liberar fase" existe, sem timeline/fotos/status por
  etapa.
- Liberação automática de fase (sempre manual pelo admin nesta fase).
- Liberação parcial de uma fase (é tudo ou nada por fase).
- Reembolso/estorno, cancelamento de projeto após pagamento, disputas.
- Comissão da própria Piscinow sobre a transação (o `total_amount`
  cobrado hoje é só a soma do que vai pra loja/prestadores).
- Múltiplos pagamentos por projeto (um projeto confirmado tem no máximo
  um `Payment`, `unique=True`).

## Próximos passos

Este documento serve de base para o plano de implementação (skill
`writing-plans`), que vai detalhar as tarefas de TDD para: a interface
`PaymentProvider` e o `FakePaymentProvider`, os modelos `Payment`/
`PaymentAllocation`, as rotas de admin (listar, montar cronograma, ver
detalhe, liberar fase), e as rotas do comprador (ver cronograma, pagar).
