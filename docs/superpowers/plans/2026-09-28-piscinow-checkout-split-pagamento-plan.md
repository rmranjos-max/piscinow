# Checkout e Split de Pagamento por Etapas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin build a payment schedule for a confirmed project (assigning each item — the product, and each service — to one of four fixed construction stages with an agreed amount), let the comprador pay the total once, and let the admin release each stage's retained amounts to the loja/prestadores as the work progresses.

**Architecture:** Adds a provider-agnostic `PaymentProvider` interface (mirroring the existing `LLMProvider` pattern) with a `FakePaymentProvider` for development and testing — no real payment gateway is wired in this sub-project. Adds `Payment`/`PaymentAllocation` models (one `Payment` per confirmed `Project`, one `PaymentAllocation` per line item). Extends the existing `admin.py` router with schedule-building and stage-release routes, and the existing `comprador_projeto.py` router with schedule-viewing and pay routes.

**Tech Stack:** Same as sub-projects 1-4 — Python 3.12, FastAPI, SQLAlchemy 2.0, Postgres 16 + pgvector, Jinja2.

**Spec:** [docs/superpowers/specs/2026-09-28-piscinow-checkout-split-pagamento-design.md](../specs/2026-09-28-piscinow-checkout-split-pagamento-design.md)

## Global Constraints

- Reuses the existing Postgres+pgvector datastore — no new datastore, no new infra.
- `PaymentProvider` is an abstract interface (`charge`, `release`); only `FakePaymentProvider` is implemented this sub-project. A real Mercado Pago (or other) adapter is explicitly out of scope.
- Four fixed payment stages: `terraplanagem`, `estrutura`, `revestimento`, `acabamento`. No other stages, no per-project custom stages.
- The comprador is charged exactly once, for the full `Payment.total_amount`, at checkout — never charged again per stage.
- Each item (the product, and each service on the project) is assigned to exactly one stage and one amount, both entered manually by the admin when building the schedule — no automatic derivation from `kind`, and no validation of a service's amount against its `price_min`/`price_max`.
- Releasing a stage releases every `RETIDO` allocation in that stage at once — there is no partial release within a stage.
- `Payment.project_id` is `unique=True` — a confirmed project has at most one payment; building a schedule twice for the same project is rejected.
- Ownership checks follow the pattern already established: 404 (not 403) for a resource that doesn't belong to the requesting comprador; `require_comprador`/`require_admin` guard every route exactly like they already do elsewhere.
- All user-facing text (templates, error messages) is Portuguese (pt-BR). Templates use HTML entities (`&aacute;`, `&atilde;`, `&ccedil;`, etc.) for accented characters, matching every existing admin/comprador template. Python string literals follow the existing project convention of unaccented ASCII.
- TDD throughout: write the failing test before the implementation, every task.
- Same environment constraint as sub-projects 1-4: no Docker/Postgres on this development machine. Tests that don't need `db_session` must show real RED→GREEN with `py -m pytest` (using the Python Launcher — bare `python`/`python3` are broken on this machine). Tests that do need `db_session` are written and reviewed carefully but will fail at fixture setup with a Docker connection error here; that failure mode is expected and does not block a task.
- Never modify `tests/conftest.py` beyond adding the one new model-import line this plan specifies (Task 2) — never mock the database, in this file or `tests/web/conftest.py`.
- `tests/web/conftest.py`'s `client` fixture already calls `limiter.reset()` before each test — no change needed there. This sub-project introduces no new rate-limited routes.
- Follow this project's established convention of mirroring small helpers across files rather than sharing them (e.g. `_project_services`-equivalent logic is written once in `comprador_projeto.py` already and, where `admin.py` needs the same shape of query, it is written again locally in `admin.py` rather than imported cross-module) — same reasoning already applied to `loja_auth.py`/`prestador_auth.py`/`comprador_auth.py`.

---

### Task 1: `PaymentProvider` interface + `FakePaymentProvider`

**Files:**
- Create: `src/piscinow/payment/__init__.py`
- Create: `src/piscinow/payment/payment_provider.py`
- Create: `src/piscinow/payment/providers/__init__.py`
- Create: `src/piscinow/payment/providers/fake_provider.py`
- Test: `tests/payment/__init__.py`
- Test: `tests/payment/test_fake_provider.py`

**Interfaces:**
- Produces: `piscinow.payment.payment_provider.PaymentProvider` (ABC with `async charge(self, *, amount: Decimal, external_reference: str) -> str` and `async release(self, *, charge_id: str, amount: Decimal, external_reference: str) -> str`), `piscinow.payment.payment_provider.PaymentProviderError` (Exception subclass, raised by any provider implementation on failure), `piscinow.payment.providers.fake_provider.FakePaymentProvider` (constructor `__init__(self, *, should_fail_charge: bool = False, should_fail_release: bool = False)`, public attributes `charges: list[dict]` and `releases: list[dict]` recording every call). Consumed by Tasks 6 and 8 (via dependency injection) and by every task's tests that need to set up a `Payment` in a known state.

This task needs NO Docker — pure in-memory logic, no database.

- [ ] **Step 1: Write the failing tests — `tests/payment/test_fake_provider.py`**

```python
import pytest
from decimal import Decimal

from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.payment.payment_provider import PaymentProviderError


@pytest.mark.asyncio
async def test_charge_returns_unique_id_and_records_call():
    provider = FakePaymentProvider()

    charge_id = await provider.charge(amount=Decimal("1000.00"), external_reference="payment-1")

    assert charge_id
    assert provider.charges == [
        {"charge_id": charge_id, "amount": Decimal("1000.00"), "external_reference": "payment-1"}
    ]


@pytest.mark.asyncio
async def test_charge_raises_when_configured_to_fail():
    provider = FakePaymentProvider(should_fail_charge=True)

    with pytest.raises(PaymentProviderError):
        await provider.charge(amount=Decimal("1000.00"), external_reference="payment-1")

    assert provider.charges == []


@pytest.mark.asyncio
async def test_release_returns_unique_id_and_records_call():
    provider = FakePaymentProvider()

    transfer_id = await provider.release(
        charge_id="fake-charge-abc", amount=Decimal("300.00"), external_reference="allocation-1"
    )

    assert transfer_id
    assert provider.releases == [
        {
            "transfer_id": transfer_id,
            "charge_id": "fake-charge-abc",
            "amount": Decimal("300.00"),
            "external_reference": "allocation-1",
        }
    ]


@pytest.mark.asyncio
async def test_release_raises_when_configured_to_fail():
    provider = FakePaymentProvider(should_fail_release=True)

    with pytest.raises(PaymentProviderError):
        await provider.release(charge_id="fake-charge-abc", amount=Decimal("300.00"), external_reference="allocation-1")

    assert provider.releases == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/payment/test_fake_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.payment'`

- [ ] **Step 3: Create `src/piscinow/payment/__init__.py` and `src/piscinow/payment/providers/__init__.py`**

Both files are empty (package markers), matching the convention of `src/piscinow/agent/__init__.py` and `src/piscinow/agent/providers/__init__.py`.

- [ ] **Step 4: Write `src/piscinow/payment/payment_provider.py`**

```python
from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentProviderError(Exception):
    """Raised by any PaymentProvider implementation when a charge or release fails."""


class PaymentProvider(ABC):
    """Provider-agnostic interface: charge the buyer once, release retained
    amounts to recipients per payment stage as work progresses."""

    @abstractmethod
    async def charge(self, *, amount: Decimal, external_reference: str) -> str:
        """Charge the buyer the full amount. Returns an external charge id."""
        raise NotImplementedError

    @abstractmethod
    async def release(self, *, charge_id: str, amount: Decimal, external_reference: str) -> str:
        """Release part of a previously-charged amount to a recipient. Returns an external transfer id."""
        raise NotImplementedError
```

- [ ] **Step 5: Write `src/piscinow/payment/providers/fake_provider.py`**

```python
import uuid
from decimal import Decimal

from piscinow.payment.payment_provider import PaymentProvider, PaymentProviderError


class FakePaymentProvider(PaymentProvider):
    """Deterministic in-memory provider for tests: records every charge/release
    call for inspection, and can be configured to simulate a failure."""

    def __init__(self, *, should_fail_charge: bool = False, should_fail_release: bool = False):
        self.should_fail_charge = should_fail_charge
        self.should_fail_release = should_fail_release
        self.charges: list[dict] = []
        self.releases: list[dict] = []

    async def charge(self, *, amount: Decimal, external_reference: str) -> str:
        if self.should_fail_charge:
            raise PaymentProviderError("simulated charge failure")
        charge_id = f"fake-charge-{uuid.uuid4()}"
        self.charges.append({"charge_id": charge_id, "amount": amount, "external_reference": external_reference})
        return charge_id

    async def release(self, *, charge_id: str, amount: Decimal, external_reference: str) -> str:
        if self.should_fail_release:
            raise PaymentProviderError("simulated release failure")
        transfer_id = f"fake-transfer-{uuid.uuid4()}"
        self.releases.append(
            {
                "transfer_id": transfer_id,
                "charge_id": charge_id,
                "amount": amount,
                "external_reference": external_reference,
            }
        )
        return transfer_id
```

- [ ] **Step 6: Create the empty `tests/payment/__init__.py`**

Matches the existing convention (`tests/agent/__init__.py`, `tests/web/__init__.py`).

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -m pytest tests/payment/test_fake_provider.py -v`
Expected: PASS (4 tests, real GREEN — no Docker needed for this task)

- [ ] **Step 8: Commit**

```bash
git add src/piscinow/payment tests/payment
git commit -m "feat: PaymentProvider interface and FakePaymentProvider"
```

---

### Task 2: `Payment`/`PaymentAllocation` models

**Files:**
- Create: `src/piscinow/models/payment.py`
- Modify: `tests/conftest.py` (add the new model import)
- Modify: `alembic/env.py` (add the new model import)
- Test: `tests/models/test_payment.py`

**Interfaces:**
- Consumes: `piscinow.db.Base`, `piscinow.models.project.Project`, `piscinow.models.member.Member`, `piscinow.models.product.Product`, `piscinow.models.service.Service` (for foreign keys).
- Produces: `piscinow.models.payment.PaymentStage` (str enum: `TERRAPLANAGEM`, `ESTRUTURA`, `REVESTIMENTO`, `ACABAMENTO`), `piscinow.models.payment.PaymentStatus` (str enum: `PENDENTE`, `PAGO`), `piscinow.models.payment.AllocationStatus` (str enum: `RETIDO`, `LIBERADO`), `piscinow.models.payment.Payment` (fields: `id`, `project_id` — `unique=True` —, `total_amount`, `status`, `external_charge_id`, `created_at`, `paid_at`), `piscinow.models.payment.PaymentAllocation` (fields: `id`, `payment_id`, `stage`, `recipient_member_id`, `product_id`, `service_id`, `amount`, `status`, `released_at`, `released_by`, `external_transfer_id`). Consumed by Tasks 3-8.

- [ ] **Step 1: Write the failing tests — `tests/models/test_payment.py`**

```python
import pytest
from sqlalchemy.exc import IntegrityError

from piscinow.models.member import Member, ProfileType
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project


def test_payment_persists_with_default_status(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    payment = Payment(project_id=project.id, total_amount=21000)
    db_session.add(payment)
    db_session.flush()
    db_session.expunge(payment)

    reloaded = db_session.get(Payment, payment.id)
    assert reloaded.status == PaymentStatus.PENDENTE
    assert reloaded.external_charge_id is None
    assert reloaded.paid_at is None


def test_payment_project_id_is_unique(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    payment_a = Payment(project_id=project.id, total_amount=21000)
    db_session.add(payment_a)
    db_session.flush()

    payment_b = Payment(project_id=project.id, total_amount=5000)
    db_session.add(payment_b)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_payment_allocation_links_payment_to_recipient_and_product(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte")
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    project = Project(member_id=comprador.id)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add_all([project, product])
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000)
    db_session.add(payment)
    db_session.flush()

    allocation = PaymentAllocation(
        payment_id=payment.id,
        stage=PaymentStage.ESTRUTURA,
        recipient_member_id=loja.id,
        product_id=product.id,
        amount=18000,
    )
    db_session.add(allocation)
    db_session.flush()
    db_session.expunge(allocation)

    reloaded = db_session.get(PaymentAllocation, allocation.id)
    assert reloaded.status == AllocationStatus.RETIDO
    assert reloaded.service_id is None
    assert reloaded.released_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/models/test_payment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.payment'`

- [ ] **Step 3: Write `src/piscinow/models/payment.py`**

```python
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


class PaymentStage(str, enum.Enum):
    TERRAPLANAGEM = "terraplanagem"
    ESTRUTURA = "estrutura"
    REVESTIMENTO = "revestimento"
    ACABAMENTO = "acabamento"


class PaymentStatus(str, enum.Enum):
    PENDENTE = "pendente"
    PAGO = "pago"


class AllocationStatus(str, enum.Enum):
    RETIDO = "retido"
    LIBERADO = "liberado"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), unique=True)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDENTE
    )
    external_charge_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"))
    stage: Mapped[PaymentStage] = mapped_column(SAEnum(PaymentStage, name="payment_stage"))
    recipient_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[AllocationStatus] = mapped_column(
        SAEnum(AllocationStatus, name="allocation_status"), default=AllocationStatus.RETIDO
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_transfer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
```

- [ ] **Step 4: Add the model import to `tests/conftest.py`**

Add `import piscinow.models.payment  # noqa: E402,F401` alongside the other `import piscinow.models...` lines so `Base.metadata.create_all` in the `engine` fixture picks up the new `payments`/`payment_allocations` tables. This is the ONLY change this plan makes to `tests/conftest.py`.

- [ ] **Step 5: Add the model import to `alembic/env.py`**

Add `import piscinow.models.payment  # noqa: F401` alongside the existing model imports there, keeping alphabetical order with `admin`, `conversation`, `member`, `memory`, `product`, `project`, `service`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/models/test_payment.py -v`
Expected: written per spec; all 3 tests need `db_session` — confirm fixture-level Docker failure only (`py -m pytest tests/models/test_payment.py --collect-only -q` should show 3 tests collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/models/payment.py tests/models/test_payment.py tests/conftest.py alembic/env.py
git commit -m "feat: Payment and PaymentAllocation models"
```

---

### Task 3: Admin — list confirmed projects awaiting a payment schedule

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_pagamentos.html`
- Modify: `src/piscinow/web/templates/admin_queue.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_corrections.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_lojas.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_prestadores.html` (nav link)
- Modify: `src/piscinow/web/templates/admin_compradores.html` (nav link)
- Test: `tests/web/test_admin_pagamentos.py`

**Interfaces:**
- Consumes: `Project`, `ProjectStatus` (existing), `Payment` (Task 2).
- Produces: `GET /admin/pagamentos` (lists confirmed projects with no `Payment` yet).

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_pagamentos.py`**

```python
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def _confirmed_project(db_session, *, comprador_name="Marina Duarte"):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name=comprador_name, status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    return project, product


def test_pagamentos_lists_confirmed_projects_without_payment(client, db_session):
    _logged_in(client, db_session)
    project, product = _confirmed_project(db_session)

    response = client.get("/admin/pagamentos")

    assert "Marina Duarte" in response.text
    assert "Piscina Fibra" in response.text


def test_pagamentos_hides_projects_that_already_have_payment(client, db_session):
    _logged_in(client, db_session)
    project, product = _confirmed_project(db_session, comprador_name="Ja Tem Pagamento")
    db_session.add(Payment(project_id=project.id, total_amount=18000))
    db_session.flush()

    response = client.get("/admin/pagamentos")

    assert "Ja Tem Pagamento" not in response.text


def test_pagamentos_hides_unconfirmed_projects(client, db_session):
    _logged_in(client, db_session)
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Rascunho Ainda", status=MemberStatus.APPROVED)
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    response = client.get("/admin/pagamentos")

    assert "Rascunho Ainda" not in response.text


def test_pagamentos_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/pagamentos", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_pagamentos.py -v`
Expected: FAIL — `404` on `/admin/pagamentos` (route doesn't exist yet)

- [ ] **Step 3: Modify `src/piscinow/web/routes/admin.py`**

Add these imports: `from piscinow.models.payment import Payment`, `from piscinow.models.product import Product`, `from piscinow.models.project import Project, ProjectStatus`. Append this route at the end of the file, right after the existing `compradores` route:

```python
@router.get("/pagamentos", response_class=HTMLResponse)
async def pagamentos(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    paid_project_ids = select(Payment.project_id)
    rows = db.execute(
        select(Project, Member, Product)
        .join(Member, Project.member_id == Member.id)
        .join(Product, Project.product_id == Product.id)
        .where(Project.status == ProjectStatus.CONFIRMADO, Project.id.not_in(paid_project_ids))
        .order_by(Project.updated_at.desc())
    ).all()
    items = [{"project": row[0], "comprador": row[1], "product": row[2]} for row in rows]
    return templates.TemplateResponse(request, "admin_pagamentos.html", {"items": items})
```

(`Member`, `select`, `HTMLResponse`, `AdminUser`, `require_admin`, `get_db` are all already imported in this file.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_pagamentos.html`**

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
        <a href="/admin/pagamentos">Pagamentos</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Projetos aguardando cronograma</h1>
      {% if items %}
      <table class="admin-table">
        <thead><tr><th>Comprador</th><th>Produto</th><th>A&ccedil;&atilde;o</th></tr></thead>
        <tbody>
        {% for item in items %}
          <tr>
            <td>{{ item.comprador.name }}</td>
            <td>{{ item.product.name }}</td>
            <td><a class="mini-btn" href="/admin/pagamentos/{{ item.project.id }}/cronograma">Montar cronograma</a></td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}
      <p class="empty-note">Nenhum projeto aguardando cronograma no momento.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Add a "Pagamentos" nav link to the existing admin templates**

In `src/piscinow/web/templates/admin_queue.html`, `admin_corrections.html`, `admin_lojas.html`, `admin_prestadores.html`, and `admin_compradores.html`, find the `<nav class="admin-nav">` block (currently five links: "Fila de admiss&atilde;o", "Lojas", "Prestadores", "Compradores", "Ensinar o concierge") and add the new link between "Compradores" and "Ensinar o concierge", matching `admin_pagamentos.html`'s nav exactly:

```html
      <nav class="admin-nav">
        <a href="/admin/fila">Fila de admiss&atilde;o</a>
        <a href="/admin/lojas">Lojas</a>
        <a href="/admin/prestadores">Prestadores</a>
        <a href="/admin/compradores">Compradores</a>
        <a href="/admin/pagamentos">Pagamentos</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_pagamentos.py -v`
Expected: written per spec; all 4 tests need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 4 tests collected with no import error).

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_pagamentos.html src/piscinow/web/templates/admin_queue.html src/piscinow/web/templates/admin_corrections.html src/piscinow/web/templates/admin_lojas.html src/piscinow/web/templates/admin_prestadores.html src/piscinow/web/templates/admin_compradores.html tests/web/test_admin_pagamentos.py
git commit -m "feat: list confirmed projects awaiting a payment schedule"
```

---

### Task 4: Admin — build the payment schedule (cronograma)

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_cronograma.html`
- Test: `tests/web/test_admin_cronograma.py`

**Interfaces:**
- Consumes: `Service` (existing), `Payment`, `PaymentAllocation`, `PaymentStage` (Task 2).
- Produces: `GET/POST /admin/pagamentos/{project_id}/cronograma`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_cronograma.py`**

```python
from decimal import Decimal

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment, PaymentAllocation
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectService, ProjectStatus
from piscinow.models.service import Service, ServiceKind
from tests.web.test_admin_pagamentos import _logged_in


def _confirmed_project_with_service(db_session):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    prestador = Member(profile_type=ProfileType.PRESTADOR, name="Instalacoes Sul")
    db_session.add_all([comprador, loja, prestador])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    service = Service(member_id=prestador.id, kind=ServiceKind.INSTALACAO, category="fibra", name="Instalacao completa")
    db_session.add(service)
    db_session.flush()
    db_session.add(ProjectService(project_id=project.id, service_id=service.id))
    db_session.flush()
    return project, product, service


def test_cronograma_form_shows_product_and_services(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.get(f"/admin/pagamentos/{project.id}/cronograma")

    assert response.status_code == 200
    assert "Piscina Fibra" in response.text
    assert "Instalacao completa" in response.text


def test_cronograma_form_rejects_non_confirmed_project(client, db_session):
    _logged_in(client, db_session)
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Rascunho", status=MemberStatus.APPROVED)
    db_session.add(comprador)
    db_session.flush()
    project = Project(member_id=comprador.id)
    db_session.add(project)
    db_session.flush()

    response = client.get(f"/admin/pagamentos/{project.id}/cronograma")

    assert response.status_code == 404


def test_cronograma_submit_creates_payment_and_allocations(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    payment = db_session.query(Payment).filter(Payment.project_id == project.id).one()
    assert payment.total_amount == Decimal("21000")
    allocations = db_session.query(PaymentAllocation).filter(PaymentAllocation.payment_id == payment.id).all()
    assert len(allocations) == 2


def test_cronograma_submit_rejects_missing_stage(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_invalid_amount(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "abc",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
    assert db_session.query(Payment).count() == 0


def test_cronograma_submit_rejects_when_payment_already_exists(client, db_session):
    _logged_in(client, db_session)
    project, product, service = _confirmed_project_with_service(db_session)
    db_session.add(Payment(project_id=project.id, total_amount=18000))
    db_session.flush()

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data={
            f"stage_product_{product.id}": "estrutura",
            f"amount_product_{product.id}": "18000",
            f"stage_service_{service.id}": "acabamento",
            f"amount_service_{service.id}": "3000",
        },
    )

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_cronograma.py -v`
Expected: FAIL — `404` on `/admin/pagamentos/{project_id}/cronograma` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/admin.py`**

Add these imports: `from decimal import Decimal, InvalidOperation`, `from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus` (replace the earlier `from piscinow.models.payment import Payment` import line from Task 3 with this fuller one), `from piscinow.models.service import Service`. Also change Task 3's `from piscinow.models.project import Project, ProjectStatus` import line to `from piscinow.models.project import Project, ProjectService, ProjectStatus` (adding `ProjectService`, needed by the helper below). Append:

```python
def _project_services(db: Session, project_id) -> list[Service]:
    return list(
        db.scalars(
            select(Service)
            .join(ProjectService, ProjectService.service_id == Service.id)
            .where(ProjectService.project_id == project_id)
        )
    )


@router.get("/pagamentos/{project_id}/cronograma", response_class=HTMLResponse)
async def cronograma_form(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    project = db.get(Project, project_id)
    if project is None or project.status != ProjectStatus.CONFIRMADO:
        raise HTTPException(status_code=404)
    existing = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Este projeto ja tem um pagamento.")
    product = db.get(Product, project.product_id)
    services = _project_services(db, project.id)
    return templates.TemplateResponse(
        request,
        "admin_cronograma.html",
        {"project": project, "product": product, "services": services, "error": None},
    )


@router.post("/pagamentos/{project_id}/cronograma")
async def cronograma_submit(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    project = db.get(Project, project_id)
    if project is None or project.status != ProjectStatus.CONFIRMADO:
        raise HTTPException(status_code=404)
    existing = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Este projeto ja tem um pagamento.")

    product = db.get(Product, project.product_id)
    services = _project_services(db, project.id)
    form = await request.form()

    def _parse_item(prefix: str, item_id) -> tuple[str | None, PaymentStage | None, Decimal | None]:
        stage_raw = form.get(f"stage_{prefix}_{item_id}", "")
        amount_raw = form.get(f"amount_{prefix}_{item_id}", "")
        if stage_raw not in {s.value for s in PaymentStage}:
            return "Escolha uma fase valida para todos os itens.", None, None
        try:
            amount = Decimal(str(amount_raw).replace(",", "."))
        except (InvalidOperation, ValueError):
            return "Informe um valor valido para todos os itens.", None, None
        if not amount.is_finite() or amount <= 0:
            return "Informe um valor valido para todos os itens.", None, None
        return None, PaymentStage(stage_raw), amount

    allocations_data = []
    error = None

    error, stage, amount = _parse_item("product", product.id)
    if not error:
        allocations_data.append(
            {"stage": stage, "amount": amount, "recipient_member_id": product.member_id, "product_id": product.id}
        )

    if not error:
        for service in services:
            error, stage, amount = _parse_item("service", service.id)
            if error:
                break
            allocations_data.append(
                {"stage": stage, "amount": amount, "recipient_member_id": service.member_id, "service_id": service.id}
            )

    if error:
        return templates.TemplateResponse(
            request,
            "admin_cronograma.html",
            {"project": project, "product": product, "services": services, "error": error},
            status_code=400,
        )

    total = sum((item["amount"] for item in allocations_data), Decimal("0"))
    payment = Payment(project_id=project.id, total_amount=total)
    db.add(payment)
    db.flush()
    for item in allocations_data:
        db.add(PaymentAllocation(payment_id=payment.id, **item))
    return RedirectResponse(url=f"/admin/pagamentos/{payment.id}", status_code=303)
```

(`Product`, `Project`, `ProjectStatus`, `Session`, `Request`, `Depends`, `HTMLResponse`, `RedirectResponse`, `AdminUser`, `require_admin`, `get_db`, `select` are all already imported from earlier tasks in this file — confirm each is present rather than re-importing duplicates.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_cronograma.html`**

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
        <a href="/admin/pagamentos">Pagamentos</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Montar cronograma</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/admin/pagamentos/{{ project.id }}/cronograma">
        <table class="admin-table">
          <thead><tr><th>Item</th><th>Fase</th><th>Valor (R$)</th></tr></thead>
          <tbody>
            <tr>
              <td>{{ product.name }} (produto)</td>
              <td>
                <select name="stage_product_{{ product.id }}">
                  <option value="">Selecione</option>
                  <option value="terraplanagem">Terraplanagem</option>
                  <option value="estrutura">Estrutura</option>
                  <option value="revestimento">Revestimento</option>
                  <option value="acabamento">Acabamento</option>
                </select>
              </td>
              <td><input type="text" name="amount_product_{{ product.id }}"></td>
            </tr>
            {% for service in services %}
            <tr>
              <td>{{ service.name }} (servi&ccedil;o)</td>
              <td>
                <select name="stage_service_{{ service.id }}">
                  <option value="">Selecione</option>
                  <option value="terraplanagem">Terraplanagem</option>
                  <option value="estrutura">Estrutura</option>
                  <option value="revestimento">Revestimento</option>
                  <option value="acabamento">Acabamento</option>
                </select>
              </td>
              <td><input type="text" name="amount_service_{{ service.id }}"></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <button class="btn accent" type="submit">Salvar cronograma</button>
      </form>
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_cronograma.py -v`
Expected: written per spec; all 5 need `db_session` — confirm fixture-level Docker failure only (`--collect-only -q` shows 5 tests collected with no import error).

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_cronograma.html tests/web/test_admin_cronograma.py
git commit -m "feat: admin builds the payment schedule for a confirmed project"
```

---

### Task 5: Admin — view payment detail

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_pagamento_detalhe.html`
- Test: `tests/web/test_admin_pagamento_detalhe.py`

**Interfaces:**
- Consumes: `Payment`, `PaymentAllocation`, `PaymentStage`, `AllocationStatus` (Task 2).
- Produces: `GET /admin/pagamentos/{payment_id}`. Renders `admin_pagamento_detalhe.html` with context `{"payment": ..., "stages_data": [...], "error": None}`, where each entry in `stages_data` is `{"stage": PaymentStage, "allocations": [(PaymentAllocation, Member), ...], "all_released": bool}` for every stage that has at least one allocation. Task 6 reuses this same context shape and template (adding release buttons where `not all_released` and `payment.status == PAGO`).

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_pagamento_detalhe.py`**

```python
import uuid

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment, PaymentAllocation, PaymentStage
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from tests.web.test_admin_pagamentos import _logged_in


def test_pagamento_detalhe_shows_allocations_grouped_by_stage(client, db_session):
    _logged_in(client, db_session)
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000)
    db_session.add(payment)
    db_session.flush()
    db_session.add(
        PaymentAllocation(
            payment_id=payment.id,
            stage=PaymentStage.ESTRUTURA,
            recipient_member_id=loja.id,
            product_id=product.id,
            amount=18000,
        )
    )
    db_session.flush()

    response = client.get(f"/admin/pagamentos/{payment.id}")

    assert response.status_code == 200
    assert "Studio Fibra Sul" in response.text
    assert "Estrutura" in response.text


def test_pagamento_detalhe_returns_404_for_unknown_payment(client, db_session):
    _logged_in(client, db_session)

    response = client.get(f"/admin/pagamentos/{uuid.uuid4()}")

    assert response.status_code == 404


def test_pagamento_detalhe_redirects_to_login_when_not_authenticated(client):
    response = client.get(f"/admin/pagamentos/{uuid.uuid4()}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_pagamento_detalhe.py -v`
Expected: FAIL — `404` on `/admin/pagamentos/{payment_id}` (route doesn't exist yet — note the plan's route ordering places this AFTER `/pagamentos/{project_id}/cronograma`'s sibling paths; FastAPI matches by declared order for equally-shaped paths, but these two paths have different suffixes (`/cronograma` vs nothing) so there is no ambiguity)

- [ ] **Step 3: Append to `src/piscinow/web/routes/admin.py`**

```python
@router.get("/pagamentos/{payment_id}", response_class=HTMLResponse)
async def pagamento_detalhe(
    payment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    templates = request.app.state.templates
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404)
    allocations = list(
        db.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id))
    )
    stages_data = []
    for stage in PaymentStage:
        stage_allocations = [
            (allocation, db.get(Member, allocation.recipient_member_id))
            for allocation in allocations
            if allocation.stage == stage
        ]
        if not stage_allocations:
            continue
        all_released = all(a.status == AllocationStatus.LIBERADO for a, _ in stage_allocations)
        stages_data.append({"stage": stage, "allocations": stage_allocations, "all_released": all_released})
    return templates.TemplateResponse(
        request, "admin_pagamento_detalhe.html", {"payment": payment, "stages_data": stages_data, "error": None}
    )
```

(`HTTPException` is already imported from an earlier task in this file — confirm rather than re-importing.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_pagamento_detalhe.html`**

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
        <a href="/admin/pagamentos">Pagamentos</a>
        <a href="/admin/correcoes">Ensinar o concierge</a>
      </nav>
    </div>
  </header>
  <main class="admin-main">
    <div class="wrap">
      <h1>Pagamento</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <p>Status: {{ "Pago" if payment.status.value == "pago" else "Pendente" }} — Total: R$ {{ payment.total_amount }}</p>

      {% for group in stages_data %}
      <h2 style="font-size:1.1rem; margin-top:20px;">
        {{ group.stage.value | capitalize }}
        {% if group.all_released %}(liberado){% endif %}
      </h2>
      <table class="admin-table">
        <thead><tr><th>Destinat&aacute;rio</th><th>Valor</th><th>Status</th></tr></thead>
        <tbody>
        {% for allocation, recipient in group.allocations %}
          <tr>
            <td>{{ recipient.name }}</td>
            <td>R$ {{ allocation.amount }}</td>
            <td>{{ "Liberado" if allocation.status.value == "liberado" else "Retido" }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% endfor %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_pagamento_detalhe.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_pagamento_detalhe.html tests/web/test_admin_pagamento_detalhe.py
git commit -m "feat: admin views a payment's schedule grouped by stage"
```

---

### Task 6: Admin — release a stage's retained allocations

**Files:**
- Modify: `src/piscinow/web/deps.py`
- Modify: `src/piscinow/web/app.py`
- Modify: `src/piscinow/web/routes/admin.py`
- Modify: `src/piscinow/web/templates/admin_pagamento_detalhe.html`
- Test: `tests/web/test_admin_liberar_fase.py`

**Interfaces:**
- Consumes: `PaymentProvider`, `FakePaymentProvider` (Task 1), `Payment`, `PaymentAllocation`, `PaymentStage`, `PaymentStatus`, `AllocationStatus` (Task 2).
- Produces: `piscinow.web.deps.get_payment_provider(request: Request) -> PaymentProvider` — the FastAPI dependency every later task (Task 8) also uses to inject the provider. `POST /admin/pagamentos/{payment_id}/fases/{stage}/liberar`.

This is the first task in this plan that actually invokes a `PaymentProvider` — the dependency and app-level wiring are introduced here rather than in Task 1, per this plan's "fold setup into the task that needs it" convention.

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_liberar_fase.py`**

```python
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStage, PaymentStatus
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.web.deps import get_payment_provider
from tests.web.test_admin_pagamentos import _logged_in


def _paid_payment_with_allocation(db_session, *, stage=PaymentStage.ESTRUTURA, status=PaymentStatus.PAGO):
    comprador = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add_all([comprador, loja])
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000, status=status, external_charge_id="fake-charge-x")
    db_session.add(payment)
    db_session.flush()
    allocation = PaymentAllocation(
        payment_id=payment.id, stage=stage, recipient_member_id=loja.id, product_id=product.id, amount=18000
    )
    db_session.add(allocation)
    db_session.flush()
    return payment, allocation


def test_liberar_fase_releases_allocation_and_calls_provider(client, db_session):
    admin_user = _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(allocation)
    assert allocation.status == AllocationStatus.LIBERADO
    assert allocation.external_transfer_id is not None
    assert allocation.released_by == admin_user.email


def test_liberar_fase_rejects_unpaid_payment(client, db_session):
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session, status=PaymentStatus.PENDENTE)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")

    assert response.status_code == 400
    db_session.refresh(allocation)
    assert allocation.status == AllocationStatus.RETIDO


def test_liberar_fase_is_idempotent(client, db_session):
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)
    provider = FakePaymentProvider()
    client.app.dependency_overrides[get_payment_provider] = lambda: provider

    client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")
    client.post(f"/admin/pagamentos/{payment.id}/fases/estrutura/liberar")

    assert len(provider.releases) == 1


def test_liberar_fase_rejects_invalid_stage_name(client, db_session):
    _logged_in(client, db_session)
    payment, allocation = _paid_payment_with_allocation(db_session)

    response = client.post(f"/admin/pagamentos/{payment.id}/fases/nao-existe/liberar")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_admin_liberar_fase.py -v`
Expected: FAIL — `404` on `/admin/pagamentos/{payment_id}/fases/{stage}/liberar` (route doesn't exist yet)

- [ ] **Step 3: Add `get_payment_provider` to `src/piscinow/web/deps.py`**

Add `from piscinow.payment.payment_provider import PaymentProvider` to the imports. Append:

```python
def get_payment_provider(request: Request) -> PaymentProvider:
    return request.app.state.payment_provider
```

- [ ] **Step 4: Wire the provider in `src/piscinow/web/app.py`**

Add `from piscinow.payment.providers.fake_provider import FakePaymentProvider` to the imports. Inside `create_app()`, add `app.state.payment_provider = FakePaymentProvider()` alongside the existing `app.state.llm_provider = build_llm_provider(settings)` line.

- [ ] **Step 5: Append to `src/piscinow/web/routes/admin.py`**

Add these imports: `from datetime import datetime, timezone`, `from piscinow.payment.payment_provider import PaymentProvider`, `from piscinow.web.deps import get_payment_provider` (add to the existing `from piscinow.web.deps import get_db` line, combining into one). Append:

```python
@router.post("/pagamentos/{payment_id}/fases/{stage}/liberar")
async def liberar_fase(
    payment_id: str,
    stage: str,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    admin: AdminUser = Depends(require_admin),
):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404)
    if payment.status != PaymentStatus.PAGO:
        raise HTTPException(status_code=400, detail="Pagamento ainda nao foi pago pelo comprador.")
    if stage not in {s.value for s in PaymentStage}:
        raise HTTPException(status_code=404)
    allocations = list(
        db.scalars(
            select(PaymentAllocation).where(
                PaymentAllocation.payment_id == payment.id,
                PaymentAllocation.stage == PaymentStage(stage),
                PaymentAllocation.status == AllocationStatus.RETIDO,
            )
        )
    )
    for allocation in allocations:
        transfer_id = await payment_provider.release(
            charge_id=payment.external_charge_id, amount=allocation.amount, external_reference=str(allocation.id)
        )
        allocation.status = AllocationStatus.LIBERADO
        allocation.released_at = datetime.now(timezone.utc)
        allocation.released_by = admin.email
        allocation.external_transfer_id = transfer_id
    return RedirectResponse(url=f"/admin/pagamentos/{payment.id}", status_code=303)
```

- [ ] **Step 6: Modify `src/piscinow/web/templates/admin_pagamento_detalhe.html`**

Inside the `{% for group in stages_data %}` loop, right after the `<h2>` heading, add a release form shown only when the payment is paid and the stage still has retained allocations:

```html
      {% for group in stages_data %}
      <h2 style="font-size:1.1rem; margin-top:20px;">
        {{ group.stage.value | capitalize }}
        {% if group.all_released %}(liberado){% endif %}
      </h2>
      {% if payment.status.value == "pago" and not group.all_released %}
      <form method="post" action="/admin/pagamentos/{{ payment.id }}/fases/{{ group.stage.value }}/liberar">
        <button class="mini-btn" type="submit">Liberar fase</button>
      </form>
      {% endif %}
      <table class="admin-table">
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_admin_liberar_fase.py -v`
Expected: written per spec; all 4 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 8: Commit**

```bash
git add src/piscinow/web/deps.py src/piscinow/web/app.py src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_pagamento_detalhe.html tests/web/test_admin_liberar_fase.py
git commit -m "feat: admin releases a payment stage's retained allocations"
```

---

### Task 7: Comprador — view the payment schedule

**Files:**
- Modify: `src/piscinow/web/routes/comprador_projeto.py`
- Create: `src/piscinow/web/templates/comprador_pagamento.html`
- Test: `tests/web/test_comprador_pagamento.py`

**Interfaces:**
- Consumes: `_get_or_create_project`, `require_comprador` (existing in this file), `Payment`, `PaymentAllocation` (Task 2).
- Produces: `GET /comprador/projeto/pagamento`. Renders `comprador_pagamento.html` with context `{"payment": ..., "allocations": [(PaymentAllocation, Member), ...], "error": None}` — Task 8 reuses this same template and context shape.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_pagamento.py`**

```python
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.payment import Payment, PaymentAllocation, PaymentStage
from piscinow.models.product import Product, ProductKind
from piscinow.models.project import Project, ProjectStatus
from tests.web.test_comprador_projeto import _comprador_logged_in


def _confirmed_project_with_payment(client, db_session):
    comprador = _comprador_logged_in(client, db_session)
    loja = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul")
    db_session.add(loja)
    db_session.flush()
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra", price=18000)
    db_session.add(product)
    db_session.flush()
    project = Project(member_id=comprador.id, product_id=product.id, status=ProjectStatus.CONFIRMADO)
    db_session.add(project)
    db_session.flush()
    payment = Payment(project_id=project.id, total_amount=18000)
    db_session.add(payment)
    db_session.flush()
    db_session.add(
        PaymentAllocation(
            payment_id=payment.id,
            stage=PaymentStage.ESTRUTURA,
            recipient_member_id=loja.id,
            product_id=product.id,
            amount=18000,
        )
    )
    db_session.flush()
    return comprador, payment


def test_ver_pagamento_shows_cronograma(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    response = client.get("/comprador/projeto/pagamento")

    assert response.status_code == 200
    assert "18000" in response.text


def test_ver_pagamento_returns_404_when_no_payment_yet(client, db_session):
    _comprador_logged_in(client, db_session)

    response = client.get("/comprador/projeto/pagamento")

    assert response.status_code == 404


def test_ver_pagamento_redirects_to_login_when_not_authenticated(client):
    response = client.get("/comprador/projeto/pagamento", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_pagamento.py -v`
Expected: FAIL — `404` on `/comprador/projeto/pagamento` (route doesn't exist yet — note this is a DIFFERENT kind of 404 than `test_ver_pagamento_returns_404_when_no_payment_yet` expects once implemented; before implementation ALL three tests fail, the first two with an unimplemented-route 404, confirm this transitions to the correct behavior in Step 4)

- [ ] **Step 3: Append to `src/piscinow/web/routes/comprador_projeto.py`**

Add `from piscinow.models.payment import Payment, PaymentAllocation` to the imports. Append:

```python
@router.get("/projeto/pagamento", response_class=HTMLResponse)
async def ver_pagamento(
    request: Request,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    payment = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if payment is None:
        raise HTTPException(status_code=404)
    allocations = [
        (allocation, db.get(Member, allocation.recipient_member_id))
        for allocation in db.scalars(
            select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id)
        )
    ]
    return templates.TemplateResponse(
        request, "comprador_pagamento.html", {"payment": payment, "allocations": allocations, "error": None}
    )
```

- [ ] **Step 4: Write `src/piscinow/web/templates/comprador_pagamento.html`**

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
      <h1>Pagamento do projeto</h1>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <p>Total: R$ {{ payment.total_amount }}</p>
      <table class="admin-table">
        <thead><tr><th>Destinat&aacute;rio</th><th>Fase</th><th>Valor</th></tr></thead>
        <tbody>
        {% for allocation, recipient in allocations %}
          <tr>
            <td>{{ recipient.name }}</td>
            <td>{{ allocation.stage.value | capitalize }}</td>
            <td>R$ {{ allocation.amount }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% if payment.status.value == "pendente" %}
      <form method="post" action="/comprador/projeto/pagamento/pagar">
        <button class="btn accent" type="submit">Pagar</button>
      </form>
      {% else %}
      <p class="empty-note">Pagamento realizado.</p>
      {% endif %}
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_comprador_pagamento.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/comprador_projeto.py src/piscinow/web/templates/comprador_pagamento.html tests/web/test_comprador_pagamento.py
git commit -m "feat: comprador views the payment schedule for their confirmed project"
```

---

### Task 8: Comprador — pay

**Files:**
- Modify: `src/piscinow/web/routes/comprador_projeto.py`
- Test: `tests/web/test_comprador_pagamento_pagar.py`

**Interfaces:**
- Consumes: `get_payment_provider` (Task 6), `PaymentProvider`, `PaymentProviderError` (Task 1), `Payment`, `PaymentStatus` (Task 2).
- Produces: `POST /comprador/projeto/pagamento/pagar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_comprador_pagamento_pagar.py`**

```python
from piscinow.models.payment import PaymentStatus
from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.web.deps import get_payment_provider
from tests.web.test_comprador_pagamento import _confirmed_project_with_payment


def test_pagar_success_charges_and_marks_paid(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)

    response = client.post("/comprador/projeto/pagamento/pagar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PAGO
    assert payment.external_charge_id is not None
    assert payment.paid_at is not None


def test_pagar_twice_returns_400(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)
    client.post("/comprador/projeto/pagamento/pagar")

    response = client.post("/comprador/projeto/pagamento/pagar")

    assert response.status_code == 400


def test_pagar_shows_error_when_provider_fails(client, db_session):
    comprador, payment = _confirmed_project_with_payment(client, db_session)
    provider = FakePaymentProvider(should_fail_charge=True)
    client.app.dependency_overrides[get_payment_provider] = lambda: provider

    response = client.post("/comprador/projeto/pagamento/pagar")

    assert response.status_code == 400
    assert "Nao foi possivel processar" in response.text
    db_session.refresh(payment)
    assert payment.status == PaymentStatus.PENDENTE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/web/test_comprador_pagamento_pagar.py -v`
Expected: FAIL — `404` on `/comprador/projeto/pagamento/pagar` (route doesn't exist yet)

- [ ] **Step 3: Append to `src/piscinow/web/routes/comprador_projeto.py`**

Add `from datetime import datetime, timezone`, `from piscinow.models.payment import PaymentStatus` (add to the existing `from piscinow.models.payment import Payment, PaymentAllocation` line, combining into one), `from piscinow.payment.payment_provider import PaymentProvider, PaymentProviderError`, and add `get_payment_provider` to the existing `from piscinow.web.deps import get_db, get_llm_provider` line. Append:

```python
@router.post("/projeto/pagamento/pagar")
async def pagar(
    request: Request,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    comprador: Member = Depends(require_comprador),
):
    templates = request.app.state.templates
    project = _get_or_create_project(db, comprador.id)
    payment = db.scalar(select(Payment).where(Payment.project_id == project.id))
    if payment is None:
        raise HTTPException(status_code=404)
    if payment.status != PaymentStatus.PENDENTE:
        raise HTTPException(status_code=400, detail="Este pagamento ja foi processado.")

    allocations = [
        (allocation, db.get(Member, allocation.recipient_member_id))
        for allocation in db.scalars(
            select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id)
        )
    ]

    try:
        charge_id = await payment_provider.charge(amount=payment.total_amount, external_reference=str(payment.id))
    except PaymentProviderError:
        return templates.TemplateResponse(
            request,
            "comprador_pagamento.html",
            {
                "payment": payment,
                "allocations": allocations,
                "error": "Nao foi possivel processar o pagamento. Tente novamente.",
            },
            status_code=400,
        )

    payment.external_charge_id = charge_id
    payment.status = PaymentStatus.PAGO
    payment.paid_at = datetime.now(timezone.utc)
    return RedirectResponse(url="/comprador/projeto/pagamento", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/web/test_comprador_pagamento_pagar.py -v`
Expected: written per spec; all 3 need `db_session` — confirm fixture-level Docker failure only.

- [ ] **Step 5: Run the whole-suite collection check**

Run: `py -m pytest --collect-only -q`
Expected: every test in the project collects with zero errors — this should be strictly more tests than the 220 collected at the end of sub-project 4.

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/comprador_projeto.py tests/web/test_comprador_pagamento_pagar.py
git commit -m "feat: comprador pays for their confirmed project's schedule"
```

---

## Self-Review Notes

- **Spec coverage:** every requirement in the spec maps to a task — the `PaymentProvider` abstraction with only a fake implementation (Task 1); one payment per confirmed project via `unique=True`, four fixed stages, manual admin-assigned stage+amount per item with no range validation (Tasks 2, 4); single upfront charge, retained then released (Tasks 7, 8, 6); release-a-whole-stage-at-once with idempotency (Task 6); ownership/404 patterns and the charge-failure error path (Tasks 7, 8).
- **Type/interface consistency check:** `Payment`/`PaymentAllocation` field names are used identically across Tasks 3-8. `get_payment_provider` (Task 6) is consumed identically by Task 8. `PaymentProviderError` (Task 1) is the one exception type both the fake provider raises and Task 8's route catches — no task introduces a second error type. The `stages_data`/`allocations` context shapes established in Tasks 5 and 7 are each reused unchanged by the one later task that extends the same template (Task 6 extends Task 5's; no task extends Task 7's, since Task 8 redirects back to Task 7's own route rather than rendering a variant of it — except on the charge-failure path, which intentionally reuses the exact same three-key context shape Task 7 established, just with `error` populated).
- **Placeholder scan:** no TBD/TODO markers. The two "fold setup into the first consumer" decisions (the `PaymentProvider` DI wiring in Task 6 rather than Task 1; the shared-nav-template touch-once-in-Task-3 rather than every task) are called out explicitly in each task's text, not left implicit.
