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
