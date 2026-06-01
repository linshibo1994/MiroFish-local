import json

from app import create_app
from app.api import simulation as simulation_api


class FakeAgentDialogueService:
    def stream_chat(self, **kwargs):
        yield {
            "event": "meta",
            "agent": {
                "user_id": kwargs["user_id"],
                "name": "张雪",
                "stable_agent_key": kwargs["agent_key"],
            },
        }
        yield {"event": "delta", "content": "你好"}
        yield {"event": "done"}

    def chat(self, **kwargs):
        return {
            "response": "你好",
            "agent": {
                "user_id": kwargs["user_id"],
                "name": "张雪",
                "stable_agent_key": kwargs["agent_key"],
            },
        }


def test_agent_chat_stream_returns_ndjson(monkeypatch):
    monkeypatch.setattr(simulation_api, "AgentDialogueService", lambda: FakeAgentDialogueService())
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/simulation/sim_1/agent-chat/stream",
        json={
            "agent_key": "entity_uuid:entity-zhangxue",
            "user_id": 0,
            "platform": "reddit",
            "message": "你好",
        },
    )

    assert response.status_code == 200
    assert response.content_type == "application/x-ndjson; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Accel-Buffering"] == "no"
    lines = [json.loads(line) for line in response.data.decode("utf-8").strip().splitlines()]
    assert [line["event"] for line in lines] == ["meta", "delta", "done"]
    assert lines[0]["agent"]["name"] == "张雪"
    assert lines[1]["content"] == "你好"


def test_agent_chat_non_stream_returns_json(monkeypatch):
    monkeypatch.setattr(simulation_api, "AgentDialogueService", lambda: FakeAgentDialogueService())
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/simulation/sim_1/agent-chat",
        json={
            "agent_key": "entity_uuid:entity-zhangxue",
            "user_id": 0,
            "platform": "reddit",
            "message": "你好",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["agent"]["name"] == "张雪"
    assert data["data"]["response"] == "你好"
