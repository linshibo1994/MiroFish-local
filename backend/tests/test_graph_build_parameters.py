from app.config import Config
from app import create_app
from app.models.project import ProjectManager, ProjectStatus
from app.services.graph_builder import GraphBuilderService


class FakeClient:
    def __init__(self):
        self.batches = []

    def add_episode_batch(self, graph_id, episodes):
        self.batches.append((graph_id, episodes))
        return [f"episode_{len(self.batches)}_{index}" for index, _ in enumerate(episodes)]


def test_graph_builder_default_batch_size_uses_config(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = FakeClient()

    chunks = [f"chunk-{index}" for index in range(Config.GRAPH_BUILD_BATCH_SIZE + 1)]
    episode_uuids = builder.add_text_batches("graph_1", chunks)

    assert [len(batch[1]) for batch in builder.client.batches] == [Config.GRAPH_BUILD_BATCH_SIZE, 1]
    assert len(episode_uuids) == len(chunks)


def test_graph_builder_keeps_raw_chunk_without_extraction_context(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = FakeClient()

    builder.add_text_batches("graph_1", ["原始文本块"], batch_size=1)

    assert builder.client.batches[0][1][0]["data"] == "原始文本块"


def test_graph_builder_wraps_chunks_with_event_relevance_constraints(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = FakeClient()

    builder.add_text_batches(
        "graph_1",
        ["张雪驾驶820RR-RS参加相关赛事讨论。网易游戏广告出现在页面侧栏。"],
        batch_size=1,
        extraction_context={
            "event_topic": "张雪机车事件",
            "simulation_requirement": "推演赛事争议后续舆情走向",
            "seed_summary": "材料围绕张雪、张雪机车、法国车手瓦伦丁·德比斯、WSBK展开。",
            "entity_hints": ["张雪", "张雪机车", "法国车手瓦伦丁·德比斯", "WSBK", "820RR-RS"],
        },
    )

    wrapped = builder.client.batches[0][1][0]["data"]
    assert "图谱实体抽取约束" in wrapped
    assert "事件主题：张雪机车事件" in wrapped
    assert "推演方向：推演赛事争议后续舆情走向" in wrapped
    assert "张雪、张雪机车、法国车手瓦伦丁·德比斯、WSBK、820RR-RS" in wrapped
    assert "网易游戏、阴阳师等无关实体即使出现在材料杂讯中也不要入图" in wrapped
    assert "# 文档文本块（唯一事实来源）" in wrapped
    assert "网易游戏广告出现在页面侧栏" in wrapped


def test_graph_build_api_passes_project_event_context_to_episodes(monkeypatch, tmp_path):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.api.graph.Config.ZEP_BACKEND", "graphiti")
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    captured = {}

    class FakeBuilder:
        def __init__(self, api_key=None, backend=None):
            self.backend = backend

        def create_graph(self, name):
            return "mirofish_test_graph"

        def set_ontology(self, graph_id, ontology):
            captured["ontology"] = ontology

        def add_text_batches(self, graph_id, chunks, batch_size, progress_callback=None, extraction_context=None):
            captured["graph_id"] = graph_id
            captured["chunks"] = chunks
            captured["batch_size"] = batch_size
            captured["extraction_context"] = extraction_context
            wrapped = GraphBuilderService._wrap_chunk_with_event_constraints(
                chunks[0],
                extraction_context,
            )
            captured["wrapped_episode"] = wrapped
            return ["episode_1"]

        def _wait_for_episodes(self, episode_uuids, progress_callback=None):
            captured["episode_uuids"] = episode_uuids

        def get_graph_data(self, graph_id):
            return {"node_count": 1, "edge_count": 1}

    class InlineThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    project = ProjectManager.create_project(name="张雪机车事件")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.search_query = "张雪机车事件"
    project.simulation_requirement = "推演赛事争议后续舆情走向"
    project.seed_summary_md = "材料围绕张雪、张雪机车、法国车手瓦伦丁·德比斯、WSBK展开。"
    project.entity_hints = ["张雪", "张雪机车", "法国车手瓦伦丁·德比斯", "WSBK", "820RR-RS"]
    project.ontology = {
        "entity_types": [{"name": "Person", "description": "person", "attributes": []}],
        "edge_types": [],
    }
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(
        project.project_id,
        "张雪驾驶820RR-RS参加相关赛事讨论。网易游戏广告出现在页面侧栏。",
    )

    monkeypatch.setattr("app.api.graph.GraphBuilderService", FakeBuilder)
    monkeypatch.setattr("app.api.graph.threading.Thread", InlineThread)

    app = create_app()
    response = app.test_client().post(
        "/api/graph/build",
        json={"project_id": project.project_id, "batch_size": 1, "chunk_size": 200},
    )

    assert response.status_code == 200
    assert captured["extraction_context"]["event_topic"] == "张雪机车事件"
    assert captured["extraction_context"]["simulation_requirement"] == "推演赛事争议后续舆情走向"
    assert "法国车手瓦伦丁·德比斯" in captured["extraction_context"]["entity_hints"]
    assert "网易游戏、阴阳师等无关实体即使出现在材料杂讯中也不要入图" in captured["wrapped_episode"]
    assert "张雪驾驶820RR-RS参加相关赛事讨论" in captured["wrapped_episode"]
