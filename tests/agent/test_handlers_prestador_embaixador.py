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
