from app import create_app
from app.api import simulation as simulation_api
from app.models.project import Project, ProjectStatus


def test_entities_uses_graph_backend_instead_of_global_cloud(monkeypatch):
    app = create_app()
    client = app.test_client()

    project = Project(
        project_id="proj_graphiti",
        name="graphiti project",
        status=ProjectStatus.GRAPH_COMPLETED,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        graph_id="graph_123",
        graph_backend="graphiti",
    )

    captured = {}

    monkeypatch.setattr(simulation_api.Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(simulation_api.Config, "ZEP_API_KEY", None)
    monkeypatch.setattr(
        simulation_api.ProjectManager,
        "get_project_by_graph_id",
        lambda graph_id: project if graph_id == "graph_123" else None,
    )

    class FakeReader:
        def __init__(self, backend=None):
            captured["backend"] = backend

        def filter_defined_entities(self, graph_id, defined_entity_types=None, enrich_with_edges=True):
            captured["graph_id"] = graph_id
            captured["entity_types"] = defined_entity_types
            captured["enrich"] = enrich_with_edges
            return type(
                "Result",
                (),
                {
                    "to_dict": lambda self: {
                        "entities": [],
                        "entity_types": [],
                        "total_count": 0,
                        "filtered_count": 0,
                    }
                },
            )()

    monkeypatch.setattr(simulation_api, "ZepEntityReader", FakeReader)

    response = client.get("/api/simulation/entities/graph_123")

    assert response.status_code == 200
    assert captured["backend"] == "graphiti"
    assert captured["graph_id"] == "graph_123"

