# Clube Piscinow — Landing + Agente

## Desenvolvimento local

    pip install -e ".[dev]"
    cp .env.example .env
    pytest -v   # requer Docker rodando (testcontainers)
    uvicorn piscinow.web.app:app --reload

Sem Docker na maquina, a CI (GitHub Actions) roda a suite completa contra Postgres real a cada push.

## Deploy (VPS, Docker Compose)

O compose sobe tres servicos: `db` (Postgres + pgvector), `app` (FastAPI, sem porta publicada) e
`proxy` (Caddy, unico servico exposto, nas portas 80 e 443, com HTTPS automatico).

Antes do primeiro deploy, aponte o DNS do dominio para a VPS e crie um `.env` ao lado do `docker-compose.yml`:

    POSTGRES_PASSWORD=<openssl rand -hex 24>
    PISCINOW_SESSION_SECRET=<openssl rand -hex 32>
    PISCINOW_DOMAIN=clube.exemplo.com.br
    PISCINOW_PUBLIC_BASE_URL=https://clube.exemplo.com.br
    PISCINOW_LLM_PROVIDER=anthropic
    PISCINOW_ANTHROPIC_API_KEY=sk-...

`POSTGRES_PASSWORD` entra numa URL, entao use apenas letras e numeros (o `openssl rand -hex` serve).

    docker compose build
    docker compose up -d db
    docker compose run --rm app alembic upgrade head
    docker compose up -d
    docker compose run --rm app python -m piscinow.scripts.create_admin equipe@piscinow.com.br "senha-forte"

Site em `https://<dominio>/` e painel da equipe em `https://<dominio>/admin/login`.
Deploys seguintes: `docker compose build && docker compose run --rm app alembic upgrade head && docker compose up -d`.

### Producao e pagamentos

`PISCINOW_ENVIRONMENT` e `production` por padrao no compose. Nesse modo o app recusa subir com o
segredo de sessao padrao, o cookie de sessao so trafega por HTTPS e, enquanto o provedor de pagamento
for uma simulacao, "Pagar" e "Liberar fase" ficam desligados (503). Para demonstracoes controladas,
`PISCINOW_ALLOW_PAYMENT_SIMULATION=true` religa a simulacao, e o app registra um erro no log a cada subida.
Nenhuma cobranca real existe nesta versao.

### Saude, logs e acesso ao banco

- `GET /healthz`: o processo esta de pe. `GET /readyz`: o banco responde (503 se nao).
- O container tem `HEALTHCHECK` e roda sem root. Ver: `docker compose ps`.
- Logs: `docker compose logs -f app proxy`. O nivel vem de `PISCINOW_LOG_LEVEL` (padrao `INFO`).
  O log de acesso fica no proxy, que troca o token de `/definir-senha/<token>` por `[redigido]` (na URL e no
  `Referer`); o uvicorn roda com `--no-access-log` justamente para nao imprimir esse token. As paginas de
  definir senha saem com `Referrer-Policy: no-referrer` e `Cache-Control: no-store`.
- Postgres (porta nao exposta ao host): `docker compose exec db psql -U piscinow`.

### Backup e restauracao

    bash scripts/backup.sh                                   # gera backups/piscinow-<data>.sql.gz (guarda 14 dias, so o dono le)
    bash scripts/restore-check.sh backups/piscinow-XXXX.sql.gz   # prova que o backup restaura, num banco descartavel

Agende o backup no cron do host (por exemplo, todo dia as 03:00) e **copie a pasta `backups/` para fora
da VPS**: um backup no mesmo disco nao protege contra a perda da maquina. Rode o `restore-check` depois
de cada mudanca de schema e ao menos uma vez por mes. Para restaurar de verdade, pare o app, recrie o
banco e carregue o arquivo: `gunzip -c arquivo.sql.gz | docker compose exec -T db psql -U piscinow -d piscinow`.

### Recuperar o acesso de alguem

Nao ha envio de e-mail, entao a recuperacao e mediada pela equipe: confirme a identidade da pessoa por fora
(telefone, WhatsApp), abra a lista dela no painel (`/admin/lojas`, `/admin/prestadores` ou `/admin/compradores`),
clique em **Gerar link de nova senha** e envie o link que aparece. O link vale 24 horas, serve uma vez, e a senha
antiga continua valendo ate a pessoa definir a nova. Cada geracao fica no log com o e-mail do admin e o membro.

Se o proprio admin esquecer a senha (o mesmo comando cria um admin novo ou troca a senha de um existente), rode no servidor:
`docker compose run --rm app python -m piscinow.scripts.create_admin <email> "<nova-senha>"`.
