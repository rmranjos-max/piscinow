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
