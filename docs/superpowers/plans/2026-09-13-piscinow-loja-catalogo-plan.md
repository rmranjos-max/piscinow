# Loja Onboarding + Catálogo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an approved loja (store) set her own password, log in, and manage a product catalog (piscinas/equipamentos) through plain web forms and a chat shortcut that extracts fields from free text — never auto-saving.

**Architecture:** Adds authentication capability directly to the existing `Member` model (password + one-time set-password token), a new `Product` model, a `loja_auth` module mirroring the existing `auth.py` (admin) pattern, and a `/loja/*` route group in the same FastAPI monolith. The chat shortcut reuses the Agent Core's `LLMProvider` and a newly-extracted shared tolerant-JSON parser.

**Tech Stack:** Same as sub-project 1 — Python 3.12, FastAPI, SQLAlchemy 2.0, Postgres 16 + pgvector, Jinja2, argon2-cffi.

**Spec:** [docs/superpowers/specs/2026-09-13-piscinow-loja-catalogo-design.md](../specs/2026-09-13-piscinow-loja-catalogo-design.md)

## Global Constraints

- Reuses the existing Postgres+pgvector datastore — no new datastore, no new infra.
- Loja authentication mirrors the existing admin auth pattern exactly: argon2 password hashing, session-based login (`request.session`), a `require_loja` FastAPI dependency that raises `HTTPException(303, headers={"Location": "/loja/login"})` when unauthenticated — same shape as `require_admin`.
- No email-sending infrastructure in this phase — the admin panel displays the set-password link for the team to copy and send manually.
- No public storefront in this sub-project — `/loja/*` routes are all behind `require_loja`; nothing here is visible to an anonymous visitor. The public storefront is sub-project 4.
- All user-facing text (templates, error messages) is Portuguese (pt-BR).
- TDD throughout: write the failing test before the implementation, every task.
- Same environment constraint as sub-project 1: no Docker/Postgres on this development machine. Tests that don't need `db_session` must show real RED→GREEN with `py -m pytest` (using the Python Launcher — bare `python`/`python3` are broken on this machine). Tests that do need `db_session` are written and reviewed carefully but will fail at fixture setup with a Docker connection error here; that failure mode is expected and does not block a task.
- Ownership checks on loja-scoped resources return 404 (not 403) for a resource that exists but isn't owned by the logged-in loja — never reveal that it exists.

---

### Task 1: Shared tolerant JSON extraction helper

**Files:**
- Create: `src/piscinow/agent/json_extraction.py`
- Modify: `src/piscinow/agent/handlers/base.py`
- Test: `tests/agent/test_json_extraction.py`

**Interfaces:**
- Produces: `piscinow.agent.json_extraction.parse_json_object(raw: str) -> dict` — finds the first `{...}` blob in `raw` and parses it, returning `{}` on no match or a parse error. Consumed by `ConversationHandler._parse_json` (this task) and by Task 11's `extract_product_fields`.

This extracts the regex-based tolerant JSON parsing that `ConversationHandler._parse_json` (from sub-project 1, Task 14) already implements, into a shared module — so Task 11's product-field extractor doesn't duplicate the same regex/try-except logic.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_json_extraction.py`**

```python
from piscinow.agent.json_extraction import parse_json_object


def test_parses_clean_json_object():
    assert parse_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extracts_json_surrounded_by_extra_text():
    raw = 'aqui esta: {"name": "Marina"} obrigado'
    assert parse_json_object(raw) == {"name": "Marina"}


def test_returns_empty_dict_for_non_json_text():
    assert parse_json_object("desculpe nao entendi") == {}


def test_returns_empty_dict_for_malformed_json():
    assert parse_json_object('{"a": }') == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/agent/test_json_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.json_extraction'`

- [ ] **Step 3: Write `src/piscinow/agent/json_extraction.py`**

```python
import json
import re


def parse_json_object(raw: str) -> dict:
    """Tolerant JSON-object extraction from LLM output: finds the first
    {...} blob in the text and parses it, returning {} on any failure."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/agent/test_json_extraction.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Modify `src/piscinow/agent/handlers/base.py`** — delegate `_parse_json` to the shared helper

Add `from piscinow.agent.json_extraction import parse_json_object` to the top imports. Replace the existing `_parse_json` static method body:

```python
    @staticmethod
    def _parse_json(raw: str) -> dict:
        return parse_json_object(raw)
```

(Remove the now-unused `import json` and `import re` from this file if nothing else in it uses them.)

- [ ] **Step 6: Run the existing handler tests to confirm no regression**

Run: `py -m pytest tests/agent/test_handlers_base.py -v`
Expected: PASS (5 tests, unchanged behavior)

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/agent/json_extraction.py src/piscinow/agent/handlers/base.py tests/agent/test_json_extraction.py
git commit -m "refactor: extract shared tolerant JSON parser for reuse by the product extractor"
```

---

### Task 2: Member authentication (password + set-password token)

**Files:**
- Modify: `src/piscinow/models/member.py`
- Test: `tests/models/test_member.py`

**Interfaces:**
- Produces (new on `Member`): `password_hash: str | None`, `set_password_token: str | None`, `set_password_token_expires_at: datetime | None` columns; `generate_set_password_token() -> str`, `consume_set_password_token(token: str) -> bool`, `set_password(password: str) -> None`, `verify_password(password: str) -> bool`. Consumed by Task 4 (`loja_auth`), Task 5 (admin approval), Task 6 (definir-senha routes).

- [ ] **Step 1: Write the failing tests** — append to `tests/models/test_member.py`

```python
from datetime import datetime, timedelta, timezone

from piscinow.models.member import Member, ProfileType


def make_loja_member(**kwargs):
    defaults = dict(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    defaults.update(kwargs)
    return Member(**defaults)


def test_generate_set_password_token_sets_token_and_future_expiry():
    member = make_loja_member()
    token = member.generate_set_password_token()
    assert member.set_password_token == token
    assert member.set_password_token_expires_at > datetime.now(timezone.utc)


def test_consume_set_password_token_accepts_valid_token():
    member = make_loja_member()
    token = member.generate_set_password_token()
    assert member.consume_set_password_token(token) is True


def test_consume_set_password_token_rejects_wrong_token():
    member = make_loja_member()
    member.generate_set_password_token()
    assert member.consume_set_password_token("token-errado") is False


def test_consume_set_password_token_rejects_expired_token():
    member = make_loja_member()
    token = member.generate_set_password_token()
    member.set_password_token_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert member.consume_set_password_token(token) is False


def test_consume_set_password_token_rejects_when_none_set():
    member = make_loja_member()
    assert member.consume_set_password_token("qualquer-coisa") is False


def test_set_password_hashes_and_clears_token():
    member = make_loja_member()
    member.generate_set_password_token()
    member.set_password("senha-forte-123")
    assert member.password_hash is not None
    assert member.password_hash != "senha-forte-123"
    assert member.set_password_token is None
    assert member.set_password_token_expires_at is None


def test_verify_password_accepts_correct_password():
    member = make_loja_member()
    member.set_password("senha-forte-123")
    assert member.verify_password("senha-forte-123") is True


def test_verify_password_rejects_wrong_password():
    member = make_loja_member()
    member.set_password("senha-forte-123")
    assert member.verify_password("errada") is False


def test_verify_password_returns_false_when_no_password_set():
    member = make_loja_member()
    assert member.verify_password("qualquer-coisa") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/models/test_member.py -v`
Expected: the 9 new tests FAIL with `AttributeError` (methods don't exist yet); the pre-existing tests still pass.

- [ ] **Step 3: Modify `src/piscinow/models/member.py`**

Add to the top imports: `import secrets`, and extend the existing `from datetime import datetime` line to `from datetime import datetime, timedelta, timezone`. Add:

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
```

Add a module-level hasher (near the top, after imports, before the `ProfileType` enum):

```python
_hasher = PasswordHasher()
```

Add these three new columns inside the `Member` class, alongside the existing `approved_by` column:

```python
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    set_password_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    set_password_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Add these four methods, alongside the existing `submit_for_review`/`approve`/`reject`/`auto_approve_via_referral` methods:

```python
    def generate_set_password_token(self) -> str:
        token = secrets.token_urlsafe(32)
        self.set_password_token = token
        self.set_password_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        return token

    def consume_set_password_token(self, token: str) -> bool:
        if not self.set_password_token or not self.set_password_token_expires_at:
            return False
        if self.set_password_token != token:
            return False
        if datetime.now(timezone.utc) > self.set_password_token_expires_at:
            return False
        return True

    def set_password(self, password: str) -> None:
        self.password_hash = _hasher.hash(password)
        self.set_password_token = None
        self.set_password_token_expires_at = None

    def verify_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        try:
            return _hasher.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/models/test_member.py -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/models/member.py tests/models/test_member.py
git commit -m "feat: password and set-password-token authentication on Member"
```

---

### Task 3: Product model

**Files:**
- Create: `src/piscinow/models/product.py`
- Modify: `tests/conftest.py` (add the new model import)
- Test: `tests/models/test_product.py`

**Interfaces:**
- Consumes: `piscinow.db.Base`, `piscinow.models.member.Member` (for the `member_id` foreign key).
- Produces: `piscinow.models.product.ProductKind` (str enum: `PISCINA`, `EQUIPAMENTO`), `piscinow.models.product.Product` (fields: `id`, `member_id`, `kind`, `category: str`, `name: str`, `description: str | None`, `price`, `size_label: str | None`, `active: bool`, `created_at`, `updated_at`). Consumed by Tasks 5, 8, 9, 10, 12.

- [ ] **Step 1: Write the failing test — `tests/models/test_product.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.models.product import Product, ProductKind


def test_product_persists_and_reloads(db_session):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()

    product = Product(
        member_id=loja.id,
        kind=ProductKind.PISCINA,
        category="fibra",
        name="Piscina Fibra 6x3",
        price=18000.00,
        size_label="6x3m",
    )
    db_session.add(product)
    db_session.flush()
    db_session.expunge(product)

    reloaded = db_session.get(Product, product.id)

    assert reloaded.name == "Piscina Fibra 6x3"
    assert reloaded.category == "fibra"
    assert reloaded.active is True
    assert reloaded.member_id == loja.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/models/test_product.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.product'`

- [ ] **Step 3: Write `src/piscinow/models/product.py`**

```python
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


class ProductKind(str, enum.Enum):
    PISCINA = "piscina"
    EQUIPAMENTO = "equipamento"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    kind: Mapped[ProductKind] = mapped_column(SAEnum(ProductKind, name="product_kind"))
    category: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    size_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
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

Add `import piscinow.models.product  # noqa: E402,F401` alongside the other `import piscinow.models...` lines (member, conversation, memory, admin) so `Base.metadata.create_all` in the `engine` fixture picks up the new `products` table.

- [ ] **Step 5: Run test to verify it passes**

Run: `py -m pytest tests/models/test_product.py -v`
Expected: written per spec; this test needs `db_session` (Postgres) — on this machine it fails at fixture setup with a Docker connection error, not a logic error. Confirm the failure is fixture-level (e.g. `docker.errors.DockerException`), not a collection/import error.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/models/product.py tests/models/test_product.py tests/conftest.py
git commit -m "feat: Product model"
```

---

### Task 4: `loja_auth` module

**Files:**
- Create: `src/piscinow/loja_auth.py`
- Test: `tests/test_loja_auth.py`

**Interfaces:**
- Consumes: `Member`, `MemberStatus`, `ProfileType` (Task 2/existing), `get_db` (existing, Task 20 of sub-project 1).
- Produces: `piscinow.loja_auth.LOJA_SESSION_KEY: str`, `login(request, db, email, password) -> bool`, `logout(request) -> None`, `require_loja(request, db=Depends(get_db)) -> Member`. Consumed by every `/loja/*` route (Tasks 6-10, 12).

This mirrors `src/piscinow/auth.py` (sub-project 1, Task 23) exactly, but scoped to `Member` rows with `profile_type=LOJA` and `status=APPROVED` instead of `AdminUser`.

- [ ] **Step 1: Write the failing tests — `tests/test_loja_auth.py`**

```python
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from piscinow.loja_auth import LOJA_SESSION_KEY, login, logout


class _FakeSession(dict):
    pass


class _FakeRequest:
    def __init__(self):
        self.session = _FakeSession()


def test_login_sets_session_key_on_success(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "loja@example.com", "senha-forte-123")

    assert result is True
    assert request.session[LOJA_SESSION_KEY] == str(member.id)


def test_login_fails_for_wrong_password(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "loja@example.com", "errada")

    assert result is False
    assert LOJA_SESSION_KEY not in request.session


def test_login_fails_for_non_loja_profile(db_session):
    from piscinow.models.member import Member, MemberStatus, ProfileType

    member = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.APPROVED, email="marina@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    request = _FakeRequest()
    result = login(request, db_session, "marina@example.com", "senha-forte-123")

    assert result is False


def test_logout_removes_session_key():
    request = _FakeRequest()
    request.session[LOJA_SESSION_KEY] = "some-id"
    logout(request)
    assert LOJA_SESSION_KEY not in request.session
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_loja_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.loja_auth'`

- [ ] **Step 3: Write `src/piscinow/loja_auth.py`**

```python
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

LOJA_SESSION_KEY = "loja_member_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    member = db.scalar(
        select(Member).where(
            Member.email == email,
            Member.profile_type == ProfileType.LOJA,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.verify_password(password):
        return False
    request.session[LOJA_SESSION_KEY] = str(member.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(LOJA_SESSION_KEY, None)


def require_loja(request: Request, db: Session = Depends(get_db)) -> Member:
    member_id = request.session.get(LOJA_SESSION_KEY)
    if not member_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/loja/login"})
    member = db.get(Member, member_id)
    if member is None or member.profile_type != ProfileType.LOJA or member.status != MemberStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/loja/login"})
    return member
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_loja_auth.py -v`
Expected: written per spec; all 4 tests need `db_session` (Postgres) — on this machine they fail at fixture setup with a Docker connection error. Confirm it's fixture-level, not a collection/import error (e.g. run `py -m pytest tests/test_loja_auth.py --collect-only -q` and confirm all 4 tests are collected with no error).

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/loja_auth.py tests/test_loja_auth.py
git commit -m "feat: loja_auth module mirroring the admin auth pattern"
```

---

### Task 5: Admin extension — set-password token on approval + `/admin/lojas` view

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_lojas.html`
- Modify: `src/piscinow/web/templates/admin_queue.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_corrections.html` (nav link)
- Test: `tests/web/test_admin_lojas.py`

**Interfaces:**
- Consumes: `Member.generate_set_password_token` (Task 2), `get_settings` (existing, Task 1 of sub-project 1 — specifically `settings.public_base_url`, added in sub-project 1's final review fix wave).
- Produces: `GET /admin/lojas` (lists approved lojas with their set-password link when still pending).

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_lojas.py`**

```python
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_aprovar_loja_generates_set_password_token(client, db_session):
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


def test_lojas_page_shows_set_password_link_when_pending(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.get("/admin/lojas")

    assert "Studio Fibra Sul" in response.text
    assert f"/loja/definir-senha/{token}" in response.text


def test_lojas_page_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/lojas", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_lojas.py -v`
Expected: FAIL — `404` on `/admin/lojas`, and `test_aprovar_loja_generates_set_password_token` fails because `aprovar` doesn't generate a token yet.

- [ ] **Step 3: Modify `src/piscinow/web/routes/admin.py`**

Find the existing `aprovar` route (from sub-project 1, Task 24):

```python
@router.post("/fila/{member_id}/aprovar")
async def aprovar(
    member_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
    return RedirectResponse(url="/admin/fila", status_code=303)
```

Change its body to:

```python
@router.post("/fila/{member_id}/aprovar")
async def aprovar(
    member_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    member = db.get(Member, member_id)
    if member is not None:
        member.approve(approved_by=admin.email)
        if member.profile_type == ProfileType.LOJA:
            member.generate_set_password_token()
    return RedirectResponse(url="/admin/fila", status_code=303)
```

Add `from piscinow.config import get_settings` to the imports if not already present. Append this new route at the end of the file:

```python
@router.get("/lojas", response_class=HTMLResponse)
async def lojas(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    items = list(
        db.scalars(
            select(Member)
            .where(Member.profile_type == ProfileType.LOJA, Member.status == MemberStatus.APPROVED)
            .order_by(Member.approved_at.desc())
        )
    )
    base_url = get_settings().public_base_url
    return templates.TemplateResponse(request, "admin_lojas.html", {"members": items, "base_url": base_url})
```

(`ProfileType`, `MemberStatus`, `select`, `Member`, `HTMLResponse` are all already imported in this file from earlier sub-project-1 tasks — confirm each is present rather than re-importing duplicates.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_lojas.html`**

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
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Lojas aprovadas</h1>
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
                <span class="mono">{{ base_url }}/loja/definir-senha/{{ member.set_password_token }}</span>
              {% else %}
                Sem acesso gerado
              {% endif %}
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhuma loja aprovada ainda.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Add a "Lojas" nav link to the existing admin templates**

In `src/piscinow/web/templates/admin_queue.html` and `src/piscinow/web/templates/admin_corrections.html`, find the `<nav class="admin-nav">` block (currently two links: "Fila de admiss&atilde;o" and "Ensinar o concierge") and add the new link between them, matching `admin_lojas.html`'s nav exactly:

```html
      <nav class="admin-nav">
        <a href="/admin/fila">Fila de admiss&atilde;o</a>
        <a href="/admin/lojas">Lojas</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_lojas.py -v`
Expected: written per spec; all 4 tests need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows all 4 collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_lojas.html src/piscinow/web/templates/admin_queue.html src/piscinow/web/templates/admin_corrections.html tests/web/test_admin_lojas.py
git commit -m "feat: generate loja set-password token on approval, add /admin/lojas view"
```

---

### Task 6: Loja routes — `/loja/definir-senha/{token}`

**Files:**
- Create: `src/piscinow/web/routes/loja.py`
- Create: `src/piscinow/web/templates/loja_definir_senha.html`
- Test: `tests/web/test_loja_definir_senha.py`

**Interfaces:**
- Consumes: `Member`, `MemberStatus`, `ProfileType` (Task 2), `get_db` (existing).
- Produces: `piscinow.web.routes.loja.router` (an `APIRouter(prefix="/loja")` — Tasks 7-10 and 12 append more routes to this same object), `GET/POST /loja/definir-senha/{token}`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_loja_definir_senha.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType


def test_definir_senha_form_rejects_invalid_token(client):
    response = client.get("/loja/definir-senha/token-invalido")
    assert response.status_code == 400


def test_definir_senha_sets_email_and_password(client, db_session):
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "loja@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/loja/login"
    db_session.refresh(member)
    assert member.email == "loja@example.com"
    assert member.verify_password("senha-forte-123") is True
    assert member.set_password_token is None


def test_definir_senha_rejects_mismatched_passwords(client, db_session):
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "loja@example.com", "password": "senha-forte-123", "password_confirm": "outra-senha"},
    )

    assert response.status_code == 400
    assert "nao coincidem" in response.text
    db_session.refresh(member)
    assert member.email is None


def test_definir_senha_rejects_duplicate_email(client, db_session):
    outra = Member(
        profile_type=ProfileType.LOJA, name="Outra Loja", status=MemberStatus.APPROVED, email="ja-usado@example.com"
    )
    db_session.add(outra)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED)
    token = member.generate_set_password_token()
    db_session.add(member)
    db_session.flush()

    response = client.post(
        f"/loja/definir-senha/{token}",
        data={"email": "ja-usado@example.com", "password": "senha-forte-123", "password_confirm": "senha-forte-123"},
    )

    assert response.status_code == 400
    assert "ja esta em uso" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_loja_definir_senha.py -v`
Expected: FAIL — `404` on `/loja/definir-senha/...` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/web/routes/loja.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, ProfileType
from piscinow.web.deps import get_db

router = APIRouter(prefix="/loja")


@router.get("/definir-senha/{token}", response_class=HTMLResponse)
async def definir_senha_form(token: str, request: Request, db: Session = Depends(get_db)):
    templates = request.app.state.templates
    member = db.scalar(select(Member).where(Member.set_password_token == token))
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "loja_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    return templates.TemplateResponse(
        request, "loja_definir_senha.html", {"token": token, "invalid": False, "error": None}
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
    member = db.scalar(select(Member).where(Member.set_password_token == token))
    if member is None or not member.consume_set_password_token(token):
        return templates.TemplateResponse(
            request, "loja_definir_senha.html", {"token": token, "invalid": True, "error": None}, status_code=400
        )
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "loja_definir_senha.html",
            {"token": token, "invalid": False, "error": "As senhas nao coincidem."},
            status_code=400,
        )
    existing = db.scalar(
        select(Member).where(
            Member.email == email,
            Member.profile_type == ProfileType.LOJA,
            Member.id != member.id,
        )
    )
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "loja_definir_senha.html",
            {"token": token, "invalid": False, "error": "Esse e-mail ja esta em uso por outra loja."},
            status_code=400,
        )
    member.email = email
    member.set_password(password)
    return RedirectResponse(url="/loja/login", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/loja_definir_senha.html`**

```html
{% extends "base.html" %}
{% block content %}
<main class="admin-shell">
  <div class="wrap narrow">
    <div class="login-card">
      <h1>Definir senha</h1>
      {% if invalid %}
        <p class="error">Link invalido ou expirado. Peca um novo a equipe Piscinow.</p>
      {% else %}
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="post" action="/loja/definir-senha/{{ token }}">
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

Run: `py -m pytest tests/web/test_loja_definir_senha.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 4 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/loja.py src/piscinow/web/templates/loja_definir_senha.html tests/web/test_loja_definir_senha.py
git commit -m "feat: loja set-password onboarding route"
```

---

### Task 7: Loja routes — login/logout

**Files:**
- Modify: `src/piscinow/web/routes/loja.py`
- Create: `src/piscinow/web/templates/loja_login.html`
- Test: `tests/web/test_loja_login.py`

**Interfaces:**
- Consumes: `login`, `logout` (Task 4, `loja_auth`).
- Produces: `GET/POST /loja/login`, `POST /loja/logout`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_loja_login.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType


def test_login_with_correct_credentials_redirects_to_produtos(client, db_session):
    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post(
        "/loja/login", data={"email": "loja@example.com", "password": "senha-forte-123"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/loja/produtos"


def test_login_with_wrong_password_shows_error(client, db_session):
    member = Member(
        profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email="loja@example.com"
    )
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()

    response = client.post("/loja/login", data={"email": "loja@example.com", "password": "errada"})

    assert response.status_code == 401
    assert "invalidos" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_loja_login.py -v`
Expected: FAIL — `404` on `/loja/login`

- [ ] **Step 3: Append to `src/piscinow/web/routes/loja.py`**

Add `from piscinow.loja_auth import login as do_login, logout as do_logout` to the imports. Append:

```python
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "loja_login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/loja/produtos", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "loja_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/loja/login", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/loja_login.html`**

```html
{% extends "base.html" %}
{% block content %}
<main class="admin-shell">
  <div class="wrap narrow">
    <div class="login-card">
      <h1>Painel da loja</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/loja/login">
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_loja_login.py -v`
Expected: written per spec; both need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/loja.py src/piscinow/web/templates/loja_login.html tests/web/test_loja_login.py
git commit -m "feat: loja login/logout"
```

---

### Task 8: Loja routes — list + create products

**Files:**
- Modify: `src/piscinow/web/routes/loja.py`
- Create: `src/piscinow/web/templates/loja_produtos.html`
- Test: `tests/web/test_loja_produtos.py`

**Interfaces:**
- Consumes: `require_loja` (Task 4), `Product`, `ProductKind` (Task 3).
- Produces: `GET /loja/produtos`, `POST /loja/produtos`. The `GET` handler renders `loja_produtos.html` with context `{"products": [...], "error": None, "prefill": {}, "note": None}` — Task 9 and Task 12 reuse this same template and context shape.

- [ ] **Step 1: Write the failing tests — `tests/web/test_loja_produtos.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product


def _loja_logged_in(client, db_session, *, email="loja@example.com", password="senha-forte-123"):
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.APPROVED, email=email)
    loja.set_password(password)
    db_session.add(loja)
    db_session.flush()
    client.post("/loja/login", data={"email": email, "password": password})
    return loja


def test_produtos_redirects_to_login_when_not_authenticated(client):
    response = client.get("/loja/produtos", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/loja/login"


def test_criar_produto_persists_and_lists(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={
            "kind": "piscina",
            "category": "fibra",
            "name": "Piscina Fibra 6x3",
            "price": "18000.00",
            "size_label": "6x3m",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    product = db_session.query(Product).filter(Product.name == "Piscina Fibra 6x3").one()
    assert product.category == "fibra"
    assert product.active is True

    listing = client.get("/loja/produtos")
    assert "Piscina Fibra 6x3" in listing.text


def test_criar_produto_with_invalid_price_shows_error_and_does_not_save(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", "price": "abc"},
    )
    assert response.status_code == 400
    assert "preco valido" in response.text
    assert db_session.query(Product).count() == 0


def test_criar_produto_with_invalid_kind_shows_error(client, db_session):
    _loja_logged_in(client, db_session)

    response = client.post(
        "/loja/produtos",
        data={"kind": "barco", "category": "fibra", "name": "Nao E Piscina", "price": "1000"},
    )
    assert response.status_code == 400
    assert db_session.query(Product).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_loja_produtos.py -v`
Expected: FAIL — `404` on `/loja/produtos`

- [ ] **Step 3: Append to `src/piscinow/web/routes/loja.py`**

Add these imports: `from decimal import Decimal, InvalidOperation`, and `from piscinow.loja_auth import require_loja`, and `from piscinow.models.product import Product, ProductKind`. Append:

```python
@router.get("/produtos", response_class=HTMLResponse)
async def produtos(
    request: Request,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    templates = request.app.state.templates
    items = list(
        db.scalars(select(Product).where(Product.member_id == loja.id).order_by(Product.created_at.desc()))
    )
    return templates.TemplateResponse(
        request, "loja_produtos.html", {"products": items, "error": None, "prefill": {}, "note": None}
    )


@router.post("/produtos")
async def criar_produto(
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price: str = Form(...),
    description: str = Form(""),
    size_label: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    templates = request.app.state.templates
    error = None
    parsed_price = None

    if kind not in {k.value for k in ProductKind}:
        error = "Selecione um tipo de produto valido."
    elif not category.strip() or not name.strip():
        error = "Preencha categoria e nome do produto."
    else:
        try:
            parsed_price = Decimal(price.replace(",", "."))
            if parsed_price <= 0:
                error = "Informe um preco valido."
        except (InvalidOperation, ValueError):
            error = "Informe um preco valido."

    if error:
        items = list(
            db.scalars(select(Product).where(Product.member_id == loja.id).order_by(Product.created_at.desc()))
        )
        prefill = {
            "kind": kind,
            "category": category,
            "name": name,
            "price": price,
            "description": description,
            "size_label": size_label,
        }
        return templates.TemplateResponse(
            request,
            "loja_produtos.html",
            {"products": items, "error": error, "prefill": prefill, "note": None},
            status_code=400,
        )

    product = Product(
        member_id=loja.id,
        kind=ProductKind(kind),
        category=category.strip(),
        name=name.strip(),
        price=parsed_price,
        description=description.strip() or None,
        size_label=size_label.strip() or None,
    )
    db.add(product)
    return RedirectResponse(url="/loja/produtos", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/loja_produtos.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="admin-shell">
  <header class="admin-topbar">
    <div class="wrap">
      <a class="brand" href="/loja/produtos">Piscinow <span class="badge">Loja</span></a>
      <form method="post" action="/loja/logout"><button class="mini-btn" type="submit">Sair</button></form>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Meus produtos</h1>

      <div class="teach-form">
        <h2 style="font-size:1.1rem; margin-bottom:14px;">Cadastrar produto</h2>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        {% if note %}<p class="error">{{ note }}</p>{% endif %}

        <details style="margin-bottom:16px;">
          <summary class="eyebrow" style="cursor:pointer;">Atalho: descreva em texto livre</summary>
          <form method="post" action="/loja/produtos/chat" style="margin-top:10px;">
            <div class="field">
              <textarea name="text" placeholder="Ex: piscina de fibra 6x3, R$18 mil"></textarea>
            </div>
            <button class="btn" type="submit">Extrair campos</button>
          </form>
        </details>

        <form method="post" action="/loja/produtos">
          <div class="field">
            <label for="kind">Tipo</label>
            <select id="kind" name="kind">
              <option value="piscina" {% if prefill.get("kind") == "piscina" %}selected{% endif %}>Piscina</option>
              <option value="equipamento" {% if prefill.get("kind") == "equipamento" %}selected{% endif %}>Equipamento</option>
            </select>
          </div>
          <div class="field">
            <label for="category">Categoria</label>
            <input id="category" type="text" name="category" value="{{ prefill.get('category', '') }}" placeholder="fibra, vinil, alvenaria, filtragem...">
          </div>
          <div class="field">
            <label for="name">Nome</label>
            <input id="name" type="text" name="name" value="{{ prefill.get('name', '') }}">
          </div>
          <div class="field">
            <label for="price">Preco (R$)</label>
            <input id="price" type="text" name="price" value="{{ prefill.get('price', '') }}">
          </div>
          <div class="field">
            <label for="size_label">Tamanho (opcional)</label>
            <input id="size_label" type="text" name="size_label" value="{{ prefill.get('size_label', '') }}" placeholder="6x3m">
          </div>
          <div class="field">
            <label for="description">Descricao (opcional)</label>
            <textarea id="description" name="description">{{ prefill.get('description', '') }}</textarea>
          </div>
          <button class="btn accent" type="submit">Salvar produto</button>
        </form>
      </div>

      {% if products %}
      <table class="admin-table">
        <thead><tr><th>Nome</th><th>Categoria</th><th>Preco</th><th>Status</th><th>A&ccedil;&atilde;o</th></tr></thead>
        <tbody>
        {% for product in products %}
          <tr>
            <td>{{ product.name }}</td>
            <td>{{ product.category }}</td>
            <td>R$ {{ product.price }}</td>
            <td>{{ "Ativo" if product.active else "Inativo" }}</td>
            <td>
              <div class="row-actions">
                <a class="mini-btn" href="/loja/produtos/{{ product.id }}/editar">Editar</a>
                {% if product.active %}
                <form method="post" action="/loja/produtos/{{ product.id }}/desativar">
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
      <p class="empty-note">Nenhum produto cadastrado ainda.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_loja_produtos.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 4 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/loja.py src/piscinow/web/templates/loja_produtos.html tests/web/test_loja_produtos.py
git commit -m "feat: loja product catalog list and create"
```

---

### Task 9: Loja routes — edit product

**Files:**
- Modify: `src/piscinow/web/routes/loja.py`
- Create: `src/piscinow/web/templates/loja_produto_editar.html`
- Test: `tests/web/test_loja_produto_editar.py`

**Interfaces:**
- Consumes: `require_loja`, `Product`, `ProductKind` (as above).
- Produces: `GET /loja/produtos/{product_id}/editar`, `POST /loja/produtos/{product_id}/editar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_loja_produto_editar.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from tests.web.test_loja_produtos import _loja_logged_in


def test_editar_produto_form_shows_current_values(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Antigo", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.get(f"/loja/produtos/{product.id}/editar")

    assert response.status_code == 200
    assert "Antigo" in response.text


def test_editar_produto_updates_fields(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Antigo", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        f"/loja/produtos/{product.id}/editar",
        data={"kind": "piscina", "category": "fibra", "name": "Novo Nome", "price": "12000.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(product)
    assert product.name == "Novo Nome"
    assert product.price == 12000


def test_editar_produto_de_outra_loja_retorna_404(client, db_session):
    _loja_logged_in(client, db_session, email="loja1@example.com")

    outra_loja = Member(profile_type=ProfileType.LOJA, name="Outra Loja", status=MemberStatus.APPROVED)
    db_session.add(outra_loja)
    db_session.flush()
    product = Product(member_id=outra_loja.id, kind=ProductKind.PISCINA, category="fibra", name="Nao Meu", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(
        f"/loja/produtos/{product.id}/editar",
        data={"kind": "piscina", "category": "fibra", "name": "Hackeado", "price": "1.00"},
    )

    assert response.status_code == 404
```

Note: `_loja_logged_in` is imported from Task 8's test file — this reuses that helper rather than redefining it, so both test files stay in sync on how a logged-in loja is set up.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_loja_produto_editar.py -v`
Expected: FAIL — `404` on `/loja/produtos/{id}/editar` for reasons unrelated to the ownership test (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/loja.py`**

Add `from fastapi import HTTPException` to the imports if not already present. Append:

```python
@router.get("/produtos/{product_id}/editar", response_class=HTMLResponse)
async def editar_produto_form(
    product_id: str,
    request: Request,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = db.get(Product, product_id)
    if product is None or product.member_id != loja.id:
        raise HTTPException(status_code=404)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "loja_produto_editar.html", {"product": product, "error": None})


@router.post("/produtos/{product_id}/editar")
async def editar_produto_submit(
    product_id: str,
    request: Request,
    kind: str = Form(...),
    category: str = Form(...),
    name: str = Form(...),
    price: str = Form(...),
    description: str = Form(""),
    size_label: str = Form(""),
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = db.get(Product, product_id)
    if product is None or product.member_id != loja.id:
        raise HTTPException(status_code=404)

    templates = request.app.state.templates
    error = None
    parsed_price = None

    if kind not in {k.value for k in ProductKind}:
        error = "Selecione um tipo de produto valido."
    elif not category.strip() or not name.strip():
        error = "Preencha categoria e nome do produto."
    else:
        try:
            parsed_price = Decimal(price.replace(",", "."))
            if parsed_price <= 0:
                error = "Informe um preco valido."
        except (InvalidOperation, ValueError):
            error = "Informe um preco valido."

    if error:
        return templates.TemplateResponse(
            request, "loja_produto_editar.html", {"product": product, "error": error}, status_code=400
        )

    product.kind = ProductKind(kind)
    product.category = category.strip()
    product.name = name.strip()
    product.price = parsed_price
    product.description = description.strip() or None
    product.size_label = size_label.strip() or None
    return RedirectResponse(url="/loja/produtos", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/loja_produto_editar.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="admin-shell">
  <header class="admin-topbar">
    <div class="wrap">
      <a class="brand" href="/loja/produtos">Piscinow <span class="badge">Loja</span></a>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap narrow">
      <h1>Editar produto</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/loja/produtos/{{ product.id }}/editar">
        <div class="field">
          <label for="kind">Tipo</label>
          <select id="kind" name="kind">
            <option value="piscina" {% if product.kind.value == "piscina" %}selected{% endif %}>Piscina</option>
            <option value="equipamento" {% if product.kind.value == "equipamento" %}selected{% endif %}>Equipamento</option>
          </select>
        </div>
        <div class="field">
          <label for="category">Categoria</label>
          <input id="category" type="text" name="category" value="{{ product.category }}">
        </div>
        <div class="field">
          <label for="name">Nome</label>
          <input id="name" type="text" name="name" value="{{ product.name }}">
        </div>
        <div class="field">
          <label for="price">Preco (R$)</label>
          <input id="price" type="text" name="price" value="{{ product.price }}">
        </div>
        <div class="field">
          <label for="size_label">Tamanho (opcional)</label>
          <input id="size_label" type="text" name="size_label" value="{{ product.size_label or '' }}">
        </div>
        <div class="field">
          <label for="description">Descricao (opcional)</label>
          <textarea id="description" name="description">{{ product.description or '' }}</textarea>
        </div>
        <button class="btn accent" type="submit">Salvar altera&ccedil;&otilde;es</button>
      </form>
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_loja_produto_editar.py -v`
Expected: written per spec; all need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/loja.py src/piscinow/web/templates/loja_produto_editar.html tests/web/test_loja_produto_editar.py
git commit -m "feat: loja product editing with ownership check"
```

---

### Task 10: Loja routes — deactivate product

**Files:**
- Modify: `src/piscinow/web/routes/loja.py`
- Test: `tests/web/test_loja_produto_desativar.py`

**Interfaces:**
- Consumes: `require_loja`, `Product` (as above).
- Produces: `POST /loja/produtos/{product_id}/desativar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_loja_produto_desativar.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.product import Product, ProductKind
from tests.web.test_loja_produtos import _loja_logged_in


def test_desativar_produto_sets_active_false(client, db_session):
    loja = _loja_logged_in(client, db_session)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina X", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(f"/loja/produtos/{product.id}/desativar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(product)
    assert product.active is False


def test_desativar_produto_de_outra_loja_retorna_404(client, db_session):
    _loja_logged_in(client, db_session, email="loja1@example.com")

    outra_loja = Member(profile_type=ProfileType.LOJA, name="Outra Loja", status=MemberStatus.APPROVED)
    db_session.add(outra_loja)
    db_session.flush()
    product = Product(member_id=outra_loja.id, kind=ProductKind.PISCINA, category="fibra", name="Nao Meu", price=10000)
    db_session.add(product)
    db_session.flush()

    response = client.post(f"/loja/produtos/{product.id}/desativar")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_loja_produto_desativar.py -v`
Expected: FAIL — `404` on `/loja/produtos/{id}/desativar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/loja.py`**

```python
@router.post("/produtos/{product_id}/desativar")
async def desativar_produto(
    product_id: str,
    db: Session = Depends(get_db),
    loja: Member = Depends(require_loja),
):
    product = db.get(Product, product_id)
    if product is None or product.member_id != loja.id:
        raise HTTPException(status_code=404)
    product.active = False
    return RedirectResponse(url="/loja/produtos", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_loja_produto_desativar.py -v`
Expected: written per spec; both need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/loja.py tests/web/test_loja_produto_desativar.py
git commit -m "feat: loja product deactivation with ownership check"
```

---

### Task 11: Product field extraction (chat shortcut, agent side)

**Files:**
- Create: `src/piscinow/agent/product_extractor.py`
- Test: `tests/agent/test_product_extractor.py`

**Interfaces:**
- Consumes: `parse_json_object` (Task 1), `ChatMessage`, `LLMProvider` (existing, sub-project 1 Task 7).
- Produces: `piscinow.agent.product_extractor.extract_product_fields(llm: LLMProvider, text: str) -> dict` — always returns a dict with the six keys `kind`, `category`, `name`, `price`, `size_label`, `description` (each a string; `""` when the LLM didn't provide that field), so the caller (Task 12) can pass it straight into the same `prefill` dict shape Task 8's template already expects.

This task needs NO Docker — it only uses `FakeLLMProvider`, no database.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_product_extractor.py`**

```python
import pytest

from piscinow.agent.product_extractor import extract_product_fields
from piscinow.agent.providers.fake_provider import FakeLLMProvider


@pytest.mark.asyncio
async def test_extracts_product_fields_from_llm_json():
    provider = FakeLLMProvider(
        [
            '{"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", '
            '"price": 18000, "size_label": "6x3m", "description": null}'
        ]
    )

    result = await extract_product_fields(provider, "piscina de fibra 6x3, R$18 mil")

    assert result["kind"] == "piscina"
    assert result["category"] == "fibra"
    assert result["name"] == "Piscina Fibra 6x3"
    assert result["price"] == "18000"
    assert result["size_label"] == "6x3m"
    assert result["description"] == ""


@pytest.mark.asyncio
async def test_extract_product_fields_returns_blank_fields_on_malformed_response():
    provider = FakeLLMProvider(["desculpe nao entendi"])

    result = await extract_product_fields(provider, "algo confuso")

    assert result == {"kind": "", "category": "", "name": "", "price": "", "size_label": "", "description": ""}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/agent/test_product_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.product_extractor'`

- [ ] **Step 3: Write `src/piscinow/agent/product_extractor.py`**

```python
from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider

_SYSTEM_PROMPT = """Voce ajuda uma loja a cadastrar um produto no Clube Piscinow
a partir de uma descricao em texto livre. Extraia os campos em JSON:
{"kind": "piscina" ou "equipamento", "category": string, "name": string,
"price": numero, "size_label": string ou null, "description": string ou null}.
Use null para campos que nao aparecem no texto. Responda APENAS com o JSON."""


async def extract_product_fields(llm: LLMProvider, text: str) -> dict:
    raw = await llm.generate([ChatMessage(role="user", content=text)], system=_SYSTEM_PROMPT)
    data = parse_json_object(raw)
    return {
        "kind": data.get("kind") or "",
        "category": data.get("category") or "",
        "name": data.get("name") or "",
        "price": str(data.get("price")) if data.get("price") is not None else "",
        "size_label": data.get("size_label") or "",
        "description": data.get("description") or "",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/agent/test_product_extractor.py -v`
Expected: PASS (2 tests, real GREEN — no Docker needed for this task)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/product_extractor.py tests/agent/test_product_extractor.py
git commit -m "feat: product field extraction from free text for the loja chat shortcut"
```

---

### Task 12: Loja route — chat shortcut for product entry

**Files:**
- Modify: `src/piscinow/web/routes/loja.py`
- Test: `tests/web/test_loja_produtos_chat.py`

**Interfaces:**
- Consumes: `extract_product_fields` (Task 11), `require_loja` (Task 4), `get_llm_provider` (existing, sub-project 1 Task 20).
- Produces: `POST /loja/produtos/chat` — never persists a `Product`; always re-renders `loja_produtos.html` with `prefill` populated from the extraction.

- [ ] **Step 1: Write the failing test — `tests/web/test_loja_produtos_chat.py`**

```python
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.product import Product
from piscinow.web.deps import get_llm_provider
from tests.web.test_loja_produtos import _loja_logged_in


def test_produtos_chat_prefills_form_without_saving(client, db_session):
    _loja_logged_in(client, db_session)
    provider = FakeLLMProvider(
        [
            '{"kind": "piscina", "category": "fibra", "name": "Piscina Fibra 6x3", '
            '"price": 18000, "size_label": "6x3m", "description": null}'
        ]
    )
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/loja/produtos/chat", data={"text": "piscina de fibra 6x3, R$18 mil"})

    assert response.status_code == 200
    assert "Piscina Fibra 6x3" in response.text
    assert db_session.query(Product).count() == 0


def test_produtos_chat_shows_note_when_extraction_fails(client, db_session):
    _loja_logged_in(client, db_session)
    provider = FakeLLMProvider(["desculpe nao entendi"])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/loja/produtos/chat", data={"text": "algo confuso"})

    assert response.status_code == 200
    assert "Nao consegui entender" in response.text
    assert db_session.query(Product).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_loja_produtos_chat.py -v`
Expected: FAIL — `404` on `/loja/produtos/chat` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/loja.py`**

Add these imports: `from piscinow.agent.llm_provider import LLMProvider`, `from piscinow.agent.product_extractor import extract_product_fields`, `from piscinow.web.deps import get_llm_provider` (add `get_llm_provider` to the existing `from piscinow.web.deps import get_db` line instead if that's cleaner — combine into one import line). Append:

```python
@router.post("/produtos/chat")
async def produtos_chat(
    request: Request,
    text: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    loja: Member = Depends(require_loja),
):
    templates = request.app.state.templates
    prefill = await extract_product_fields(llm, text)
    items = list(
        db.scalars(select(Product).where(Product.member_id == loja.id).order_by(Product.created_at.desc()))
    )
    note = None
    if not any(prefill.values()):
        note = "Nao consegui entender, preencha manualmente."
    return templates.TemplateResponse(
        request, "loja_produtos.html", {"products": items, "error": None, "prefill": prefill, "note": note}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_loja_produtos_chat.py -v`
Expected: written per spec; both need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/web/routes/loja.py tests/web/test_loja_produtos_chat.py
git commit -m "feat: chat shortcut for product entry, always confirmed before saving"
```

---

### Task 13: Register the loja router

**Files:**
- Modify: `src/piscinow/web/app.py`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: `piscinow.web.routes.loja.router` (Task 6).

- [ ] **Step 1: Write the failing test** — append to `tests/web/test_app.py`

```python
def test_app_serves_loja_login_page(client):
    response = client.get("/loja/login")
    assert response.status_code == 200
    assert "Painel da loja" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/web/test_app.py -v`
Expected: the new test FAILs with a `404` (router not registered yet); the pre-existing home-page test still passes.

- [ ] **Step 3: Modify `src/piscinow/web/app.py`**

Change `from piscinow.web.routes import admin, chat, pages` to:

```python
from piscinow.web.routes import admin, chat, loja, pages
```

Add `app.include_router(loja.router)` alongside the existing `app.include_router(pages.router)` / `app.include_router(chat.router)` / `app.include_router(admin.router)` lines inside `create_app()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/web/test_app.py -v`
Expected: PASS (both tests) — the loja login page doesn't touch the database, so this is a real, Docker-free GREEN.

- [ ] **Step 5: Run the whole-suite collection check**

Run: `py -m pytest --collect-only -q`
Expected: every test in the project collects with zero errors (confirms this task, and every prior task in this plan, introduced no import/syntax mistakes anywhere).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/app.py tests/web/test_app.py
git commit -m "feat: register the loja router"
```

---

## Self-Review Notes

- **Spec coverage:** every requirement in the spec maps to a task — set-password onboarding via one-time token (Tasks 2, 5, 6); loja login mirroring the admin pattern (Tasks 4, 7); product CRUD via forms (Tasks 3, 8, 9, 10); chat shortcut that only ever pre-fills, never auto-saves (Tasks 11, 12); admin visibility into pending/active lojas (Task 5); reuse of the existing Agent Core rather than a parallel JSON parser (Task 1, consumed by Task 11).
- **Type/interface consistency check:** `Product`'s field names (`kind`, `category`, `name`, `price`, `size_label`, `description`, `active`) are used identically by Tasks 8, 9, 10, and by `extract_product_fields`'s return-dict keys in Task 11/12 — the `prefill` dict Task 8's template reads (`prefill.get("kind")`, etc.) matches exactly what Task 11 returns, so Task 12 can hand the extractor's output straight to the template with no translation layer. `require_loja`'s return type (`Member`) is consumed identically across Tasks 8, 9, 10, 12. `LOJA_SESSION_KEY`/`login`/`logout` (Task 4) are consumed only by Task 7's routes, matching signatures exactly.
- **Placeholder scan:** no TBD/TODO markers. The one open design question from the spec (whether `Member.email` was reliably populated by sub-project 1's concierge pre-cadastro) was resolved during planning, not left as a placeholder: the `/loja/definir-senha` flow (Task 6) collects `email` explicitly at that step — it does not assume `Member.email` was already set, since sub-project 1's `LojaHandler` only collects a free-text `contact` field (phone or email, LLM-extracted) into `profile_details`, not the structured `email` column.

