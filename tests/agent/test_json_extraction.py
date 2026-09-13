from piscinow.agent.json_extraction import parse_json_object


def test_parses_clean_json_object():
    assert parse_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extracts_json_surrounded_by_extra_text():
    raw = 'aqui esta: {"name": "Marina"} obrigado'
    assert parse_json_object(raw) == {"name": "Marina"}


def test_returns_empty_dict_for_non_json_text():
    assert parse_json_object("desculpe nao entendi") == {}


def test_returns_empty_dict_for_malformed_json():
    assert parse_json_object('{"a": }') == {}
