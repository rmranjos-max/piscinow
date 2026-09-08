# Clube Piscinow — Landing + Agente

## Desenvolvimento local

    pip install -e ".[dev]"
    cp .env.example .env
    pytest -v   # requer Docker rodando (testcontainers)
    uvicorn piscinow.web.app:app --reload

## Deploy (VPS, Docker Compose)

    export PISCINOW_SESSION_SECRET=$(openssl rand -hex 32)
    export PISCINOW_LLM_PROVIDER=anthropic
    export PISCINOW_ANTHROPIC_API_KEY=sk-...
    docker compose build
    docker compose up -d
    docker compose run --rm app alembic upgrade head
    docker compose run --rm app python -m piscinow.scripts.create_admin equipe@piscinow.com.br "senha-forte"

Acesse `http://<vps>:8000/` para o site e `http://<vps>:8000/admin/login` para o painel da equipe.
