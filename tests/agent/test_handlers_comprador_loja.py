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
