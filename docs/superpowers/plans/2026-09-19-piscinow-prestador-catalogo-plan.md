# Prestador Onboarding + Catálogo de Serviços — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an approved prestador (service provider/installer) set her own password, log in, and manage a catalog of services (instalação/manutenção/reparo) with a price range, through plain web forms and a chat shortcut that extracts fields from free text — never auto-saving.

**Architecture:** Reuses the `Member` authentication capability added in sub-project 2 (password + one-time set-password token — already generic, no schema change needed here), adds a new `Service` model, a `prestador_auth` module mirroring the existing `loja_auth.py` pattern exactly, and a `/prestador/*` route group in the same FastAPI monolith. The chat shortcut reuses the Agent Core's `LLMProvider` and the shared tolerant-JSON parser (`parse_json_object`, sub-project 2 Task 1). Every security/validation lesson learned in sub-project 2's final-review fix waves (rate limiting on login and on the chat shortcut, profile/status filtering on the set-password-token lookup, shared form validation with length/finiteness/range limits, normalized+unique email) is built into this plan from the first task, not discovered later.

**Tech Stack:** Same as sub-projects 1 and 2 — Python 3.12, FastAPI, SQLAlchemy 2.0, Postgres 16 + pgvector, Jinja2, argon2-cffi, slowapi.

**Spec:** [docs/superpowers/specs/2026-09-17-piscinow-prestador-catalogo-design.md](../specs/2026-09-17-piscinow-prestador-catalogo-design.md)

## Global Constraints

- Reuses the existing Postgres+pgvector datastore — no new datastore, no new infra, no new columns on `Member` (sub-project 2 already made its auth fields profile-agnostic).
- Prestador authentication mirrors `loja_auth.py` exactly: argon2 password hashing (via `Member.verify_password`, already implemented), session-based login (`request.session`), a `require_prestador` FastAPI dependency that raises `HTTPException(303, headers={"Location": "/prestador/login"})` when unauthenticated or when the session's member is no longer `profile_type=PRESTADOR`/`status=APPROVED`.
- The set-password-token lookup query filters `profile_type == PRESTADOR` and `status == APPROVED` directly in the `select(...)`, from the first version of the route — do not write the unfiltered query and fix it later.
- `POST /prestador/login` is rate-limited (`5/minute`) from its first commit. `POST /prestador/servicos/chat` is rate-limited (reusing `chat_rate_limit_string`) from its first commit.
- Product/service form validation lives in one shared function used by both the create and the edit route from the first commit — never write the validation twice and deduplicate later.
- Email is normalized with `.strip().lower()` at every point it's read from a form, matching `Member.email`'s existing `unique=True` constraint (added in sub-project 2).
- No email-sending infrastructure in this phase — the admin panel displays the set-password link for the team to copy and send manually.
- No public storefront or automatic prestador↔comprador matching in this sub-project — `/prestador/*` routes are all behind `require_prestador`. The matching logic is sub-project 4.
- All user-facing text (templates, error messages) is Portuguese (pt-BR). Templates use HTML entities (`&aacute;`, `&atilde;`, `&ccedil;`, etc.) for accented characters, matching the existing admin/loja templates. Python string literals (error messages) follow the existing project convention of unaccented ASCII (consistent with `auth.py`, `loja.py`, `orchestrator.py` — a deliberate final-review decision in sub-project 2, not an oversight).
- TDD throughout: write the failing test before the implementation, every task.
- Same environment constraint as sub-projects 1 and 2: no Docker/Postgres on this development machine. Tests that don't need `db_session` must show real RED→GREEN with `py -m pytest` (using the Python Launcher — bare `python`/`python3` are broken on this machine). Tests that do need `db_session` are written and reviewed carefully but will fail at fixture setup with a Docker connection error here; that failure mode is expected and does not block a task.
- Ownership checks on prestador-scoped resources return 404 (not 403) for a resource that exists but isn't owned by the logged-in prestador — never reveal that it exists.
- Never modify `tests/conftest.py` beyond adding the one new model-import line this plan specifies (Task 1) — do not create alternate fixtures that mock the database. Never modify `tests/conftest.py` for any other reason in this plan.
- `tests/web/conftest.py`'s `client` fixture already calls `limiter.reset()` before each test (fixed in sub-project 2) — no change needed there.

---

### Task 1: `Service` model

**Files:**
- Create: `src/piscinow/models/service.py`
- Modify: `tests/conftest.py` (add the new model import)
- Test: `tests/models/test_service.py`

**Interfaces:**
- Consumes: `piscinow.db.Base`, `piscinow.models.member.Member` (for the `member_id` foreign key).
- Produces: `piscinow.models.service.ServiceKind` (str enum: `INSTALACAO`, `MANUTENCAO`, `REPARO`), `piscinow.models.service.Service` (fields: `id`, `member_id`, `kind`, `category: str`, `name: str`, `description: str | None`, `price_min`, `price_max`, `active: bool`, `created_at`, `updated_at`). Consumed by Tasks 3, 6, 7, 8, 10.

- [ ] **Step 1: Write the failing test — `tests/models/test_service.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.models.service import Service, ServiceKind


def test_service_persists_and_reloads(db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()

    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="piscina de fibra",
        name="Instalacao completa",
        price_min=3000.00,
        price_max=8000.00,
    )
    db_session.add(service)
    db_session.flush()
    db_session.expunge(service)

    reloaded = db_session.get(Service, service.id)

    assert reloaded.name == "Instalacao completa"
    assert reloaded.category == "piscina de fibra"
    assert reloaded.active is True
    assert reloaded.member_id == prestador.id
    assert reloaded.price_min == 3000
    assert reloaded.price_max == 8000


def test_service_allows_null_price_range(db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()

    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.MANUTENCAO,
        category="filtragem",
        name="Manutencao mensal",
    )
    db_session.add(service)
    db_session.flush()
    db_session.expunge(service)

    reloaded = db_session.get(Service, service.id)

    assert reloaded.price_min is None
    assert reloaded.price_max is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/models/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.service'`

- [ ] **Step 3: Write `src/piscinow/models/service.py`**

```python
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


class ServiceKind(str, enum.Enum):
    INSTALACAO = "instalacao"
    MANUTENCAO = "manutencao"
    REPARO = "reparo"


class Service(Base):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    kind: Mapped[ServiceKind] = mapped_column(SAEnum(ServiceKind, name="service_kind"))
    category: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_min: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Add the model import to `tests/conftest.py`**

Add `import piscinow.models.service  # noqa: E402,F401` alongside the other `import piscinow.models...` lines (member, conversation, memory, admin, product) so `Base.metadata.create_all` in the `engine` fixture picks up the new `services` table. This is the ONLY change this plan makes to `tests/conftest.py` — do not touch anything else in that file, in this task or any later one.

- [ ] **Step 5: Run test to verify it passes**

Run: `py -m pytest tests/models/test_service.py -v`
Expected: written per spec; both tests need `db_session` (Postgres) — on this machine they fail at fixture setup with a Docker connection error, not a logic error. Confirm the failure is fixture-level (e.g. `docker.errors.DockerException`), not a collection/import error (`py -m pytest tests/models/test_service.py --collect-only -q` should show both tests collected with zero errors).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/models/service.py tests/models/test_service.py tests/conftest.py
git commit -m "feat: Service model"
```

---

### Task 2: `prestador_auth` module

**Files:**
- Create: `src/piscinow/prestador_auth.py`
- Test: `tests/test_prestador_auth.py`

**Interfaces:**
- Consumes: `Member`, `MemberStatus`, `ProfileType` (existing), `get_db` (existing).
- Produces: `piscinow.prestador_auth.PRESTADOR_SESSION_KEY: str`, `login(request, db, email, password) -> bool`, `logout(request) -> None`, `require_prestador(request, db=Depends(get_db)) -> Member`. Consumed by every `/prestador/*` route (Tasks 4-8, 10).

This mirrors `src/piscinow/loja_auth.py` exactly, but scoped to `Member` rows with `profile_type=PRESTADOR` and `status=APPROVED` instead of `LOJA`, and with the email normalization (`.strip().lower()`) that sub-project 2's final review added to `loja_auth.login` built in from the start.

- [ ] **Step 1: Write the failing tests — `tests/test_prestador_auth.py`**

```python
from piscinow.prestador_auth import PRESTADOR_SESSION_KEY, login, logout


class _FakeSession(dict):
    pass


class _FakeRequest:
    def __init__(self):
        self.session = _FakeSession()


def test_login_sets_session_key_on_success(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "prestador@example.com", "senha-forte-123")

    assert result is True
    assert request.session[PRESTADOR_SESSION_KEY] == str(member.id)


def test_login_normalizes_email_case_and_whitespace(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "  Prestador@Example.com  ", "senha-forte-123")

    assert result is True


def test_login_fails_for_wrong_password(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "prestador@example.com", "errada")

    assert result is False
    assert PRESTADOR_SESSION_KEY not in request.session


def test_login_fails_for_non_prestador_profile(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "loja@example.com", "senha-forte-123")

    assert result is False
    assert PRESTADOR_SESSION_KEY not in request.session


def test_logout_removes_session_key():
    request = _FakeRequest()
    request.session[PRESTADOR_SESSION_KEY] = "some-id"
    logout(request)
    assert PRESTADOR_SESSION_KEY not in request.session
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_prestador_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.prestador_auth'`

- [ ] **Step 3: Write `src/piscinow/prestador_auth.py`**

```python
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

PRESTADOR_SESSION_KEY = "prestador_member_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    member = db.scalar(
        select(Member).where(
            Member.email == email.strip().lower(),
            Member.profile_type == ProfileType.PRESTADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.verify_password(password):
        return False
    request.session[PRESTADOR_SESSION_KEY] = str(member.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(PRESTADOR_SESSION_KEY, None)


def require_prestador(request: Request, db: Session = Depends(get_db)) -> Member:
    member_id = request.session.get(PRESTADOR_SESSION_KEY)
    if not member_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/prestador/login"})
    member = db.get(Member, member_id)
    if member is None or member.profile_type != ProfileType.PRESTADOR or member.status != MemberStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/prestador/login"})
    return member
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_prestador_auth.py -v`
Expected: written per spec; all 5 tests need `db_session` (Postgres) — on this machine they fail at fixture setup with a Docker connection error. Confirm it's fixture-level, not a collection/import error (`py -m pytest tests/test_prestador_auth.py --collect-only -q` should show 5 tests collected with no error).

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/prestador_auth.py tests/test_prestador_auth.py
git commit -m "feat: prestador_auth module mirroring the loja auth pattern"
```

---

### Task 3: Admin extension — set-password token for prestadores + `/admin/prestadores` view

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_prestadores.html`
- Modify: `src/piscinow/web/templates/admin_queue.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_corrections.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_lojas.html` (nav link)
- Test: `tests/web/test_admin_prestadores.py`

**Interfaces:**
- Consumes: `Member.generate_set_password_token` (existing), `get_settings().public_base_url` (existing).
- Produces: `GET /admin/prestadores` (lists approved prestadores with their set-password link when still pending).

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_prestadores.py`**

```python
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_aprovar_prestador_generates_set_password_token(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    client.post(f"/admin/fila/{member.id}/aprovar")

    db_session.refresh(member)
    assert member.set_password_token is not None


def test_aprovar_loja_still_generates_set_password_token(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    client.post(f"/admin/fila/{member.id}/aprovar")

    db_session.refresh(member)
    assert member.set_password_token is not None


def test_aprovar_comprador_does_not_generate_token(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    client.post(f"/admin/fila/{member.id}/aprovar")

    db_session.refresh(member)
    assert member.set_password_token is None


def test_prestadores_page_shows_set_password_link_when_pending(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get("/admin/prestadores")

    assert "Instalacoes Sul" in response.text
    assert f"/prestador/definir-senha/{token}" in response.text


def test_prestadores_page_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/prestadores", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_prestadores.py -v`
Expected: FAIL — `404` on `/admin/prestadores`, and `test_aprovar_prestador_generates_set_password_token` fails because `aprovar` doesn't generate a token for prestadores yet.

- [ ] **Step 3: Modify `src/piscinow/web/routes/admin.py`**

Find the existing `aprovar` route body:

```python
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
        if member.profile_type == ProfileType.LOJA:
            member.generate_set_password_token()
    return RedirectResponse(url="/admin/fila", status_code=303)
```

Change the condition to cover both profiles:

```python
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
        if member.profile_type in (ProfileType.LOJA, ProfileType.PRESTADOR):
            member.generate_set_password_token()
    return RedirectResponse(url="/admin/fila", status_code=303)
```

Append this new route at the end of the file, right after the existing `lojas` route:

```python
@router.get("/prestadores", response_class=HTMLResponse)
async def prestadores(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    items = list(
        db.scalars(
            select(Member)
            .where(Member.profile_type == ProfileType.PRESTADOR, Member.status == MemberStatus.APPROVED)
            .order_by(Member.approved_at.desc())
        )
    )
    base_url = get_settings().public_base_url
    return templates.TemplateResponse(
        request, "admin_prestadores.html", {"members": items, "base_url": base_url}
    )
```

(`ProfileType`, `MemberStatus`, `select`, `Member`, `HTMLResponse`, `get_settings` are all already imported in this file — confirm each is present rather than re-importing duplicates.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_prestadores.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="admin-shell">
  <header class="admin-topbar">
    <div class="wrap">
      <a class="brand" href="/admin/fila">Piscinow <span class="badge">Admin</span></a>
      <nav class="admin-nav">
        <a href="/admin/fila">Fila de admiss&atilde;o</a>
        <a href="/admin/lojas">Lojas</a>
        <a href="/admin/prestadores">Prestadores</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Prestadores aprovados</h1>
      {% if members %}
      <table class="admin-table">
        <thead><tr><th>Nome</th><th>E-mail</th><th>Status</th></tr></thead>
        <tbody>
        {% for member in members %}
          <tr>
            <td>{{ member.name }}</td>
            <td>{{ member.email or "-" }}</td>
            <td>
              {% if member.password_hash %}
                Ativo
              {% elif member.set_password_token %}
                Aguardando defini&ccedil;&atilde;o de senha —
                <span class="mono">{{ base_url }}/prestador/definir-senha/{{ member.set_password_token }}</span>
              {% else %}
                Sem acesso gerado
              {% endif %}
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhum prestador aprovado ainda.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Add a "Prestadores" nav link to the existing admin templates**

In `src/piscinow/web/templates/admin_queue.html`, `src/piscinow/web/templates/admin_corrections.html`, and `src/piscinow/web/templates/admin_lojas.html`, find the `<nav class="admin-nav">` block (currently three links: "Fila de admiss&atilde;o", "Lojas", "Ensinar o concierge") and add the new link between "Lojas" and "Ensinar o concierge", matching `admin_prestadores.html`'s nav exactly:

```html
      <nav class="admin-nav">
        <a href="/admin/fila">Fila de admiss&atilde;o</a>
        <a href="/admin/lojas">Lojas</a>
        <a href="/admin/prestadores">Prestadores</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_prestadores.py -v`
Expected: written per spec; all 5 tests need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 5 tests collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_prestadores.html src/piscinow/web/templates/admin_queue.html src/piscinow/web/templates/admin_corrections.html src/piscinow/web/templates/admin_lojas.html tests/web/test_admin_prestadores.py
git commit -m "feat: generate prestador set-password token on approval, add /admin/prestadores view"
```

---

### Task 4: Prestador routes — `/prestador/definir-senha/{token}`

**Files:**
- Create: `src/piscinow/web/routes/prestador.py`
- Create: `src/piscinow/web/templates/prestador_definir_senha.html`
- Test: `tests/web/test_prestador_definir_senha.py`

**Interfaces:**
- Consumes: `Member`, `MemberStatus`, `ProfileType` (existing), `get_db` (existing).
- Produces: `piscinow.web.routes.prestador.router` (an `APIRouter(prefix="/prestador")` — Tasks 5-8 and 10 append more routes to this same object), `GET/POST /prestador/definir-senha/{token}`.

The set-password-token query filters `profile_type == PRESTADOR` and `status == APPROVED` directly, from this first version — this is the fix sub-project 2 had to apply after the fact to `loja.py`, applied here from the start.

- [ ] **Step 1: Write the failing tests — `tests/web/test_prestador_definir_senha.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType


def test_definir_senha_form_rejects_invalid_token(client):
    response = client.get("/prestador/definir-senha/token-invalido")
    assert response.status_code == 400


def test_definir_senha_sets_email_and_password(client, db_session):
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/prestador/definir-senha/{token}",
        data={"email": "prestador@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/prestador/login"
    db_session.refresh(member)
    assert member.email == "prestador@example.com"
    assert member.verify_password("senha-forte-123") is True
    assert member.set_password_token is None


def test_definir_senha_normalizes_email_case(client, db_session):
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    client.post(
        f"/prestador/definir-senha/{token}",
        data={
            "email": "  Prestador@Example.com  ",
            "password": "senha-forte-123",
            "password_confirm": "senha-forte-123",
        },
    )

    db_session.refresh(member)
    assert member.email == "prestador@example.com"


def test_definir_senha_rejects_mismatched_passwords(client, db_session):
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/prestador/definir-senha/{token}",
        data={"email": "prestador@example.com", "password": "senha-forte-123", "password_confirm": "outra-senha"},
    )

    assert response.status_code == 400
    assert "nao coincidem" in response.text
    db_session.refresh(member)
    assert member.email is None


def test_definir_senha_rejects_duplicate_email_case_insensitive(client, db_session):
    outra = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Outro Prestador",
        status=MemberStatus.APPROVED,
        email="ja-usado@example.com",
    )
    db_session.add(outra)
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/prestador/definir-senha/{token}",
        data={"email": "Ja-Usado@Example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
    )

    assert response.status_code == 400
    assert "ja esta em uso" in response.text


def test_definir_senha_rejects_token_for_non_prestador_profile(client, db_session):
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get(f"/prestador/definir-senha/{token}")

    assert response.status_code == 400


def test_definir_senha_rejects_token_for_non_approved_member(client, db_session):
    member = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.WAITLISTED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get(f"/prestador/definir-senha/{token}")

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_prestador_definir_senha.py -v`
Expected: FAIL — `404` on `/prestador/definir-senha/...` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/web/routes/prestador.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

router = APIRouter(prefix="/prestador")


@router.get("/definir-senha/{token}", response_class=HTMLResponse)
async def definir_senha_form(token: str, request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.PRESTADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "prestador_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    return templates.TemplateResponse(
        request, "prestador_definir_senha.html", {"token": token, "invalid": False, "error": None}
    )


@router.post("/definir-senha/{token}")
async def definir_senha_submit(
    token: str,
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.PRESTADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "prestador_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "prestador_definir_senha.html",
            {"token": token, "invalid": False, "error": "As senhas nao coincidem."},
            status_code=400,
        )
    normalized_email = email.strip().lower()
    existing = db.scalar(
        select(Member).where(
            Member.email == normalized_email,
            Member.profile_type == ProfileType.PRESTADOR,
            Member.id != member.id,
        )
    )
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "prestador_definir_senha.html",
            {"token": token, "invalid": False, "error": "Esse e-mail ja esta em uso por outro prestador."},
            status_code=400,
        )
    member.email = normalized_email
    member.set_password(password)
    return RedirectResponse(url="/prestador/login", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/prestador_definir_senha.html`**

```html
{% extends "base.html" %}
{% block content %}
<main class="admin-shell">
  <div class="wrap narrow">
    <div class="login-card">
      <h1>Definir senha</h1>
      {% if invalid %}
        <p class="error">Link inv&aacute;lido ou expirado. Pe&ccedil;a um novo &agrave; equipe Piscinow.</p>
      {% else %}
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="post" action="/prestador/definir-senha/{{ token }}">
          <div class="field">
            <label for="email">E-mail</label>
            <input id="email" type="email" name="email" required>
          </div>
          <div class="field">
            <label for="password">Senha</label>
            <input id="password" type="password" name="password" required>
          </div>
          <div class="field">
            <label for="password_confirm">Confirme a senha</label>
            <input id="password_confirm" type="password" name="password_confirm" required>
          </div>
          <button class="btn accent block" type="submit">Definir senha e continuar</button>
        </form>
      {% endif %}
    </div>
  </div>
</main>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_prestador_definir_senha.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 7 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/prestador.py src/piscinow/web/templates/prestador_definir_senha.html tests/web/test_prestador_definir_senha.py
git commit -m "feat: prestador set-password onboarding route"
```

---

### Task 5: Prestador routes — login/logout (with rate limit)

**Files:**
- Modify: `src/piscinow/rate_limit.py`
- Modify: `src/piscinow/web/routes/prestador.py`
- Create: `src/piscinow/web/templates/prestador_login.html`
- Test: `tests/web/test_prestador_login.py`

**Interfaces:**
- Consumes: `login`, `logout` (Task 2, `prestador_auth`).
- Produces: `piscinow.rate_limit.prestador_login_rate_limit_string() -> str`, `GET/POST /prestador/login`, `POST /prestador/logout`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_prestador_login.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType


def test_login_with_correct_credentials_redirects_to_servicos(client, db_session):
    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post(
        "/prestador/login",
        data={"email": "prestador@example.com", "password": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/prestador/servicos"


def test_login_with_wrong_password_shows_error(client, db_session):
    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post("/prestador/login", data={"email": "prestador@example.com", "password": "errada"})

    assert response.status_code == 401
    assert "invalidos" in response.text


def test_login_blocks_after_rate_limit_exceeded(client, db_session):
    member = Member(
        profile_type=ProfileType.PRESTADOR,
        name="Instalacoes Sul",
        status=MemberStatus.APPROVED,
        email="prestador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    for _ in range(5):
        response = client.post("/prestador/login", data={"email": "prestador@example.com", "password": "errada"})
        assert response.status_code == 401

    response = client.post("/prestador/login", data={"email": "prestador@example.com", "password": "errada"})
    assert response.status_code == 429
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_prestador_login.py -v`
Expected: FAIL — `404` on `/prestador/login`

- [ ] **Step 3: Add `prestador_login_rate_limit_string` to `src/piscinow/rate_limit.py`**

Append, alongside the existing `admin_login_rate_limit_string` and `loja_login_rate_limit_string`:

```python
def prestador_login_rate_limit_string() -> str:
    return "5/minute"
```

- [ ] **Step 4: Append to `src/piscinow/web/routes/prestador.py`**

Add these imports: `from piscinow.prestador_auth import login as do_login, logout as do_logout` and `from piscinow.rate_limit import limiter, prestador_login_rate_limit_string`. Append:

```python
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "prestador_login.html", {"error": None})


@router.post("/login")
@limiter.limit(prestador_login_rate_limit_string)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/prestador/servicos", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "prestador_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/prestador/login", status_code=303)
```

- [ ] **Step 5: Write `src/piscinow/web/templates/prestador_login.html`**

```html
{% extends "base.html" %}
{% block content %}
<main class="admin-shell">
  <div class="wrap narrow">
    <div class="login-card">
      <h1>Painel do prestador</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/prestador/login">
        <div class="field">
          <label for="email">E-mail</label>
          <input id="email" type="email" name="email" required>
        </div>
        <div class="field">
          <label for="password">Senha</label>
          <input id="password" type="password" name="password" required>
        </div>
        <button class="btn accent block" type="submit">Entrar</button>
      </form>
    </div>
  </div>
</main>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_prestador_login.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 3 tests collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/rate_limit.py src/piscinow/web/routes/prestador.py src/piscinow/web/templates/prestador_login.html tests/web/test_prestador_login.py
git commit -m "feat: prestador login/logout with rate limiting"
```

---

### Task 6: Prestador routes — list + create services

**Files:**
- Modify: `src/piscinow/web/routes/prestador.py`
- Create: `src/piscinow/web/templates/prestador_servicos.html`
- Test: `tests/web/test_prestador_servicos.py`

**Interfaces:**
- Consumes: `require_prestador` (Task 2), `Service`, `ServiceKind` (Task 1).
- Produces: `GET /prestador/servicos`, `POST /prestador/servicos`. The `GET` handler renders `prestador_servicos.html` with context `{"services": [...], "error": None, "prefill": {}, "note": None}` — Tasks 7 and 10 reuse this same template and context shape. Also produces the module-level `_validate_service_form(kind, category, name, price_min, price_max) -> tuple[str | None, Decimal | None, Decimal | None]` helper, reused as-is by Task 7's edit route.

- [ ] **Step 1: Write the failing tests — `tests/web/test_prestador_servicos.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service


def _prestador_logged_in(client, db_session, *, email="prestador@example.com", password="senha-forte-123"):
    prestador = Member(
        profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", status=MemberStatus.APPROVED, email=email
    )
    prestador.set_password(password)
    db_session.add(prestador)
    db_session.flush()
    client.post("/prestador/login", data={"email": email, "password": password})
    return prestador


def test_servicos_redirects_to_login_when_not_authenticated(client):
    response = client.get("/prestador/servicos", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/prestador/login"


def test_criar_servico_persists_and_lists(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "Instalacao completa",
            "price_min": "3000.00",
            "price_max": "8000.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    service = db_session.query(Service).filter(Service.name == "Instalacao completa").one()
    assert service.category == "piscina de fibra"
    assert service.active is True
    assert service.price_min == 3000
    assert service.price_max == 8000

    listing = client.get("/prestador/servicos")
    assert "Instalacao completa" in listing.text


def test_criar_servico_with_empty_price_range_persists(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={"kind": "manutencao", "category": "filtragem", "name": "Manutencao mensal", "price_min": "", "price_max": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303

    service = db_session.query(Service).filter(Service.name == "Manutencao mensal").one()
    assert service.price_min is None
    assert service.price_max is None


def test_criar_servico_with_invalid_kind_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={"kind": "pintura", "category": "geral", "name": "Nao E Servico Valido", "price_min": "", "price_max": ""},
    )
    assert response.status_code == 400
    assert "tipo de servico" in response.text
    assert db_session.query(Service).count() == 0


def test_criar_servico_with_non_finite_price_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "Instalacao",
            "price_min": "Infinity",
            "price_max": "",
        },
    )
    assert response.status_code == 400
    assert db_session.query(Service).count() == 0


def test_criar_servico_with_min_greater_than_max_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "Instalacao",
            "price_min": "9000",
            "price_max": "3000",
        },
    )
    assert response.status_code == 400
    assert db_session.query(Service).count() == 0


def test_criar_servico_with_name_over_limit_shows_error(client, db_session):
    _prestador_logged_in(client, db_session)

    response = client.post(
        "/prestador/servicos",
        data={
            "kind": "instalacao",
            "category": "piscina de fibra",
            "name": "x" * 201,
            "price_min": "",
            "price_max": "",
        },
    )
    assert response.status_code == 400
    assert db_session.query(Service).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_prestador_servicos.py -v`
Expected: FAIL — `404` on `/prestador/servicos`

- [ ] **Step 3: Append to `src/piscinow/web/routes/prestador.py`**

Add these imports: `from decimal import Decimal, InvalidOperation`, `from piscinow.prestador_auth import require_prestador`, and `from piscinow.models.service import Service, ServiceKind`. Append:

```python
_MAX_PRICE = Decimal("99999999.99")


def _validate_service_form(
    kind: str, category: str, name: str, price_min: str, price_max: str
) -> tuple[str | None, Decimal | None, Decimal | None]:
    if kind not in {k.value for k in ServiceKind}:
        return "Selecione um tipo de servico valido.", None, None
    if not category.strip() or not name.strip():
        return "Preencha categoria e nome do servico.", None, None
    if len(category.strip()) > 100 or len(name.strip()) > 200:
        return "Categoria ou nome do servico excede o limite permitido.", None, None

    def _parse_price(raw: str, label: str) -> tuple[str | None, Decimal | None]:
        if not raw.strip():
            return None, None
        try:
            parsed = Decimal(raw.strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            return f"Informe um preco {label} valido.", None
        if not parsed.is_finite() or parsed <= 0 or parsed > _MAX_PRICE:
            return f"Informe um preco {label} valido.", None
        return None, parsed

    error, parsed_min = _parse_price(price_min, "minimo")
    if error:
        return error, None, None
    error, parsed_max = _parse_price(price_max, "maximo")
    if error:
        return error, None, None

    if parsed_min is not None and parsed_max is not None and parsed_min > parsed_max:
        return "O preco minimo nao pode ser maior que o preco maximo.", None, None

    return None, parsed_min, parsed_max


@router.get("/servicos", response_class=HTMLResponse)
async def servicos(
    request: Request,
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    templates = request.app.state.templates
    items = list(
        db.scalars(select(Service).where(Service.member_id == prestador.id).order_by(Service.created_at.desc()))
    )
    return templates.TemplateResponse(
        request, "prestador_servicos.html", {"services": items, "error": None, "prefill": {}, "note": None}
    )


@router.post("/servicos")
async def criar_servico(
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price_min: str = Form(""),
    price_max: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    templates = request.app.state.templates
    error, parsed_min, parsed_max = _validate_service_form(kind, category, name, price_min, price_max)

    if error:
        items = list(
            db.scalars(select(Service).where(Service.member_id == prestador.id).order_by(Service.created_at.desc()))
        )
        prefill = {
            "kind": kind,
            "category": category,
            "name": name,
            "price_min": price_min,
            "price_max": price_max,
            "description": description,
        }
        return templates.TemplateResponse(
            request,
            "prestador_servicos.html",
            {"services": items, "error": error, "prefill": prefill, "note": None},
            status_code=400,
        )

    service = Service(
        member_id=prestador.id,
        kind=ServiceKind(kind),
        category=category.strip(),
        name=name.strip(),
        price_min=parsed_min,
        price_max=parsed_max,
        description=description.strip() or None,
    )
    db.add(service)
    return RedirectResponse(url="/prestador/servicos", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/prestador_servicos.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="admin-shell">
  <header class="admin-topbar">
    <div class="wrap">
      <a class="brand" href="/prestador/servicos">Piscinow <span class="badge">Prestador</span></a>
      <form method="post" action="/prestador/logout"><button class="mini-btn" type="submit">Sair</button></form>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Meus servi&ccedil;os</h1>

      <div class="teach-form">
        <h2 style="font-size:1.1rem; margin-bottom:14px;">Cadastrar servi&ccedil;o</h2>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        {% if note %}<p class="error">{{ note }}</p>{% endif %}

        <details style="margin-bottom:16px;">
          <summary class="eyebrow" style="cursor:pointer;">Atalho: descreva em texto livre</summary>
          <form method="post" action="/prestador/servicos/chat" style="margin-top:10px;">
            <div class="field">
              <textarea name="text" placeholder="Ex: instalacao de piscina de fibra, de 3 a 8 mil"></textarea>
            </div>
            <button class="btn" type="submit">Extrair campos</button>
          </form>
        </details>

        <form method="post" action="/prestador/servicos">
          <div class="field">
            <label for="kind">Tipo</label>
            <select id="kind" name="kind">
              <option value="instalacao" {% if prefill.get("kind") == "instalacao" %}selected{% endif %}>Instala&ccedil;&atilde;o</option>
              <option value="manutencao" {% if prefill.get("kind") == "manutencao" %}selected{% endif %}>Manuten&ccedil;&atilde;o</option>
              <option value="reparo" {% if prefill.get("kind") == "reparo" %}selected{% endif %}>Reparo</option>
            </select>
          </div>
          <div class="field">
            <label for="category">Categoria</label>
            <input id="category" type="text" name="category" value="{{ prefill.get('category', '') }}" placeholder="piscina de fibra, aquecimento, automacao...">
          </div>
          <div class="field">
            <label for="name">Nome</label>
            <input id="name" type="text" name="name" value="{{ prefill.get('name', '') }}">
          </div>
          <div class="field">
            <label for="price_min">Pre&ccedil;o m&iacute;nimo (R$, opcional)</label>
            <input id="price_min" type="text" name="price_min" value="{{ prefill.get('price_min', '') }}">
          </div>
          <div class="field">
            <label for="price_max">Pre&ccedil;o m&aacute;ximo (R$, opcional)</label>
            <input id="price_max" type="text" name="price_max" value="{{ prefill.get('price_max', '') }}">
          </div>
          <div class="field">
            <label for="description">Descri&ccedil;&atilde;o (opcional)</label>
            <textarea id="description" name="description">{{ prefill.get('description', '') }}</textarea>
          </div>
          <button class="btn accent" type="submit">Salvar servi&ccedil;o</button>
        </form>
      </div>

      {% if services %}
      <table class="admin-table">
        <thead><tr><th>Nome</th><th>Categoria</th><th>Pre&ccedil;o</th><th>Status</th><th>A&ccedil;&atilde;o</th></tr></thead>
        <tbody>
        {% for service in services %}
          <tr>
            <td>{{ service.name }}</td>
            <td>{{ service.category }}</td>
            <td>
              {% if service.price_min and service.price_max %}
                R$ {{ service.price_min }} - R$ {{ service.price_max }}
              {% elif service.price_min %}
                a partir de R$ {{ service.price_min }}
              {% else %}
                A combinar
              {% endif %}
            </td>
            <td>{{ "Ativo" if service.active else "Inativo" }}</td>
            <td>
              <div class="row-actions">
                <a class="mini-btn" href="/prestador/servicos/{{ service.id }}/editar">Editar</a>
                {% if service.active %}
                <form method="post" action="/prestador/servicos/{{ service.id }}/desativar">
                  <button class="mini-btn" type="submit">Desativar</button>
                </form>
                {% endif %}
              </div>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhum servi&ccedil;o cadastrado ainda.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_prestador_servicos.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 7 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/prestador.py src/piscinow/web/templates/prestador_servicos.html tests/web/test_prestador_servicos.py
git commit -m "feat: prestador service catalog list and create"
```

---

### Task 7: Prestador routes — edit service

**Files:**
- Modify: `src/piscinow/web/routes/prestador.py`
- Create: `src/piscinow/web/templates/prestador_servico_editar.html`
- Test: `tests/web/test_prestador_servico_editar.py`

**Interfaces:**
- Consumes: `require_prestador`, `Service`, `ServiceKind`, `_validate_service_form` (Task 6).
- Produces: `GET /prestador/servicos/{service_id}/editar`, `POST /prestador/servicos/{service_id}/editar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_prestador_servico_editar.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service, ServiceKind
from tests.web.test_prestador_servicos import _prestador_logged_in


def test_editar_servico_form_shows_current_values(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Antigo", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.get(f"/prestador/servicos/{service.id}/editar")

    assert response.status_code == 200
    assert "Antigo" in response.text


def test_editar_servico_updates_fields(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Antigo", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(
        f"/prestador/servicos/{service.id}/editar",
        data={
            "kind": "manutencao",
            "category": "filtragem",
            "name": "Novo Nome",
            "price_min": "1000",
            "price_max": "2000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(service)
    assert service.name == "Novo Nome"
    assert service.kind == ServiceKind.MANUTENCAO
    assert service.price_min == 1000
    assert service.price_max == 2000


def test_editar_servico_with_non_finite_price_shows_error(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Antigo", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(
        f"/prestador/servicos/{service.id}/editar",
        data={"kind": "instalacao", "category": "piscina de fibra", "name": "Antigo", "price_min": "inf", "price_max": ""},
    )

    assert response.status_code == 400
    db_session.refresh(service)
    assert service.name == "Antigo"


def test_editar_servico_de_outro_prestador_retorna_404(client, db_session):
    _prestador_logged_in(client, db_session, email="prestador1@example.com")

    outro_prestador = Member(profile_type=ProfileType.PRESTADOR, name="Outro Prestador", status=MemberStatus.APPROVED)
    db_session.add(outro_prestador)
    db_session.flush()
    service = Service(
        member_id=outro_prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Nao Meu", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(
        f"/prestador/servicos/{service.id}/editar",
        data={"kind": "instalacao", "category": "piscina de fibra", "name": "Hackeado", "price_min": "1", "price_max": ""},
    )

    assert response.status_code == 404
```

Note: `_prestador_logged_in` is imported from Task 6's test file — this reuses that helper rather than redefining it, so both test files stay in sync on how a logged-in prestador is set up.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_prestador_servico_editar.py -v`
Expected: FAIL — `404` on `/prestador/servicos/{id}/editar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/prestador.py`**

Add `from fastapi import HTTPException` to the imports if not already present. Append:

```python
@router.get("/servicos/{service_id}/editar", response_class=HTMLResponse)
async def editar_servico_form(
    service_id: str,
    request: Request,
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    service = db.get(Service, service_id)
    if service is None or service.member_id != prestador.id:
        raise HTTPException(status_code=404)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "prestador_servico_editar.html", {"service": service, "error": None}
    )


@router.post("/servicos/{service_id}/editar")
async def editar_servico_submit(
    service_id: str,
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price_min: str = Form(""),
    price_max: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    service = db.get(Service, service_id)
    if service is None or service.member_id != prestador.id:
        raise HTTPException(status_code=404)

    templates = request.app.state.templates
    error, parsed_min, parsed_max = _validate_service_form(kind, category, name, price_min, price_max)

    if error:
        return templates.TemplateResponse(
            request, "prestador_servico_editar.html", {"service": service, "error": error}, status_code=400
        )

    service.kind = ServiceKind(kind)
    service.category = category.strip()
    service.name = name.strip()
    service.price_min = parsed_min
    service.price_max = parsed_max
    service.description = description.strip() or None
    return RedirectResponse(url="/prestador/servicos", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/prestador_servico_editar.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="admin-shell">
  <header class="admin-topbar">
    <div class="wrap">
      <a class="brand" href="/prestador/servicos">Piscinow <span class="badge">Prestador</span></a>
      <form method="post" action="/prestador/logout"><button class="mini-btn" type="submit">Sair</button></form>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap narrow">
      <h1>Editar servi&ccedil;o</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/prestador/servicos/{{ service.id }}/editar">
        <div class="field">
          <label for="kind">Tipo</label>
          <select id="kind" name="kind">
            <option value="instalacao" {% if service.kind.value == "instalacao" %}selected{% endif %}>Instala&ccedil;&atilde;o</option>
            <option value="manutencao" {% if service.kind.value == "manutencao" %}selected{% endif %}>Manuten&ccedil;&atilde;o</option>
            <option value="reparo" {% if service.kind.value == "reparo" %}selected{% endif %}>Reparo</option>
          </select>
        </div>
        <div class="field">
          <label for="category">Categoria</label>
          <input id="category" type="text" name="category" value="{{ service.category }}">
        </div>
        <div class="field">
          <label for="name">Nome</label>
          <input id="name" type="text" name="name" value="{{ service.name }}">
        </div>
        <div class="field">
          <label for="price_min">Pre&ccedil;o m&iacute;nimo (R$, opcional)</label>
          <input id="price_min" type="text" name="price_min" value="{{ service.price_min or '' }}">
        </div>
        <div class="field">
          <label for="price_max">Pre&ccedil;o m&aacute;ximo (R$, opcional)</label>
          <input id="price_max" type="text" name="price_max" value="{{ service.price_max or '' }}">
        </div>
        <div class="field">
          <label for="description">Descri&ccedil;&atilde;o (opcional)</label>
          <textarea id="description" name="description">{{ service.description or '' }}</textarea>
        </div>
        <button class="btn accent" type="submit">Salvar altera&ccedil;&otilde;es</button>
      </form>
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_prestador_servico_editar.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 4 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/prestador.py src/piscinow/web/templates/prestador_servico_editar.html tests/web/test_prestador_servico_editar.py
git commit -m "feat: prestador service editing with ownership check"
```

---

### Task 8: Prestador routes — deactivate service

**Files:**
- Modify: `src/piscinow/web/routes/prestador.py`
- Test: `tests/web/test_prestador_servico_desativar.py`

**Interfaces:**
- Consumes: `require_prestador`, `Service` (as above).
- Produces: `POST /prestador/servicos/{service_id}/desativar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_prestador_servico_desativar.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.service import Service, ServiceKind
from tests.web.test_prestador_servicos import _prestador_logged_in


def test_desativar_servico_sets_active_false(client, db_session):
    prestador = _prestador_logged_in(client, db_session)
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Servico X", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/prestador/servicos/{service.id}/desativar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(service)
    assert service.active is False


def test_desativar_servico_de_outro_prestador_retorna_404(client, db_session):
    _prestador_logged_in(client, db_session, email="prestador1@example.com")

    outro_prestador = Member(profile_type=ProfileType.PRESTADOR, name="Outro Prestador", status=MemberStatus.APPROVED)
    db_session.add(outro_prestador)
    db_session.flush()
    service = Service(
        member_id=outro_prestador.id, kind=ServiceKind.INSTALACAO, category="piscina de fibra", name="Nao Meu", price_min=3000
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/prestador/servicos/{service.id}/desativar")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_prestador_servico_desativar.py -v`
Expected: FAIL — `404` on `/prestador/servicos/{id}/desativar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/prestador.py`**

```python
@router.post("/servicos/{service_id}/desativar")
async def desativar_servico(
    service_id: str,
    db: Session = Depends(get_db),
    prestador: Member = Depends(require_prestador),
):
    service = db.get(Service, service_id)
    if service is None or service.member_id != prestador.id:
        raise HTTPException(status_code=404)
    service.active = False
    return RedirectResponse(url="/prestador/servicos", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_prestador_servico_desativar.py -v`
Expected: written per spec; both need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/prestador.py tests/web/test_prestador_servico_desativar.py
git commit -m "feat: prestador service deactivation with ownership check"
```

---

### Task 9: Service field extraction (chat shortcut, agent side)

**Files:**
- Create: `src/piscinow/agent/service_extractor.py`
- Test: `tests/agent/test_service_extractor.py`

**Interfaces:**
- Consumes: `parse_json_object` (existing, sub-project 2 Task 1), `ChatMessage`, `LLMProvider` (existing).
- Produces: `piscinow.agent.service_extractor.extract_service_fields(llm: LLMProvider, text: str) -> dict` — always returns a dict with the six keys `kind`, `category`, `name`, `price_min`, `price_max`, `description` (each a string; `""` when the LLM didn't provide that field), so the caller (Task 10) can pass it straight into the same `prefill` dict shape Task 6's template already expects.

This task needs NO Docker — it only uses `FakeLLMProvider`, no database.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_service_extractor.py`**

```python
import pytest

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.service_extractor import extract_service_fields


@pytest.mark.asyncio
async def test_extracts_service_fields_from_llm_json():
    provider = FakeLLMProvider(
        [
            '{"kind": "instalacao", "category": "piscina de fibra", "name": "Instalacao completa", '
            '"price_min": 3000, "price_max": 8000, "description": null}'
        ]
    )

    result = await extract_service_fields(provider, "instalacao de piscina de fibra, de 3 a 8 mil")

    assert result["kind"] == "instalacao"
    assert result["category"] == "piscina de fibra"
    assert result["name"] == "Instalacao completa"
    assert result["price_min"] == "3000"
    assert result["price_max"] == "8000"
    assert result["description"] == ""


@pytest.mark.asyncio
async def test_extract_service_fields_returns_blank_fields_on_malformed_response():
    provider = FakeLLMProvider(["desculpe nao entendi"])

    result = await extract_service_fields(provider, "algo confuso")

    assert result == {"kind": "", "category": "", "name": "", "price_min": "", "price_max": "", "description": ""}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/agent/test_service_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.service_extractor'`

- [ ] **Step 3: Write `src/piscinow/agent/service_extractor.py`**

```python
from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider

_SYSTEM_PROMPT = """Voce ajuda um prestador de servico a cadastrar um servico
no Clube Piscinow a partir de uma descricao em texto livre. Extraia os campos
em JSON: {"kind": "instalacao", "manutencao" ou "reparo", "category": string,
"name": string, "price_min": numero ou null, "price_max": numero ou null,
"description": string ou null}.
Use null para campos que nao aparecem no texto. Responda APENAS com o JSON."""


async def extract_service_fields(llm: LLMProvider, text: str) -> dict:
    raw = await llm.generate([ChatMessage(role="user", content=text)], system=_SYSTEM_PROMPT)
    data = parse_json_object(raw)
    return {
        "kind": data.get("kind") or "",
        "category": data.get("category") or "",
        "name": data.get("name") or "",
        "price_min": str(data.get("price_min")) if data.get("price_min") is not None else "",
        "price_max": str(data.get("price_max")) if data.get("price_max") is not None else "",
        "description": data.get("description") or "",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/agent/test_service_extractor.py -v`
Expected: PASS (2 tests, real GREEN — no Docker needed for this task)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/service_extractor.py tests/agent/test_service_extractor.py
git commit -m "feat: service field extraction from free text for the prestador chat shortcut"
```

---

### Task 10: Prestador route — chat shortcut for service entry

**Files:**
- Modify: `src/piscinow/web/routes/prestador.py`
- Test: `tests/web/test_prestador_servicos_chat.py`

**Interfaces:**
- Consumes: `extract_service_fields` (Task 9), `require_prestador` (Task 2), `get_llm_provider` (existing).
- Produces: `POST /prestador/servicos/chat` — never persists a `Service`; always re-renders `prestador_servicos.html` with `prefill` populated from the extraction.

- [ ] **Step 1: Write the failing test — `tests/web/test_prestador_servicos_chat.py`**

```python
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.service import Service
from piscinow.web.deps import get_llm_provider
from tests.web.test_prestador_servicos import _prestador_logged_in


def test_servicos_chat_prefills_form_without_saving(client, db_session):
    _prestador_logged_in(client, db_session)
    provider = FakeLLMProvider(
        [
            '{"kind": "instalacao", "category": "piscina de fibra", "name": "Instalacao completa", '
            '"price_min": 3000, "price_max": 8000, "description": null}'
        ]
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/prestador/servicos/chat", data={"text": "instalacao de piscina de fibra, de 3 a 8 mil"})

    assert response.status_code == 200
    assert "Instalacao completa" in response.text
    assert db_session.query(Service).count() == 0


def test_servicos_chat_shows_note_when_extraction_fails(client, db_session):
    _prestador_logged_in(client, db_session)
    provider = FakeLLMProvider(["desculpe nao entendi"])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/prestador/servicos/chat", data={"text": "algo confuso"})

    assert response.status_code == 200
    assert "Nao consegui entender" in response.text
    assert db_session.query(Service).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_prestador_servicos_chat.py -v`
Expected: FAIL — `404` on `/prestador/servicos/chat` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/prestador.py`**

Add these imports: `from piscinow.agent.llm_provider import LLMProvider`, `from piscinow.agent.service_extractor import extract_service_fields`, and add `get_llm_provider` to the existing `from piscinow.web.deps import get_db` line (combine into `from piscinow.web.deps import get_db, get_llm_provider`). Also add `from piscinow.rate_limit import chat_rate_limit_string` to the existing `from piscinow.rate_limit import limiter, prestador_login_rate_limit_string` import line (combine into one line). Append:

```python
@router.post("/servicos/chat")
@limiter.limit(chat_rate_limit_string)
async def servicos_chat(
    request: Request,
    text: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    prestador: Member = Depends(require_prestador),
):
    templates = request.app.state.templates
    prefill = await extract_service_fields(llm, text)
    items = list(
        db.scalars(select(Service).where(Service.member_id == prestador.id).order_by(Service.created_at.desc()))
    )
    note = None
    if not any(prefill.values()):
        note = "Nao consegui entender, preencha manualmente."
    return templates.TemplateResponse(
        request, "prestador_servicos.html", {"services": items, "error": None, "prefill": prefill, "note": note}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_prestador_servicos_chat.py -v`
Expected: written per spec; both need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/prestador.py tests/web/test_prestador_servicos_chat.py
git commit -m "feat: chat shortcut for service entry, always confirmed before saving"
```

---

### Task 11: Register the prestador router

**Files:**
- Modify: `src/piscinow/web/app.py`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: `piscinow.web.routes.prestador.router` (Task 4).

- [ ] **Step 1: Write the failing test** — append to `tests/web/test_app.py`

```python
def test_app_serves_prestador_login_page(client):
    response = client.get("/prestador/login")
    assert response.status_code == 200
    assert "Painel do prestador" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/web/test_app.py -v`
Expected: the new test FAILs with a `404` (router not registered yet); the pre-existing tests still pass.

- [ ] **Step 3: Modify `src/piscinow/web/app.py`**

Change `from piscinow.web.routes import admin, chat, loja, pages` to:

```python
from piscinow.web.routes import admin, chat, loja, pages, prestador
```

Add `app.include_router(prestador.router)` alongside the existing `app.include_router(pages.router)` / `app.include_router(chat.router)` / `app.include_router(admin.router)` / `app.include_router(loja.router)` lines inside `create_app()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/web/test_app.py -v`
Expected: PASS (all tests) — the prestador login page doesn't touch the database, so this is a real, Docker-free GREEN.

- [ ] **Step 5: Run the whole-suite collection check**

Run: `py -m pytest --collect-only -q`
Expected: every test in the project collects with zero errors (confirms this task, and every prior task in this plan, introduced no import/syntax mistakes anywhere — this should be strictly more tests than the 126 collected at the end of sub-project 2).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/app.py tests/web/test_app.py
git commit -m "feat: register the prestador router"
```

---

## Self-Review Notes

- **Spec coverage:** every requirement in the spec maps to a task — set-password onboarding via one-time token filtered by profile/status from the start (Tasks 3, 4); prestador login mirroring the loja pattern with rate limiting built in (Tasks 2, 5); service catalog CRUD via forms with shared validation and a price range (Tasks 1, 6, 7, 8); chat shortcut that only ever pre-fills, never auto-saves, rate-limited from the start (Tasks 9, 10); admin visibility into pending/active prestadores (Task 3); reuse of the existing Agent Core rather than a parallel JSON parser (existing `parse_json_object`, consumed by Task 9); the explicit decision to mirror `loja_auth.py` rather than generalize (Task 2).
- **Type/interface consistency check:** `Service`'s field names (`kind`, `category`, `name`, `price_min`, `price_max`, `description`, `active`) are used identically by Tasks 6, 7, 8, and by `extract_service_fields`'s return-dict keys in Task 9/10 — the `prefill` dict Task 6's template reads (`prefill.get("kind")`, etc.) matches exactly what Task 9 returns, so Task 10 can hand the extractor's output straight to the template with no translation layer. `require_prestador`'s return type (`Member`) is consumed identically across Tasks 6, 7, 8, 10. `PRESTADOR_SESSION_KEY`/`login`/`logout` (Task 2) are consumed only by Task 5's routes, matching signatures exactly. `_validate_service_form`'s three-tuple return `(error, price_min, price_max)` is used identically in Task 6's `criar_servico` and Task 7's `editar_servico_submit`.
- **Placeholder scan:** no TBD/TODO markers. The lessons from sub-project 2's final-review fix waves (rate limiting on login and chat, profile/status filtering on the token lookup, shared form validation with length/finiteness/range checks, normalized+unique email) are built into Tasks 2, 3, 4, 5, 6, and 7 directly, rather than left as a follow-up fix wave.
