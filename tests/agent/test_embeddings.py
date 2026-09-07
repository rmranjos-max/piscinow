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
