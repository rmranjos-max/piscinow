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
