from sqlalchemy import text


def test_vector_extension_available(db_session):
    result = db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname='vector'")
    ).scalar()
    assert result == "vector"
