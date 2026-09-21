# Configurador de Projeto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an approved comprador (buyer) her own account, a public storefront to discover products/services without price, and a panel to assemble and confirm a project (one product + N services) — with a chat shortcut that suggests matching items, never adding them automatically.

**Architecture:** Reuses the `Member` authentication capability from sub-project 2 (already profile-agnostic, no schema change needed), adds `Project`/`ProjectService` models, a `comprador_auth` module mirroring `prestador_auth.py`, a public (unauthenticated) `/vitrine/*` route group, and a `/comprador/*` route group behind `require_comprador`. Includes one targeted fix to the existing chat-onboarding orchestrator: `Member.region` is never populated from the pre-cadastro chat flow today, which would silently break the vitrine's region filter.

**Tech Stack:** Same as sub-projects 1-3 — Python 3.12, FastAPI, SQLAlchemy 2.0, Postgres 16 + pgvector, Jinja2, argon2-cffi, slowapi.

**Spec:** [docs/superpowers/specs/2026-09-21-piscinow-configurador-projeto-design.md](../specs/2026-09-21-piscinow-configurador-projeto-design.md)

## Global Constraints

- Reuses the existing Postgres+pgvector datastore — no new datastore, no new infra.
- Comprador authentication mirrors `prestador_auth.py`/`loja_auth.py` exactly: argon2 password hashing (via `Member.verify_password`, already implemented), session-based login, a `require_comprador` FastAPI dependency that raises `HTTPException(303, headers={"Location": "/comprador/login"})` when unauthenticated or when the session's member is no longer `profile_type=COMPRADOR`/`status=APPROVED`.
- The set-password-token lookup query filters `profile_type == COMPRADOR` and `status == APPROVED` directly in the `select(...)`, from the first version of the route (same lesson already applied in sub-project 3).
- `POST /comprador/login` is rate-limited (`5/minute`) from its first commit. `POST /comprador/projeto/buscar` is rate-limited (reusing `chat_rate_limit_string`) from its first commit.
- Duplicate-email check on the definir-senha route is GLOBAL (no `profile_type` predicate) from the first commit — `Member.email` is `unique=True` across all profiles (sub-project 2), and scoping the check by profile was a real bug fixed in sub-project 3's final review. Do not reintroduce it here.
- `product_id`/`service_id` path/form params are validated as UUIDs (via `uuid.UUID(...)` in a try/except, raising `HTTPException(404)` on failure) before any `db.get(...)` call — the malformed-id-gives-500 bug fixed in sub-project 3's final review must not reappear here.
- `Project` has exactly one product and any number of services (via `ProjectService`); a `Member` has at most one `Project` (`Project.member_id` is `unique=True`) — creating a second project after confirming the first is out of scope for this plan.
- A confirmed project (`status == CONFIRMADO`) is immutable: any attempt to change its product or services is rejected with `HTTPException(400)`, regardless of what the UI shows.
- The public vitrine (`/vitrine/*`) never requires authentication and never renders a price.
- All user-facing text (templates, error messages) is Portuguese (pt-BR). Templates use HTML entities (`&aacute;`, `&atilde;`, `&ccedil;`, etc.) for accented characters. Python string literals (error messages) follow the existing project convention of unaccented ASCII.
- TDD throughout: write the failing test before the implementation, every task.
- Same environment constraint as sub-projects 1-3: no Docker/Postgres on this development machine. Tests that don't need `db_session` must show real RED→GREEN with `py -m pytest` (using the Python Launcher — bare `python`/`python3` are broken on this machine). Tests that do need `db_session` are written and reviewed carefully but will fail at fixture setup with a Docker connection error here; that failure mode is expected and does not block a task.
- Never modify `tests/conftest.py` beyond adding the one new model-import line this plan specifies (Task 2) — never mock the database, in this file or `tests/web/conftest.py`.
- `tests/web/conftest.py`'s `client` fixture already calls `limiter.reset()` before each test (fixed in sub-project 2) — no change needed there.

---

### Task 1: Fix — populate `Member.region` on finalization

**Files:**
- Modify: `src/piscinow/agent/orchestrator.py:82-89`
- Test: `tests/agent/test_orchestrator.py`

**Interfaces:**
- Modifies: `Orchestrator._finalize_member` (private method, no external interface change) — now also sets `Member.region` from `collected_fields["region"]`. Consumed by Task 7/8/13's region filters, which read `Member.region` via join.

- [ ] **Step 1: Write the failing test** — append to `tests/agent/test_orchestrator.py`

```python
@pytest.mark.asyncio
async def test_finalize_member_populates_region_column(db_session):
    provider = FakeLLMProvider()
    orchestrator = Orchestrator(db_session, provider)
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    provider.queue_response(
        '{"name": "Marina Duarte", "contact": "(19) 99999-0000", "region": "Valinhos", "intent": "alvenaria 6x3"}'
    )
    result = await orchestrator.handle_user_message(
        conversation,
        "Marina Duarte, (19) 99999-0000, em Valinhos, alvenaria 6x3",
        referred_by=None,
    )

    assert result.finalized is True
    member = db_session.get(Member, conversation.member_id)
    assert member.region == "Valinhos"
    assert member.profile_details["region"] == "Valinhos"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/agent/test_orchestrator.py::test_finalize_member_populates_region_column -v`
Expected: written per spec; needs `db_session` — confirm fixture-level Docker failure only (not a logic error). Run `py -m pytest tests/agent/test_orchestrator.py --collect-only -q` to confirm the new test collects with no import error.

- [ ] **Step 3: Modify `src/piscinow/agent/orchestrator.py`**

Find the existing `_finalize_member` body:

```python
    def _finalize_member(self, conversation: Conversation, *, referred_by: Member | None) -> Member:
        fields = conversation.collected_fields
        member = Member(
            profile_type=conversation.profile_type_detected,
            name=fields.get("name", ""),
            profile_details=fields,
            referred_by_member_id=referred_by.id if referred_by else None,
        )
```

Add a `region` argument alongside `name`:

```python
    def _finalize_member(self, conversation: Conversation, *, referred_by: Member | None) -> Member:
        fields = conversation.collected_fields
        member = Member(
            profile_type=conversation.profile_type_detected,
            name=fields.get("name", ""),
            region=fields.get("region") or None,
            profile_details=fields,
            referred_by_member_id=referred_by.id if referred_by else None,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/agent/test_orchestrator.py -v`
Expected: written per spec; needs `db_session` — confirm fixture-level Docker failure only for ALL tests in this file (both the new one and the pre-existing ones), not a logic/import error. This confirms the change didn't break the file's syntax or existing tests' collection.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/orchestrator.py tests/agent/test_orchestrator.py
git commit -m "fix: populate Member.region from chat pre-cadastro fields"
```

---

### Task 2: `Project`/`ProjectService` models

**Files:**
- Create: `src/piscinow/models/project.py`
- Modify: `tests/conftest.py` (add the new model import)
- Test: `tests/models/test_project.py`

**Interfaces:**
- Consumes: `piscinow.db.Base`, `piscinow.models.member.Member`, `piscinow.models.product.Product`, `piscinow.models.service.Service` (for foreign keys).
- Produces: `piscinow.models.project.ProjectStatus` (str enum: `RASCUNHO`, `CONFIRMADO`), `piscinow.models.project.Project` (fields: `id`, `member_id` — `unique=True` —, `product_id` — nullable —, `status`, `created_at`, `updated_at`), `piscinow.models.project.ProjectService` (fields: `id`, `project_id`, `service_id`). Consumed by Tasks 4, 9, 10, 11, 13.

- [ ] **Step 1: Write the failing tests — `tests/models/test_project.py`**

```python
import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.member import Member, ProfileType
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service, ServiceKind


def test_project_persists_with_default_status(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()

    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()
    db_session.expunge(project)

    reloaded = db_session.get(Project, project.id)
    assert reloaded.status == ProjectStatus.RASCUNHO
    assert reloaded.product_id is None


def test_project_service_links_project_to_service(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add_all([comprador, prestador])
    db_session.flush()

    project = Project(member_id=comprador.id)
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add_all([project, service])
    db_session.flush()

    link = ProjectService(project_id=project.id, service_id=service.id)
    db_session.add(link)
    db_session.flush()
    db_session.expunge(link)

    reloaded = db_session.get(ProjectService, link.id)
    assert reloaded.project_id == project.id
    assert reloaded.service_id == service.id


def test_project_member_id_is_unique(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()

    project_a = Project(member_id=comprador.id)
    db_session.add(project_a)
    db_session.flush()

    project_b = Project(member_id=comprador.id)
    db_session.add(project_b)
    with pytest.raises(IntegrityError):
        db_session.flush()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/models/test_project.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.project'`

- [ ] **Step 3: Write `src/piscinow/models/project.py`**

```python
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


class ProjectStatus(str, enum.Enum):
    RASCUNHO = "rascunho"
    CONFIRMADO = "confirmado"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), unique=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=True
    )
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status"), default=ProjectStatus.RASCUNHO
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ProjectService(Base):
    __tablename__ = "project_services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"))
```

- [ ] **Step 4: Add the model import to `tests/conftest.py`**

Add `import piscinow.models.project  # noqa: E402,F401` alongside the other `import piscinow.models...` lines (member, conversation, memory, admin, product, service) so `Base.metadata.create_all` in the `engine` fixture picks up the new `projects`/`project_services` tables. This is the ONLY change this plan makes to `tests/conftest.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/models/test_project.py -v`
Expected: written per spec; all 3 tests need `db_session` — confirm fixture-level Docker failure only (`py -m pytest tests/models/test_project.py --collect-only -q` should show 3 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/models/project.py tests/models/test_project.py tests/conftest.py
git commit -m "feat: Project and ProjectService models"
```

---

### Task 3: `comprador_auth` module

**Files:**
- Create: `src/piscinow/comprador_auth.py`
- Test: `tests/test_comprador_auth.py`

**Interfaces:**
- Consumes: `Member`, `MemberStatus`, `ProfileType` (existing), `get_db` (existing).
- Produces: `piscinow.comprador_auth.COMPRADOR_SESSION_KEY: str`, `login(request, db, email, password) -> bool`, `logout(request) -> None`, `require_comprador(request, db=Depends(get_db)) -> Member`. Consumed by every `/comprador/*` route (Tasks 5, 6, 9, 10, 11, 13).

This mirrors `src/piscinow/prestador_auth.py` exactly, but scoped to `Member` rows with `profile_type=COMPRADOR` and `status=APPROVED`.

- [ ] **Step 1: Write the failing tests — `tests/test_comprador_auth.py`**

```python
from piscinow.comprador_auth import COMPRADOR_SESSION_KEY, login, logout


class _FakeSession(dict):
    pass


class _FakeRequest:
    def __init__(self):
        self.session = _FakeSession()


def test_login_sets_session_key_on_success(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.COMPRADOR,
        name="Marina Duarte",
        status=MemberStatus.APPROVED,
        email="comprador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "comprador@example.com", "senha-forte-123")

    assert result is True
    assert request.session[COMPRADOR_SESSION_KEY] == str(member.id)


def test_login_normalizes_email_case_and_whitespace(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.COMPRADOR,
        name="Marina Duarte",
        status=MemberStatus.APPROVED,
        email="comprador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "  Comprador@Example.com  ", "senha-forte-123")

    assert result is True


def test_login_fails_for_wrong_password(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.COMPRADOR,
        name="Marina Duarte",
        status=MemberStatus.APPROVED,
        email="comprador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "comprador@example.com", "errada")

    assert result is False
    assert COMPRADOR_SESSION_KEY not in request.session


def test_login_fails_for_non_comprador_profile(db_session):
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
    assert COMPRADOR_SESSION_KEY not in request.session


def test_logout_removes_session_key():
    request = _FakeRequest()
    request.session[COMPRADOR_SESSION_KEY] = "some-id"
    logout(request)
    assert COMPRADOR_SESSION_KEY not in request.session
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_comprador_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.comprador_auth'`

- [ ] **Step 3: Write `src/piscinow/comprador_auth.py`**

```python
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

COMPRADOR_SESSION_KEY = "comprador_member_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    member = db.scalar(
        select(Member).where(
            Member.email == email.strip().lower(),
            Member.profile_type == ProfileType.COMPRADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.verify_password(password):
        return False
    request.session[COMPRADOR_SESSION_KEY] = str(member.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(COMPRADOR_SESSION_KEY, None)


def require_comprador(request: Request, db: Session = Depends(get_db)) -> Member:
    member_id = request.session.get(COMPRADOR_SESSION_KEY)
    if not member_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/comprador/login"})
    member = db.get(Member, member_id)
    if member is None or member.profile_type != ProfileType.COMPRADOR or member.status != MemberStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/comprador/login"})
    return member
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_comprador_auth.py -v`
Expected: written per spec; all 5 tests need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 5 tests collected with no error).

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/comprador_auth.py tests/test_comprador_auth.py
git commit -m "feat: comprador_auth module mirroring the prestador auth pattern"
```

---

### Task 4: Admin extension — set-password token for compradores + `/admin/compradores` view

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_compradores.html`
- Modify: `src/piscinow/web/templates/admin_queue.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_corrections.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_lojas.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_prestadores.html` (nav link)
- Test: `tests/web/test_admin_compradores.py`

**Interfaces:**
- Consumes: `Member.generate_set_password_token` (existing), `get_settings().public_base_url` (existing).
- Produces: `GET /admin/compradores` (lists approved compradores with their set-password link when still pending).

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_compradores.py`**

```python
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_aprovar_comprador_generates_set_password_token(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.WAITLISTED)
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


def test_compradores_page_shows_set_password_link_when_pending(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get("/admin/compradores")

    assert "Marina Duarte" in response.text
    assert f"/comprador/definir-senha/{token}" in response.text


def test_compradores_page_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/compradores", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_compradores.py -v`
Expected: FAIL — `404` on `/admin/compradores`, and `test_aprovar_comprador_generates_set_password_token` fails because `aprovar` doesn't generate a token for compradores yet.

- [ ] **Step 3: Modify `src/piscinow/web/routes/admin.py`**

Find the existing `aprovar` route body:

```python
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
        if member.profile_type in (ProfileType.LOJA, ProfileType.PRESTADOR):
            member.generate_set_password_token()
    return RedirectResponse(url="/admin/fila", status_code=303)
```

Change the condition to cover all three profiles:

```python
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
        if member.profile_type in (ProfileType.LOJA, ProfileType.PRESTADOR, ProfileType.COMPRADOR):
            member.generate_set_password_token()
    return RedirectResponse(url="/admin/fila", status_code=303)
```

Append this new route at the end of the file, right after the existing `prestadores` route:

```python
@router.get("/compradores", response_class=HTMLResponse)
async def compradores(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    items = list(
        db.scalars(
            select(Member)
            .where(Member.profile_type == ProfileType.COMPRADOR, Member.status == MemberStatus.APPROVED)
            .order_by(Member.approved_at.desc())
        )
    )
    base_url = get_settings().public_base_url
    return templates.TemplateResponse(
        request, "admin_compradores.html", {"members": items, "base_url": base_url}
    )
```

(`ProfileType`, `MemberStatus`, `select`, `Member`, `HTMLResponse`, `get_settings` are all already imported in this file — confirm each is present rather than re-importing duplicates.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_compradores.html`**

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
        <a href="/admin/compradores">Compradores</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Compradores aprovados</h1>
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
                <span class="mono">{{ base_url }}/comprador/definir-senha/{{ member.set_password_token }}</span>
              {% else %}
                Sem acesso gerado
              {% endif %}
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhum comprador aprovado ainda.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Add a "Compradores" nav link to the existing admin templates**

In `src/piscinow/web/templates/admin_queue.html`, `src/piscinow/web/templates/admin_corrections.html`, `src/piscinow/web/templates/admin_lojas.html`, and `src/piscinow/web/templates/admin_prestadores.html`, find the `<nav class="admin-nav">` block (currently four links: "Fila de admiss&atilde;o", "Lojas", "Prestadores", "Ensinar o concierge") and add the new link between "Prestadores" and "Ensinar o concierge", matching `admin_compradores.html`'s nav exactly:

```html
      <nav class="admin-nav">
        <a href="/admin/fila">Fila de admiss&atilde;o</a>
        <a href="/admin/lojas">Lojas</a>
        <a href="/admin/prestadores">Prestadores</a>
        <a href="/admin/compradores">Compradores</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_compradores.py -v`
Expected: written per spec; all 4 tests need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 4 tests collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_compradores.html src/piscinow/web/templates/admin_queue.html src/piscinow/web/templates/admin_corrections.html src/piscinow/web/templates/admin_lojas.html src/piscinow/web/templates/admin_prestadores.html tests/web/test_admin_compradores.py
git commit -m "feat: generate comprador set-password token on approval, add /admin/compradores view"
```

---

### Task 5: Comprador routes — `/comprador/definir-senha/{token}`

**Files:**
- Create: `src/piscinow/web/routes/comprador.py`
- Create: `src/piscinow/web/templates/comprador_definir_senha.html`
- Test: `tests/web/test_comprador_definir_senha.py`

**Interfaces:**
- Consumes: `Member`, `MemberStatus`, `ProfileType` (existing), `get_db` (existing).
- Produces: `piscinow.web.routes.comprador.router` (an `APIRouter(prefix="/comprador")` — Tasks 6, 9, 10, 11, 13 append more routes to this same object), `GET/POST /comprador/definir-senha/{token}`.

The set-password-token query filters `profile_type == COMPRADOR` and `status == APPROVED` directly, from this first version. The duplicate-email check is GLOBAL (no `profile_type` predicate) from this first version — this is the fix sub-project 3's final review had to apply after the fact to `loja.py`/`prestador.py`, applied here from the start.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_definir_senha.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType


def test_definir_senha_form_rejects_invalid_token(client):
    response = client.get("/comprador/definir-senha/token-invalido")
    assert response.status_code == 400


def test_definir_senha_sets_email_and_password(client, db_session):
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/comprador/definir-senha/{token}",
        data={"email": "comprador@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"
    db_session.refresh(member)
    assert member.email == "comprador@example.com"
    assert member.verify_password("senha-forte-123") is True
    assert member.set_password_token is None


def test_definir_senha_rejects_mismatched_passwords(client, db_session):
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/comprador/definir-senha/{token}",
        data={"email": "comprador@example.com", "password": "senha-forte-123", "password_confirm": "outra-senha"},
    )

    assert response.status_code == 400
    assert "nao coincidem" in response.text
    db_session.refresh(member)
    assert member.email is None


def test_definir_senha_rejects_duplicate_email_across_profiles(client, db_session):
    loja = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="ja-usado@example.com"
    )
    db_session.add(loja)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/comprador/definir-senha/{token}",
        data={"email": "ja-usado@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
    )

    assert response.status_code == 400
    assert "ja esta em uso" in response.text


def test_definir_senha_rejects_token_for_non_comprador_profile(client, db_session):
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get(f"/comprador/definir-senha/{token}")

    assert response.status_code == 400


def test_definir_senha_rejects_token_for_non_approved_member(client, db_session):
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.WAITLISTED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get(f"/comprador/definir-senha/{token}")

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_definir_senha.py -v`
Expected: FAIL — `404` on `/comprador/definir-senha/...` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/web/routes/comprador.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

router = APIRouter(prefix="/comprador")


@router.get("/definir-senha/{token}", response_class=HTMLResponse)
async def definir_senha_form(token: str, request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    member = db.scalar(
        select(Member).where(
            Member.set_password_token == token,
            Member.profile_type == ProfileType.COMPRADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "comprador_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    return templates.TemplateResponse(
        request, "comprador_definir_senha.html", {"token": token, "invalid": False, "error": None}
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
            Member.profile_type == ProfileType.COMPRADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "comprador_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "comprador_definir_senha.html",
            {"token": token, "invalid": False, "error": "As senhas nao coincidem."},
            status_code=400,
        )
    normalized_email = email.strip().lower()
    existing = db.scalar(
        select(Member).where(
            Member.email == normalized_email,
            Member.id != member.id,
        )
    )
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "comprador_definir_senha.html",
            {"token": token, "invalid": False, "error": "Esse e-mail ja esta em uso."},
            status_code=400,
        )
    member.email = normalized_email
    member.set_password(password)
    return RedirectResponse(url="/comprador/login", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/comprador_definir_senha.html`**

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
        <form method="post" action="/comprador/definir-senha/{{ token }}">
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

Run: `py -m pytest tests/web/test_comprador_definir_senha.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 6 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/comprador.py src/piscinow/web/templates/comprador_definir_senha.html tests/web/test_comprador_definir_senha.py
git commit -m "feat: comprador set-password onboarding route"
```

---

### Task 6: Comprador routes — login/logout (with rate limit)

**Files:**
- Modify: `src/piscinow/rate_limit.py`
- Modify: `src/piscinow/web/routes/comprador.py`
- Create: `src/piscinow/web/templates/comprador_login.html`
- Test: `tests/web/test_comprador_login.py`

**Interfaces:**
- Consumes: `login`, `logout` (Task 3, `comprador_auth`).
- Produces: `piscinow.rate_limit.comprador_login_rate_limit_string() -> str`, `GET/POST /comprador/login`, `POST /comprador/logout`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_login.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType


def test_login_with_correct_credentials_redirects_to_projeto(client, db_session):
    member = Member(
        profile_type=ProfileType.COMPRADOR,
        name="Marina Duarte",
        status=MemberStatus.APPROVED,
        email="comprador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post(
        "/comprador/login",
        data={"email": "comprador@example.com", "password": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/projeto"


def test_login_with_wrong_password_shows_error(client, db_session):
    member = Member(
        profile_type=ProfileType.COMPRADOR,
        name="Marina Duarte",
        status=MemberStatus.APPROVED,
        email="comprador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post("/comprador/login", data={"email": "comprador@example.com", "password": "errada"})

    assert response.status_code == 401
    assert "invalidos" in response.text


def test_login_blocks_after_rate_limit_exceeded(client, db_session):
    member = Member(
        profile_type=ProfileType.COMPRADOR,
        name="Marina Duarte",
        status=MemberStatus.APPROVED,
        email="comprador@example.com",
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    for _ in range(5):
        response = client.post("/comprador/login", data={"email": "comprador@example.com", "password": "errada"})
        assert response.status_code == 401

    response = client.post("/comprador/login", data={"email": "comprador@example.com", "password": "errada"})
    assert response.status_code == 429
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_login.py -v`
Expected: FAIL — `404` on `/comprador/login`

- [ ] **Step 3: Add `comprador_login_rate_limit_string` to `src/piscinow/rate_limit.py`**

Append, alongside the existing `admin_login_rate_limit_string`/`loja_login_rate_limit_string`/`prestador_login_rate_limit_string`:

```python
def comprador_login_rate_limit_string() -> str:
    return "5/minute"
```

- [ ] **Step 4: Append to `src/piscinow/web/routes/comprador.py`**

Add these imports: `from piscinow.comprador_auth import login as do_login, logout as do_logout` and `from piscinow.rate_limit import limiter, comprador_login_rate_limit_string`. Append:

```python
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "comprador_login.html", {"error": None})


@router.post("/login")
@limiter.limit(comprador_login_rate_limit_string)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/comprador/projeto", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "comprador_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/comprador/login", status_code=303)
```

- [ ] **Step 5: Write `src/piscinow/web/templates/comprador_login.html`**

```html
{% extends "base.html" %}
{% block content %}
<main class="admin-shell">
  <div class="wrap narrow">
    <div class="login-card">
      <h1>Painel do comprador</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/comprador/login">
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

Run: `py -m pytest tests/web/test_comprador_login.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 3 tests collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/rate_limit.py src/piscinow/web/routes/comprador.py src/piscinow/web/templates/comprador_login.html tests/web/test_comprador_login.py
git commit -m "feat: comprador login/logout with rate limiting"
```

---

### Task 7: Vitrine pública — produtos

**Files:**
- Create: `src/piscinow/web/routes/vitrine.py`
- Create: `src/piscinow/web/templates/vitrine_produtos.html`
- Test: `tests/web/test_vitrine_produtos.py`

**Interfaces:**
- Consumes: `Product`, `ProductKind` (existing), `Member` (existing, for the region join), `get_db` (existing).
- Produces: `piscinow.web.routes.vitrine.router` (an `APIRouter(prefix="/vitrine")` — Task 8 appends the `/servicos` route to this same object), `GET /vitrine/produtos`. No authentication anywhere in this file.

- [ ] **Step 1: Write the failing tests — `tests/web/test_vitrine_produtos.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind


def test_vitrine_produtos_lists_active_items_without_price(client, db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", region="Valinhos")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra 6x3", price=18000
    )
    db_session.add(product)
    db_session.flush()

    response = client.get("/vitrine/produtos")

    assert response.status_code == 200
    assert "Piscina Fibra 6x3" in response.text
    assert "18000" not in response.text


def test_vitrine_produtos_hides_inactive_items(client, db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id,
        kind=ProductKind.PISCINA,
        category="fibra",
        name="Piscina Desativada",
        price=18000,
        active=False,
    )
    db_session.add(product)
    db_session.flush()

    response = client.get("/vitrine/produtos")

    assert "Piscina Desativada" not in response.text


def test_vitrine_produtos_filters_by_kind(client, db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    piscina = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    equipamento = Product(
        member_id=loja.id, kind=ProductKind.EQUIPAMENTO, category="filtragem", name="Filtro X", price=500
    )
    db_session.add_all([piscina, equipamento])
    db_session.flush()

    response = client.get("/vitrine/produtos", params={"kind": "equipamento"})

    assert "Filtro X" in response.text
    assert "Piscina Fibra" not in response.text


def test_vitrine_produtos_filters_by_region(client, db_session):
    loja_valinhos = Member(profile_type=ProfileType.LOJA, name="Loja Valinhos", region="Valinhos")
    loja_campinas = Member(profile_type=ProfileType.LOJA, name="Loja Campinas", region="Campinas")
    db_session.add_all([loja_valinhos, loja_campinas])
    db_session.flush()
    produto_valinhos = Product(
        member_id=loja_valinhos.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina V", price=1000
    )
    produto_campinas = Product(
        member_id=loja_campinas.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina C", price=1000
    )
    db_session.add_all([produto_valinhos, produto_campinas])
    db_session.flush()

    response = client.get("/vitrine/produtos", params={"regiao": "Valinhos"})

    assert "Piscina V" in response.text
    assert "Piscina C" not in response.text


def test_vitrine_produtos_does_not_require_authentication(client):
    response = client.get("/vitrine/produtos")
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_vitrine_produtos.py -v`
Expected: FAIL — `404` on `/vitrine/produtos` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/web/routes/vitrine.py`**

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member
from piscinow.models.product import Product, ProductKind
from piscinow.web.deps import get_db

router = APIRouter(prefix="/vitrine")


@router.get("/produtos", response_class=HTMLResponse)
async def vitrine_produtos(
    request: Request,
    kind: str = "",
    category: str = "",
    regiao: str = "",
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    query = select(Product, Member).join(Member, Product.member_id == Member.id).where(Product.active.is_(True))
    if kind in {k.value for k in ProductKind}:
        query = query.where(Product.kind == ProductKind(kind))
    if category:
        query = query.where(Product.category.ilike(f"%{category}%"))
    if regiao:
        query = query.where(Member.region.ilike(f"%{regiao}%"))
    rows = db.execute(query.order_by(Product.created_at.desc())).all()
    items = [{"product": row[0], "loja": row[1]} for row in rows]
    return templates.TemplateResponse(
        request,
        "vitrine_produtos.html",
        {"items": items, "kind": kind, "category": category, "regiao": regiao},
    )
```

- [ ] **Step 4: Write `src/piscinow/web/templates/vitrine_produtos.html`**

```html
{% extends "base.html" %}
{% block content %}
<header class="site">
  <div class="wrap nav-row">
    <a class="brand" href="/">Piscinow <span class="badge">Clube</span></a>
  </div>
</header>
<main>
  <section class="block">
    <div class="wrap">
      <h1>Produtos</h1>
      <form method="get" action="/vitrine/produtos">
        <div class="field">
          <label for="kind">Tipo</label>
          <select id="kind" name="kind">
            <option value="">Todos</option>
            <option value="piscina" {% if kind == "piscina" %}selected{% endif %}>Piscina</option>
            <option value="equipamento" {% if kind == "equipamento" %}selected{% endif %}>Equipamento</option>
          </select>
        </div>
        <div class="field">
          <label for="category">Categoria</label>
          <input id="category" type="text" name="category" value="{{ category }}">
        </div>
        <div class="field">
          <label for="regiao">Regi&atilde;o</label>
          <input id="regiao" type="text" name="regiao" value="{{ regiao }}">
        </div>
        <button class="btn" type="submit">Filtrar</button>
      </form>

      {% if items %}
      <table class="admin-table">
        <thead><tr><th>Nome</th><th>Categoria</th><th>Loja</th><th>Regi&atilde;o</th></tr></thead>
        <tbody>
        {% for item in items %}
          <tr>
            <td>{{ item.product.name }}</td>
            <td>{{ item.product.category }}</td>
            <td>{{ item.loja.name }}</td>
            <td>{{ item.loja.region or "-" }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhum produto encontrado.</p>
      {% endif %}

      <p><a href="/comprador/login">Entrar para ver pre&ccedil;o e montar projeto</a></p>
    </div>
  </section>
</main>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_vitrine_produtos.py -v`
Expected: written per spec; all 5 need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 5 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/vitrine.py src/piscinow/web/templates/vitrine_produtos.html tests/web/test_vitrine_produtos.py
git commit -m "feat: public storefront for products, no price, no auth"
```

---

### Task 8: Vitrine pública — serviços

**Files:**
- Modify: `src/piscinow/web/routes/vitrine.py`
- Create: `src/piscinow/web/templates/vitrine_servicos.html`
- Test: `tests/web/test_vitrine_servicos.py`

**Interfaces:**
- Consumes: `Service`, `ServiceKind` (existing), `Member` (existing, for the region join).
- Produces: `GET /vitrine/servicos`. No authentication.

- [ ] **Step 1: Write the failing tests — `tests/web/test_vitrine_servicos.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.models.service import Service, ServiceKind


def test_vitrine_servicos_lists_active_items_without_price(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul", region="Valinhos")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="piscina de fibra",
        name="Instalacao completa",
        price_min=3000,
        price_max=8000,
    )
    db_session.add(service)
    db_session.flush()

    response = client.get("/vitrine/servicos")

    assert response.status_code == 200
    assert "Instalacao completa" in response.text
    assert "3000" not in response.text
    assert "8000" not in response.text


def test_vitrine_servicos_hides_inactive_items(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id,
        kind=ServiceKind.INSTALACAO,
        category="fibra",
        name="Servico Desativado",
        active=False,
    )
    db_session.add(service)
    db_session.flush()

    response = client.get("/vitrine/servicos")

    assert "Servico Desativado" not in response.text


def test_vitrine_servicos_filters_by_kind(client, db_session):
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    instalacao = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    manutencao = Service(member_id=prestador.id, kind=ServiceKind.MANUTENCAO, category="filtragem", name="Manutencao")
    db_session.add_all([instalacao, manutencao])
    db_session.flush()

    response = client.get("/vitrine/servicos", params={"kind": "manutencao"})

    assert "Manutencao" in response.text
    assert "Instalacao" not in response.text


def test_vitrine_servicos_filters_by_region(client, db_session):
    prestador_valinhos = Member(profile_type=ProfileType.PRESTADOR, name="Prestador Valinhos", region="Valinhos")
    prestador_campinas = Member(profile_type=ProfileType.PRESTADOR, name="Prestador Campinas", region="Campinas")
    db_session.add_all([prestador_valinhos, prestador_campinas])
    db_session.flush()
    servico_valinhos = Service(member_id=prestador_valinhos.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Servico V")
    servico_campinas = Service(member_id=prestador_campinas.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Servico C")
    db_session.add_all([servico_valinhos, servico_campinas])
    db_session.flush()

    response = client.get("/vitrine/servicos", params={"regiao": "Valinhos"})

    assert "Servico V" in response.text
    assert "Servico C" not in response.text


def test_vitrine_servicos_does_not_require_authentication(client):
    response = client.get("/vitrine/servicos")
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_vitrine_servicos.py -v`
Expected: FAIL — `404` on `/vitrine/servicos` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/vitrine.py`**

Add `from piscinow.models.service import Service, ServiceKind` to the imports. Append:

```python
@router.get("/servicos", response_class=HTMLResponse)
async def vitrine_servicos(
    request: Request,
    kind: str = "",
    category: str = "",
    regiao: str = "",
    db: Session = Depends(get_db),
):
    templates = request.app.state.templates
    query = select(Service, Member).join(Member, Service.member_id == Member.id).where(Service.active.is_(True))
    if kind in {k.value for k in ServiceKind}:
        query = query.where(Service.kind == ServiceKind(kind))
    if category:
        query = query.where(Service.category.ilike(f"%{category}%"))
    if regiao:
        query = query.where(Member.region.ilike(f"%{regiao}%"))
    rows = db.execute(query.order_by(Service.created_at.desc())).all()
    items = [{"service": row[0], "prestador": row[1]} for row in rows]
    return templates.TemplateResponse(
        request,
        "vitrine_servicos.html",
        {"items": items, "kind": kind, "category": category, "regiao": regiao},
    )
```

- [ ] **Step 4: Write `src/piscinow/web/templates/vitrine_servicos.html`**

```html
{% extends "base.html" %}
{% block content %}
<header class="site">
  <div class="wrap nav-row">
    <a class="brand" href="/">Piscinow <span class="badge">Clube</span></a>
  </div>
</header>
<main>
  <section class="block">
    <div class="wrap">
      <h1>Servi&ccedil;os</h1>
      <form method="get" action="/vitrine/servicos">
        <div class="field">
          <label for="kind">Tipo</label>
          <select id="kind" name="kind">
            <option value="">Todos</option>
            <option value="instalacao" {% if kind == "instalacao" %}selected{% endif %}>Instala&ccedil;&atilde;o</option>
            <option value="manutencao" {% if kind == "manutencao" %}selected{% endif %}>Manuten&ccedil;&atilde;o</option>
            <option value="reparo" {% if kind == "reparo" %}selected{% endif %}>Reparo</option>
          </select>
        </div>
        <div class="field">
          <label for="category">Categoria</label>
          <input id="category" type="text" name="category" value="{{ category }}">
        </div>
        <div class="field">
          <label for="regiao">Regi&atilde;o</label>
          <input id="regiao" type="text" name="regiao" value="{{ regiao }}">
        </div>
        <button class="btn" type="submit">Filtrar</button>
      </form>

      {% if items %}
      <table class="admin-table">
        <thead><tr><th>Nome</th><th>Categoria</th><th>Prestador</th><th>Regi&atilde;o</th></tr></thead>
        <tbody>
        {% for item in items %}
          <tr>
            <td>{{ item.service.name }}</td>
            <td>{{ item.service.category }}</td>
            <td>{{ item.prestador.name }}</td>
            <td>{{ item.prestador.region or "-" }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhum servi&ccedil;o encontrado.</p>
      {% endif %}

      <p><a href="/comprador/login">Entrar para ver pre&ccedil;o e montar projeto</a></p>
    </div>
  </section>
</main>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_vitrine_servicos.py -v`
Expected: written per spec; all 5 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/vitrine.py src/piscinow/web/templates/vitrine_servicos.html tests/web/test_vitrine_servicos.py
git commit -m "feat: public storefront for services, no price, no auth"
```

---

### Task 9: Comprador routes — show/create project, choose product

**Files:**
- Create: `src/piscinow/web/routes/comprador_projeto.py`
- Create: `src/piscinow/web/templates/comprador_projeto.html`
- Test: `tests/web/test_comprador_projeto.py`

**Interfaces:**
- Consumes: `require_comprador` (Task 3), `Project`, `ProjectStatus`, `ProjectService` (Task 2), `Product` (existing).
- Produces: `piscinow.web.routes.comprador_projeto.router` (an `APIRouter(prefix="/comprador")` — Tasks 10, 11, 13 append more routes to this same object), `piscinow.web.routes.comprador_projeto._get_or_create_project(db, member_id) -> Project` (module-level helper, reused by Tasks 10, 11, 13), `GET /comprador/projeto`, `POST /comprador/projeto/produto`. The `GET` handler renders `comprador_projeto.html` with context `{"project": ..., "product": ..., "services": [...], "error": None, "note": None, "sugestoes": None}` — Tasks 10, 11, 13 reuse this same template and context shape.

This is a SECOND router with the same `/comprador` prefix as Task 5/6's `comprador.py` — FastAPI allows multiple `APIRouter`s with the same prefix; both get registered separately in Task 14. Splitting the file here (rather than growing `comprador.py` further) keeps auth/onboarding routes separate from project-management routes, matching this codebase's convention of one file per cohesive concern once a router grows past a handful of routes.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_projeto.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project


def _comprador_logged_in(client, db_session, *, email="comprador@example.com", password="senha-forte-123"):
    comprador = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED, email=email
    )
    comprador.set_password(password)
    db_session.add(comprador)
    db_session.flush()
    client.post("/comprador/login", data={"email": email, "password": password})
    return comprador


def test_projeto_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador/projeto", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_projeto_creates_draft_on_first_visit(client, db_session):
    comprador = _comprador_logged_in(client, db_session)

    response = client.get("/comprador/projeto")

    assert response.status_code == 200
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.status.value == "rascunho"


def test_escolher_produto_sets_product_on_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        "/comprador/projeto/produto", data={"product_id": str(product.id)}, follow_redirects=False
    )

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.product_id == product.id


def test_escolher_produto_inativo_retorna_404(client, db_session):
    _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Inativo", price=1000, active=False
    )
    db_session.add(product)
    db_session.flush()

    response = client.post("/comprador/projeto/produto", data={"product_id": str(product.id)})

    assert response.status_code == 404


def test_escolher_produto_id_malformado_retorna_404(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.post("/comprador/projeto/produto", data={"product_id": "nao-e-um-uuid"})

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_projeto.py -v`
Expected: FAIL — `404` on `/comprador/projeto` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/web/routes/comprador_projeto.py`**

```python
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.comprador_auth import require_comprador
from piscinow.models.member import Member
from piscinow.models.product import Product
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service
from piscinow.web.deps import get_db

router = APIRouter(prefix="/comprador")


def _get_or_create_project(db: Session, member_id) -> Project:
    project = db.scalar(select(Project).where(Project.member_id == member_id))
    if project is None:
        project = Project(member_id=member_id)
        db.add(project)
        db.flush()
    return project


def _project_services(db: Session, project_id) -> list[Service]:
    return list(
        db.scalars(
            select(Service)
            .join(ProjectService, ProjectService.service_id == Service.id)
            .where(ProjectService.project_id == project_id)
        )
    )


@router.get("/projeto", response_class=HTMLResponse)
async def projeto(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    product = db.get(Product, project.product_id) if project.product_id else None
    services = _project_services(db, project.id)
    return templates.TemplateResponse(
        request,
        "comprador_projeto.html",
        {"project": project, "product": product, "services": services, "error": None, "note": None, "sugestoes": None},
    )


@router.post("/projeto/produto")
async def escolher_produto(
    product_id: str = Form(...),
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado, nao pode ser alterado.")
    try:
        parsed_id = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=404)
    product = db.get(Product, parsed_id)
    if product is None or not product.active:
        raise HTTPException(status_code=404)
    project.product_id = product.id
    return RedirectResponse(url="/comprador/projeto", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/comprador_projeto.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="admin-shell">
  <header class="admin-topbar">
    <div class="wrap">
      <a class="brand" href="/comprador/projeto">Piscinow <span class="badge">Comprador</span></a>
      <form method="post" action="/comprador/logout"><button class="mini-btn" type="submit">Sair</button></form>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Meu projeto</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      {% if note %}<p class="error">{{ note }}</p>{% endif %}

      <div class="teach-form">
        <h2 style="font-size:1.1rem; margin-bottom:14px;">
          Status: {{ "Confirmado" if project.status.value == "confirmado" else "Rascunho" }}
        </h2>

        <h3>Produto</h3>
        {% if product %}
          <p>{{ product.name }} — {{ product.category }} — R$ {{ product.price }}</p>
        {% else %}
          <p class="empty-note">Nenhum produto escolhido ainda. <a href="/vitrine/produtos">Ver produtos</a></p>
        {% endif %}

        <h3>Servi&ccedil;os</h3>
        {% if services %}
        <table class="admin-table">
          <thead><tr><th>Nome</th><th>Categoria</th><th>A&ccedil;&atilde;o</th></tr></thead>
          <tbody>
          {% for service in services %}
            <tr>
              <td>{{ service.name }}</td>
              <td>{{ service.category }}</td>
              <td>
                {% if project.status.value == "rascunho" %}
                <form method="post" action="/comprador/projeto/servicos/{{ service.id }}/remover">
                  <button class="mini-btn" type="submit">Remover</button>
                </form>
                {% endif %}
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
        {% else %}
        <p class="empty-note">Nenhum servi&ccedil;o adicionado ainda. <a href="/vitrine/servicos">Ver servi&ccedil;os</a></p>
        {% endif %}

        {% if project.status.value == "rascunho" %}
        <details style="margin-bottom:16px;">
          <summary class="eyebrow" style="cursor:pointer;">Atalho: descreva o que voc&ecirc; quer</summary>
          <form method="post" action="/comprador/projeto/buscar" style="margin-top:10px;">
            <div class="field">
              <textarea name="text" placeholder="Ex: piscina de fibra 6x3 em Valinhos, com instalacao"></textarea>
            </div>
            <button class="btn" type="submit">Buscar sugest&otilde;es</button>
          </form>
        </details>

        {% if sugestoes %}
        <h3>Sugest&otilde;es</h3>
        {% if sugestoes.produtos %}
        <ul>
          {% for p in sugestoes.produtos %}
          <li>
            {{ p.name }} — {{ p.category }} — R$ {{ p.price }}
            <form method="post" action="/comprador/projeto/produto" style="display:inline;">
              <input type="hidden" name="product_id" value="{{ p.id }}">
              <button class="mini-btn" type="submit">Escolher</button>
            </form>
          </li>
          {% endfor %}
        </ul>
        {% endif %}
        {% if sugestoes.servicos %}
        <ul>
          {% for s in sugestoes.servicos %}
          <li>
            {{ s.name }} — {{ s.category }}
            <form method="post" action="/comprador/projeto/servicos/{{ s.id }}/adicionar" style="display:inline;">
              <button class="mini-btn" type="submit">Adicionar</button>
            </form>
          </li>
          {% endfor %}
        </ul>
        {% endif %}
        {% endif %}

        <form method="post" action="/comprador/projeto/confirmar">
          <button class="btn accent" type="submit">Confirmar projeto</button>
        </form>
        {% endif %}
      </div>
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_comprador_projeto.py -v`
Expected: written per spec; all 5 need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 5 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/comprador_projeto.py src/piscinow/web/templates/comprador_projeto.html tests/web/test_comprador_projeto.py
git commit -m "feat: comprador project view and product selection"
```

---

### Task 10: Comprador routes — add/remove service

**Files:**
- Modify: `src/piscinow/web/routes/comprador_projeto.py`
- Test: `tests/web/test_comprador_projeto_servicos.py`

**Interfaces:**
- Consumes: `_get_or_create_project`, `require_comprador`, `Project`, `ProjectService`, `ProjectStatus` (Task 9/2), `Service` (existing).
- Produces: `POST /comprador/projeto/servicos/{service_id}/adicionar`, `POST /comprador/projeto/servicos/{service_id}/remover`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_projeto_servicos.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.models.project import Project, ProjectService
from piscinow.models.service import Service, ServiceKind
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_adicionar_servico_links_service_to_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/comprador/projeto/servicos/{service.id}/adicionar", follow_redirects=False)

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    link = db_session.query(ProjectService).filter(ProjectService.project_id == project.id).one()
    assert link.service_id == service.id


def test_adicionar_servico_duas_vezes_nao_duplica(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add(service)
    db_session.flush()

    client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")
    client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")

    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    count = db_session.query(ProjectService).filter(ProjectService.project_id == project.id).count()
    assert count == 1


def test_adicionar_servico_inativo_retorna_404(client, db_session):
    _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(
        member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Inativo", active=False
    )
    db_session.add(service)
    db_session.flush()

    response = client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")

    assert response.status_code == 404


def test_remover_servico_unlinks_service_from_project(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add(prestador)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao")
    db_session.add(service)
    db_session.flush()
    client.post(f"/comprador/projeto/servicos/{service.id}/adicionar")

    response = client.post(f"/comprador/projeto/servicos/{service.id}/remover", follow_redirects=False)

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    count = db_session.query(ProjectService).filter(ProjectService.project_id == project.id).count()
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_projeto_servicos.py -v`
Expected: FAIL — `404` on `/comprador/projeto/servicos/{id}/adicionar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/comprador_projeto.py`**

```python
@router.post("/projeto/servicos/{service_id}/adicionar")
async def adicionar_servico(
    service_id: str,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado, nao pode ser alterado.")
    try:
        parsed_id = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=404)
    service = db.get(Service, parsed_id)
    if service is None or not service.active:
        raise HTTPException(status_code=404)
    existing = db.scalar(
        select(ProjectService).where(
            ProjectService.project_id == project.id, ProjectService.service_id == service.id
        )
    )
    if existing is None:
        db.add(ProjectService(project_id=project.id, service_id=service.id))
    return RedirectResponse(url="/comprador/projeto", status_code=303)


@router.post("/projeto/servicos/{service_id}/remover")
async def remover_servico(
    service_id: str,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado, nao pode ser alterado.")
    try:
        parsed_id = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=404)
    link = db.scalar(
        select(ProjectService).where(
            ProjectService.project_id == project.id, ProjectService.service_id == parsed_id
        )
    )
    if link is not None:
        db.delete(link)
    return RedirectResponse(url="/comprador/projeto", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_comprador_projeto_servicos.py -v`
Expected: written per spec; all 4 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/comprador_projeto.py tests/web/test_comprador_projeto_servicos.py
git commit -m "feat: add and remove services on the comprador's project"
```

---

### Task 11: Comprador routes — confirm project

**Files:**
- Modify: `src/piscinow/web/routes/comprador_projeto.py`
- Test: `tests/web/test_comprador_projeto_confirmar.py`

**Interfaces:**
- Consumes: `_get_or_create_project`, `_project_services`, `require_comprador`, `Project`, `ProjectStatus` (Task 9), `Product` (existing).
- Produces: `POST /comprador/projeto/confirmar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_projeto_confirmar.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_confirmar_sem_produto_mostra_erro(client, db_session):
    _comprador_logged_in(client, db_session)
    client.get("/comprador/projeto")

    response = client.post("/comprador/projeto/confirmar")

    assert response.status_code == 400
    assert "Escolha um produto" in response.text


def test_confirmar_com_produto_muda_status(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    client.post("/comprador/projeto/produto", data={"product_id": str(product.id)})

    response = client.post("/comprador/projeto/confirmar", follow_redirects=False)

    assert response.status_code == 303
    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.status.value == "confirmado"


def test_alterar_produto_apos_confirmar_retorna_400(client, db_session):
    _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    outro_produto = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Outra Piscina", price=20000
    )
    db_session.add_all([product, outro_produto])
    db_session.flush()
    client.post("/comprador/projeto/produto", data={"product_id": str(product.id)})
    client.post("/comprador/projeto/confirmar")

    response = client.post("/comprador/projeto/produto", data={"product_id": str(outro_produto.id)})

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_projeto_confirmar.py -v`
Expected: FAIL — `404` on `/comprador/projeto/confirmar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/comprador_projeto.py`**

```python
@router.post("/projeto/confirmar")
async def confirmar_projeto(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    project = _get_or_create_project(db, comprador.id)
    if project.status != ProjectStatus.RASCUNHO:
        raise HTTPException(status_code=400, detail="Projeto ja confirmado.")
    if project.product_id is None:
        templates = request.app.state.templates
        services = _project_services(db, project.id)
        return templates.TemplateResponse(
            request,
            "comprador_projeto.html",
            {
                "project": project,
                "product": None,
                "services": services,
                "error": "Escolha um produto antes de confirmar o projeto.",
                "note": None,
                "sugestoes": None,
            },
            status_code=400,
        )
    project.status = ProjectStatus.CONFIRMADO
    return RedirectResponse(url="/comprador/projeto", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_comprador_projeto_confirmar.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/comprador_projeto.py tests/web/test_comprador_projeto_confirmar.py
git commit -m "feat: confirm comprador project, lock it against further edits"
```

---

### Task 12: Search-filter extraction (chat shortcut, agent side)

**Files:**
- Create: `src/piscinow/agent/project_search.py`
- Test: `tests/agent/test_project_search.py`

**Interfaces:**
- Consumes: `parse_json_object` (existing, sub-project 2 Task 1), `ChatMessage`, `LLMProvider` (existing).
- Produces: `piscinow.agent.project_search.extract_search_filters(llm: LLMProvider, text: str) -> dict` — always returns a dict with the three keys `kind`, `category`, `region` (each a string, empty when not present). Consumed by Task 13.

This task needs NO Docker — it only uses `FakeLLMProvider`, no database.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_project_search.py`**

```python
import pytest

from piscinow.agent.project_search import extract_search_filters
from piscinow.agent.providers.fake_provider import FakeLLMProvider


@pytest.mark.asyncio
async def test_extracts_search_filters_from_llm_json():
    provider = FakeLLMProvider(['{"kind": "piscina", "category": "fibra", "region": "Valinhos"}'])

    result = await extract_search_filters(provider, "piscina de fibra em Valinhos")

    assert result["kind"] == "piscina"
    assert result["category"] == "fibra"
    assert result["region"] == "Valinhos"


@pytest.mark.asyncio
async def test_extract_search_filters_returns_blank_fields_on_malformed_response():
    provider = FakeLLMProvider(["desculpe nao entendi"])

    result = await extract_search_filters(provider, "algo confuso")

    assert result == {"kind": "", "category": "", "region": ""}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/agent/test_project_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.project_search'`

- [ ] **Step 3: Write `src/piscinow/agent/project_search.py`**

```python
from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider

_SYSTEM_PROMPT = """Voce ajuda um comprador do Clube Piscinow a encontrar
produtos e servicos a partir de uma descricao em texto livre. Extraia os
filtros em JSON: {"kind": "piscina", "equipamento", "instalacao",
"manutencao" ou "reparo", "category": string, "region": string}.
Use null para campos que nao aparecem no texto. Responda APENAS com o JSON."""


async def extract_search_filters(llm: LLMProvider, text: str) -> dict:
    raw = await llm.generate([ChatMessage(role="user", content=text)], system=_SYSTEM_PROMPT)
    data = parse_json_object(raw)
    return {
        "kind": data.get("kind") or "",
        "category": data.get("category") or "",
        "region": data.get("region") or "",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/agent/test_project_search.py -v`
Expected: PASS (2 tests, real GREEN — no Docker needed for this task)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/project_search.py tests/agent/test_project_search.py
git commit -m "feat: search-filter extraction from free text for the comprador chat shortcut"
```

---

### Task 13: Comprador route — chat shortcut for project suggestions

**Files:**
- Modify: `src/piscinow/web/routes/comprador_projeto.py`
- Test: `tests/web/test_comprador_projeto_buscar.py`

**Interfaces:**
- Consumes: `extract_search_filters` (Task 12), `_get_or_create_project`, `_project_services`, `require_comprador` (Task 9), `get_llm_provider` (existing), `ProductKind`, `ServiceKind` (existing).
- Produces: `POST /comprador/projeto/buscar` — never adds a product or service to the project; always re-renders `comprador_projeto.html` with `sugestoes` populated from the search.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_projeto_buscar.py`**

```python
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectService
from piscinow.web.deps import get_llm_provider
from tests.web.test_comprador_projeto import _comprador_logged_in


def test_buscar_sugestoes_shows_matching_products(client, db_session):
    _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", region="Valinhos")
    db_session.add(loja)
    db_session.flush()
    product = Product(
        member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra 6x3", price=18000
    )
    db_session.add(product)
    db_session.flush()

    provider = FakeLLMProvider(['{"kind": "piscina", "category": "fibra", "region": "Valinhos"}'])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/comprador/projeto/buscar", data={"text": "piscina de fibra em Valinhos"})

    assert response.status_code == 200
    assert "Piscina Fibra 6x3" in response.text


def test_buscar_sugestoes_shows_note_when_no_match(client, db_session):
    _comprador_logged_in(client, db_session)
    provider = FakeLLMProvider(["desculpe nao entendi"])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/comprador/projeto/buscar", data={"text": "algo confuso"})

    assert response.status_code == 200
    assert "Nao encontrei nada" in response.text


def test_buscar_sugestoes_never_persists_a_choice(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()

    provider = FakeLLMProvider(['{"kind": "piscina", "category": "fibra", "region": null}'])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    client.post("/comprador/projeto/buscar", data={"text": "piscina de fibra"})

    project = db_session.query(Project).filter(Project.member_id == comprador.id).one()
    assert project.product_id is None
    assert db_session.query(ProjectService).filter(ProjectService.project_id == project.id).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_projeto_buscar.py -v`
Expected: FAIL — `404` on `/comprador/projeto/buscar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/comprador_projeto.py`**

Add these imports: `from piscinow.agent.llm_provider import LLMProvider`, `from piscinow.agent.project_search import extract_search_filters`, `from piscinow.models.product import ProductKind` (add `ProductKind` to the existing `from piscinow.models.product import Product` line), `from piscinow.models.service import ServiceKind` (add to the existing `from piscinow.models.service import Service` line), `from piscinow.rate_limit import limiter, chat_rate_limit_string`, and add `get_llm_provider` to the existing `from piscinow.web.deps import get_db` line. Append:

```python
@router.post("/projeto/buscar")
@limiter.limit(chat_rate_limit_string)
async def buscar_sugestoes(
    request: Request,
    text: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    product = db.get(Product, project.product_id) if project.product_id else None
    services = _project_services(db, project.id)
    filters = await extract_search_filters(llm, text)

    produtos_query = select(Product).join(Member, Product.member_id == Member.id).where(Product.active.is_(True))
    if filters["kind"] in {k.value for k in ProductKind}:
        produtos_query = produtos_query.where(Product.kind == ProductKind(filters["kind"]))
    if filters["category"]:
        produtos_query = produtos_query.where(Product.category.ilike(f"%{filters['category']}%"))
    if filters["region"]:
        produtos_query = produtos_query.where(Member.region.ilike(f"%{filters['region']}%"))
    produtos_sugeridos = list(db.scalars(produtos_query.limit(10)))

    servicos_query = select(Service).join(Member, Service.member_id == Member.id).where(Service.active.is_(True))
    if filters["kind"] in {k.value for k in ServiceKind}:
        servicos_query = servicos_query.where(Service.kind == ServiceKind(filters["kind"]))
    if filters["category"]:
        servicos_query = servicos_query.where(Service.category.ilike(f"%{filters['category']}%"))
    if filters["region"]:
        servicos_query = servicos_query.where(Member.region.ilike(f"%{filters['region']}%"))
    servicos_sugeridos = list(db.scalars(servicos_query.limit(10)))

    note = None
    if not produtos_sugeridos and not servicos_sugeridos:
        note = "Nao encontrei nada com esses filtros, tente ajustar."

    return templates.TemplateResponse(
        request,
        "comprador_projeto.html",
        {
            "project": project,
            "product": product,
            "services": services,
            "error": None,
            "note": note,
            "sugestoes": {"produtos": produtos_sugeridos, "servicos": servicos_sugeridos},
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_comprador_projeto_buscar.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/comprador_projeto.py tests/web/test_comprador_projeto_buscar.py
git commit -m "feat: chat shortcut for project suggestions, always confirmed before adding"
```

---

### Task 14: Register the vitrine and comprador_projeto routers

**Files:**
- Modify: `src/piscinow/web/app.py`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: `piscinow.web.routes.vitrine.router` (Task 7), `piscinow.web.routes.comprador.router` (Task 5), `piscinow.web.routes.comprador_projeto.router` (Task 9).

- [ ] **Step 1: Write the failing tests** — append to `tests/web/test_app.py`

```python
def test_app_serves_vitrine_produtos_page(client):
    response = client.get("/vitrine/produtos")
    assert response.status_code == 200


def test_app_serves_comprador_login_page(client):
    response = client.get("/comprador/login")
    assert response.status_code == 200
    assert "Painel do comprador" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_app.py -v`
Expected: the two new tests FAIL with a `404` (routers not registered yet); the pre-existing tests still pass.

- [ ] **Step 3: Modify `src/piscinow/web/app.py`**

Change `from piscinow.web.routes import admin, chat, loja, pages, prestador` to:

```python
from piscinow.web.routes import admin, chat, comprador, comprador_projeto, loja, pages, prestador, vitrine
```

Add `app.include_router(vitrine.router)`, `app.include_router(comprador.router)`, and `app.include_router(comprador_projeto.router)` alongside the existing `app.include_router(...)` lines inside `create_app()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_app.py -v`
Expected: `test_app_serves_vitrine_produtos_page` PASSES for real (no auth, no DB write needed — but the shared `client` fixture still resolves `db_session`, so confirm PASS or a fixture-level Docker error consistently, matching what earlier tasks in this plan observed for this exact fixture composition). `test_app_serves_comprador_login_page` — same.

- [ ] **Step 5: Run the whole-suite collection check**

Run: `py -m pytest --collect-only -q`
Expected: every test in the project collects with zero errors (confirms this task, and every prior task in this plan, introduced no import/syntax mistakes anywhere — this should be strictly more tests than the 166 collected at the end of sub-project 3).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/app.py tests/web/test_app.py
git commit -m "feat: register the vitrine and comprador_projeto routers"
```

---

## Self-Review Notes

- **Spec coverage:** every requirement in the spec maps to a task — the `Member.region` fix (Task 1); comprador own account, set-password onboarding with global email uniqueness and profile/status-filtered token lookup from the start (Tasks 3, 4, 5); login rate-limited from the start (Task 6); public storefront without price, with basic kind/category/region filters (Tasks 7, 8); project structure (one product + N services, one project per comprador via `unique=True`) (Task 2); project assembly (Tasks 9, 10); confirm-locks-the-project (Task 11); chat shortcut that only ever suggests, never adds automatically, rate-limited from the start (Tasks 12, 13); admin visibility into pending/active compradores (Task 4).
- **Type/interface consistency check:** `Project`/`ProjectService` field names are used identically across Tasks 9, 10, 11, 13. `_get_or_create_project(db, member_id) -> Project` and `_project_services(db, project_id) -> list[Service]` (Task 9) are reused as-is by Tasks 10, 11, 13 — no task redefines or duplicates them. `extract_search_filters`'s three-key return shape (Task 12) matches exactly what Task 13 destructures. `comprador_projeto.html`'s context shape (`project`, `product`, `services`, `error`, `note`, `sugestoes`) is established in Task 9 and every later task that renders this template (11, 13) passes the exact same five keys, never a subset.
- **Placeholder scan:** no TBD/TODO markers. The lessons from sub-project 3's final-review fix wave (rate limiting on login and chat from the first commit, profile/status filtering on the token lookup, global not per-profile duplicate-email check, malformed-id-to-404 via UUID validation before `db.get`) are built into Tasks 3, 4, 5, 6, 9, 10, 13 directly, rather than left as a follow-up fix wave.
