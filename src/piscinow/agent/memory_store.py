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
