# Piscinow — Configurador de Projeto (Sub-projeto 4)

**Data:** 2026-09-21
**Status:** Aprovado para virar plano de implementação
**Branch:** `piscinow-landing-clube-agente` (continuação dos sub-projetos 1, 2 e 3, ainda sem merge no `main`)

## Contexto

Este é o **sub-projeto 4** de 7 do Clube Piscinow (ver decomposição completa em
[`2026-09-06-piscinow-landing-clube-agente-design.md`](2026-09-06-piscinow-landing-clube-agente-design.md)).

Os sub-projetos 1, 2 e 3 já entregam: landing page, Clube por
indicação/fila, um agente de atendimento que faz o pré-cadastro de
lojas, prestadores **e compradores** pelo chat (`CompradorHandler` já
existe, coletando nome, contato, região e intenção), e áreas próprias
para loja (`/loja/*`) e prestador (`/prestador/*`) com autenticação
própria e catálogos de produto (`Product`) e serviço (`Service`).

Este sub-projeto cobre o que a spec original chama de "configurador de
projeto": dar ao comprador uma conta própria, uma vitrine pública para
descobrir produtos e serviços, e um painel para montar e confirmar um
projeto combinando um produto (piscina/equipamento) com serviços
(instalação/manutenção/reparo). Não inclui pagamento, split entre loja
e prestador, nem acompanhamento de obra — isso nasce nos sub-projetos
5 e 6.

## Requisitos levantados com o usuário

- **Conta do comprador**: mesmo padrão de loja/prestador — ao ser
  aprovado, gera-se um link de definir-senha; o comprador loga e tem
  um painel próprio (`/comprador/*`).
- **Vitrine pública**: qualquer visitante navega produtos e serviços
  (nome, categoria, descrição) **sem precisar de login e sem preço**.
  O preço só aparece depois de logado, dentro do configurador.
- **Filtros básicos na vitrine**: por tipo (`kind`), categoria e
  região — sem busca semântica.
- **Estrutura do projeto**: um produto principal (a piscina/equipamento)
  mais N serviços (podem ser de prestadores diferentes). Um comprador
  tem um projeto ativo por vez nesta fase — criar um segundo projeto
  depois de confirmar o atual fica fora de escopo.
- **Ciclo de vida do projeto**: rascunho (editável) → confirmado
  (somente-leitura). Confirmar exige produto escolhido; serviços são
  opcionais.
- **Atalho por chat no configurador**: o comprador descreve o que quer
  em texto livre, o agente extrai filtros estruturados (`kind`,
  `category`, `region`) e sugere produtos/serviços compatíveis — o
  comprador escolhe manualmente entre as sugestões, nada é adicionado
  automaticamente ao projeto.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                  FastAPI monolito (existente)              │
│                                                              │
│  Concierge público (sub-proj. 1)                            │
│    → pré-cadastro do comprador (CompradorHandler já existe) │
│                                                              │
│  Admin (existente)                                          │
│    → aprova comprador → gera token "definir senha"          │
│      → NOVO: /admin/compradores lista aprovados + link       │
│                                                              │
│  NOVO: Vitrine pública (sem login, /vitrine/*)               │
│    ├─ /vitrine/produtos (lista + filtro, SEM preço)          │
│    └─ /vitrine/servicos (lista + filtro, SEM preço)          │
│                                                              │
│  NOVO: Área do comprador (/comprador/*)                     │
│    ├─ /comprador/definir-senha/{token}, /login, /logout      │
│    └─ /comprador/projeto                                     │
│         ├─ escolher produto (COM preço) / adicionar serviços │
│         ├─ confirmar projeto (rascunho → confirmado)         │
│         └─ atalho por chat: descreve → agente filtra          │
│                → sugere produto/serviços → comprador escolhe │
│                                                              │
│  Banco: Member (auth já genérica) + Project (novo) +          │
│         ProjectService (novo, N serviços por projeto)         │
└─────────────────────────────────────────────────────────┘
```

O núcleo do agente (`LLMProvider`, extração tolerante de JSON,
`extract_product_fields`/`extract_service_fields` como referência de
padrão) já existe dos sub-projetos anteriores — o atalho por chat do
configurador reaproveita a mesma estrutura, só que para extrair
**filtros de busca** em vez de campos de cadastro.

### Achado pré-existente que afeta este sub-projeto

`Member.region` (coluna estruturada) nunca é populada pelo fluxo de
pré-cadastro via chat — `orchestrator.py::_finalize_member` só copia
`name` de `collected_fields` para uma coluna estruturada; todo o resto
(incluindo `region`) fica só dentro do JSONB `profile_details`. Como o
filtro de região da vitrine pública precisa consultar
`Member.region` (via join com o dono do produto/serviço), este
sub-projeto inclui uma correção pontual em `_finalize_member` para
também copiar `region`, mesmo padrão de `name`. Sem essa correção, o
filtro de região nunca encontraria nada.

### Abordagens consideradas (recomendação por chat no configurador)

1. **Extração de filtros estruturados via LLM (escolhida)** — mesmo
   padrão de `product_extractor.py`/`service_extractor.py`: o texto
   livre vira um JSON de filtros (`kind`, `category`, `region`), que
   roda uma query SQL normal em `Product`/`Service`. Reaproveita 100%
   do padrão já estabelecido, sem novo subsistema.
2. **Busca semântica com embeddings (pgvector)** — usa o
   `embeddings.py` já existente (hoje só para memória do agente) para
   matching por similaridade textual. Mais flexível para descrições
   vagas, mas introduz indexação de embeddings de produto/serviço, algo
   que nada neste projeto ainda faz — escopo bem maior.

**Escolhida: Abordagem 1** — YAGNI e consistência com o padrão já
estabelecido; pode evoluir para busca semântica depois se a extração
estruturada não for suficiente.

## Componentes

### `src/piscinow/models/project.py` (novo)
- `ProjectStatus` (enum `str`): `RASCUNHO = "rascunho"`,
  `CONFIRMADO = "confirmado"`.
- `Project`: `id`, `member_id` (FK para o comprador, um projeto por
  comprador nesta fase), `product_id` (FK para `Product`, opcional até
  o comprador escolher), `status` (default `RASCUNHO`), `created_at`,
  `updated_at`.
- `ProjectService`: `id`, `project_id` (FK), `service_id` (FK para
  `Service`) — tabela de associação, N serviços por projeto.

### `src/piscinow/comprador_auth.py` (novo)
Espelha `src/piscinow/prestador_auth.py`/`loja_auth.py`:
- `login(request, db, email, password) -> bool` — e-mail normalizado
  (`.strip().lower()`) desde o início, checagem global de duplicidade
  (lição já corrigida no sub-projeto 3, herdada aqui de saída).
- `logout(request) -> None`
- `require_comprador(request, db=Depends(get_db)) -> Member` —
  redireciona (303) para `/comprador/login` se não autenticado ou se o
  `Member` da sessão não for mais `profile_type=COMPRADOR` /
  `status=APPROVED`.

### `src/piscinow/agent/project_search.py` (novo)
`extract_search_filters(llm: LLMProvider, text: str) -> dict`, sempre
retornando um dict com as chaves `kind`, `category`, `region` (cada
uma string, vazia quando ausente) — mesmo padrão tolerante de
`extract_product_fields`/`extract_service_fields`.

### Admin (extensão)
A condição de geração de token na rota `/admin/fila/{id}/aprovar`
passa a cobrir `(ProfileType.LOJA, ProfileType.PRESTADOR,
ProfileType.COMPRADOR)`. Nova rota `GET /admin/compradores`,
espelhando `/admin/lojas`/`/admin/prestadores`.

### `orchestrator.py` (correção pontual)
`_finalize_member` passa a construir o `Member` com
`region=fields.get("region") or None` além de `name`, corrigindo o
achado descrito acima.

### Rotas novas — vitrine pública (`src/piscinow/web/routes/vitrine.py`, SEM autenticação)
- `GET /vitrine/produtos` — lista `Product`s ativos, com filtros
  opcionais via query string (`kind`, `category`, `regiao` — este
  último via join com `Member.region` do dono). Template **sem**
  campo de preço.
- `GET /vitrine/servicos` — mesma estrutura, para `Service`s ativos.

### Rotas novas — área do comprador (`src/piscinow/web/routes/comprador.py`)
- `GET/POST /comprador/definir-senha/{token}` — mesmo padrão já
  estabelecido (query já filtra `profile_type`/`status` desde o
  início).
- `GET/POST /comprador/login`, `POST /comprador/logout` — rate limit
  `5/minuto` desde o primeiro commit (`comprador_login_rate_limit_string`).
- `GET /comprador/projeto` — mostra o projeto atual (cria um rascunho
  vazio se o comprador ainda não tiver nenhum).
- `POST /comprador/projeto/produto` — define/troca o produto principal
  do projeto (só se `status == RASCUNHO`; produto precisa existir e
  estar ativo).
- `POST /comprador/projeto/servicos/{service_id}/adicionar` /
  `POST /comprador/projeto/servicos/{service_id}/remover` — adiciona/
  remove um serviço do projeto (só se `status == RASCUNHO`; serviço
  precisa existir e estar ativo).
- `POST /comprador/projeto/confirmar` — valida que há um produto
  escolhido, muda `status` para `CONFIRMADO`. Depois disso, qualquer
  tentativa de alterar o projeto (produto ou serviços) é rejeitada com
  400, independente do que a UI mostrar.
- `POST /comprador/projeto/buscar` — recebe texto livre, usa
  `extract_search_filters` para extrair filtros, consulta
  `Product`/`Service` ativos compatíveis, devolve como sugestões na
  tela (nunca adiciona ao projeto automaticamente); rate limit
  reaproveitando `chat_rate_limit_string`, desde o início.

## Fluxo de dados

**Aprovação → acesso:**
1. Admin aprova o `Member` (perfil comprador) na fila → a rota chama
   `member.approve(...)` e, por ser `profile_type == COMPRADOR`, também
   chama `generate_set_password_token()` → `/admin/compradores` mostra
   o link.
2. Comprador define senha → login (mesmos padrões de segurança já
   estabelecidos nos sub-projetos 2 e 3).

**Descoberta pública:**
3. Qualquer visitante acessa `/vitrine/produtos`/`/vitrine/servicos`,
   filtra por tipo/categoria/região — vê nome, categoria, descrição,
   **sem preço**. Um link "Entrar para ver preço e montar projeto"
   leva ao login do comprador.

**Montar o projeto (logado):**
4. `/comprador/projeto` mostra o rascunho atual (cria um vazio se não
   existir) — escolher/trocar o produto principal (agora com preço),
   adicionar/remover serviços. Cada ação salva direto.
5. **Atalho por chat**: texto livre → `extract_search_filters` extrai
   `kind`/`category`/`region` → a rota busca produtos/serviços
   compatíveis e devolve como sugestões — o comprador escolhe
   manualmente entre elas.
6. **Confirmar projeto**: rascunho → confirmado (exige produto
   escolhido). Projeto confirmado fica somente-leitura; edição
   pós-confirmação é fora de escopo (sub-projeto 5 decide o que
   acontece a partir daí).

## Tratamento de erros

- **Filtros inválidos na vitrine**: simplesmente não retornam
  resultados — sem erro 400, é busca, não formulário de cadastro.
- **Token/login/posse**: mesmos padrões já estabelecidos (404 não 403,
  mensagens genéricas, filtro de perfil/status desde o primeiro
  commit, rate limit no login).
- **Escolher produto/serviço inexistente ou inativo**: 404.
- **Confirmar projeto sem produto escolhido**: validação no backend,
  reexibe com erro — nunca confirma projeto incompleto.
- **Editar projeto já confirmado**: 400 com mensagem clara — o backend
  rejeita a mudança independente do que a UI permitir clicar.
- **Atalho por chat sem nenhum resultado compatível**: aviso "não
  encontrei nada com esses filtros, tente ajustar" em vez de lista
  vazia sem explicação — mesmo espírito do aviso já usado nos
  atalhos de cadastro de loja/prestador.
- **Projeto de outro comprador**: 404 (mesma regra de posse já
  estabelecida).

## Estratégia de testes

Mesmo padrão TDD dos sub-projetos anteriores:
- **Lógica pura (sem banco)**: `extract_search_filters` testada
  isoladamente com `FakeLLMProvider` roteirizado — real GREEN, sem
  Docker.
- **Integração (precisa de `db_session`)**: fluxo completo
  definir-senha → login → escolher produto → adicionar/remover
  serviço → confirmar; isolamento entre compradores (um não vê/edita
  projeto de outro); vitrine pública acessível sem login e sem preço
  no HTML; filtro de região funcionando de ponta a ponta.
- **Teste da correção do orchestrator**: `region` chega em
  `Member.region` (coluna estruturada) depois da finalização de um
  `CompradorHandler`/`LojaHandler`/`PrestadorHandler`, não só em
  `profile_details`.
- Mesma ressalva de sempre: sem Docker nesta máquina de
  desenvolvimento, os testes que tocam banco são escritos e revisados
  com cuidado (leitura linha a linha), mas só confirmados de fato
  quando rodados num ambiente com Postgres.

## Fora de escopo nesta fase

- Pagamento, split entre loja/prestador, retenção por etapas (nasce no
  sub-projeto 5).
- Acompanhamento de obra (nasce no sub-projeto 6).
- Múltiplos projetos por comprador — criar um segundo projeto depois
  de confirmar o atual fica para depois.
- Edição de projeto após confirmação.
- Busca semântica/embeddings na vitrine ou no atalho de chat — só
  filtros estruturados exatos nesta fase.
- Envio automático de e-mail/SMS do link de definir-senha (mesmo
  padrão manual já estabelecido).
- Detalhe de item individual na vitrine (página própria por produto/
  serviço) — a listagem com filtros já mostra nome/categoria/
  descrição, suficiente por enquanto.

## Próximos passos

Este documento serve de base para o plano de implementação (skill
`writing-plans`), que vai detalhar as tarefas de TDD para: a correção
do `orchestrator.py`, o modelo `Project`/`ProjectService`, o módulo
`comprador_auth.py`, o `project_search.py`, as rotas de `/vitrine/*` e
`/comprador/*`, e a extensão da fila de admin.
