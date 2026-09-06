# Piscinow — Landing Page + Clube + Agente de Atendimento (Sub-projeto 1)

**Data:** 2026-09-06
**Status:** Aprovado para virar plano de implementação

## Contexto e visão geral do produto

O **Clube Piscinow** é um e-commerce + marketplace de piscinas (venda de piscinas,
equipamentos e mão de obra) onde o comprador entra e monta o seu projeto. A
Piscinow não vende a piscina diretamente: ela conecta o comprador a lojas
físicas (fornecedores) e prestadores de serviço (instaladores) homologados,
organiza o contrato, o pagamento protegido (cobrança única, dividida
automaticamente entre loja e instalador, com parte retida até a conclusão das
etapas acordadas) e o acompanhamento da obra.

É um clube fechado, por indicação: quem tem link de convite (de um
embaixador) entra direto; quem não tem, se cadastra e entra na fila de
admissão, aprovada manualmente pela equipe Piscinow.

A operação começa em Campinas e região metropolitana (Valinhos, Vinhedo,
Indaiatuba, Paulínia, Hortolândia, Sumaré), com expansão progressiva para o
interior de São Paulo.

### Perfis de usuário
- **Comprador** — quer construir uma piscina, monta o projeto, entra pela
  fila de admissão ou por indicação.
- **Loja (fornecedor)** — loja física que cadastra catálogo de produtos
  (piscinas, equipamentos) e recebe pedidos qualificados.
- **Prestador de serviço (instalador)** — executa a obra (terraplanagem,
  estrutura, hidráulica, revestimento, acabamento) e recebe repasse por
  etapa concluída.
- **Embaixador** — angaria clientes através de links de indicação; quem
  entra pelo link do embaixador pula a fila de admissão.

### Decomposição em sub-projetos
O produto completo é grande demais para uma spec só. Foi decomposto em:

1. **Landing page + Clube (waitlist/indicação) + agente de atendimento** ← este documento
2. Cadastro e catálogo de fornecedores (lojas)
3. Cadastro de prestadores de serviço (instaladores)
4. Configurador de projeto (comprador monta o projeto)
5. Checkout, split de pagamento e retenção por etapas
6. Acompanhamento de obra
7. Programa de embaixadores (geração de links, atribuição, comissão)

Cada sub-projeto segue seu próprio ciclo spec → plano → implementação.

## Escopo deste sub-projeto

Landing page pública do Clube Piscinow com:
- Apresentação do conceito, FAQ e cobertura regional.
- Fila de admissão por indicação (com aprovação manual da equipe).
- Um **agente de atendimento conversacional em Python**, presente desde o
  início, que identifica o perfil do visitante (comprador, loja, prestador,
  embaixador) e conduz o fluxo certo para cada um.
- Um **núcleo de agente (Agent Core)** desenhado para toda a plataforma, não
  só para esta fase: LLM plugável (qualquer provedor de fronteira) e memória
  de aprendizado persistente fora do LLM, que evolui com o uso.

Fora de escopo nesta fase (fica para os sub-projetos seguintes): catálogo de
produtos real, configurador de projeto, checkout/pagamento real, split entre
loja e instalador, acompanhamento de obra, comissão de embaixador.

## Requisitos levantados com o usuário

- Ordem de prioridade dos sub-projetos confirmada, começando pela landing page.
- Loja "operada por agentes em Python": **(c)** agente de atendimento
  conversacional na ponta **e** agentes de operação de back-office (catálogo,
  pedidos, matching, split) — a parte de back-office pertence aos
  sub-projetos 2+; aqui construímos o Agent Core que sustenta ambos.
- Agente de atendimento já presente na landing page desde o início (não só a
  partir do configurador de projeto).
- Agente identifica o perfil de cada visitante e conduz o fluxo certo.
- Fila de admissão (sem link de convite) tem **aprovação manual pela equipe
  Piscinow**.
- LLM deve ser **de fronteira e plugável** — qualquer API de LLM pode ser
  conectada, sem lock-in.
- O agente deve **aprender e armazenar seu aprendizado, evoluindo com o
  tempo** — a inteligência não deve ficar presa ao LLM (nem à memória de
  contexto, nem ao framework).
- Fonte do aprendizado: **(c)** ambas — automático a partir das próprias
  interações, e ensinado/corrigido manualmente por um humano da equipe
  (correção vira memória permanente, com prioridade sobre o aprendizado
  automático).
- Deploy em **VPS** (self-managed).

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                    VPS (Docker Compose)               │
│                                                         │
│  ┌───────────────┐      ┌──────────────────────────┐ │
│  │   FastAPI      │      │        Postgres            │ │
│  │  (web + API)   │◄────►│  + pgvector                 │ │
│  │                │      │  (dados relacionais +       │ │
│  │  - Páginas     │      │   memória do agente)        │ │
│  │    (Jinja2)    │      └──────────────────────────┘ │
│  │  - HTMX/Alpine │                                     │
│  │  - Chat (SSE)  │      ┌──────────────────────────┐ │
│  │  - Painel admin│      │   Agent Core (Python)       │ │
│  │    (aprovação) │◄────►│  - LLMProvider (interface)   │ │
│  └───────────────┘      │    adapters: Anthropic/      │ │
│                          │    OpenAI/Google/...         │ │
│                          │  - MemoryStore (Postgres)    │ │
│                          │  - Extractor (pós-conversa)  │ │
│                          └──────────────────────────┘ │
│                                    │                    │
│                                    ▼                    │
│                      APIs de LLM externas (via HTTPS)   │
└─────────────────────────────────────────────────────┘
```

Um único serviço FastAPI cuida do site, do chat e do painel admin (monólito
Python). O Agent Core é uma camada Python interna (biblioteca, não um serviço
separado nesta fase) que qualquer rota pode chamar. O Postgres guarda tanto
os dados de negócio (membros, fila, links) quanto a memória do agente — nada
de estado importante vive só no LLM ou em memória do processo.

### Abordagens consideradas

1. **Monólito Python — FastAPI + HTMX, núcleo de agente próprio (escolhida)**
   Um único codebase e deploy no VPS. Jinja2 + HTMX/Alpine.js para
   interatividade, sem pipeline de build de frontend. Núcleo de agente
   autoral (LLMProvider plugável + MemoryStore em Postgres/pgvector). Mais
   rápido de construir e manter por uma pessoa só; migração de frontend para
   algo mais rico (ex. Next.js) fica possível depois sem tocar o núcleo do
   agente.
2. **Frontend e backend separados — Next.js + FastAPI (API only)**
   UI mais "produto", melhor para evoluir dashboards ricos nas fases
   seguintes, mas dobra a complexidade operacional (dois pipelines, duas
   linguagens) sem necessidade nesta fase inicial.
3. **Framework de agente (LangGraph) + Next.js**
   Ganha velocidade de scaffolding, mas empurra o estado para os checkpoints
   do próprio framework — conflita com o requisito de manter a inteligência
   fora do LLM/framework, e cria lock-in de orquestração.

**Escolhida: Abordagem 1.**

## Componentes

### Camada Web (FastAPI + Jinja2/HTMX)
- Páginas públicas: home, FAQ, cobertura regional, tratamento de chegada por
  link de embaixador (`?ref=<codigo>`).
- Widget de chat embutido na home, comunicação via SSE para resposta em
  streaming.
- Painel admin autenticado: fila de admissão (aprovar/recusar) e tela de
  correções, onde a equipe revisa trechos de conversa e ensina o agente
  (vira memória permanente).

### Agent Core (biblioteca Python interna)
- **Router/Classifier** — primeira função do agente em cada conversa nova:
  decide o perfil do visitante (comprador / loja / prestador / embaixador) a
  partir da mensagem inicial e do contexto (ex: veio de `?ref=`, já é
  embaixador conhecido). Pode reclassificar se a conversa indicar outro
  perfil no meio do caminho. Se a confiança for baixa, pergunta diretamente
  em vez de arriscar o fluxo errado.
- **Conversation Handler** — um fluxo de condução por perfil (objetivos e
  dados a coletar diferentes por perfil). Usa o `LLMProvider` para gerar
  respostas, sempre municiado com o que o `MemoryStore` traz de relevante
  para aquele perfil/situação.
- **LLMProvider** — interface única (`generate(messages, system, tools) ->
  response`) com adapters por fornecedor (Anthropic, OpenAI, Google, etc.),
  escolha configurável via variável de ambiente. Trocar de modelo/provedor
  não toca no resto do sistema.
- **MemoryStore** — leitura (busca semântica via pgvector antes de cada
  resposta) e escrita (grava fatos novos, objeções, o que funcionou).
  Separa aprendizado **automático** (`source=auto`, extraído das próprias
  conversas) de aprendizado **ensinado** (`source=human`, corrigido pela
  equipe), com o ensinado tendo prioridade/confiança maior na recuperação.
- **Extractor** — roda ao final de cada conversa (background, best-effort):
  analisa o que aconteceu e grava novos itens de memória como `auto`.

### Sistema de indicação/embaixador
- Geração de link único por embaixador; toda visita/lead que chega por ele é
  atribuída a essa indicação, usada para eventual admissão facilitada (ver
  nota abaixo) e, em fase futura, cálculo de comissão.

## Fluxo de dados / jornada

**Chegada:** visitante acessa o site (com ou sem `?ref=<codigo>`). Se veio
por link, o sistema já grava a atribuição antes mesmo do chat começar. O chat
abre com uma mensagem inicial do agente.

**Classificação e condução:**
1. Router/Classifier lê a primeira mensagem (+ sinal do `?ref=`, se houver) e
   decide o perfil.
2. Conversation Handler correspondente assume: busca no MemoryStore o que
   for relevante e conduz a conversa com esse contexto.
3. Ao longo da conversa, o agente coleta os dados por perfil:
   - **Comprador**: nome, contato, região, intenção → registra como lead na
     fila de admissão (ou admissão facilitada se veio de indicação válida —
     ver nota sobre decisão em aberto abaixo).
   - **Loja / Prestador**: dados de pré-cadastro (CNPJ, região, categoria) →
     registra como pré-cadastro pendente (aprovação manual).
   - **Embaixador**: gera/recupera o link único, explica como funciona a
     indicação.
4. Ao final, o registro é salvo no Postgres com o perfil, os dados coletados
   e a origem (indicação ou fila orgânica).

**Admissão:** fila visível no painel admin. Quem não tem indicação aguarda
revisão manual da equipe (confirmado). Quem tem indicação válida de um
embaixador recebe alguma forma de admissão facilitada — **decisão em
aberto para o plano de implementação**: entrada totalmente automática, ou
apenas prioridade/simplificação na revisão manual. Este documento não fecha
essa escolha; ela deve ser decidida (ou perguntada ao usuário) antes ou
durante a implementação.

**Loop de aprendizado:** ao fim de cada conversa, o Extractor grava itens
`auto` no MemoryStore. Periodicamente, a equipe revisa conversas no painel
admin e pode adicionar/corrigir itens `human`, que têm prioridade sobre os
automáticos na busca semântica.

## Modelagem de dados (Postgres)

- **`members`** — todo mundo que passa pelo clube: `profile_type`
  (`comprador` | `loja` | `prestador` | `embaixador`), nome, e-mail, telefone,
  região, `status` (`pending` | `waitlisted` | `approved` | `rejected`),
  `referred_by_member_id` (FK opcional), `profile_details` (JSONB — campos
  específicos do perfil), timestamps de criação/aprovação, quem aprovou.
- **`conversations`** — uma por sessão de chat: `member_id` (nulo até o
  agente identificar quem é), `profile_type_detected`, horários de
  início/fim.
- **`messages`** — mensagens da conversa (`conversation_id`, `role`,
  `content`, `created_at`) — histórico bruto para o Extractor analisar.
- **`memory_items`** — a memória do agente: `kind` (`fact` | `rule` | `faq` |
  `correction`), `source` (`auto` | `human`), `content`, `embedding`
  (pgvector), `confidence`, `profile_type` (escopo opcional), `created_by`
  (admin, se `human`), `superseded_by` (permite substituir sem apagar
  histórico).
- **`admin_users`** — login da equipe para o painel de aprovação/correção.

Fora de escopo por ora (YAGNI): tabela separada de cliques/visitas de link de
embaixador — `referred_by_member_id` já cobre atribuição para admissão e
futura comissão; métricas de clique pré-conversão ficam para quando forem
necessárias.

## Tratamento de erros

- **Falha na API do LLM**: retry com backoff simples; se persistir, mensagem
  padrão de instabilidade e log do erro — nunca trava o chat sem resposta.
- **Classificação incerta do perfil**: o agente pergunta diretamente em vez
  de arriscar o fluxo errado.
- **Link de indicação inválido/expirado**: segue pelo fluxo orgânico (fila
  manual), sem atribuição de indicação — não bloqueia o acesso.
- **Cadastro duplicado** (mesmo e-mail/telefone em `members`): agente
  reconhece e informa o status atual em vez de criar registro novo.
- **Falha na busca de memória (pgvector)**: degrada com graça — agente
  responde sem o contexto extra em vez de quebrar a conversa.
- **Falha no Extractor**: best-effort, erro só no log, nunca afeta o
  visitante que já terminou a conversa.
- **Abuso/spam no chat**: rate limit básico por IP/sessão, para evitar custo
  descontrolado de LLM.

## Estratégia de testes

- **LLMProvider**: testes unitários por adapter (mock HTTP) — garante que
  qualquer provedor implementa o mesmo contrato e que trocar de provedor não
  muda o comportamento do resto do sistema.
- **MemoryStore**: testes de integração contra Postgres de teste (container
  descartável) — grava, busca por similaridade, confirma prioridade de
  `human` sobre `auto`.
- **Lógica de negócio (sem LLM)**: testes unitários diretos para partes
  determinísticas — transição de status de `members`, atribuição de
  indicação, validação de link de convite.
- **Fluxo de conversa ponta a ponta**: testes de integração usando um
  `LLMProvider` fake (respostas roteirizadas) simulando cada perfil — testa o
  encaixe do sistema (roteamento, handler certo, registro final correto), não
  a qualidade da conversa em si.
- **Qualidade da conversa real**: não é testável automaticamente (LLM não é
  determinístico) — fica por conta da revisão manual no painel admin, que é
  o próprio mecanismo de qualidade contínua (loop de correção).
- **Painel admin**: testes de rota padrão (autenticação exigida, aprovar/
  recusar muda o status certo, correção grava `memory_item` com
  `source=human`).

Desenvolvimento segue TDD (skill `test-driven-development`), começando pelas
partes determinísticas antes de plugar o LLM de verdade.

## Protótipo visual

Um protótipo de landing page (HTML/CSS/JS, conversas simuladas sem LLM real)
foi construído para validar a direção visual e o conceito de identificação de
perfil + condução de fluxo pelo concierge, publicado como Artifact durante o
brainstorming. Arquivo de referência local:
`prototypes/clube-piscinow-landing.html`.

## Próximos passos

Este documento serve de base para o plano de implementação (skill
`writing-plans`), que vai detalhar as tarefas de TDD para construir o Agent
Core, o MemoryStore, os fluxos por perfil, a fila de admissão e o painel
admin descritos acima.
