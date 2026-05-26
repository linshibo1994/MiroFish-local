from app import create_app
from app.api import graph as graph_api
from app.api import report as report_api
from app.api import simulation as simulation_api
from app.services.graph_builder import GraphBuilderService


def test_graph_data_requires_project_metadata(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project_by_graph_id",
        lambda graph_id: None,
    )

    response = client.get("/api/graph/data/orphan_graph")

    assert response.status_code == 404
    data = response.get_json()
    assert data["success"] is False
    assert "图谱未绑定到任何项目元数据" in data["error"]


def test_report_search_tool_requires_project_metadata(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        report_api.ProjectManager,
        "get_project_by_graph_id",
        lambda graph_id: None,
    )

    response = client.post(
        "/api/report/tools/search",
        json={"graph_id": "orphan_graph", "query": "test"},
    )

    assert response.status_code == 404
    data = response.get_json()
    assert data["success"] is False
    assert "图谱未绑定到任何项目元数据" in data["error"]


def test_simulation_entities_requires_project_metadata(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        simulation_api.ProjectManager,
        "get_project_by_graph_id",
        lambda graph_id: None,
    )

    response = client.get("/api/simulation/entities/orphan_graph")

    assert response.status_code == 404
    data = response.get_json()
    assert data["success"] is False
    assert "图谱未绑定到任何项目元数据" in data["error"]


def test_generate_profiles_requires_project_metadata(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        simulation_api.ProjectManager,
        "get_project_by_graph_id",
        lambda graph_id: None,
    )

    response = client.post(
        "/api/simulation/generate-profiles",
        json={"graph_id": "orphan_graph", "platform": "reddit"},
    )

    assert response.status_code == 404
    data = response.get_json()
    assert data["success"] is False
    assert "图谱未绑定到任何项目元数据" in data["error"]


def test_graph_data_sanitizes_internal_embedding_attributes():
    attributes = GraphBuilderService._sanitize_display_attributes(
        {
            "name_embedding": [0.1, 0.2],
            "Name_Embedding": [0.3],
            "summary": "可展示摘要",
            "custom_label": "可展示标签",
        }
    )

    assert "name_embedding" not in attributes
    assert "Name_Embedding" not in attributes
    assert attributes == {
        "summary": "可展示摘要",
        "custom_label": "可展示标签",
    }
