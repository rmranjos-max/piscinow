# Piscinow — Cadastro de Prestadores de Serviço (Sub-projeto 3)

**Data:** 2026-09-17
**Status:** Aprovado para virar plano de implementação
**Branch:** `piscinow-landing-clube-agente` (continuação dos sub-projetos 1 e 2, ainda sem merge no `main`)

## Contexto

Este é o **sub-projeto 3** de 7 do Clube Piscinow (ver decomposição completa em
[`2026-09-06-piscinow-landing-clube-agente-design.md`](2026-09-06-piscinow-landing-clube-agente-design.md)).

Os sub-projetos 1 e 2 já entregam: landing page, Clube por
indicação/fila, um agente de atendimento que faz o pré-cadastro de
lojas **e prestadores de serviço** pelo chat (`LojaHandler` e
`PrestadorHandler` já existem), e a área da loja (`/loja/*`) com
autenticação própria e catálogo de produtos. A estrutura de
autenticação do `Member` (`password_hash`, `set_password_token`,
`generate_set_password_token`/`consume_set_password_token`/
`set_password`/`verify_password`) foi desenhada de propósito no
sub-projeto 2 para ser reaproveitada por prestadores sem mudança de
schema.

Este sub-projeto cobre o que acontece **depois** da aprovação de um
prestador: acesso ao sistema e gerenciamento do catálogo de serviços
que ele oferece (instalação, manutenção, reparo). Não inclui nenhuma
vitrine pública nem o casamento automático prestador↔comprador — isso
nasce no sub-projeto 4 (configurador), que combina produto + comprador
+ instalador.

## Requisitos levantados com o usuário

- **Gestão do catálogo de serviços**: os dois caminhos — painel web com
  formulários (cadastro/edição/desativação) **e** um atalho
  conversacional (texto livre → extração de campos → confirmação →
  salvar), reaproveitando o `service_extractor.py` (mesmo padrão do
  `product_extractor.py`).
- **Preço do serviço**: faixa (`price_min`/`price_max`, ambos
  opcionais), não um valor fixo — instalação varia por obra, diferente
  do produto da loja.
- **Tipo de serviço**: `kind` fixo (`instalacao` | `manutencao` |
  `reparo`) + `category` livre para o detalhe (ex.: "piscina de
  fibra", "aquecimento") — mesma estrutura de `kind`/`category` do
  `Product`.
- **Visibilidade do admin**: nova tela `/admin/prestadores`, mesmo
  padrão de `/admin/lojas` — lista prestadores aprovados e o link de
  definir senha.
- **Autenticação**: módulo `prestador_auth.py` espelhando
  `loja_auth.py` linha a linha (login/logout/`require_prestador`),
  filtrando por `profile_type == PRESTADOR`. Decisão explícita de
  espelhar em vez de generalizar num módulo único parametrizado por
  perfil — ver seção de abordagens.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                  FastAPI monolito (existente)              │
│                                                              │
│  Concierge público (sub-proj. 1)                            │
│    → pré-cadastro do prestador (PrestadorHandler já existe) │
│                                                              │
│  Admin (existente)                                          │
│    → aprova prestador na fila → gera token "definir senha"  │
│      → NOVO: /admin/prestadores lista aprovados + link      │
│                                                              │
│  NOVO: Área do prestador (/prestador/*)                     │
│    ├─ /prestador/definir-senha/{token}  (primeiro acesso)   │
│    ├─ /prestador/login, /prestador/logout                   │
│    └─ /prestador/servicos                                    │
│         ├─ listar / cadastrar / editar / desativar (form)    │
│         └─ atalho por chat: texto livre → extrai campos      │
│                → mostra confirmação → prestador confirma     │
│                → salva                                       │
│                                                              │
│  Banco: Member (auth já genérica, zero mudança) +             │
│         Service (novo, mesmo padrão de Product)               │
└─────────────────────────────────────────────────────────┘
```

O núcleo do agente (`LLMProvider`, extração tolerante de JSON,
`extract_product_fields` como referência de padrão) já existe dos
sub-projetos 1 e 2 — o atalho por chat do prestador reaproveita a
mesma estrutura, só com os campos de serviço.

### Abordagens consideradas (módulo de autenticação do prestador)

1. **Espelhar `loja_auth.py` (escolhida)** — criar `prestador_auth.py`
   quase idêntico, só trocando o filtro de `ProfileType.LOJA` para
   `ProfileType.PRESTADOR`. Consistente com o padrão já usado duas
   vezes no projeto (`auth.py` → `loja_auth.py`); o schema do `Member`
   já é genérico, sem mudança de banco necessária. Duplica ~30 linhas
   de código simples, mas mantém cada módulo pequeno e independente.
2. **Generalizar num único módulo parametrizado por `ProfileType`** —
   uma função `require_member_with_profile(profile_type)` reaproveitada
   por admin/loja/prestador. Remove a duplicação, mas introduz uma
   abstração nova agora, para um caso que só se repete 2 vezes.

**Escolhida: Abordagem 1** — YAGNI e consistência com o padrão já
estabelecido no projeto.

## Componentes

### `src/piscinow/models/service.py` (novo)
Mesmo padrão de `Product`:
- `ServiceKind` (enum `str`): `INSTALACAO = "instalacao"`,
  `MANUTENCAO = "manutencao"`, `REPARO = "reparo"`.
- `Service`: `id`, `member_id` (FK para o prestador), `kind`,
  `category` (texto livre, ex.: vinil/fibra/alvenaria/aquecimento),
  `name`, `description` (opcional), `price_min` (opcional, numérico),
  `price_max` (opcional, numérico), `active` (bool, default `True`),
  `created_at`, `updated_at`.

### `src/piscinow/prestador_auth.py` (novo)
Espelha `src/piscinow/loja_auth.py`:
- `login(request, db, email, password) -> bool` — mesma normalização
  de e-mail (`.strip().lower()`) já corrigida no sub-projeto 2, desde
  o início aqui.
- `logout(request) -> None`
- `require_prestador(request, db=Depends(get_db)) -> Member` —
  dependência FastAPI, redireciona (303) pra `/prestador/login` se não
  autenticado ou se o `Member` da sessão não for mais
  `profile_type=PRESTADOR` / `status=APPROVED`.

### `src/piscinow/agent/service_extractor.py` (novo)
Espelha `src/piscinow/agent/product_extractor.py`:
`extract_service_fields(llm: LLMProvider, text: str) -> dict`, sempre
retornando um dict com as chaves `kind`, `category`, `name`,
`price_min`, `price_max`, `description` (cada uma string, vazia
quando ausente), para alimentar o `prefill` do template.

### Admin (extensão da fila)
A rota `/admin/fila/{id}/aprovar` passa a checar também
`profile_type == ProfileType.PRESTADOR` (além do já existente
`LOJA`) para gerar o token de definir-senha. Nova rota `GET
/admin/prestadores`, espelhando `/admin/lojas`: lista `Member`s com
`profile_type=PRESTADOR AND status=APPROVED`, mostrando o link
`/prestador/definir-senha/{token}` para quem ainda não definiu senha.

### Rotas novas (`src/piscinow/web/routes/prestador.py`)
- `GET/POST /prestador/definir-senha/{token}` — primeiro acesso,
  define senha. A query de busca do token já filtra
  `profile_type == PRESTADOR` e `status == APPROVED` desde o início
  (lição do fix wave do sub-projeto 2, aplicada de saída aqui, não
  como correção posterior).
- `GET/POST /prestador/login` — com rate limit `5/minuto`
  (`prestador_login_rate_limit_string`, mesmo padrão de
  `loja_login_rate_limit_string`), `POST /prestador/logout`.
- `GET /prestador/servicos` — lista os serviços **daquele prestador**
  (filtro por `member_id`) + formulário de cadastro.
- `POST /prestador/servicos` — cria serviço.
- `POST /prestador/servicos/{id}/editar` — edita (só se `member_id`
  bate com o prestador logado; senão 404).
- `POST /prestador/servicos/{id}/desativar` — marca `active=False`
  (mesma regra de posse).
- `POST /prestador/servicos/chat` — recebe texto livre, usa
  `extract_service_fields` para extrair campos, **nunca salva
  direto** — devolve os campos para pré-preencher o formulário; rate
  limit reaproveitando `chat_rate_limit_string` (mesmo limite do chat
  público), aplicado desde o início.

Validação de formulário (`_validate_service_form`, compartilhada entre
criar e editar desde o início, sem duplicação a corrigir depois):
`kind` válido, `category`/`name` não vazios e dentro do tamanho da
coluna, `price_min`/`price_max` finitos (rejeita `Infinity`/`NaN`),
dentro do teto de `Numeric(10,2)`, e quando ambos vierem preenchidos,
`price_min <= price_max`.

## Fluxo de dados

**Aprovação → acesso:**
1. Admin aprova o `Member` (perfil prestador) na fila → a rota chama
   `member.approve(...)` e, por ser `profile_type == PRESTADOR`,
   também chama `generate_set_password_token()` → `/admin/prestadores`
   mostra o link `/prestador/definir-senha/{token}`.
2. Prestador abre o link → `consume_set_password_token` valida (existe,
   não expirou, não foi usado) **e** a query já filtra
   `profile_type == PRESTADOR AND status == APPROVED` → formulário de
   senha.
3. Ao definir a senha, o token é invalidado (uso único) e o prestador é
   redirecionado para `/prestador/login`.

**Gestão do catálogo de serviços:**
4. Login (com rate limit) → sessão nos mesmos moldes da loja;
   `require_prestador` protege todas as rotas de `/prestador/servicos`.
5. `/prestador/servicos` lista só os serviços daquele prestador
   (filtro por `member_id`), com formulário de cadastro/edição inline.
6. **Atalho por chat**: o prestador escreve algo como "instalação de
   piscina de fibra, de 3 a 8 mil, prazo 2 semanas" →
   `/prestador/servicos/chat` extrai os campos → devolve **pré-
   preenchidos no formulário**, nunca salva direto — o prestador revisa
   e confirma antes de gravar.
7. Editar/desativar seguem o mesmo padrão de posse (404, não 403) já
   validado no sub-projeto 2.

**Consumo futuro (fora de escopo aqui):** o sub-projeto 4
(configurador) vai poder listar serviços ativos por `kind`/`category`/
região do prestador para casar com o projeto do comprador — este
sub-projeto só deixa o catálogo pronto para ser consultado depois,
sem construir esse casamento agora.

## Tratamento de erros

- **Token de definir-senha inválido/expirado/já usado/perfil ou status
  errado**: mensagem genérica ("link inválido ou expirado, peça um
  novo à equipe") — não revela se o token chegou a existir. A query já
  nasce filtrando `profile_type`/`status`, sem depender de uma
  correção posterior.
- **Login com credenciais erradas**: mensagem genérica; rate limit de
  `5/minuto` aplicado desde a implementação inicial da rota, não como
  fix wave.
- **Acesso a `/prestador/servicos` sem sessão**: `require_prestador`
  redireciona para o login, igual `require_loja`.
- **Prestador tentando editar/desativar serviço de outro prestador**:
  retorna 404 (não 403).
- **Atalho por chat com resposta malformada do LLM**: reaproveita o
  parser tolerante já existente — se não conseguir extrair, volta um
  formulário vazio com aviso ("não consegui entender, preencha
  manualmente") em vez de quebrar; rate limit aplicado desde o início.
- **Formulário de serviço com campo obrigatório faltando, preço
  inválido/não-finito/acima do teto, `price_min > price_max`, ou texto
  acima do tamanho da coluna**: validação no backend via
  `_validate_service_form` (função única, compartilhada entre criar e
  editar desde a primeira versão), reexibe o formulário com o erro —
  nunca salva serviço incompleto ou inconsistente.
- **E-mail no definir-senha**: normalizado (`.strip().lower()`) e a
  coluna `Member.email` já é `unique=True` (herdado do sub-projeto 2)
  — checagem de duplicidade já nasce correta.

## Estratégia de testes

Mesmo padrão TDD dos sub-projetos 1 e 2:
- **Lógica pura (sem banco)**: `extract_service_fields` testada
  isoladamente com `FakeLLMProvider` roteirizado — real GREEN, sem
  Docker, mesmo padrão de `test_product_extractor.py`.
- **Integração (precisa de `db_session`)**: fluxo completo
  definir-senha → login → CRUD de serviço; isolamento entre
  prestadores (um não vê/edita serviço de outro); rate limit em
  `/prestador/login` e `/prestador/servicos/chat`.
- **Rate limiter em testes**: `tests/web/conftest.py` já reseta o
  `limiter` (slowapi) a cada teste, corrigido no sub-projeto 2 — os
  testes novos deste sub-projeto já nascem livres do bug de vazamento
  de contador entre testes que foi descoberto e corrigido lá.
- Mesma ressalva dos sub-projetos anteriores: sem Docker disponível
  nesta máquina de desenvolvimento, os testes que tocam banco são
  escritos e revisados com cuidado (leitura linha a linha), mas só
  confirmados de fato quando rodados num ambiente com Postgres.

## Fora de escopo nesta fase

- Vitrine pública de serviços e o casamento automático
  prestador↔comprador↔projeto (nasce no sub-projeto 4).
- Envio automático de e-mail/SMS do link de definir-senha (o admin
  compartilha manualmente, mesmo padrão da loja).
- Agenda/disponibilidade do prestador (fora do escopo levantado com o
  usuário — só perfil e catálogo de serviços por enquanto).
- Múltiplos usuários por prestador (uma credencial por `Member`).
- Generalizar o módulo de autenticação num único módulo parametrizado
  por perfil — decisão explícita de continuar espelhando
  (`auth.py`/`loja_auth.py`/`prestador_auth.py`) em vez de introduzir
  essa abstração agora.

## Próximos passos

Este documento serve de base para o plano de implementação (skill
`writing-plans`), que vai detalhar as tarefas de TDD para: criar o
modelo `Service`, o módulo `prestador_auth.py`, o
`service_extractor.py`, as rotas de `/prestador/*`, a extensão da fila
de admin, e a nova tela `/admin/prestadores`.
