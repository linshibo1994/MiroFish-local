from app.services.zep_graphiti_impl import _ensure_graphiti_json_instruction
from app.utils.neo4j_errors import format_neo4j_auth_error, is_neo4j_auth_error


class DummyMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


class DummyNeo4jAuthError(Exception):
    neo4j_code = "Neo.ClientError.Security.AuthenticationRateLimit"


def test_graphiti_json_instruction_is_appended_when_missing():
    messages = [
        DummyMessage("system", "你是结构化抽取助手。"),
        DummyMessage("user", "抽取实体和关系。"),
    ]

    _ensure_graphiti_json_instruction((messages,), {})

    assert "JSON" in messages[0].content
    assert "Markdown" in messages[0].content
    assert messages[1].content == "抽取实体和关系。"


def test_graphiti_json_instruction_keeps_existing_json_prompt():
    messages = [
        DummyMessage("system", "Return a valid json object."),
        DummyMessage("user", "抽取实体和关系。"),
    ]

    _ensure_graphiti_json_instruction((messages,), {})

    assert messages[0].content == "Return a valid json object."


def test_neo4j_auth_rate_limit_is_classified_as_auth_error():
    error = DummyNeo4jAuthError("The client has provided incorrect authentication details too many times in a row.")

    assert is_neo4j_auth_error(error)
    assert "NEO4J_PASSWORD" in format_neo4j_auth_error(error)
