# Landing Page + Clube + Agente de Atendimento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Clube Piscinow landing page — invite-based club waitlist, a Python conversational agent that identifies visitor profile (comprador/loja/prestador/embaixador) and routes each to the right flow, and an admin panel for approval and teaching the agent — as a single deployable FastAPI monolith.

**Architecture:** A FastAPI monolith (Jinja2 + HTMX-ready pages, no separate frontend build) backed by Postgres+pgvector. An internal "Agent Core" library (LLMProvider abstraction, MemoryStore, Router, per-profile ConversationHandlers, Extractor) is called directly by the web routes — no separate agent service in this phase.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 + Alembic, Postgres 16 + pgvector, Jinja2, sentence-transformers (local embeddings), argon2-cffi (password hashing), slowapi (rate limiting), pytest + pytest-asyncio + testcontainers, Docker Compose for deployment.

**Spec:** [docs/superpowers/specs/2026-09-06-piscinow-landing-clube-agente-design.md](../specs/2026-09-06-piscinow-landing-clube-agente-design.md)

## Global Constraints

- Backend is a single FastAPI monolith (Jinja2/HTMX, no separate frontend build) — per the spec's chosen Abordagem 1.
- Postgres + pgvector is the only datastore, for both business data and agent memory.
- LLM access goes only through the `LLMProvider` interface (`src/piscinow/agent/llm_provider.py`); no code outside `agent/providers/` may import a provider SDK directly. Provider choice is selected via the `PISCINOW_LLM_PROVIDER` env var (`anthropic` | `openai` | `fake`).
- Embeddings for the MemoryStore come from a local `sentence-transformers` model (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions), independent of the configured LLM provider — this keeps the memory layer usable even if the LLM provider has no embeddings endpoint.
- `MemoryItem` rows with `source=human` must outrank `source=auto` rows of similar relevance in `MemoryStore.search` (implemented as a ranking boost, not an absolute filter ahead of relevance).
- All user-facing text (templates, agent prompts, error messages) is in Portuguese (pt-BR).
- Admission resolution (spec left this open): visitor with **no referral** → `Member.status=waitlisted`, requires manual admin approval. Visitor with a **valid referral code** → `Member.status=approved` automatically. This resolves the spec's open decision, consistent with the embaixador flow already shown in the approved prototype (`prototypes/clube-piscinow-landing.html`).
- Visual fidelity: templates built in this plan are functional, not a pixel-for-pixel port of `prototypes/clube-piscinow-landing.html`. Porting the full visual design is a follow-up styling pass, out of scope here.
- TDD throughout: write the failing test before the implementation, every task.
- Tests that only exercise pure business logic (no DB) run without infrastructure. Anything touching `MemoryStore`, real persistence, or a full conversation flow runs against a real Postgres via `testcontainers` (`pgvector/pgvector:pg16` image) — **requires Docker running locally** to execute this plan's test suite.
- Deploy target: a single VPS via Docker Compose (`pgvector/pgvector:pg16` + the FastAPI app container).

---

## Phase A — Foundations (data models)

### Task 1: Project scaffolding & settings

**Files:**
- Create: `pyproject.toml`
- Create: `src/piscinow/__init__.py`
- Create: `src/piscinow/config.py`
- Create: `.env.example`
- Test: `tests/test_config.py`
- Test: `tests/__init__.py`

**Interfaces:**
- Produces: `piscinow.config.Settings` (pydantic-settings model), `piscinow.config.get_settings() -> Settings`. Fields used by later tasks: `database_url: str`, `llm_provider: str`, `anthropic_api_key: str | None`, `openai_api_key: str | None`, `session_secret: str`, `chat_rate_limit_per_minute: int`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "piscinow"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "psycopg[binary]>=3.1",
  "pgvector>=0.3",
  "pydantic-settings>=2.4",
  "jinja2>=3.1",
  "python-multipart>=0.0.9",
  "itsdangerous>=2.2",
  "argon2-cffi>=23.1",
  "sentence-transformers>=3.0",
  "anthropic>=0.34",
  "openai>=1.40",
  "slowapi>=0.1.9",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "testcontainers[postgres]>=4.8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/piscinow"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```
PISCINOW_DATABASE_URL=postgresql+psycopg://piscinow:piscinow@localhost:5432/piscinow
PISCINOW_LLM_PROVIDER=fake
PISCINOW_ANTHROPIC_API_KEY=
PISCINOW_OPENAI_API_KEY=
PISCINOW_SESSION_SECRET=change-me-in-production
PISCINOW_CHAT_RATE_LIMIT_PER_MINUTE=20
```

- [ ] **Step 3: Create `src/piscinow/__init__.py`** (empty file) and `tests/__init__.py` (empty file)

- [ ] **Step 4: Write the failing test — `tests/test_config.py`**

```python
from piscinow.config import Settings


def test_settings_default_llm_provider_is_fake():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "fake"


def test_settings_reads_env_prefix(monkeypatch):
    monkeypatch.setenv("PISCINOW_LLM_PROVIDER", "anthropic")
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "anthropic"
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pip install -e ".[dev]" && pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'piscinow.config'`

- [ ] **Step 6: Write minimal implementation — `src/piscinow/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PISCINOW_")

    database_url: str = "postgresql+psycopg://piscinow:piscinow@localhost:5432/piscinow"
    llm_provider: str = "fake"  # "anthropic" | "openai" | "fake"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    session_secret: str = "change-me-in-production"
    chat_rate_limit_per_minute: int = 20


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example src/piscinow/__init__.py src/piscinow/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: project scaffolding and settings"
```

---

### Task 2: Database engine/session + Postgres test fixture

**Files:**
- Create: `src/piscinow/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `piscinow.config.get_settings` (Task 1).
- Produces: `piscinow.db.Base` (SQLAlchemy `DeclarativeBase`, used by every model task), `piscinow.db.make_engine(database_url=None) -> Engine`, `piscinow.db.make_session_factory(engine) -> sessionmaker`. Test fixtures `postgres_container` (session scope), `engine` (session scope), `db_session` (function scope, rolls back after each test) — used by every later integration test.

- [ ] **Step 1: Write the failing test — `tests/test_db.py`**

```python
from sqlalchemy import text


def test_vector_extension_available(db_session):
    result = db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname='vector'")
    ).scalar()
    assert result == "vector"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `db_session` fixture not found (conftest.py doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/db.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from piscinow.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    settings = get_settings()
    url = database_url or settings.database_url
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from piscinow.db import Base

# Importing every model module here ensures Base.metadata knows about all
# tables before `create_all` runs in the `engine` fixture below.
import piscinow.models.member  # noqa: E402,F401
import piscinow.models.conversation  # noqa: E402,F401
import piscinow.models.memory  # noqa: E402,F401
import piscinow.models.admin  # noqa: E402,F401


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="session")
def engine(postgres_container):
    url = postgres_container.get_connection_url().replace("psycopg2", "psycopg")
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

Note: this conftest imports model modules that don't exist yet (`piscinow.models.member`, etc.) — Task 3-6 create them. Task 2's own test only needs the `vector` extension, not any table, so temporarily comment out the four `import piscinow.models...` lines and the docstring above them until Task 3 lands; Task 3's Step 1 will restore the `member` import (Task 4/5/6 restore the rest as they land).

- [ ] **Step 5: Comment out the not-yet-existing model imports**

Edit `tests/conftest.py`: prefix the four `import piscinow.models...` lines and their comment with `# ` (restored one at a time in Tasks 3-6).

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS. (First run pulls the `pgvector/pgvector:pg16` Docker image — requires Docker running and internet access.)

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: database engine and Postgres test fixture"
```

---

### Task 3: Member model + status/referral business-logic tests

**Files:**
- Create: `src/piscinow/models/__init__.py`
- Create: `src/piscinow/models/member.py`
- Modify: `tests/conftest.py:9` (uncomment `import piscinow.models.member`)
- Test: `tests/models/__init__.py`
- Test: `tests/models/test_member.py`

**Interfaces:**
- Consumes: `piscinow.db.Base` (Task 2).
- Produces: `piscinow.models.member.ProfileType` (str enum: `COMPRADOR`, `LOJA`, `PRESTADOR`, `EMBAIXADOR`), `piscinow.models.member.MemberStatus` (str enum: `PENDING`, `WAITLISTED`, `APPROVED`, `REJECTED`), `piscinow.models.member.Member` (SQLAlchemy model) with methods `submit_for_review()`, `approve(*, approved_by: str)`, `reject(*, approved_by: str)`, `auto_approve_via_referral()`, and fields `id: uuid.UUID`, `profile_type`, `status`, `name: str`, `email: str | None`, `phone: str | None`, `region: str | None`, `profile_details: dict`, `referral_code: str | None`, `referred_by_member_id: uuid.UUID | None`, `created_at`, `approved_at`, `approved_by`.

- [ ] **Step 1: Write the failing tests — `tests/models/test_member.py`**

```python
import uuid

import pytest

from piscinow.models.member import Member, MemberStatus, ProfileType


def make_member(**kwargs):
    defaults = dict(profile_type=ProfileType.COMPRADOR, name="Teste")
    defaults.update(kwargs)
    return Member(**defaults)


def test_new_member_starts_pending():
    assert make_member().status == MemberStatus.PENDING


def test_submit_for_review_moves_to_waitlisted():
    member = make_member()
    member.submit_for_review()
    assert member.status == MemberStatus.WAITLISTED


def test_submit_for_review_twice_raises():
    member = make_member()
    member.submit_for_review()
    with pytest.raises(ValueError):
        member.submit_for_review()


def test_approve_sets_approved_fields():
    member = make_member()
    member.submit_for_review()
    member.approve(approved_by="admin@piscinow.com.br")
    assert member.status == MemberStatus.APPROVED
    assert member.approved_by == "admin@piscinow.com.br"
    assert member.approved_at is not None


def test_reject_sets_rejected_status():
    member = make_member()
    member.submit_for_review()
    member.reject(approved_by="admin@piscinow.com.br")
    assert member.status == MemberStatus.REJECTED


def test_auto_approve_via_referral_requires_referrer():
    with pytest.raises(ValueError):
        make_member().auto_approve_via_referral()


def test_auto_approve_via_referral_sets_approved():
    member = make_member(referred_by_member_id=uuid.uuid4())
    member.auto_approve_via_referral()
    assert member.status == MemberStatus.APPROVED
    assert member.approved_by == "referral"
```

- [ ] **Step 2: Create `tests/models/__init__.py`** (empty file)

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/models/test_member.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'piscinow.models'`

- [ ] **Step 4: Create `src/piscinow/models/__init__.py`** (empty file)

- [ ] **Step 5: Write minimal implementation — `src/piscinow/models/member.py`**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


class ProfileType(str, enum.Enum):
    COMPRADOR = "comprador"
    LOJA = "loja"
    PRESTADOR = "prestador"
    EMBAIXADOR = "embaixador"


class MemberStatus(str, enum.Enum):
    PENDING = "pending"        # conversa em andamento, dados incompletos
    WAITLISTED = "waitlisted"  # dados completos, aguardando revisao manual
    APPROVED = "approved"      # admitido no Clube / homologado
    REJECTED = "rejected"      # recusado pela equipe


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_type: Mapped[ProfileType] = mapped_column(SAEnum(ProfileType, name="profile_type"))
    status: Mapped[MemberStatus] = mapped_column(
        SAEnum(MemberStatus, name="member_status"), default=MemberStatus.PENDING
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_details: Mapped[dict] = mapped_column(JSONB, default=dict)
    referral_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    referred_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    def submit_for_review(self) -> None:
        if self.status != MemberStatus.PENDING:
            raise ValueError(f"cannot submit member in status {self.status}")
        self.status = MemberStatus.WAITLISTED

    def approve(self, *, approved_by: str) -> None:
        self.status = MemberStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = datetime.utcnow()

    def reject(self, *, approved_by: str) -> None:
        self.status = MemberStatus.REJECTED
        self.approved_by = approved_by
        self.approved_at = datetime.utcnow()

    def auto_approve_via_referral(self) -> None:
        if self.referred_by_member_id is None:
            raise ValueError("cannot auto-approve a member without a referral")
        self.status = MemberStatus.APPROVED
        self.approved_by = "referral"
        self.approved_at = datetime.utcnow()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/models/test_member.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Uncomment the `member` import in `tests/conftest.py`**

Edit `tests/conftest.py`: restore `import piscinow.models.member  # noqa: E402,F401` (remove the leading `# `).

- [ ] **Step 8: Write the integration round-trip test**

Append to `tests/models/test_member.py`:

```python
from piscinow.models.member import Member, ProfileType


def test_member_persists_and_reloads(db_session):
    member = Member(
        profile_type=ProfileType.LOJA,
        name="Studio Fibra Sul",
        profile_details={"cnpj": "12.345.678/0001-90", "categories": ["fibra"]},
    )
    db_session.add(member)
    db_session.flush()
    db_session.expunge(member)

    reloaded = db_session.get(Member, member.id)

    assert reloaded.name == "Studio Fibra Sul"
    assert reloaded.profile_details["cnpj"] == "12.345.678/0001-90"
```

- [ ] **Step 9: Run the full test file to verify it passes**

Run: `pytest tests/models/test_member.py -v`
Expected: PASS (8 tests)

- [ ] **Step 10: Commit**

```bash
git add src/piscinow/models tests/models tests/conftest.py
git commit -m "feat: Member model with status/referral business logic"
```

---

### Task 4: Conversation & Message models

**Files:**
- Create: `src/piscinow/models/conversation.py`
- Modify: `tests/conftest.py` (uncomment `import piscinow.models.conversation`)
- Test: `tests/models/test_conversation.py`

**Interfaces:**
- Consumes: `piscinow.db.Base`, `piscinow.models.member.ProfileType` (Task 3).
- Produces: `piscinow.models.conversation.MessageRole` (str enum: `USER`, `AGENT`), `piscinow.models.conversation.Conversation` (fields: `id`, `member_id: uuid.UUID | None`, `profile_type_detected: ProfileType | None`, `collected_fields: dict`, `started_at`, `ended_at`, `messages: list[Message]`), `piscinow.models.conversation.Message` (fields: `id`, `conversation_id`, `role: MessageRole`, `content: str`, `created_at`, `conversation`).

- [ ] **Step 1: Write the failing test — `tests/models/test_conversation.py`**

```python
from piscinow.models.conversation import Conversation, Message, MessageRole


def test_conversation_persists_messages_in_order(db_session):
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    db_session.add(Message(conversation=conversation, role=MessageRole.USER, content="oi"))
    db_session.add(Message(conversation=conversation, role=MessageRole.AGENT, content="ola!"))
    db_session.flush()
    db_session.expunge_all()

    reloaded = db_session.get(Conversation, conversation.id)

    assert [m.content for m in reloaded.messages] == ["oi", "ola!"]
    assert reloaded.collected_fields == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_conversation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.conversation'`

- [ ] **Step 3: Write `src/piscinow/models/conversation.py`**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from piscinow.db import Base
from piscinow.models.member import ProfileType


class MessageRole(str, enum.Enum):
    USER = "user"
    AGENT = "agent"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), nullable=True)
    profile_type_detected: Mapped[ProfileType | None] = mapped_column(
        SAEnum(ProfileType, name="profile_type"), nullable=True
    )
    collected_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, name="message_role"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
```

- [ ] **Step 4: Uncomment the `conversation` import in `tests/conftest.py`**

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/models/test_conversation.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/models/conversation.py tests/models/test_conversation.py tests/conftest.py
git commit -m "feat: Conversation and Message models"
```

---

### Task 5: MemoryItem model (pgvector)

**Files:**
- Create: `src/piscinow/models/memory.py`
- Modify: `tests/conftest.py` (uncomment `import piscinow.models.memory`)
- Test: `tests/models/test_memory.py`

**Interfaces:**
- Consumes: `piscinow.db.Base`, `piscinow.models.member.ProfileType` (Task 3).
- Produces: `piscinow.models.memory.EMBEDDING_DIM = 384`, `piscinow.models.memory.MemoryKind` (str enum: `FACT`, `RULE`, `FAQ`, `CORRECTION`), `piscinow.models.memory.MemorySource` (str enum: `AUTO`, `HUMAN`), `piscinow.models.memory.MemoryItem` (fields: `id`, `kind`, `source`, `content: str`, `embedding: list[float]`, `confidence: float`, `profile_type: ProfileType | None`, `created_by: str | None`, `superseded_by: uuid.UUID | None`, `created_at`).

- [ ] **Step 1: Write the failing test — `tests/models/test_memory.py`**

```python
from piscinow.models.memory import EMBEDDING_DIM, MemoryItem, MemoryKind, MemorySource


def test_memory_item_persists_embedding_and_finds_nearest_neighbor(db_session):
    close = MemoryItem(
        kind=MemoryKind.FACT,
        source=MemorySource.AUTO,
        content="perto",
        embedding=[1.0] + [0.0] * (EMBEDDING_DIM - 1),
    )
    far = MemoryItem(
        kind=MemoryKind.FACT,
        source=MemorySource.AUTO,
        content="longe",
        embedding=[0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2),
    )
    db_session.add_all([close, far])
    db_session.flush()

    query_vector = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
    nearest = db_session.query(MemoryItem).order_by(
        MemoryItem.embedding.cosine_distance(query_vector)
    ).first()

    assert nearest.content == "perto"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.memory'`

- [ ] **Step 3: Write `src/piscinow/models/memory.py`**

```python
import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base
from piscinow.models.member import ProfileType

EMBEDDING_DIM = 384


class MemoryKind(str, enum.Enum):
    FACT = "fact"
    RULE = "rule"
    FAQ = "faq"
    CORRECTION = "correction"


class MemorySource(str, enum.Enum):
    AUTO = "auto"
    HUMAN = "human"


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[MemoryKind] = mapped_column(SAEnum(MemoryKind, name="memory_kind"))
    source: Mapped[MemorySource] = mapped_column(SAEnum(MemorySource, name="memory_source"))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    profile_type: Mapped[ProfileType | None] = mapped_column(
        SAEnum(ProfileType, name="profile_type"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_items.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
```

- [ ] **Step 4: Uncomment the `memory` import in `tests/conftest.py`**

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/models/test_memory.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/models/memory.py tests/models/test_memory.py tests/conftest.py
git commit -m "feat: MemoryItem model with pgvector embedding column"
```

---

### Task 6: AdminUser model + password hashing

**Files:**
- Create: `src/piscinow/models/admin.py`
- Modify: `tests/conftest.py` (uncomment `import piscinow.models.admin`)
- Test: `tests/models/test_admin.py`

**Interfaces:**
- Consumes: `piscinow.db.Base` (Task 2).
- Produces: `piscinow.models.admin.AdminUser` with classmethod `AdminUser.create(*, email: str, password: str) -> AdminUser` and method `verify_password(self, password: str) -> bool`. Fields: `id`, `email: str`, `password_hash: str`, `created_at`.

- [ ] **Step 1: Write the failing tests — `tests/models/test_admin.py`**

```python
from piscinow.models.admin import AdminUser


def test_create_hashes_the_password():
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    assert admin.password_hash != "senha-forte-123"


def test_verify_password_accepts_correct_password():
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    assert admin.verify_password("senha-forte-123") is True


def test_verify_password_rejects_wrong_password():
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    assert admin.verify_password("errada") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/models/test_admin.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.models.admin'`

- [ ] **Step 3: Write `src/piscinow/models/admin.py`**

```python
import uuid
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base

_hasher = PasswordHasher()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    @classmethod
    def create(cls, *, email: str, password: str) -> "AdminUser":
        return cls(email=email, password_hash=_hasher.hash(password))

    def verify_password(self, password: str) -> bool:
        try:
            return _hasher.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False
```

- [ ] **Step 4: Uncomment the `admin` import in `tests/conftest.py`**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/models/test_admin.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/models/admin.py tests/models/test_admin.py tests/conftest.py
git commit -m "feat: AdminUser model with argon2 password hashing"
```

---

## Phase B — Agent Core

### Task 7: LLMProvider interface + FakeLLMProvider

**Files:**
- Create: `src/piscinow/agent/__init__.py`
- Create: `src/piscinow/agent/llm_provider.py`
- Create: `src/piscinow/agent/providers/__init__.py`
- Create: `src/piscinow/agent/providers/fake_provider.py`
- Test: `tests/agent/__init__.py`
- Test: `tests/agent/test_llm_provider.py`

**Interfaces:**
- Produces: `piscinow.agent.llm_provider.ChatMessage` (dataclass: `role: str`, `content: str`), `piscinow.agent.llm_provider.LLMProvider` (ABC with abstract `stream(messages: list[ChatMessage], system: str) -> AsyncIterator[str]` and concrete `async generate(messages, system) -> str`). `piscinow.agent.providers.fake_provider.FakeLLMProvider` with `__init__(scripted_responses: list[str] | None = None)` and `queue_response(text: str) -> None`.

- [ ] **Step 1: Add `pytest-asyncio` to dev dependencies**

Edit `pyproject.toml`: confirm `pytest-asyncio>=0.24` is already listed under `[project.optional-dependencies].dev` (added in Task 1). No change needed if present.

- [ ] **Step 2: Write the failing tests — `tests/agent/test_llm_provider.py`**

```python
import pytest

from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.providers.fake_provider import FakeLLMProvider


@pytest.mark.asyncio
async def test_fake_provider_streams_scripted_response():
    provider = FakeLLMProvider(["Ola tudo bem"])
    chunks = [c async for c in provider.stream([ChatMessage(role="user", content="oi")], system="")]
    assert "".join(chunks).strip() == "Ola tudo bem"


@pytest.mark.asyncio
async def test_generate_accumulates_stream():
    provider = FakeLLMProvider(["resposta completa"])
    result = await provider.generate([ChatMessage(role="user", content="oi")], system="")
    assert result.strip() == "resposta completa"


@pytest.mark.asyncio
async def test_fake_provider_echoes_when_queue_empty():
    provider = FakeLLMProvider()
    result = await provider.generate([ChatMessage(role="user", content="teste")], system="")
    assert "teste" in result


@pytest.mark.asyncio
async def test_queue_response_appends_to_existing_queue():
    provider = FakeLLMProvider(["primeira"])
    provider.queue_response("segunda")
    first = await provider.generate([ChatMessage(role="user", content="a")], system="")
    second = await provider.generate([ChatMessage(role="user", content="b")], system="")
    assert first.strip() == "primeira"
    assert second.strip() == "segunda"
```

- [ ] **Step 3: Create `tests/agent/__init__.py`** (empty file)

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/agent/test_llm_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent'`

- [ ] **Step 5: Create `src/piscinow/agent/__init__.py`** and `src/piscinow/agent/providers/__init__.py`** (empty files)

- [ ] **Step 6: Write `src/piscinow/agent/llm_provider.py`**

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Provider-agnostic interface. Every adapter implements `stream`;
    `generate` is derived from it so adapters never duplicate accumulation logic."""

    @abstractmethod
    def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        """Yield response text chunks as they're generated."""
        raise NotImplementedError

    async def generate(self, messages: list[ChatMessage], system: str) -> str:
        chunks = []
        async for chunk in self.stream(messages, system):
            chunks.append(chunk)
        return "".join(chunks)
```

- [ ] **Step 7: Write `src/piscinow/agent/providers/fake_provider.py`**

```python
from collections.abc import AsyncIterator

from piscinow.agent.llm_provider import ChatMessage, LLMProvider


class FakeLLMProvider(LLMProvider):
    """Deterministic provider for tests: returns a scripted response queue,
    or echoes the last user message if the queue is empty."""

    def __init__(self, scripted_responses: list[str] | None = None):
        self._queue: list[str] = list(scripted_responses or [])

    def queue_response(self, text: str) -> None:
        self._queue.append(text)

    async def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        if self._queue:
            text = self._queue.pop(0)
        else:
            last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
            text = f"[fake reply to: {last_user}]"
        for chunk in text.split(" "):
            yield chunk + " "
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/agent/test_llm_provider.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
git add src/piscinow/agent tests/agent
git commit -m "feat: LLMProvider interface and FakeLLMProvider for tests"
```

---

### Task 8: AnthropicProvider adapter

**Files:**
- Create: `src/piscinow/agent/providers/anthropic_provider.py`
- Test: `tests/agent/test_anthropic_provider.py`

**Interfaces:**
- Consumes: `ChatMessage`, `LLMProvider` (Task 7).
- Produces: `piscinow.agent.providers.anthropic_provider.AnthropicProvider(api_key: str, model: str = "claude-sonnet-5")`.

- [ ] **Step 1: Write the failing test — `tests/agent/test_anthropic_provider.py`**

```python
from unittest.mock import MagicMock

import pytest

from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.providers.anthropic_provider import AnthropicProvider


class _FakeStreamCtx:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _agen(self):
        for c in self._chunks:
            yield c

    @property
    def text_stream(self):
        return self._agen()


@pytest.mark.asyncio
async def test_anthropic_provider_streams_text():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=_FakeStreamCtx(["Ola", " mundo"]))

    provider = AnthropicProvider(api_key="test-key")
    provider._client = fake_client

    chunks = [
        c async for c in provider.stream([ChatMessage(role="user", content="oi")], system="seja gentil")
    ]

    assert "".join(chunks) == "Ola mundo"
    fake_client.messages.stream.assert_called_once()
    _, kwargs = fake_client.messages.stream.call_args
    assert kwargs["system"] == "seja gentil"
    assert kwargs["messages"] == [{"role": "user", "content": "oi"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_anthropic_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.providers.anthropic_provider'`

- [ ] **Step 3: Write `src/piscinow/agent/providers/anthropic_provider.py`**

```python
from collections.abc import AsyncIterator

import anthropic

from piscinow.agent.llm_provider import ChatMessage, LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        anthropic_messages = [{"role": m.role, "content": m.content} for m in messages]
        async with self._client.messages.stream(
            model=self._model,
            system=system,
            messages=anthropic_messages,
            max_tokens=1024,
        ) as stream:
            async for text in stream.text_stream:
                yield text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_anthropic_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/providers/anthropic_provider.py tests/agent/test_anthropic_provider.py
git commit -m "feat: Anthropic LLMProvider adapter"
```

---

### Task 9: OpenAIProvider adapter

**Files:**
- Create: `src/piscinow/agent/providers/openai_provider.py`
- Test: `tests/agent/test_openai_provider.py`

**Interfaces:**
- Consumes: `ChatMessage`, `LLMProvider` (Task 7).
- Produces: `piscinow.agent.providers.openai_provider.OpenAIProvider(api_key: str, model: str = "gpt-5")`.

- [ ] **Step 1: Write the failing test — `tests/agent/test_openai_provider.py`**

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.providers.openai_provider import OpenAIProvider


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeEvent:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


async def _fake_stream(chunks):
    for c in chunks:
        yield _FakeEvent(c)


@pytest.mark.asyncio
async def test_openai_provider_streams_text():
    provider = OpenAIProvider(api_key="test-key")
    provider._client = MagicMock()
    provider._client.chat.completions.create = AsyncMock(return_value=_fake_stream(["Ola", " mundo"]))

    chunks = [
        c async for c in provider.stream([ChatMessage(role="user", content="oi")], system="seja gentil")
    ]

    assert "".join(chunks) == "Ola mundo"
    _, kwargs = provider._client.chat.completions.create.call_args
    assert kwargs["messages"][0] == {"role": "system", "content": "seja gentil"}
    assert kwargs["stream"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_openai_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.providers.openai_provider'`

- [ ] **Step 3: Write `src/piscinow/agent/providers/openai_provider.py`**

```python
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from piscinow.agent.llm_provider import ChatMessage, LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-5"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def stream(self, messages: list[ChatMessage], system: str) -> AsyncIterator[str]:
        openai_messages = [{"role": "system", "content": system}]
        openai_messages += [{"role": m.role, "content": m.content} for m in messages]
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            stream=True,
        )
        async for event in stream:
            delta = event.choices[0].delta.content
            if delta:
                yield delta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_openai_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/providers/openai_provider.py tests/agent/test_openai_provider.py
git commit -m "feat: OpenAI LLMProvider adapter"
```

---

### Task 10: Provider factory (env-driven selection)

**Files:**
- Create: `src/piscinow/agent/provider_factory.py`
- Test: `tests/agent/test_provider_factory.py`

**Interfaces:**
- Consumes: `piscinow.config.Settings` (Task 1), `AnthropicProvider` (Task 8), `OpenAIProvider` (Task 9), `FakeLLMProvider` (Task 7).
- Produces: `piscinow.agent.provider_factory.build_llm_provider(settings: Settings) -> LLMProvider`.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_provider_factory.py`**

```python
import pytest

from piscinow.agent.provider_factory import build_llm_provider
from piscinow.agent.providers.anthropic_provider import AnthropicProvider
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.providers.openai_provider import OpenAIProvider
from piscinow.config import Settings


def test_builds_fake_provider_by_default():
    settings = Settings(_env_file=None, llm_provider="fake")
    assert isinstance(build_llm_provider(settings), FakeLLMProvider)


def test_builds_anthropic_provider_when_configured():
    settings = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key="test-key")
    assert isinstance(build_llm_provider(settings), AnthropicProvider)


def test_builds_openai_provider_when_configured():
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="test-key")
    assert isinstance(build_llm_provider(settings), OpenAIProvider)


def test_raises_when_anthropic_key_missing():
    settings = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key=None)
    with pytest.raises(ValueError):
        build_llm_provider(settings)


def test_raises_for_unknown_provider():
    settings = Settings(_env_file=None, llm_provider="unknown")
    with pytest.raises(ValueError):
        build_llm_provider(settings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_provider_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.provider_factory'`

- [ ] **Step 3: Write `src/piscinow/agent/provider_factory.py`**

```python
from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.providers.anthropic_provider import AnthropicProvider
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.providers.openai_provider import OpenAIProvider
from piscinow.config import Settings


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("PISCINOW_ANTHROPIC_API_KEY is required for llm_provider=anthropic")
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("PISCINOW_OPENAI_API_KEY is required for llm_provider=openai")
        return OpenAIProvider(api_key=settings.openai_api_key)
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    raise ValueError(f"unknown llm_provider: {settings.llm_provider}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_provider_factory.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/provider_factory.py tests/agent/test_provider_factory.py
git commit -m "feat: LLM provider factory driven by settings"
```

---

### Task 11: Local embeddings module

**Files:**
- Create: `src/piscinow/agent/embeddings.py`
- Test: `tests/agent/test_embeddings.py`

**Interfaces:**
- Produces: `piscinow.agent.embeddings.EMBEDDING_DIM = 384`, `piscinow.agent.embeddings.embed_text(text: str) -> list[float]`.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_embeddings.py`**

```python
import numpy as np

from piscinow.agent.embeddings import EMBEDDING_DIM, embed_text


def test_embed_text_returns_correct_dimension():
    vector = embed_text("piscina de alvenaria em Valinhos")
    assert len(vector) == EMBEDDING_DIM


def test_similar_sentences_are_closer_than_unrelated_ones():
    a = np.array(embed_text("quero construir uma piscina de alvenaria"))
    b = np.array(embed_text("gostaria de fazer uma piscina de concreto"))
    c = np.array(embed_text("qual o horario de funcionamento da loja"))

    sim_ab = float(np.dot(a, b))
    sim_ac = float(np.dot(a, c))
    assert sim_ab > sim_ac
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.embeddings'`

- [ ] **Step 3: Write `src/piscinow/agent/embeddings.py`**

```python
from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    vector = _model().encode(text, normalize_embeddings=True)
    return vector.tolist()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_embeddings.py -v`
Expected: PASS. First run downloads the model (~470MB) — requires internet access; the model is cached locally afterward (`~/.cache/torch/sentence_transformers`).

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/embeddings.py tests/agent/test_embeddings.py
git commit -m "feat: local multilingual embeddings for the memory store"
```

---

### Task 12: MemoryStore

**Files:**
- Create: `src/piscinow/agent/memory_store.py`
- Test: `tests/agent/test_memory_store.py`

**Interfaces:**
- Consumes: `embed_text` (Task 11), `MemoryItem`, `MemoryKind`, `MemorySource` (Task 5), `ProfileType` (Task 3), a SQLAlchemy `Session`.
- Produces: `piscinow.agent.memory_store.MemoryStore(session: Session)` with `write(*, content: str, kind: MemoryKind, source: MemorySource, profile_type: ProfileType | None = None, confidence: float = 0.5, created_by: str | None = None) -> MemoryItem` and `search(*, query: str, profile_type: ProfileType | None = None, limit: int = 5) -> list[MemoryItem]`.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_memory_store.py`**

```python
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.member import ProfileType
from piscinow.models.memory import MemoryKind, MemorySource


def test_write_and_search_returns_relevant_item(db_session):
    store = MemoryStore(db_session)
    store.write(
        content="Piscinas de alvenaria em Valinhos costumam levar 45 dias de obra.",
        kind=MemoryKind.FACT,
        source=MemorySource.AUTO,
    )
    store.write(
        content="A loja atende das 9h as 18h de segunda a sexta.",
        kind=MemoryKind.FAQ,
        source=MemorySource.AUTO,
    )

    results = store.search(query="quanto tempo demora construir piscina de alvenaria", limit=1)

    assert len(results) == 1
    assert "45 dias" in results[0].content


def test_human_sourced_memory_ranks_above_auto_for_similar_relevance(db_session):
    store = MemoryStore(db_session)
    store.write(
        content="Prazo medio de obra de piscina de alvenaria e 45 dias.",
        kind=MemoryKind.FACT,
        source=MemorySource.AUTO,
    )
    store.write(
        content="Prazo medio de obra de piscina de alvenaria e 45 dias, corrigido pela equipe.",
        kind=MemoryKind.CORRECTION,
        source=MemorySource.HUMAN,
        created_by="admin@piscinow.com.br",
    )

    results = store.search(query="quanto tempo demora a obra de uma piscina de alvenaria", limit=2)

    assert results[0].source == MemorySource.HUMAN


def test_search_filters_by_profile_type(db_session):
    store = MemoryStore(db_session)
    store.write(
        content="Lojas devem informar CNPJ no pre-cadastro.",
        kind=MemoryKind.RULE,
        source=MemorySource.AUTO,
        profile_type=ProfileType.LOJA,
    )
    store.write(
        content="Compradores devem informar a regiao da obra.",
        kind=MemoryKind.RULE,
        source=MemorySource.AUTO,
        profile_type=ProfileType.COMPRADOR,
    )

    results = store.search(query="quais dados preciso informar", profile_type=ProfileType.LOJA, limit=5)

    assert all(r.profile_type in (ProfileType.LOJA, None) for r in results)
    assert any("CNPJ" in r.content for r in results)


def test_search_ignores_superseded_items(db_session):
    store = MemoryStore(db_session)
    old = store.write(content="Prazo de obra e 30 dias.", kind=MemoryKind.FACT, source=MemorySource.AUTO)
    old.superseded_by = store.write(
        content="Prazo de obra e 45 dias (atualizado).", kind=MemoryKind.CORRECTION, source=MemorySource.HUMAN
    ).id

    results = store.search(query="qual o prazo de obra", limit=5)

    assert all("30 dias" not in r.content for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_memory_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.memory_store'`

- [ ] **Step 3: Write `src/piscinow/agent/memory_store.py`**

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.agent.embeddings import embed_text
from piscinow.models.member import ProfileType
from piscinow.models.memory import MemoryItem, MemoryKind, MemorySource

HUMAN_RANK_BOOST = 0.15


class MemoryStore:
    def __init__(self, session: Session):
        self._session = session

    def write(
        self,
        *,
        content: str,
        kind: MemoryKind,
        source: MemorySource,
        profile_type: ProfileType | None = None,
        confidence: float = 0.5,
        created_by: str | None = None,
    ) -> MemoryItem:
        item = MemoryItem(
            content=content,
            kind=kind,
            source=source,
            profile_type=profile_type,
            confidence=confidence,
            created_by=created_by,
            embedding=embed_text(content),
        )
        self._session.add(item)
        self._session.flush()
        return item

    def search(
        self,
        *,
        query: str,
        profile_type: ProfileType | None = None,
        limit: int = 5,
    ) -> list[MemoryItem]:
        query_vector = embed_text(query)
        candidate_limit = max(limit * 4, 20)
        stmt = select(MemoryItem).where(MemoryItem.superseded_by.is_(None))
        if profile_type is not None:
            stmt = stmt.where(
                (MemoryItem.profile_type == profile_type) | (MemoryItem.profile_type.is_(None))
            )
        stmt = stmt.order_by(MemoryItem.embedding.cosine_distance(query_vector)).limit(candidate_limit)
        candidates = list(self._session.scalars(stmt))

        def score(item: MemoryItem) -> float:
            # lower is better; embeddings are normalized, so dot product == cosine similarity
            distance = 1 - sum(x * y for x, y in zip(list(item.embedding), query_vector))
            boost = HUMAN_RANK_BOOST if item.source == MemorySource.HUMAN else 0.0
            return distance - boost

        candidates.sort(key=score)
        return candidates[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_memory_store.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/memory_store.py tests/agent/test_memory_store.py
git commit -m "feat: MemoryStore with human-priority semantic search"
```

---

### Task 13: Router/Classifier

**Files:**
- Create: `src/piscinow/agent/router.py`
- Test: `tests/agent/test_router.py`

**Interfaces:**
- Consumes: `LLMProvider`, `ChatMessage` (Task 7), `ProfileType` (Task 3).
- Produces: `piscinow.agent.router.CONFIDENCE_THRESHOLD = 0.6`, `piscinow.agent.router.ClassificationResult` (dataclass: `profile_type: ProfileType | None`, `confidence: float`), `piscinow.agent.router.Router(llm: LLMProvider)` with `async classify(message: str) -> ClassificationResult`.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_router.py`**

```python
import pytest

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.agent.router import Router
from piscinow.models.member import ProfileType


@pytest.mark.asyncio
async def test_classifies_comprador_with_high_confidence():
    provider = FakeLLMProvider(['{"profile": "comprador", "confidence": 0.92}'])
    router = Router(provider)

    result = await router.classify("quero fazer uma piscina de alvenaria")

    assert result.profile_type == ProfileType.COMPRADOR
    assert result.confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_low_confidence_returns_none_profile():
    provider = FakeLLMProvider(['{"profile": "loja", "confidence": 0.3}'])
    router = Router(provider)

    result = await router.classify("oi")

    assert result.profile_type is None


@pytest.mark.asyncio
async def test_malformed_response_returns_none_profile():
    provider = FakeLLMProvider(["desculpe nao entendi"])
    router = Router(provider)

    result = await router.classify("oi")

    assert result.profile_type is None


@pytest.mark.asyncio
async def test_unknown_profile_value_returns_none_profile():
    provider = FakeLLMProvider(['{"profile": "turista", "confidence": 0.9}'])
    router = Router(provider)

    result = await router.classify("oi")

    assert result.profile_type is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.router'`

- [ ] **Step 3: Write `src/piscinow/agent/router.py`**

```python
import json
import re
from dataclasses import dataclass

from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.models.member import ProfileType

CONFIDENCE_THRESHOLD = 0.6

_SYSTEM_PROMPT = """Voce e o classificador de perfil do Clube Piscinow.
Leia a mensagem do visitante e decida qual perfil ele tem: comprador, loja,
prestador ou embaixador. Responda APENAS com um JSON de uma linha no formato
{"profile": "<comprador|loja|prestador|embaixador>", "confidence": <0.0 a 1.0>}
sem nenhum texto adicional."""


@dataclass
class ClassificationResult:
    profile_type: ProfileType | None
    confidence: float


class Router:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def classify(self, message: str) -> ClassificationResult:
        raw = await self._llm.generate(
            [ChatMessage(role="user", content=message)],
            system=_SYSTEM_PROMPT,
        )
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> ClassificationResult:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return ClassificationResult(profile_type=None, confidence=0.0)
        try:
            data = json.loads(match.group(0))
            profile = ProfileType(data["profile"])
            confidence = float(data["confidence"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return ClassificationResult(profile_type=None, confidence=0.0)
        if confidence < CONFIDENCE_THRESHOLD:
            return ClassificationResult(profile_type=None, confidence=confidence)
        return ClassificationResult(profile_type=profile, confidence=confidence)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_router.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/router.py tests/agent/test_router.py
git commit -m "feat: profile Router/Classifier"
```

---

### Task 14: Base ConversationHandler

**Files:**
- Create: `src/piscinow/agent/handlers/__init__.py`
- Create: `src/piscinow/agent/handlers/base.py`
- Test: `tests/agent/test_handlers_base.py`

**Interfaces:**
- Consumes: `LLMProvider`, `ChatMessage` (Task 7), `MemoryStore` (Task 12), `ProfileType` (Task 3).
- Produces: `piscinow.agent.handlers.base.FieldSpec` (dataclass: `name: str`, `ask_hint: str`), `piscinow.agent.handlers.base.ConversationHandler` — base class with class attributes `profile_type: ProfileType`, `required_fields: list[FieldSpec]`, `role_description: str`; instance methods `missing_fields(collected: dict) -> list[FieldSpec]`, `async reply(history: list[ChatMessage], collected: dict) -> str`, `async extract_fields(history: list[ChatMessage], collected: dict) -> dict`. Every profile handler (Tasks 15-18) subclasses this.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_handlers_base.py`**

```python
import pytest

from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.agent.llm_provider import ChatMessage
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import ProfileType


class _DummyHandler(ConversationHandler):
    profile_type = ProfileType.COMPRADOR
    role_description = "visitante de teste"
    required_fields = [
        FieldSpec("name", "pergunte o nome"),
        FieldSpec("contact", "pergunte o contato"),
    ]


def _handler(db_session, provider=None):
    provider = provider or FakeLLMProvider()
    return _DummyHandler(provider, MemoryStore(db_session)), provider


def test_missing_fields_lists_all_when_nothing_collected(db_session):
    handler, _ = _handler(db_session)
    missing = handler.missing_fields({})
    assert {f.name for f in missing} == {"name", "contact"}


def test_missing_fields_shrinks_as_data_collected(db_session):
    handler, _ = _handler(db_session)
    missing = handler.missing_fields({"name": "Marina"})
    assert {f.name for f in missing} == {"contact"}


@pytest.mark.asyncio
async def test_extract_fields_parses_llm_json(db_session):
    provider = FakeLLMProvider(['{"name": "Marina Duarte", "contact": "(19) 99999-0000"}'])
    handler, _ = _handler(db_session, provider)

    updated = await handler.extract_fields(
        [ChatMessage(role="user", content="sou a Marina Duarte, (19) 99999-0000")],
        collected={},
    )

    assert updated["name"] == "Marina Duarte"
    assert updated["contact"] == "(19) 99999-0000"


@pytest.mark.asyncio
async def test_extract_fields_keeps_previously_collected_values_when_llm_returns_null(db_session):
    provider = FakeLLMProvider(['{"name": null, "contact": "(19) 99999-0000"}'])
    handler, _ = _handler(db_session, provider)

    updated = await handler.extract_fields(
        [ChatMessage(role="user", content="(19) 99999-0000")],
        collected={"name": "Marina Duarte"},
    )

    assert updated["name"] == "Marina Duarte"
    assert updated["contact"] == "(19) 99999-0000"


@pytest.mark.asyncio
async def test_reply_system_prompt_names_missing_fields(db_session):
    handler, provider = _handler(db_session)
    captured = {}

    async def fake_generate(history, system):
        captured["system"] = system
        return "ok"

    provider.generate = fake_generate

    await handler.reply([ChatMessage(role="user", content="oi")], collected={"name": "Marina"})

    assert "contato" in captured["system"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_handlers_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.handlers'`

- [ ] **Step 3: Create `src/piscinow/agent/handlers/__init__.py`** (empty file)

- [ ] **Step 4: Write `src/piscinow/agent/handlers/base.py`**

```python
import json
import re
from dataclasses import dataclass

from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.member import ProfileType


@dataclass
class FieldSpec:
    name: str
    ask_hint: str  # instrucao em portugues do que perguntar/extrair


class ConversationHandler:
    profile_type: ProfileType
    required_fields: list[FieldSpec] = []
    role_description: str = ""

    def __init__(self, llm: LLMProvider, memory: MemoryStore):
        self.llm = llm
        self.memory = memory

    def missing_fields(self, collected: dict) -> list[FieldSpec]:
        return [f for f in self.required_fields if not collected.get(f.name)]

    def _build_system_prompt(self, collected: dict, memory_items: list) -> str:
        missing = self.missing_fields(collected)
        missing_text = (
            "; ".join(f.ask_hint for f in missing)
            if missing
            else "todos os dados necessarios ja foram coletados"
        )
        memory_text = "\n".join(f"- {m.content}" for m in memory_items) or "nenhum aprendizado relevante ainda"
        return (
            f"Voce e o concierge do Clube Piscinow, falando com um(a) {self.role_description}.\n"
            f"Responda sempre em portugues, de forma direta e cordial.\n"
            f"Dados ainda faltando: {missing_text}.\n"
            f"Aprendizados relevantes:\n{memory_text}"
        )

    async def reply(self, history: list[ChatMessage], collected: dict) -> str:
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        memory_items = self.memory.search(query=last_user, profile_type=self.profile_type, limit=5)
        system = self._build_system_prompt(collected, memory_items)
        return await self.llm.generate(history, system=system)

    async def extract_fields(self, history: list[ChatMessage], collected: dict) -> dict:
        field_names = [f.name for f in self.required_fields]
        instruction = (
            "Extraia do historico da conversa os seguintes campos, em JSON: "
            f"{field_names}. Use null para campos ainda nao informados. "
            "Responda APENAS com o JSON."
        )
        raw = await self.llm.generate(history, system=instruction)
        extracted = self._parse_json(raw)
        updated = dict(collected)
        for name in field_names:
            value = extracted.get(name)
            if value:
                updated[name] = value
        return updated

    @staticmethod
    def _parse_json(raw: str) -> dict:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agent/test_handlers_base.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/agent/handlers tests/agent/test_handlers_base.py
git commit -m "feat: base ConversationHandler with field-collection loop"
```

---

### Task 15: CompradorHandler and LojaHandler

**Files:**
- Create: `src/piscinow/agent/handlers/comprador.py`
- Create: `src/piscinow/agent/handlers/loja.py`
- Test: `tests/agent/test_handlers_comprador_loja.py`

**Interfaces:**
- Consumes: `ConversationHandler`, `FieldSpec` (Task 14).
- Produces: `piscinow.agent.handlers.comprador.CompradorHandler` (required fields: `name`, `contact`, `region`, `intent`), `piscinow.agent.handlers.loja.LojaHandler` (required fields: `name`, `contact`, `cnpj`, `region`, `categories`).

- [ ] **Step 1: Write the failing tests — `tests/agent/test_handlers_comprador_loja.py`**

```python
from piscinow.agent.handlers.comprador import CompradorHandler
from piscinow.agent.handlers.loja import LojaHandler
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import ProfileType


def test_comprador_handler_required_fields(db_session):
    handler = CompradorHandler(FakeLLMProvider(), MemoryStore(db_session))
    assert handler.profile_type == ProfileType.COMPRADOR
    assert {f.name for f in handler.required_fields} == {"name", "contact", "region", "intent"}


def test_loja_handler_required_fields(db_session):
    handler = LojaHandler(FakeLLMProvider(), MemoryStore(db_session))
    assert handler.profile_type == ProfileType.LOJA
    assert {f.name for f in handler.required_fields} == {"name", "contact", "cnpj", "region", "categories"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_handlers_comprador_loja.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.handlers.comprador'`

- [ ] **Step 3: Write `src/piscinow/agent/handlers/comprador.py`**

```python
from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class CompradorHandler(ConversationHandler):
    profile_type = ProfileType.COMPRADOR
    role_description = "comprador que quer construir uma piscina"
    required_fields = [
        FieldSpec("name", "pergunte o nome completo do visitante"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
        FieldSpec("region", "pergunte em qual cidade/regiao sera a obra"),
        FieldSpec("intent", "pergunte que tipo de piscina e tamanho aproximado ele quer"),
    ]
```

- [ ] **Step 4: Write `src/piscinow/agent/handlers/loja.py`**

```python
from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class LojaHandler(ConversationHandler):
    profile_type = ProfileType.LOJA
    role_description = "loja que quer se cadastrar como fornecedora"
    required_fields = [
        FieldSpec("name", "pergunte o nome da loja"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
        FieldSpec("cnpj", "pergunte o CNPJ da loja"),
        FieldSpec("region", "pergunte em qual cidade/regiao a loja atende"),
        FieldSpec(
            "categories",
            "pergunte quais categorias de produto a loja trabalha (vinil, fibra, alvenaria, equipamentos)",
        ),
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agent/test_handlers_comprador_loja.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/agent/handlers/comprador.py src/piscinow/agent/handlers/loja.py tests/agent/test_handlers_comprador_loja.py
git commit -m "feat: Comprador and Loja conversation handlers"
```

---

### Task 16: PrestadorHandler and EmbaixadorHandler

**Files:**
- Create: `src/piscinow/agent/handlers/prestador.py`
- Create: `src/piscinow/agent/handlers/embaixador.py`
- Test: `tests/agent/test_handlers_prestador_embaixador.py`

**Interfaces:**
- Consumes: `ConversationHandler`, `FieldSpec` (Task 14).
- Produces: `piscinow.agent.handlers.prestador.PrestadorHandler` (required fields: `name`, `contact`, `document`, `region`, `experience_years`), `piscinow.agent.handlers.embaixador.EmbaixadorHandler` (required fields: `name`, `contact`).

- [ ] **Step 1: Write the failing tests — `tests/agent/test_handlers_prestador_embaixador.py`**

```python
from piscinow.agent.handlers.embaixador import EmbaixadorHandler
from piscinow.agent.handlers.prestador import PrestadorHandler
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.member import ProfileType


def test_prestador_handler_required_fields(db_session):
    handler = PrestadorHandler(FakeLLMProvider(), MemoryStore(db_session))
    assert handler.profile_type == ProfileType.PRESTADOR
    assert {f.name for f in handler.required_fields} == {
        "name", "contact", "document", "region", "experience_years"
    }


def test_embaixador_handler_only_requires_name_and_contact(db_session):
    handler = EmbaixadorHandler(FakeLLMProvider(), MemoryStore(db_session))
    assert handler.profile_type == ProfileType.EMBAIXADOR
    assert {f.name for f in handler.required_fields} == {"name", "contact"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_handlers_prestador_embaixador.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.handlers.prestador'`

- [ ] **Step 3: Write `src/piscinow/agent/handlers/prestador.py`**

```python
from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class PrestadorHandler(ConversationHandler):
    profile_type = ProfileType.PRESTADOR
    role_description = "prestador de servico que quer se cadastrar como instalador"
    required_fields = [
        FieldSpec("name", "pergunte o nome do prestador ou da empresa"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
        FieldSpec("document", "pergunte o CPF ou CNPJ"),
        FieldSpec("region", "pergunte em quais cidades/regioes ele atende"),
        FieldSpec("experience_years", "pergunte ha quantos anos trabalha com obras de piscina"),
    ]
```

- [ ] **Step 4: Write `src/piscinow/agent/handlers/embaixador.py`**

```python
from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class EmbaixadorHandler(ConversationHandler):
    profile_type = ProfileType.EMBAIXADOR
    role_description = "pessoa que quer se tornar embaixador do Clube e indicar amigos"
    required_fields = [
        FieldSpec("name", "pergunte o nome completo"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agent/test_handlers_prestador_embaixador.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/agent/handlers/prestador.py src/piscinow/agent/handlers/embaixador.py tests/agent/test_handlers_prestador_embaixador.py
git commit -m "feat: Prestador and Embaixador conversation handlers"
```

---

### Task 17: Referral code module

**Files:**
- Create: `src/piscinow/referral.py`
- Test: `tests/test_referral.py`

**Interfaces:**
- Consumes: `Member`, `ProfileType` (Task 3), a SQLAlchemy `Session`.
- Produces: `piscinow.referral.generate_referral_code(*, length: int = 8) -> str`, `piscinow.referral.get_or_create_referral_code(session: Session, member: Member) -> str`, `piscinow.referral.find_referrer(session: Session, code: str) -> Member | None`.

- [ ] **Step 1: Write the failing tests — `tests/test_referral.py`**

```python
from piscinow.models.member import Member, ProfileType
from piscinow.referral import find_referrer, generate_referral_code, get_or_create_referral_code


def test_generate_referral_code_has_expected_length():
    assert len(generate_referral_code()) == 8


def test_get_or_create_referral_code_is_stable(db_session):
    member = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo")
    db_session.add(member)
    db_session.flush()

    first = get_or_create_referral_code(db_session, member)
    second = get_or_create_referral_code(db_session, member)

    assert first == second


def test_find_referrer_returns_matching_member(db_session):
    member = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(member)
    db_session.flush()

    found = find_referrer(db_session, "RM7X2K9A")

    assert found is not None
    assert found.id == member.id


def test_find_referrer_returns_none_for_unknown_code(db_session):
    assert find_referrer(db_session, "UNKNOWN1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_referral.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.referral'`

- [ ] **Step 3: Write `src/piscinow/referral.py`**

```python
import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member

_ALPHABET = string.ascii_uppercase + string.digits


def generate_referral_code(*, length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def get_or_create_referral_code(session: Session, member: Member) -> str:
    if member.referral_code:
        return member.referral_code
    code = generate_referral_code()
    while session.scalar(select(Member).where(Member.referral_code == code)) is not None:
        code = generate_referral_code()
    member.referral_code = code
    session.flush()
    return member.referral_code


def find_referrer(session: Session, code: str) -> Member | None:
    return session.scalar(select(Member).where(Member.referral_code == code))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_referral.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/referral.py tests/test_referral.py
git commit -m "feat: referral code generation and lookup"
```

---

### Task 18: Orchestrator

**Files:**
- Create: `src/piscinow/agent/orchestrator.py`
- Test: `tests/agent/test_orchestrator.py`

**Interfaces:**
- Consumes: `Router` (Task 13), all four handlers (Tasks 15-16), `MemoryStore` (Task 12), `get_or_create_referral_code` (Task 17), `Member`, `MemberStatus`, `ProfileType` (Task 3), `Conversation`, `Message`, `MessageRole` (Task 4).
- Produces: `piscinow.agent.orchestrator.TurnResult` (dataclass: `reply_text: str`, `finalized: bool`), `piscinow.agent.orchestrator.CLARIFYING_QUESTION: str`, `piscinow.agent.orchestrator.HANDLER_CLASSES: dict[ProfileType, type[ConversationHandler]]`, `piscinow.agent.orchestrator.Orchestrator(session: Session, llm: LLMProvider)` with `async handle_user_message(conversation: Conversation, message_text: str, *, referred_by: Member | None) -> TurnResult`. This is what `agent/extractor.py` (Task 19) and the chat route (Task 24) call.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_orchestrator.py`**

```python
import pytest

from piscinow.agent.orchestrator import Orchestrator
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.conversation import Conversation
from piscinow.models.member import Member, MemberStatus, ProfileType


@pytest.mark.asyncio
async def test_comprador_flow_without_referral_ends_waitlisted(db_session):
    provider = FakeLLMProvider()
    orchestrator = Orchestrator(db_session, provider)
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    provider.queue_response('{"name": null, "contact": null, "region": null, "intent": null}')
    result = await orchestrator.handle_user_message(conversation, "quero fazer uma piscina", referred_by=None)
    assert result.finalized is False

    provider.queue_response(
        '{"name": "Marina Duarte", "contact": "(19) 99999-0000", "region": "Valinhos", "intent": "alvenaria 6x3"}'
    )
    # NOTE: no reply text is queued here — once every required field is
    # collected, the orchestrator finalizes via `_finalize_reply`, which is
    # deterministic (no LLM call), so nothing needs to be scripted for it.
    result = await orchestrator.handle_user_message(
        conversation,
        "Marina Duarte, (19) 99999-0000, em Valinhos, alvenaria 6x3",
        referred_by=None,
    )

    assert result.finalized is True
    member = db_session.get(Member, conversation.member_id)
    assert member.status == MemberStatus.WAITLISTED
    assert member.profile_type == ProfileType.COMPRADOR


@pytest.mark.asyncio
async def test_embaixador_referral_auto_approves_member(db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    provider = FakeLLMProvider()
    orchestrator = Orchestrator(db_session, provider)
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    provider.queue_response('{"profile": "comprador", "confidence": 0.95}')
    provider.queue_response(
        '{"name": "Joao Silva", "contact": "19988887777", "region": "Campinas", "intent": "vinil pequena"}'
    )
    # Finalize reply is deterministic (no LLM call) once fields are complete —
    # no extra queued response needed here.

    result = await orchestrator.handle_user_message(
        conversation,
        "Joao Silva, 19988887777, Campinas, quero uma piscina de vinil pequena",
        referred_by=referrer,
    )

    assert result.finalized is True
    member = db_session.get(Member, conversation.member_id)
    assert member.status == MemberStatus.APPROVED
    assert member.referred_by_member_id == referrer.id


@pytest.mark.asyncio
async def test_low_confidence_classification_asks_clarifying_question(db_session):
    provider = FakeLLMProvider()
    orchestrator = Orchestrator(db_session, provider)
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    provider.queue_response('{"profile": "comprador", "confidence": 0.2}')

    result = await orchestrator.handle_user_message(conversation, "oi", referred_by=None)

    assert result.finalized is False
    assert conversation.profile_type_detected is None


@pytest.mark.asyncio
async def test_embaixador_flow_generates_referral_code_in_reply(db_session):
    provider = FakeLLMProvider()
    orchestrator = Orchestrator(db_session, provider)
    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    provider.queue_response('{"profile": "embaixador", "confidence": 0.9}')
    provider.queue_response('{"name": "Rodrigo Anjos", "contact": "19999990000"}')
    # No third queued response: finalize reply is built deterministically by
    # `_finalize_reply`, not generated by the LLM.

    result = await orchestrator.handle_user_message(
        conversation, "quero ser embaixador, Rodrigo Anjos, 19999990000", referred_by=None
    )

    member = db_session.get(Member, conversation.member_id)
    assert member.referral_code is not None
    assert member.referral_code in result.reply_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.orchestrator'`

- [ ] **Step 3: Write `src/piscinow/agent/orchestrator.py`**

```python
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from piscinow.agent.handlers.base import ConversationHandler
from piscinow.agent.handlers.comprador import CompradorHandler
from piscinow.agent.handlers.embaixador import EmbaixadorHandler
from piscinow.agent.handlers.loja import LojaHandler
from piscinow.agent.handlers.prestador import PrestadorHandler
from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.router import Router
from piscinow.models.conversation import Conversation, Message, MessageRole
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.referral import get_or_create_referral_code

HANDLER_CLASSES: dict[ProfileType, type[ConversationHandler]] = {
    ProfileType.COMPRADOR: CompradorHandler,
    ProfileType.LOJA: LojaHandler,
    ProfileType.PRESTADOR: PrestadorHandler,
    ProfileType.EMBAIXADOR: EmbaixadorHandler,
}

CLARIFYING_QUESTION = (
    "Voce e comprador, loja, prestador de servico ou quer ser embaixador do Clube?"
)


@dataclass
class TurnResult:
    reply_text: str
    finalized: bool


class Orchestrator:
    def __init__(self, session: Session, llm: LLMProvider):
        self._session = session
        self._llm = llm
        self._memory = MemoryStore(session)
        self._router = Router(llm)

    async def handle_user_message(
        self, conversation: Conversation, message_text: str, *, referred_by: Member | None
    ) -> TurnResult:
        self._session.add(Message(conversation=conversation, role=MessageRole.USER, content=message_text))
        self._session.flush()
        history = self._history_as_messages(conversation)

        if conversation.profile_type_detected is None:
            classification = await self._router.classify(message_text)
            if classification.profile_type is None:
                self._session.add(
                    Message(conversation=conversation, role=MessageRole.AGENT, content=CLARIFYING_QUESTION)
                )
                return TurnResult(reply_text=CLARIFYING_QUESTION, finalized=False)
            conversation.profile_type_detected = classification.profile_type

        handler = HANDLER_CLASSES[conversation.profile_type_detected](self._llm, self._memory)
        conversation.collected_fields = await handler.extract_fields(history, conversation.collected_fields)

        if handler.missing_fields(conversation.collected_fields):
            reply = await handler.reply(history, conversation.collected_fields)
            self._session.add(Message(conversation=conversation, role=MessageRole.AGENT, content=reply))
            return TurnResult(reply_text=reply, finalized=False)

        member = self._finalize_member(conversation, handler, referred_by=referred_by)
        reply = self._finalize_reply(member)
        self._session.add(Message(conversation=conversation, role=MessageRole.AGENT, content=reply))
        conversation.ended_at = conversation.ended_at or datetime.utcnow()
        return TurnResult(reply_text=reply, finalized=True)

    def _finalize_member(
        self, conversation: Conversation, handler: ConversationHandler, *, referred_by: Member | None
    ) -> Member:
        fields = conversation.collected_fields
        member = Member(
            profile_type=conversation.profile_type_detected,
            name=fields.get("name", ""),
            profile_details=fields,
            referred_by_member_id=referred_by.id if referred_by else None,
        )
        member.submit_for_review()
        if referred_by is not None:
            member.auto_approve_via_referral()
        if member.profile_type == ProfileType.EMBAIXADOR:
            self._session.add(member)
            self._session.flush()
            get_or_create_referral_code(self._session, member)
        else:
            self._session.add(member)
            self._session.flush()
        conversation.member_id = member.id
        return member

    @staticmethod
    def _finalize_reply(member: Member) -> str:
        if member.status == MemberStatus.APPROVED:
            base = "Voce entrou direto no Clube pela indicacao recebida."
        else:
            base = "Voce esta na fila de admissao do Clube; a equipe revisa e libera o acesso."
        if member.profile_type == ProfileType.EMBAIXADOR:
            return f"{base} Seu link de indicacao: clubepiscinow.com.br/convite/{member.referral_code}"
        return base

    @staticmethod
    def _history_as_messages(conversation: Conversation) -> list[ChatMessage]:
        role_map = {MessageRole.USER: "user", MessageRole.AGENT: "assistant"}
        return [ChatMessage(role=role_map[m.role], content=m.content) for m in conversation.messages]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_orchestrator.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/orchestrator.py tests/agent/test_orchestrator.py
git commit -m "feat: Orchestrator wiring router, handlers, and member finalization"
```

---

### Task 19: Extractor

**Files:**
- Create: `src/piscinow/agent/extractor.py`
- Test: `tests/agent/test_extractor.py`

**Interfaces:**
- Consumes: `LLMProvider`, `ChatMessage` (Task 7), `MemoryStore` (Task 12), `Conversation` (Task 4), `MemoryKind`, `MemorySource` (Task 5).
- Produces: `piscinow.agent.extractor.Extractor(llm: LLMProvider, memory: MemoryStore)` with `async process(conversation: Conversation) -> None`.

- [ ] **Step 1: Write the failing tests — `tests/agent/test_extractor.py`**

```python
import pytest

from piscinow.agent.extractor import Extractor
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.conversation import Conversation, Message, MessageRole
from piscinow.models.member import ProfileType


@pytest.mark.asyncio
async def test_extractor_writes_learning_when_llm_finds_one(db_session):
    provider = FakeLLMProvider(["Compradores de Valinhos costumam perguntar sobre prazo antes de fechar."])
    memory = MemoryStore(db_session)
    extractor = Extractor(provider, memory)

    conversation = Conversation(profile_type_detected=ProfileType.COMPRADOR)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation=conversation, role=MessageRole.USER, content="quanto tempo demora?"))
    db_session.flush()

    await extractor.process(conversation)

    results = memory.search(query="prazo de obra em Valinhos", profile_type=ProfileType.COMPRADOR, limit=5)
    assert any("prazo" in r.content.lower() for r in results)


@pytest.mark.asyncio
async def test_extractor_writes_nothing_when_llm_says_nada(db_session):
    provider = FakeLLMProvider(["NADA"])
    memory = MemoryStore(db_session)
    extractor = Extractor(provider, memory)

    conversation = Conversation(profile_type_detected=ProfileType.COMPRADOR)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation=conversation, role=MessageRole.USER, content="oi"))
    db_session.flush()

    await extractor.process(conversation)

    results = memory.search(query="oi", profile_type=ProfileType.COMPRADOR, limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_extractor_does_nothing_for_empty_conversation(db_session):
    provider = FakeLLMProvider(["nao deveria ser chamado"])
    memory = MemoryStore(db_session)
    extractor = Extractor(provider, memory)

    conversation = Conversation()
    db_session.add(conversation)
    db_session.flush()

    await extractor.process(conversation)

    results = memory.search(query="nao deveria ser chamado", limit=5)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.agent.extractor'`

- [ ] **Step 3: Write `src/piscinow/agent/extractor.py`**

```python
from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.conversation import Conversation
from piscinow.models.memory import MemoryKind, MemorySource

_SYSTEM_PROMPT = """Analise a conversa entre o concierge do Clube Piscinow e um
visitante. Se houver algum fato, objecao ou padrao reaproveitavel para
conversas futuras do mesmo perfil, escreva UMA frase curta e autocontida
resumindo esse aprendizado. Se nao houver nada relevante, responda apenas
com a palavra NADA."""


class Extractor:
    def __init__(self, llm: LLMProvider, memory: MemoryStore):
        self._llm = llm
        self._memory = memory

    async def process(self, conversation: Conversation) -> None:
        history = [
            ChatMessage(role="user" if m.role.value == "user" else "assistant", content=m.content)
            for m in conversation.messages
        ]
        if not history:
            return
        learning = (await self._llm.generate(history, system=_SYSTEM_PROMPT)).strip()
        if not learning or learning.upper() == "NADA":
            return
        self._memory.write(
            content=learning,
            kind=MemoryKind.FACT,
            source=MemorySource.AUTO,
            profile_type=conversation.profile_type_detected,
            confidence=0.4,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_extractor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/piscinow/agent/extractor.py tests/agent/test_extractor.py
git commit -m "feat: post-conversation learning Extractor"
```

---

## Phase C — Web layer

### Task 20: FastAPI app skeleton

**Files:**
- Create: `src/piscinow/web/__init__.py`
- Create: `src/piscinow/web/deps.py`
- Create: `src/piscinow/web/app.py`
- Create: `src/piscinow/web/routes/__init__.py`
- Create: `src/piscinow/web/routes/pages.py`
- Create: `src/piscinow/web/routes/chat.py` (stub `router = APIRouter()`, filled in Task 22)
- Create: `src/piscinow/web/routes/admin.py` (stub `router = APIRouter()`, filled in Task 23)
- Create: `src/piscinow/web/templates/base.html`
- Create: `src/piscinow/web/templates/home.html`
- Create: `src/piscinow/static/css/app.css`
- Test: `tests/web/__init__.py`
- Test: `tests/web/conftest.py`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: `get_settings` (Task 1).
- Produces: `piscinow.web.deps.get_db` (FastAPI dependency yielding a `Session`), `piscinow.web.app.create_app() -> FastAPI`. Test fixture `client` (in `tests/web/conftest.py`) — a `TestClient` wired to `db_session`, reused by every later web test.

- [ ] **Step 1: Write the failing test — `tests/web/test_app.py`**

```python
def test_app_serves_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Piscinow" in response.text
```

- [ ] **Step 2: Write `tests/web/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from piscinow.web.app import create_app
from piscinow.web.deps import get_db


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)
```

- [ ] **Step 3: Create `tests/web/__init__.py`** (empty file)

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/web/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'piscinow.web'`

- [ ] **Step 5: Write `src/piscinow/web/deps.py`**

```python
from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from piscinow.agent.llm_provider import LLMProvider
from piscinow.db import make_engine, make_session_factory

_engine = make_engine()
_SessionFactory = make_session_factory(_engine)


def get_db() -> Generator[Session, None, None]:
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider
```

- [ ] **Step 6: Write `src/piscinow/web/routes/pages.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "home.html", {"referred_by_name": None})
```

- [ ] **Step 7: Write stub routers — `src/piscinow/web/routes/chat.py` and `src/piscinow/web/routes/admin.py`**

```python
# src/piscinow/web/routes/chat.py
from fastapi import APIRouter

router = APIRouter()
```

```python
# src/piscinow/web/routes/admin.py
from fastapi import APIRouter

router = APIRouter(prefix="/admin")
```

- [ ] **Step 8: Create `src/piscinow/web/routes/__init__.py`** (empty file)

- [ ] **Step 9: Write `src/piscinow/web/templates/base.html`**

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Clube Piscinow{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
  {% block content %}{% endblock %}
</body>
</html>
```

- [ ] **Step 10: Write `src/piscinow/web/templates/home.html`**

```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Clube Piscinow</h1>
  <p>Um clube de piscinas, nao uma loja.</p>
  <section id="chat">
    <div id="chat-body"></div>
    <form id="chat-form">
      <input id="chat-input" type="text" name="message" placeholder="Fale com o concierge...">
      <button type="submit">Enviar</button>
    </form>
  </section>
</main>
<script src="/static/js/chat.js"></script>
{% endblock %}
```

- [ ] **Step 11: Write `src/piscinow/static/css/app.css`**

```css
body { font-family: sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
#chat-body { border: 1px solid #ccc; min-height: 200px; padding: 0.5rem; margin-bottom: 0.5rem; }
.msg { margin: 0.25rem 0; }
.msg.user { text-align: right; }
```

- [ ] **Step 12: Write `src/piscinow/web/app.py`**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from piscinow.agent.provider_factory import build_llm_provider
from piscinow.config import get_settings
from piscinow.web.routes import admin, chat, pages

TEMPLATES = Jinja2Templates(directory="src/piscinow/web/templates")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Clube Piscinow")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount("/static", StaticFiles(directory="src/piscinow/static"), name="static")
    app.state.templates = TEMPLATES
    app.state.llm_provider = build_llm_provider(settings)
    app.include_router(pages.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


app = create_app()
```

- [ ] **Step 13: Create `src/piscinow/web/__init__.py`** (empty file)

- [ ] **Step 14: Run test to verify it passes**

Run: `pytest tests/web/test_app.py -v`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add src/piscinow/web src/piscinow/static tests/web
git commit -m "feat: FastAPI app skeleton with home page"
```

---

### Task 21: Referral landing route + home referral banner

**Files:**
- Modify: `src/piscinow/web/routes/pages.py`
- Modify: `src/piscinow/web/templates/home.html`
- Test: `tests/web/test_pages.py`

**Interfaces:**
- Consumes: `find_referrer` (Task 17), `get_db` (Task 20).
- Produces: `GET /convite/{code}` (sets `piscinow_ref` cookie, redirects to `/`), updated `home()` reading that cookie and passing `referred_by_name` to the template.

- [ ] **Step 1: Write the failing tests — `tests/web/test_pages.py`**

```python
from piscinow.models.member import Member, ProfileType


def test_convite_sets_cookie_for_valid_code(client, db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    response = client.get("/convite/RM7X2K9A", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.cookies.get("piscinow_ref") == "RM7X2K9A"


def test_convite_with_unknown_code_does_not_set_cookie(client):
    response = client.get("/convite/UNKNOWN1", follow_redirects=False)
    assert response.cookies.get("piscinow_ref") is None


def test_home_shows_referrer_name_when_cookie_present(client, db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo Anjos", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    client.cookies.set("piscinow_ref", "RM7X2K9A")
    response = client.get("/")

    assert "Rodrigo Anjos" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_pages.py -v`
Expected: FAIL — `404` on `/convite/RM7X2K9A` (route doesn't exist yet)

- [ ] **Step 3: Rewrite `src/piscinow/web/routes/pages.py`**

```python
from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.referral import find_referrer
from piscinow.web.deps import get_db

router = APIRouter()

REFERRAL_COOKIE = "piscinow_ref"


@router.get("/convite/{code}")
async def convite(code: str, db: Session = Depends(get_db)):
    referrer = find_referrer(db, code)
    response = RedirectResponse(url="/")
    if referrer is not None:
        response.set_cookie(REFERRAL_COOKIE, code, max_age=60 * 60 * 24 * 30)
    return response


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: Session = Depends(get_db),
    piscinow_ref: str | None = Cookie(default=None),
):
    templates = request.app.state.templates
    referrer = find_referrer(db, piscinow_ref) if piscinow_ref else None
    return templates.TemplateResponse(
        request, "home.html", {"referred_by_name": referrer.name if referrer else None}
    )
```

- [ ] **Step 4: Update `src/piscinow/web/templates/home.html`** — add the referral banner right after `<h1>`

```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Clube Piscinow</h1>
  {% if referred_by_name %}
    <p class="referral-banner">Voce foi indicado por {{ referred_by_name }} — entrada facilitada no Clube.</p>
  {% endif %}
  <p>Um clube de piscinas, nao uma loja.</p>
  <section id="chat">
    <div id="chat-body"></div>
    <form id="chat-form">
      <input id="chat-input" type="text" name="message" placeholder="Fale com o concierge...">
      <button type="submit">Enviar</button>
    </form>
  </section>
</main>
<script src="/static/js/chat.js"></script>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/web/test_pages.py tests/web/test_app.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/pages.py src/piscinow/web/templates/home.html tests/web/test_pages.py
git commit -m "feat: referral landing route and home referral banner"
```

---

### Task 22: Chat endpoint + client script

**Files:**
- Modify: `src/piscinow/web/routes/chat.py`
- Create: `src/piscinow/static/js/chat.js`
- Test: `tests/web/test_chat.py`

**Interfaces:**
- Consumes: `Orchestrator` (Task 18), `Extractor` (Task 19), `find_referrer` (Task 17), `get_db`, `get_llm_provider` (Task 20).
- Produces: `POST /api/chat/message` (form field `message`, sets `piscinow_session` cookie, returns the assistant's full reply as `text/plain` via `StreamingResponse`). When a turn finalizes (`result.finalized is True`), schedules `Extractor.process(conversation)` as a FastAPI `BackgroundTasks` job — this is the plan's wiring of the spec's "loop de aprendizado": the Extractor built in Task 19 is otherwise never invoked by the running application.

- [ ] **Step 1: Write the failing tests — `tests/web/test_chat.py`**

```python
from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.conversation import Conversation
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_llm_provider


def test_send_message_creates_conversation_and_sets_session_cookie(client):
    provider = FakeLLMProvider(['{"profile": "comprador", "confidence": 0.9}'])
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    response = client.post("/api/chat/message", data={"message": "quero uma piscina"})

    assert response.status_code == 200
    assert response.cookies.get("piscinow_session") is not None


def test_second_message_reuses_same_conversation(client, db_session):
    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero uma piscina"})
    session_cookie = first.cookies.get("piscinow_session")

    provider.queue_response('{"name": null, "contact": null, "region": null, "intent": null}')
    client.cookies.set("piscinow_session", session_cookie)
    client.post("/api/chat/message", data={"message": "ainda nao sei os detalhes"})

    conversations = db_session.query(Conversation).all()
    assert len(conversations) == 1
    assert len(conversations[0].messages) == 4  # 2 user + 2 agent


def test_referred_visitor_gets_auto_approved_member(client, db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider
    client.cookies.set("piscinow_ref", "RM7X2K9A")

    provider.queue_response('{"profile": "comprador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero uma piscina"})
    client.cookies.set("piscinow_session", first.cookies.get("piscinow_session"))

    provider.queue_response(
        '{"name": "Joao Silva", "contact": "19988887777", "region": "Campinas", "intent": "vinil"}'
    )
    client.post("/api/chat/message", data={"message": "Joao Silva, 19988887777, Campinas, vinil"})

    member = db_session.query(Member).filter(Member.name == "Joao Silva").one()
    assert member.status == MemberStatus.APPROVED


def test_finalized_conversation_schedules_extractor(client, db_session):
    provider = FakeLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: provider

    provider.queue_response('{"profile": "embaixador", "confidence": 0.9}')
    first = client.post("/api/chat/message", data={"message": "quero ser embaixador"})
    client.cookies.set("piscinow_session", first.cookies.get("piscinow_session"))

    provider.queue_response('{"name": "Ana Paula", "contact": "19977776666"}')
    # Consumed by the Extractor's background call after finalization:
    provider.queue_response("Visitantes que querem ser embaixador costumam ja ter indicacoes em mente.")
    client.post("/api/chat/message", data={"message": "Ana Paula, 19977776666"})

    from piscinow.agent.memory_store import MemoryStore
    from piscinow.models.member import ProfileType as PT

    memory = MemoryStore(db_session)
    results = memory.search(query="embaixador com indicacoes em mente", profile_type=PT.EMBAIXADOR, limit=5)
    assert any("indicacoes" in r.content for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_chat.py -v`
Expected: FAIL — `404` on `/api/chat/message` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/web/routes/chat.py`**

```python
import uuid

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Form, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from piscinow.agent.extractor import Extractor
from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.orchestrator import Orchestrator
from piscinow.models.conversation import Conversation
from piscinow.referral import find_referrer
from piscinow.web.deps import get_db, get_llm_provider

router = APIRouter()

SESSION_COOKIE = "piscinow_session"
REFERRAL_COOKIE = "piscinow_ref"


def _get_or_create_conversation(db: Session, session_id: str | None) -> tuple[Conversation, str]:
    if session_id:
        try:
            conversation = db.get(Conversation, uuid.UUID(session_id))
        except ValueError:
            conversation = None
        if conversation is not None:
            return conversation, session_id
    conversation = Conversation()
    db.add(conversation)
    db.flush()
    return conversation, str(conversation.id)


@router.post("/api/chat/message")
async def send_message(
    response: Response,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    piscinow_session: str | None = Cookie(default=None),
    piscinow_ref: str | None = Cookie(default=None),
):
    conversation, session_id = _get_or_create_conversation(db, piscinow_session)
    response.set_cookie(SESSION_COOKIE, session_id, max_age=60 * 60 * 2)

    referrer = find_referrer(db, piscinow_ref) if piscinow_ref else None
    orchestrator = Orchestrator(db, llm)

    # NOTE: delivers the full reply as soon as it's ready, not token-by-token —
    # extraction + classification must finish before the final reply is known.
    # StreamingResponse keeps the wire contract open for true token streaming later.
    async def body():
        result = await orchestrator.handle_user_message(conversation, message, referred_by=referrer)
        if result.finalized:
            # Best-effort learning loop (spec: "roda ao final de cada conversa,
            # background, best-effort") — never blocks the reply.
            background_tasks.add_task(_run_extractor, db, llm, conversation)
        yield result.reply_text

    return StreamingResponse(body(), media_type="text/plain")


async def _run_extractor(db: Session, llm: LLMProvider, conversation: Conversation) -> None:
    # No explicit db.commit() here: `MemoryStore.write` already flushes, and
    # `get_db`'s own post-yield commit (Task 20) runs after background tasks
    # complete, persisting this write in production. Committing here would
    # also break the tests' rollback-based session isolation (Task 2's
    # `db_session` fixture), since in tests `db` is that same fixture session.
    extractor = Extractor(llm, MemoryStore(db))
    await extractor.process(conversation)
```

- [ ] **Step 4: Write `src/piscinow/static/js/chat.js`**

```javascript
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const body = document.getElementById("chat-body");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendMessage("user", message);
    input.value = "";

    const response = await fetch("/api/chat/message", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ message }),
    });
    const text = await response.text();
    appendMessage("agent", text);
  });

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = "msg " + role;
    el.textContent = text;
    body.appendChild(el);
  }
});
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/web/test_chat.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/chat.py src/piscinow/static/js/chat.js tests/web/test_chat.py
git commit -m "feat: chat endpoint wired to the Orchestrator and Extractor"
```

---

### Task 23: Admin login/logout

**Files:**
- Create: `src/piscinow/auth.py`
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_login.html`
- Test: `tests/web/test_admin_auth.py`

**Interfaces:**
- Consumes: `AdminUser` (Task 6), `get_db` (Task 20).
- Produces: `piscinow.auth.ADMIN_SESSION_KEY: str`, `piscinow.auth.login(request, db, email, password) -> bool`, `piscinow.auth.logout(request) -> None`, `piscinow.auth.require_admin(request, db=Depends(get_db)) -> AdminUser` (FastAPI dependency; every protected admin route in Tasks 24-25 depends on this). Routes `GET/POST /admin/login`, `POST /admin/logout`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_auth.py`**

```python
from piscinow.models.admin import AdminUser


def test_login_with_correct_credentials_redirects_to_fila(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/admin/login",
        data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/fila"


def test_login_with_wrong_password_shows_error(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/admin/login", data={"email": "equipe@piscinow.com.br", "password": "errada"}
    )

    assert response.status_code == 401
    assert "invalidos" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_admin_auth.py -v`
Expected: FAIL — `404` on `/admin/login` (route doesn't exist yet)

- [ ] **Step 3: Write `src/piscinow/auth.py`**

```python
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.admin import AdminUser
from piscinow.web.deps import get_db

ADMIN_SESSION_KEY = "admin_user_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    admin = db.scalar(select(AdminUser).where(AdminUser.email == email))
    if admin is None or not admin.verify_password(password):
        return False
    request.session[ADMIN_SESSION_KEY] = str(admin.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(ADMIN_SESSION_KEY, None)


def require_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    admin_id = request.session.get(ADMIN_SESSION_KEY)
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    admin = db.get(AdminUser, admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    return admin
```

- [ ] **Step 4: Write `src/piscinow/web/routes/admin.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.auth import login as do_login
from piscinow.auth import logout as do_logout
from piscinow.web.deps import get_db

router = APIRouter(prefix="/admin")


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if do_login(request, db, email, password):
        return RedirectResponse(url="/admin/fila", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "admin_login.html", {"error": "E-mail ou senha invalidos"}, status_code=401
    )


@router.post("/logout")
async def logout_submit(request: Request):
    do_logout(request)
    return RedirectResponse(url="/admin/login", status_code=303)
```

- [ ] **Step 5: Write `src/piscinow/web/templates/admin_login.html`**

```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Painel Piscinow</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post" action="/admin/login">
    <input type="email" name="email" placeholder="E-mail" required>
    <input type="password" name="password" placeholder="Senha" required>
    <button type="submit">Entrar</button>
  </form>
</main>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/web/test_admin_auth.py -v`
Expected: PASS (2 tests) — `/admin/fila` doesn't exist yet, but Step 1's test only checks the redirect `Location` header, not that the target resolves; Task 24 creates it.

- [ ] **Step 7: Commit**

```bash
git add src/piscinow/auth.py src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_login.html tests/web/test_admin_auth.py
git commit -m "feat: admin login/logout with session auth"
```

---

### Task 24: Admin queue (list, approve, reject)

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_queue.html`
- Test: `tests/web/test_admin_queue.py`

**Interfaces:**
- Consumes: `require_admin` (Task 23), `Member`, `MemberStatus` (Task 3), `get_db` (Task 20).
- Produces: `GET /admin/fila` (lists `WAITLISTED` members), `POST /admin/fila/{member_id}/aprovar`, `POST /admin/fila/{member_id}/recusar`.

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_queue.py`**

```python
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus, ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_fila_redirects_to_login_when_not_authenticated(client):
    response = client.get("/admin/fila", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_fila_lists_waitlisted_members(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    response = client.get("/admin/fila")

    assert "Marina Duarte" in response.text


def test_aprovar_sets_member_status_approved(client, db_session):
    admin = _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    response = client.post(f"/admin/fila/{member.id}/aprovar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(member)
    assert member.status == MemberStatus.APPROVED
    assert member.approved_by == admin.email


def test_recusar_sets_member_status_rejected(client, db_session):
    _logged_in(client, db_session)
    member = Member(profile_type=ProfileType.LOJA, name="Studio Fibra Sul", status=MemberStatus.WAITLISTED)
    db_session.add(member)
    db_session.flush()

    response = client.post(f"/admin/fila/{member.id}/recusar", follow_redirects=False)

    assert response.status_code == 303
    db_session.refresh(member)
    assert member.status == MemberStatus.REJECTED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_admin_queue.py -v`
Expected: FAIL — `404` on `/admin/fila`

- [ ] **Step 3: Append to `src/piscinow/web/routes/admin.py`**

```python
from sqlalchemy import select

from piscinow.auth import require_admin
from piscinow.models.admin import AdminUser
from piscinow.models.member import Member, MemberStatus


@router.get("/fila", response_class=HTMLResponse)
async def fila(request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)):
    templates = request.app.state.templates
    pending = list(db.scalars(select(Member).where(Member.status == MemberStatus.WAITLISTED)))
    return templates.TemplateResponse(request, "admin_queue.html", {"members": pending})


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


@router.post("/fila/{member_id}/recusar")
async def recusar(
    member_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    member = db.get(Member, member_id)
    if member is not None:
        member.reject(approved_by=admin.email)
    return RedirectResponse(url="/admin/fila", status_code=303)
```

(Add these imports/routes below the existing login/logout routes in the same file; the top-of-file imports of `APIRouter, Depends, Form, Request, HTMLResponse, RedirectResponse, Session, get_db` already cover what's reused.)

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_queue.html`**

```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Fila de admissao</h1>
  <table>
    <thead><tr><th>Nome</th><th>Perfil</th><th>Regiao</th><th>Acao</th></tr></thead>
    <tbody>
    {% for member in members %}
      <tr>
        <td>{{ member.name }}</td>
        <td>{{ member.profile_type.value }}</td>
        <td>{{ member.region or member.profile_details.get("region", "-") }}</td>
        <td>
          <form method="post" action="/admin/fila/{{ member.id }}/aprovar" style="display:inline">
            <button type="submit">Aprovar</button>
          </form>
          <form method="post" action="/admin/fila/{{ member.id }}/recusar" style="display:inline">
            <button type="submit">Recusar</button>
          </form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</main>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/web/test_admin_queue.py tests/web/test_admin_auth.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_queue.html tests/web/test_admin_queue.py
git commit -m "feat: admin admission queue with approve/reject"
```

---

### Task 25: Admin corrections (teach the agent)

**Files:**
- Modify: `src/piscinow/web/routes/admin.py`
- Create: `src/piscinow/web/templates/admin_corrections.html`
- Test: `tests/web/test_admin_corrections.py`

**Interfaces:**
- Consumes: `require_admin` (Task 23), `MemoryStore` (Task 12), `MemoryKind`, `MemorySource` (Task 5), `ProfileType` (Task 3), `Conversation` (Task 4).
- Produces: `GET /admin/correcoes` (lists 20 most recent conversations), `POST /admin/correcoes/ensinar` (writes a `source=human` `MemoryItem`).

- [ ] **Step 1: Write the failing tests — `tests/web/test_admin_corrections.py`**

```python
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.admin import AdminUser
from piscinow.models.conversation import Conversation, Message, MessageRole
from piscinow.models.member import ProfileType


def _logged_in(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    return admin


def test_correcoes_lists_recent_conversations(client, db_session):
    _logged_in(client, db_session)
    conversation = Conversation(profile_type_detected=ProfileType.COMPRADOR)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation=conversation, role=MessageRole.USER, content="quero uma piscina"))
    db_session.flush()

    response = client.get("/admin/correcoes")

    assert "quero uma piscina" in response.text


def test_ensinar_creates_human_sourced_memory(client, db_session):
    admin = _logged_in(client, db_session)

    response = client.post(
        "/admin/correcoes/ensinar",
        data={"content": "Sempre confirmar o tamanho em metros quadrados.", "profile_type": "comprador"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    memory = MemoryStore(db_session)
    results = memory.search(query="tamanho em metros quadrados", profile_type=ProfileType.COMPRADOR, limit=5)
    assert len(results) == 1
    assert results[0].created_by == admin.email
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_admin_corrections.py -v`
Expected: FAIL — `404` on `/admin/correcoes`

- [ ] **Step 3: Append to `src/piscinow/web/routes/admin.py`**

```python
from piscinow.agent.memory_store import MemoryStore
from piscinow.models.conversation import Conversation
from piscinow.models.member import ProfileType
from piscinow.models.memory import MemoryKind, MemorySource


@router.get("/correcoes", response_class=HTMLResponse)
async def correcoes(
    request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_admin)
):
    templates = request.app.state.templates
    conversations = list(
        db.scalars(select(Conversation).order_by(Conversation.started_at.desc()).limit(20))
    )
    return templates.TemplateResponse(request, "admin_corrections.html", {"conversations": conversations})


@router.post("/correcoes/ensinar")
async def ensinar(
    content: str = Form(...),
    profile_type: str = Form(...),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_admin),
):
    memory = MemoryStore(db)
    memory.write(
        content=content,
        kind=MemoryKind.CORRECTION,
        source=MemorySource.HUMAN,
        profile_type=ProfileType(profile_type) if profile_type != "geral" else None,
        confidence=0.9,
        created_by=admin.email,
    )
    return RedirectResponse(url="/admin/correcoes", status_code=303)
```

- [ ] **Step 4: Write `src/piscinow/web/templates/admin_corrections.html`**

```html
{% extends "base.html" %}
{% block content %}
<main>
  <h1>Ensinar o concierge</h1>
  <form method="post" action="/admin/correcoes/ensinar">
    <select name="profile_type">
      <option value="geral">Geral</option>
      <option value="comprador">Comprador</option>
      <option value="loja">Loja</option>
      <option value="prestador">Prestador</option>
      <option value="embaixador">Embaixador</option>
    </select>
    <textarea name="content" placeholder="Escreva o aprendizado em uma frase curta"></textarea>
    <button type="submit">Salvar</button>
  </form>

  <h2>Conversas recentes</h2>
  <ul>
  {% for conversation in conversations %}
    <li>
      {{ conversation.profile_type_detected.value if conversation.profile_type_detected else "nao identificado" }}
      — {{ conversation.started_at }}
      <ul>
      {% for message in conversation.messages %}
        <li><strong>{{ message.role.value }}:</strong> {{ message.content }}</li>
      {% endfor %}
      </ul>
    </li>
  {% endfor %}
  </ul>
</main>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/web/test_admin_corrections.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/piscinow/web/routes/admin.py src/piscinow/web/templates/admin_corrections.html tests/web/test_admin_corrections.py
git commit -m "feat: admin corrections screen to teach the agent"
```

---

### Task 26: Rate limiting on the chat endpoint

**Files:**
- Create: `src/piscinow/rate_limit.py`
- Modify: `src/piscinow/web/app.py`
- Modify: `src/piscinow/web/routes/chat.py`
- Test: `tests/web/test_chat_rate_limit.py`

**Interfaces:**
- Consumes: `get_settings` (Task 1).
- Produces: `piscinow.rate_limit.limiter: Limiter`, `piscinow.rate_limit.chat_rate_limit_string() -> str`.

- [ ] **Step 1: Write the failing test — `tests/web/test_chat_rate_limit.py`**

```python
import pytest
from fastapi.testclient import TestClient

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.web.app import create_app
from piscinow.web.deps import get_db, get_llm_provider


@pytest.fixture()
def rate_limited_client(db_session, monkeypatch):
    monkeypatch.setenv("PISCINOW_CHAT_RATE_LIMIT_PER_MINUTE", "2")
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    return TestClient(app)


def test_chat_endpoint_blocks_after_rate_limit_exceeded(rate_limited_client):
    for _ in range(2):
        response = rate_limited_client.post("/api/chat/message", data={"message": "oi"})
        assert response.status_code == 200

    response = rate_limited_client.post("/api/chat/message", data={"message": "oi de novo"})
    assert response.status_code == 429
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_chat_rate_limit.py -v`
Expected: FAIL — all three requests return 200 (no rate limiting yet)

- [ ] **Step 3: Write `src/piscinow/rate_limit.py`**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

from piscinow.config import get_settings

limiter = Limiter(key_func=get_remote_address)


def chat_rate_limit_string() -> str:
    settings = get_settings()
    return f"{settings.chat_rate_limit_per_minute}/minute"
```

- [ ] **Step 4: Modify `src/piscinow/web/app.py`** — register the limiter

```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from piscinow.rate_limit import limiter
```

Add these imports near the top, and inside `create_app()` after `app.state.llm_provider = ...`:

```python
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

- [ ] **Step 5: Modify `src/piscinow/web/routes/chat.py`** — decorate the route

Add `Request` to the existing `from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Form, Response` line (so it reads `from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Form, Request, Response`), add `from piscinow.rate_limit import chat_rate_limit_string, limiter`, add `request: Request` as the route's first parameter (`background_tasks: BackgroundTasks` — already present from Task 22 — stays right after it), and decorate:

```python
@router.post("/api/chat/message")
@limiter.limit(chat_rate_limit_string)
async def send_message(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    piscinow_session: str | None = Cookie(default=None),
    piscinow_ref: str | None = Cookie(default=None),
):
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/web/test_chat_rate_limit.py -v`
Expected: PASS

- [ ] **Step 7: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: PASS (all tests across every task so far)

- [ ] **Step 8: Commit**

```bash
git add src/piscinow/rate_limit.py src/piscinow/web/app.py src/piscinow/web/routes/chat.py tests/web/test_chat_rate_limit.py
git commit -m "feat: rate limit the chat endpoint"
```

---

## Phase D — Deployment

### Task 27: Docker Compose deployment + admin bootstrap script

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `src/piscinow/scripts/__init__.py`
- Create: `src/piscinow/scripts/create_admin.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `README.md`

**Interfaces:**
- Consumes: everything built in Tasks 1-26.
- Produces: a runnable Docker Compose stack (`app` + `db`), an Alembic migration setup for production schema changes, and a CLI to create the first `AdminUser`.

- [ ] **Step 1: Scaffold Alembic**

Run: `pip install -e ".[dev]" && alembic init alembic`
This generates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, and `alembic/versions/`.

- [ ] **Step 2: Edit `alembic/env.py`** — point it at `piscinow`'s models and settings

Replace the `target_metadata = None` line and the `run_migrations_online` URL wiring with:

```python
from piscinow.config import get_settings
from piscinow.db import Base
import piscinow.models.admin  # noqa: F401
import piscinow.models.conversation  # noqa: F401
import piscinow.models.member  # noqa: F401
import piscinow.models.memory  # noqa: F401

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

(Insert the imports near the top of `alembic/env.py`, and replace the existing `target_metadata = None` line with the last line above — the `config.set_main_option(...)` line goes right before it, inside `run_migrations_online()`'s setup or at module level, following whatever `alembic init` generated; both `run_migrations_offline` and `run_migrations_online` read `target_metadata` from this module-level variable.)

- [ ] **Step 3: Generate the initial migration**

Run: `alembic revision --autogenerate -m "initial schema"`
Expected: a new file under `alembic/versions/` creating `members`, `conversations`, `messages`, `memory_items`, `admin_users`, plus the `vector` extension is assumed pre-installed by the `pgvector/pgvector` Docker image (Step 6 confirms this end to end).

- [ ] **Step 4: Write `src/piscinow/scripts/create_admin.py`**

```python
import sys

from piscinow.db import make_engine, make_session_factory
from piscinow.models.admin import AdminUser


def main() -> None:
    if len(sys.argv) != 3:
        print("uso: python -m piscinow.scripts.create_admin <email> <senha>")
        raise SystemExit(1)
    email, password = sys.argv[1], sys.argv[2]
    engine = make_engine()
    session = make_session_factory(engine)()
    session.add(AdminUser.create(email=email, password=password))
    session.commit()
    print(f"admin criado: {email}")


if __name__ == "__main__":
    main()
```

Also create `src/piscinow/scripts/__init__.py` (empty file).

- [ ] **Step 5: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "piscinow.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 6: Write `docker-compose.yml`**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: piscinow
      POSTGRES_PASSWORD: piscinow
      POSTGRES_DB: piscinow
    volumes:
      - piscinow_db_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  app:
    build: .
    depends_on:
      - db
    environment:
      PISCINOW_DATABASE_URL: postgresql+psycopg://piscinow:piscinow@db:5432/piscinow
      PISCINOW_LLM_PROVIDER: ${PISCINOW_LLM_PROVIDER:-fake}
      PISCINOW_ANTHROPIC_API_KEY: ${PISCINOW_ANTHROPIC_API_KEY:-}
      PISCINOW_OPENAI_API_KEY: ${PISCINOW_OPENAI_API_KEY:-}
      PISCINOW_SESSION_SECRET: ${PISCINOW_SESSION_SECRET:?session secret required}
    ports:
      - "8000:8000"

volumes:
  piscinow_db_data:
```

- [ ] **Step 7: Write `README.md`**

```markdown
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
```

- [ ] **Step 8: Verify the stack end to end**

Run:
```bash
export PISCINOW_SESSION_SECRET=dev-secret-only
docker compose build
docker compose up -d
docker compose run --rm app alembic upgrade head
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/
docker compose run --rm app python -m piscinow.scripts.create_admin admin@piscinow.com.br senha-forte-123
docker compose down
```
Expected: the `curl` line prints `200`; `create_admin` prints `admin criado: admin@piscinow.com.br`.

- [ ] **Step 9: Commit**

```bash
git add Dockerfile docker-compose.yml alembic.ini alembic README.md src/piscinow/scripts
git commit -m "feat: Docker Compose deployment, migrations, and admin bootstrap script"
```

---

## Self-Review Notes

- **Spec coverage:** every component in the spec's "Componentes" section maps to a task — Camada Web → Tasks 20-26; Router/Classifier → Task 13; Conversation Handler → Tasks 14-16; LLMProvider → Tasks 7-10; MemoryStore → Task 12; Extractor → Task 19; sistema de indicação → Task 17; painel admin (fila + correções) → Tasks 24-25. The spec's open admission decision is resolved in Global Constraints and implemented in Task 18 (`auto_approve_via_referral`) and verified in Task 18/22's tests.
- **Type consistency check:** `Orchestrator.handle_user_message` (Task 18) is consumed with the exact same signature by `chat.py` (Task 22). `ConversationHandler.missing_fields`/`reply`/`extract_fields` (Task 14) are used identically by all four handlers (Tasks 15-16) and by `Orchestrator` (Task 18). `MemoryStore.search`/`write` signatures (Task 12) match every caller (Tasks 14, 19, 25). `find_referrer`/`get_or_create_referral_code` (Task 17) match their usage in Tasks 18, 21, 22.
- **Placeholder scan:** no TBD/TODO markers; the one intentionally simplified piece (chat streaming delivers the full reply in one chunk rather than token-by-token) is called out explicitly in Task 22 as a scoped simplification, not left vague.

