# Piscinow — Cadastro de Fornecedores + Catálogo (Sub-projeto 2)

**Data:** 2026-09-13
**Status:** Aprovado para virar plano de implementação
**Branch:** `piscinow-landing-clube-agente` (continuação do sub-projeto 1, ainda sem merge no `main`)

## Contexto

Este é o **sub-projeto 2** de 7 do Clube Piscinow (ver decomposição completa em
[`2026-09-06-piscinow-landing-clube-agente-design.md`](2026-09-06-piscinow-landing-clube-agente-design.md)).

O sub-projeto 1 já entrega: landing page, Clube por indicação/fila, e um
agente de atendimento (`ConversationHandler`s) que faz o **pré-cadastro**
de uma loja pelo chat — coleta nome, CNPJ, região e categorias, e a
registra como `Member(profile_type=LOJA, status=WAITLISTED)` na fila de
aprovação do admin.

Este sub-projeto cobre o que acontece **depois** da aprovação: a loja
precisa de um jeito de acessar o sistema e gerenciar o catálogo de
produtos que vai vender (piscinas e equipamentos). Não inclui nenhuma
vitrine pública — isso nasce no sub-projeto 4 (configurador), que combina
produto + comprador + instalador.

## Requisitos levantados com o usuário

- **Gestão do catálogo**: os dois caminhos — painel web com formulários
  (cadastro/edição/desativação normal) **e** um atalho conversacional
  (texto livre → extração de campos → confirmação → salvar), reaproveitando
  o núcleo de agente já existente.
- **Sem vitrine pública nesta fase** — só gestão interna da loja.
- **Acesso da loja**: ao ser aprovada pelo admin, gera-se um link de
  "definir senha" (token de uso único, com expiração) — a loja não recebe
  senha provisória, define a própria. Sem infraestrutura de envio de
  e-mail nesta fase; o admin copia o link e envia pelo canal que preferir.
- **Autenticação**: capacidade de login embutida diretamente no `Member`
  (não uma tabela de credencial separada, nem reaproveitar `AdminUser`) —
  desenhada de forma genérica o bastante para ser reutilizada por
  prestadores de serviço no sub-projeto 3, mas ligada só a
  `profile_type=LOJA` por enquanto.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                  FastAPI monolito (existente)              │
│                                                              │
│  Concierge público (sub-proj. 1)                            │
│    → pré-cadastro da loja (LojaHandler já existe)           │
│                                                              │
│  Admin (existente)                                          │
│    → aprova loja na fila → gera token "definir senha"       │
│      → exibe link pro admin copiar/enviar (sem e-mail ainda)│
│                                                              │
│  NOVO: Área da loja (/loja/*)                                │
│    ├─ /loja/definir-senha/{token}  (primeiro acesso)         │
│    ├─ /loja/login, /loja/logout    (mesmo padrão do admin)   │
│    └─ /loja/produtos                                         │
│         ├─ listar / cadastrar / editar / desativar (form)    │
│         └─ atalho por chat: texto livre → extrai campos      │
│                → mostra confirmação → loja confirma → salva  │
│                                                              │
│  Banco: Member (ganha password_hash + token) + Product (novo)│
└─────────────────────────────────────────────────────────┘
```

O núcleo do agente (`LLMProvider`, extração tolerante de JSON) já existe
do sub-projeto 1 — o atalho por chat reaproveita o mesmo padrão de
"extrair JSON de texto livre" que o `ConversationHandler.extract_fields`
já usa, só que para campos de produto em vez de campos de cadastro.

### Abordagens consideradas (autenticação da loja)

1. **Login embutido no `Member` (escolhida)** — adiciona `password_hash` e
   um token de "definir senha" direto na tabela `Member`, só usado quando
   `profile_type=LOJA` e `status=APPROVED`. Reaproveita a identidade que
   já existe do pré-cadastro, sem duplicar em outra tabela.
2. **Tabela de credencial separada (`StoreCredential`)** — 1:1 com
   `Member`, mantendo `Member` "limpo" como só dados de perfil. Mais uma
   tabela e um join a mais em todo lugar que precisa checar login, para um
   ganho de separação que não parece crítico aqui.
3. **Reaproveitar `AdminUser` com um campo de "papel"** — generaliza a
   tabela de admin pra qualquer tipo de conta. Mistura conceitos
   diferentes (equipe interna vs. parceiro externo) numa tabela só —
   arriscado misturar permissões no futuro.

**Escolhida: Abordagem 1** — mais simples, segue o mesmo padrão de auth
(argon2, sessão) já estabelecido para `AdminUser`, só que aplicado ao
`Member`.

## Componentes

### `Member` (estendido)
Novos campos: `password_hash` (nulo até a loja definir), `set_password_token`,
`set_password_token_expires_at`. Novos métodos:
- `set_password(senha: str) -> None` — hash via argon2 (mesmo padrão de
  `AdminUser`), limpa o token.
- `verify_password(senha: str) -> bool` — trata `password_hash` nulo sem
  quebrar (retorna `False`).
- `generate_set_password_token() -> str` — gera token de uso único com
  validade de 7 dias.
- `consume_set_password_token(token: str) -> bool` — valida (existe, não
  expirou, bate com o `Member`), retorna se é válido; não invalida sozinho
  (isso acontece em `set_password`).

### `src/piscinow/loja_auth.py` (novo)
Espelha `src/piscinow/auth.py`:
- `login(request, db, email, password) -> bool`
- `logout(request) -> None`
- `require_loja(request, db=Depends(get_db)) -> Member` — dependência
  FastAPI, redireciona (303) pra `/loja/login` se não autenticado ou se o
  `Member` da sessão não for mais `profile_type=LOJA` / `status=APPROVED`.

### Admin (extensão da fila — Task 24 do sub-projeto 1)
A decisão de gerar o token fica na **rota** `/admin/fila/{id}/aprovar`
(não dentro de `Member.approve()`, que continua um método genérico de
transição de status, usado também no auto-approve de embaixador via
indicação): depois de chamar `member.approve(...)`, a rota checa
`if member.profile_type == ProfileType.LOJA:` e só então chama
`member.generate_set_password_token()`. A tela da fila passa a mostrar o
link `/loja/definir-senha/{token}` ao lado do membro recém-aprovado, para
o time copiar e enviar pelo canal que preferir.

### Rotas novas (`src/piscinow/web/routes/loja.py`)
- `GET/POST /loja/definir-senha/{token}` — primeiro acesso, define senha.
- `GET/POST /loja/login`, `POST /loja/logout`.
- `GET /loja/produtos` — lista os produtos **daquela loja** (filtro por
  `member_id`) + formulário de cadastro.
- `POST /loja/produtos` — cria produto.
- `POST /loja/produtos/{id}/editar` — edita (só se `member_id` bate com a
  loja logada; senão 404).
- `POST /loja/produtos/{id}/desativar` — marca `active=False` (mesma
  regra de posse).
- `POST /loja/produtos/chat` — recebe texto livre, usa o `LLMProvider`
  para extrair campos de produto (kind, category, name, price,
  size_label), **nunca salva direto** — devolve os campos para
  pré-preencher o formulário; a loja confirma/ajusta antes de gravar.

### Modelo novo: `Product`
`id`, `member_id` (FK para a loja), `kind` (`piscina` | `equipamento`),
`category` (ex.: vinil/fibra/alvenaria para piscinas; filtragem/
aquecimento/automação para equipamentos), `name`, `description`
(opcional), `price` (numérico), `size_label` (opcional, ex.: "6x3m"),
`active` (bool, default `True`), `created_at`, `updated_at`.

## Fluxo de dados

**Aprovação → acesso:**
1. Admin aprova o `Member` (perfil loja) na fila → a rota chama
   `member.approve(...)` e, por ser `profile_type == LOJA`, também chama
   `generate_set_password_token()` → a tela da fila mostra o link
   `/loja/definir-senha/{token}`.
2. Loja abre o link → `consume_set_password_token` valida (existe, não
   expirou, não foi usado, `Member` é loja aprovada) → formulário de
   senha.
3. Ao definir a senha (`set_password`), o token é invalidado (uso único)
   e a loja é redirecionada para `/loja/login`.

**Gestão do catálogo:**
4. Login → sessão nos mesmos moldes do admin; `require_loja` protege
   todas as rotas de `/loja/produtos`.
5. `/loja/produtos` lista só os produtos daquela loja (filtro por
   `member_id`), com formulário de cadastro/edição inline.
6. **Atalho por chat**: a loja escreve algo como "piscina de fibra 6x3,
   R$18 mil" → `/loja/produtos/chat` extrai os campos (mesmo padrão de
   extração tolerante de JSON já usado no Agent Core) → devolve os campos
   **pré-preenchidos no formulário**, nunca salva direto — a loja revisa
   e confirma antes de gravar. Isso evita que uma extração errada do LLM
   vire produto publicado sem revisão.
7. Editar/desativar seguem o mesmo padrão de formulário-por-linha que a
   fila de admissão já usa (aprovar/recusar).

## Tratamento de erros

- **Token de definir-senha inválido/expirado/já usado**: mensagem
  genérica ("link inválido ou expirado, peça um novo à equipe") — não
  revela se o token chegou a existir, evitando enumeração.
- **Login com credenciais erradas**: mensagem genérica (não diz se foi
  e-mail ou senha); `verify_password` trata `password_hash` nulo (loja
  aprovada que ainda não definiu senha) sem quebrar, só retorna falso.
- **Acesso a `/loja/produtos` sem sessão**: `require_loja` redireciona
  para o login, igual `require_admin` já faz.
- **Loja tentando editar/desativar produto de outra loja**: retorna 404
  (não 403) — não revela que o produto existe.
- **Atalho por chat com resposta malformada do LLM**: reaproveita o
  parser tolerante já existente no Agent Core — se não conseguir extrair,
  volta um formulário vazio com aviso ("não consegui entender, preencha
  manualmente") em vez de quebrar.
- **Formulário de produto com campo obrigatório faltando ou preço
  inválido**: validação no backend, reexibe o formulário com o erro —
  nunca salva produto incompleto.

## Estratégia de testes

Mesmo padrão TDD do sub-projeto 1:
- **Lógica pura (sem banco)**: `set_password`/`verify_password`/geração e
  expiração do token no `Member` — testes unitários diretos, como os que
  já existem para `submit_for_review`/`approve`.
- **Extração via chat**: testa a função de extração de produto isolada
  com `FakeLLMProvider` roteirizado (mesmo padrão de
  `ConversationHandler.extract_fields`), sem precisar de banco.
- **Integração (precisa de `db_session`)**: fluxo completo
  definir-senha → login → CRUD de produto; e um teste específico
  garantindo que uma loja **não vê nem edita** produtos de outra loja
  (isolamento por `member_id`).
- Mesma ressalva do sub-projeto 1: sem Docker disponível nesta máquina de
  desenvolvimento, os testes que tocam banco são escritos e revisados com
  cuidado (leitura linha a linha, mesmo processo rigoroso), mas só
  confirmados de fato quando rodados num ambiente com Postgres.

## Fora de escopo nesta fase

- Vitrine pública de produtos (nasce no sub-projeto 4).
- Envio automático de e-mail/SMS do link de definir-senha (o admin
  compartilha manualmente por enquanto).
- Login de prestadores de serviço (sub-projeto 3) — mas a estrutura de
  auth em `Member` é desenhada para ser reaproveitada lá sem retrabalho.
- Múltiplos usuários por loja (por enquanto, uma credencial por
  `Member`/CNPJ).

## Próximos passos

Este documento serve de base para o plano de implementação (skill
`writing-plans`), que vai detalhar as tarefas de TDD para: estender
`Member` com autenticação, criar o modelo `Product`, o módulo
`loja_auth.py`, as rotas de `/loja/*`, a extensão da fila de admin, e o
atalho de extração de produto via chat.
