import asyncio
import threading
import time

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


class OrderedFakeClient:
    def __init__(self):
        self.batches = []

    def add_episode_batch(self, graph_id, episodes):
        self.batches.append((graph_id, episodes))
        return [episodes[0]["data"]]


def test_graph_builder_uses_independent_boost_client_only_in_build_mode(monkeypatch):
    created = []

    class Endpoint:
        model = "boost-model"
        is_boost = True

    def fake_create_zep_client(**kwargs):
        created.append(("create", kwargs))
        return FakeClient()

    def fake_get_zep_client(backend=None):
        created.append(("get", {"backend": backend}))
        return FakeClient()

    monkeypatch.setattr("app.services.graph_builder.get_preferred_llm_endpoint", lambda prefer_boost=True: Endpoint())
    monkeypatch.setattr("app.services.graph_builder.create_zep_client", fake_create_zep_client)
    monkeypatch.setattr("app.services.graph_builder.get_zep_client", fake_get_zep_client)

    GraphBuilderService(backend="graphiti", build_mode=True)
    GraphBuilderService(backend="graphiti", build_mode=False)

    assert created[0][0] == "create"
    assert created[0][1]["use_singleton"] is False
    assert created[0][1]["llm_endpoint"].model == "boost-model"
    assert created[1] == ("get", {"backend": "graphiti"})


def test_graphiti_async_loop_waits_for_ready_when_thread_is_alive(monkeypatch):
    from app.services import zep_graphiti_impl

    loop = asyncio.new_event_loop()

    class AliveThread:
        def is_alive(self):
            return True

    ready = threading.Event()
    monkeypatch.setattr(zep_graphiti_impl, "_async_loop", None)
    monkeypatch.setattr(zep_graphiti_impl, "_async_thread", AliveThread())
    monkeypatch.setattr(zep_graphiti_impl, "_async_loop_ready", ready)

    def mark_ready():
        time.sleep(0.02)
        zep_graphiti_impl._async_loop = loop
        ready.set()

    starter = threading.Thread(target=mark_ready)
    starter.start()
    try:
        assert zep_graphiti_impl._ensure_async_loop() is loop
    finally:
        starter.join(timeout=1)
        monkeypatch.setattr(zep_graphiti_impl, "_async_loop", None)
        monkeypatch.setattr(zep_graphiti_impl, "_async_thread", None)
        ready.clear()
        loop.close()


def test_graphiti_embedding_throttle_waits_between_requests(monkeypatch):
    from app.services import zep_graphiti_impl

    sleeps = []
    clock = {"value": 100.0}

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["value"] += seconds

    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_EMBEDDING_MIN_INTERVAL_SECONDS", 0.5)
    monkeypatch.setattr("app.services.zep_graphiti_impl.time.monotonic", lambda: clock["value"])
    monkeypatch.setattr("app.services.zep_graphiti_impl.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(zep_graphiti_impl, "_last_embedding_request_at", 0.0)

    async def run_throttle():
        await zep_graphiti_impl._throttle_embedding_request("embedding.create", 1)
        await zep_graphiti_impl._throttle_embedding_request("embedding.create", 1)

    asyncio.run(run_throttle())

    assert sleeps == [0.5]


def test_graphiti_llm_rate_limit_wrapper_throttles_and_retries(monkeypatch):
    from app.services import zep_graphiti_impl
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.errors import RateLimitError

    sleeps = []
    clock = {"value": 100.0}

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["value"] += seconds

    class FakeLLM:
        config = LLMConfig(model="fake-model", temperature=0, max_tokens=128)
        model = "fake-model"
        small_model = None
        temperature = 0
        max_tokens = 128

        def __init__(self):
            self.calls = 0

        def set_tracer(self, tracer):
            self.tracer = tracer

        async def generate_response(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError("Rate limit exceeded. Please try again later.")
            return {"ok": True}

    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_LLM_CONCURRENCY", 1)
    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_LLM_MIN_INTERVAL_SECONDS", 0.5)
    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_RATE_LIMIT_MAX_RETRIES", 2)
    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_RATE_LIMIT_RETRY_SECONDS", 20)
    monkeypatch.setattr("app.services.zep_graphiti_impl.time.monotonic", lambda: clock["value"])
    monkeypatch.setattr("app.services.zep_graphiti_impl.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(zep_graphiti_impl, "_last_llm_request_at", 0.0)

    fake_llm = FakeLLM()
    wrapped = zep_graphiti_impl._create_graphiti_llm_rate_limit_wrapper(fake_llm)

    async def run_calls():
        first = await wrapped.generate_response([])
        second = await wrapped.generate_response([])
        return first, second

    first_result, second_result = asyncio.run(run_calls())

    assert first_result == {"ok": True}
    assert second_result == {"ok": True}
    assert fake_llm.calls == 3
    assert sleeps == [20, 0.5]


def test_graphiti_quota_exhausted_error_does_not_retry(monkeypatch):
    from app.services import zep_graphiti_impl
    from graphiti_core.llm_client.errors import RateLimitError

    calls = {"count": 0}

    async def fake_sleep(seconds):
        raise AssertionError("额度耗尽错误不应进入退避等待")

    async def always_quota_error():
        calls["count"] += 1
        upstream = Exception("Error code: 429 - insufficient_quota: You exceeded your current quota")
        raise RateLimitError("Rate limit exceeded. Please try again later.") from upstream

    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_RATE_LIMIT_MAX_RETRIES", 3)
    monkeypatch.setattr("app.services.zep_graphiti_impl.Config.GRAPHITI_RATE_LIMIT_RETRY_SECONDS", 20)
    monkeypatch.setattr("app.services.zep_graphiti_impl.asyncio.sleep", fake_sleep)

    try:
        asyncio.run(
            zep_graphiti_impl._call_with_graphiti_rate_limit_retry(
                always_quota_error,
                operation="llm.generate_response",
                item_count=1,
            )
        )
    except Exception as exc:
        assert zep_graphiti_impl._is_quota_exhausted_error(exc)
    else:
        raise AssertionError("应抛出额度耗尽异常")

    assert calls["count"] == 1


def test_graph_builder_default_batch_size_uses_config(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = FakeClient()

    chunks = [f"chunk-{index}" for index in range(Config.GRAPH_BUILD_BATCH_SIZE + 1)]
    episode_uuids = builder.add_text_batches("graph_1", chunks)

    assert [len(batch[1]) for batch in builder.client.batches] == [Config.GRAPH_BUILD_BATCH_SIZE, 1]
    assert len(episode_uuids) == len(chunks)


def test_graph_builder_graphiti_uses_configured_concurrency_and_keeps_uuid_order(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)
    captured_workers = []

    class InlineFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class FakeExecutor:
        def __init__(self, max_workers):
            captured_workers.append(max_workers)
            self.futures = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args):
            future = InlineFuture(fn(*args))
            self.futures.append(future)
            return future

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = OrderedFakeClient()
    builder._backend = "graphiti"

    monkeypatch.setattr("app.services.graph_builder.ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(
        "app.services.graph_builder.as_completed",
        lambda futures: reversed(list(futures)),
    )

    episode_uuids = builder.add_text_batches(
        "graph_1",
        ["chunk-0", "chunk-1", "chunk-2", "chunk-3"],
        batch_size=1,
        concurrency=3,
    )

    assert captured_workers == [3]
    assert episode_uuids == ["chunk-0", "chunk-1", "chunk-2", "chunk-3"]


def test_graph_builder_formats_quota_error_message(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    class QuotaClient:
        def add_episode_batch(self, graph_id, episodes):
            upstream = Exception("Error code: 429 - insufficient_quota: You exceeded your current quota")
            raise Exception("Rate limit exceeded. Please try again later.") from upstream

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = QuotaClient()
    builder._backend = "graphiti"

    try:
        builder.add_text_batches("graph_1", ["chunk-0"], batch_size=1)
    except RuntimeError as exc:
        assert "LLM 服务额度不足" in str(exc)
    else:
        raise AssertionError("应抛出批次写入失败异常")


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


def test_graph_build_worker_runs_complete_flow_with_parallel_batches(monkeypatch):
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    class FlowClient:
        def __init__(self):
            self.graph_created = False
            self.ontology_set = False
            self.episodes = []

        def create_graph(self, graph_id, name, description):
            self.graph_created = True

        def set_ontology(self, graph_ids, entities=None, edges=None):
            self.ontology_set = True

        def add_episode_batch(self, graph_id, episodes):
            self.episodes.extend(episodes)
            return [f"episode-{len(self.episodes)}-{index}" for index, _ in enumerate(episodes)]

        def get_all_nodes(self, graph_id):
            from app.services.zep_adapter import GraphNode

            return [
                GraphNode(
                    uuid="node-1",
                    name="张雪",
                    labels=["Entity", "Person"],
                    summary="测试节点",
                    attributes={},
                )
            ]

        def get_all_edges(self, graph_id):
            from app.services.zep_adapter import GraphEdge

            return [
                GraphEdge(
                    uuid="edge-1",
                    name="RELATED_TO",
                    fact="张雪与测试事件相关",
                    source_node_uuid="node-1",
                    target_node_uuid="node-1",
                    attributes={},
                )
            ]

    task_updates = []

    class FakeTaskManager:
        def update_task(self, task_id, **kwargs):
            task_updates.append(("update", kwargs))

        def complete_task(self, task_id, result):
            task_updates.append(("complete", result))

        def fail_task(self, task_id, error):
            task_updates.append(("fail", error))

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder._backend = "graphiti"
    builder.client = FlowClient()
    builder.task_manager = FakeTaskManager()

    builder._build_graph_worker(
        task_id="task-1",
        text="张雪参加赛事讨论。\n\n公众关注事件走向。",
        ontology={"entity_types": [{"name": "Person", "attributes": []}], "edge_types": []},
        graph_name="测试图谱",
        chunk_size=10,
        chunk_overlap=0,
        batch_size=1,
        concurrency=2,
        extraction_context={"event_topic": "张雪机车事件"},
    )

    complete_events = [payload for action, payload in task_updates if action == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["graph_info"]["node_count"] == 1
    assert complete_events[0]["graph_info"]["edge_count"] == 1
    assert builder.client.graph_created is True
    assert builder.client.ontology_set is True
    assert len(builder.client.episodes) >= 2
    assert "图谱实体抽取约束" in builder.client.episodes[0]["data"]


def test_graph_data_coalesces_duplicate_graphiti_entities_by_name_and_type():
    from app.services.zep_adapter import GraphEdge, GraphNode

    class DuplicateEntityClient:
        def get_all_nodes(self, graph_id):
            return [
                GraphNode(
                    uuid="person-a",
                    name="许国利",
                    labels=["Entity", "嫌疑人"],
                    summary="案件相关人员",
                    attributes={"来源": "batch-1"},
                    created_at="2021-01-02",
                ),
                GraphNode(
                    uuid="person-b",
                    name=" 许国利 ",
                    labels=["Entity", "嫌疑人"],
                    summary="杭州市民，案件核心嫌疑人",
                    attributes={"来源": "batch-2", "年龄": "55"},
                    created_at="2021-01-01",
                ),
                GraphNode(
                    uuid="victim-a",
                    name="来惠利",
                    labels=["Entity", "受害人"],
                    summary="案件受害人",
                    attributes={},
                    created_at="2021-01-03",
                ),
            ]

        def get_all_edges(self, graph_id):
            return [
                GraphEdge(
                    uuid="edge-a",
                    name="家庭关系",
                    fact="许国利与来惠利为夫妻关系",
                    source_node_uuid="person-a",
                    target_node_uuid="victim-a",
                    attributes={},
                ),
                GraphEdge(
                    uuid="edge-b",
                    name="家庭关系",
                    fact="许国利与来惠利为夫妻关系",
                    source_node_uuid="person-b",
                    target_node_uuid="victim-a",
                    attributes={},
                ),
                GraphEdge(
                    uuid="edge-c",
                    name="起诉",
                    fact="检方起诉许国利",
                    source_node_uuid="victim-a",
                    target_node_uuid="person-b",
                    attributes={},
                ),
            ]

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = DuplicateEntityClient()

    graph_data = builder.get_graph_data("graph-1")

    assert graph_data["node_count"] == 2
    assert graph_data["edge_count"] == 2

    merged_person = next(node for node in graph_data["nodes"] if node["name"] == "许国利")
    assert merged_person["summary"] == "杭州市民，案件核心嫌疑人"
    assert merged_person["created_at"] == "2021-01-01"
    assert merged_person["attributes"]["年龄"] == "55"
    assert merged_person["attributes"]["merged_duplicate_uuids"] == ["person-a", "person-b"]

    person_edges = [
        edge for edge in graph_data["edges"]
        if edge["source_node_uuid"] == merged_person["uuid"] or edge["target_node_uuid"] == merged_person["uuid"]
    ]
    assert len(person_edges) == 2
    assert {edge["source_node_name"] for edge in person_edges} | {edge["target_node_name"] for edge in person_edges} == {"许国利", "来惠利"}


def test_graph_data_filters_location_entities_and_edges():
    from app.services.zep_adapter import GraphEdge, GraphNode

    class LocationEntityClient:
        def get_all_nodes(self, graph_id):
            return [
                GraphNode("person-1", "张雪", ["Entity", "Person"], "", {}),
                GraphNode("org-1", "杭州市公安局", ["Entity", "GovernmentAgency"], "", {}),
                GraphNode("city-1", "杭州市", ["Entity", "City"], "", {}),
                GraphNode("place-1", "某小区", ["Entity", "Place"], "", {}),
            ]

        def get_all_edges(self, graph_id):
            return [
                GraphEdge("edge-1", "回应", "张雪回应争议", "person-1", "org-1", {}),
                GraphEdge("edge-2", "位于", "事件发生于杭州市", "person-1", "city-1", {}),
                GraphEdge("edge-3", "位于", "某小区位于杭州市", "place-1", "city-1", {}),
            ]

    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = LocationEntityClient()

    graph_data = builder.get_graph_data("graph-1")

    assert graph_data["node_count"] == 2
    assert graph_data["edge_count"] == 1
    assert {node["name"] for node in graph_data["nodes"]} == {"张雪", "杭州市公安局"}
    assert graph_data["edges"][0]["uuid"] == "edge-1"


def test_entity_reader_uses_coalesced_graph_entities():
    from app.services.zep_adapter import GraphEdge, GraphNode
    from app.services.zep_entity_reader import ZepEntityReader

    class DuplicateEntityClient:
        def get_all_nodes(self, graph_id):
            return [
                GraphNode("person-a", "许国利", ["Entity", "嫌疑人"], "", {}),
                GraphNode("person-b", "许国利", ["Entity", "嫌疑人"], "", {}),
                GraphNode("victim-a", "来惠利", ["Entity", "受害人"], "", {}),
            ]

        def get_all_edges(self, graph_id):
            return [
                GraphEdge("edge-a", "家庭关系", "许国利与来惠利为夫妻关系", "person-a", "victim-a", {}),
                GraphEdge("edge-b", "家庭关系", "许国利与来惠利为夫妻关系", "person-b", "victim-a", {}),
            ]

    reader = ZepEntityReader.__new__(ZepEntityReader)
    reader.client = DuplicateEntityClient()

    result = reader.filter_defined_entities("graph-1")

    assert result.total_count == 2
    assert result.filtered_count == 2
    assert [entity.name for entity in result.entities] == ["许国利", "来惠利"]
    assert len(result.entities[0].related_edges) == 1


def test_entity_reader_filters_location_entities_from_agent_candidates():
    from app.services.zep_adapter import GraphEdge, GraphNode
    from app.services.zep_entity_reader import ZepEntityReader

    class LocationEntityClient:
        def get_all_nodes(self, graph_id):
            return [
                GraphNode("person-1", "张雪", ["Entity", "Person"], "", {}),
                GraphNode("city-1", "杭州市", ["Entity", "City"], "", {}),
                GraphNode("location-1", "比赛场地", ["Entity", "Location"], "", {}),
            ]

        def get_all_edges(self, graph_id):
            return [
                GraphEdge("edge-1", "提及", "张雪提及杭州市", "person-1", "city-1", {}),
                GraphEdge("edge-2", "讨论", "张雪讨论赛事", "person-1", "person-1", {}),
            ]

    reader = ZepEntityReader.__new__(ZepEntityReader)
    reader.client = LocationEntityClient()

    result = reader.filter_defined_entities("graph-1")

    assert result.total_count == 1
    assert result.filtered_count == 1
    assert [entity.name for entity in result.entities] == ["张雪"]
    assert result.entities[0].related_edges == [
        {
            "direction": "outgoing",
            "edge_name": "讨论",
            "fact": "张雪讨论赛事",
            "target_node_uuid": "person-1",
        }
    ]


def test_zep_tools_statistics_use_coalesced_graph_entities():
    from app.services.zep_adapter import GraphEdge, GraphNode
    from app.services.zep_tools import ZepToolsService

    class DuplicateEntityClient:
        def get_all_nodes(self, graph_id):
            return [
                GraphNode("person-a", "许国利", ["Entity", "嫌疑人"], "", {}),
                GraphNode("person-b", "许国利", ["Entity", "嫌疑人"], "", {}),
                GraphNode("victim-a", "来惠利", ["Entity", "受害人"], "", {}),
            ]

        def get_all_edges(self, graph_id):
            return [
                GraphEdge("edge-a", "家庭关系", "许国利与来惠利为夫妻关系", "person-a", "victim-a", {}),
                GraphEdge("edge-b", "家庭关系", "许国利与来惠利为夫妻关系", "person-b", "victim-a", {}),
            ]

    tools = ZepToolsService.__new__(ZepToolsService)
    tools.client = DuplicateEntityClient()

    stats = tools.get_graph_statistics("graph-1")

    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1
    assert stats["entity_types"] == {"嫌疑人": 1, "受害人": 1}


def test_zep_tools_statistics_filter_location_entities():
    from app.services.zep_adapter import GraphEdge, GraphNode
    from app.services.zep_tools import ZepToolsService

    class LocationEntityClient:
        def get_all_nodes(self, graph_id):
            return [
                GraphNode("person-1", "张雪", ["Entity", "Person"], "", {}),
                GraphNode("city-1", "杭州市", ["Entity", "City"], "", {}),
            ]

        def get_all_edges(self, graph_id):
            return [
                GraphEdge("edge-1", "位于", "事件发生于杭州市", "person-1", "city-1", {}),
            ]

    tools = ZepToolsService.__new__(ZepToolsService)
    tools.client = LocationEntityClient()

    stats = tools.get_graph_statistics("graph-1")

    assert stats["total_nodes"] == 1
    assert stats["total_edges"] == 0
    assert stats["entity_types"] == {"Person": 1}
    assert stats["relation_types"] == {}


def test_ontology_processing_strips_location_entity_types_and_source_targets():
    from app.services.ontology_generator import OntologyGenerator

    generator = OntologyGenerator.__new__(OntologyGenerator)
    ontology = generator._validate_and_process({
        "entity_types": [
            {"name": "Person", "description": "person", "attributes": []},
            {"name": "City", "description": "city", "attributes": []},
            {"name": "Place", "description": "place", "attributes": []},
            {"name": "GovernmentAgency", "description": "agency", "attributes": []},
        ],
        "edge_types": [
            {
                "name": "LOCATED_IN",
                "description": "location relation",
                "source_targets": [{"source": "Person", "target": "City"}],
            },
            {
                "name": "REGULATES",
                "description": "agency relation",
                "source_targets": [{"source": "GovernmentAgency", "target": "Person"}],
            },
        ],
        "analysis_summary": "测试",
    })

    entity_names = [entity["name"] for entity in ontology["entity_types"]]
    edge_names = [edge["name"] for edge in ontology["edge_types"]]

    assert "City" not in entity_names
    assert "Place" not in entity_names
    assert "Person" in entity_names
    assert "Organization" in entity_names
    assert "GovernmentAgency" in entity_names
    assert edge_names == ["REGULATES"]


def test_location_filter_keeps_speaking_actor_types_with_location_words():
    from app.services.location_entity_filter import is_location_entity_type, is_location_entity_node
    from app.services.zep_adapter import GraphNode

    assert is_location_entity_type("CityResident") is False
    assert is_location_entity_node(GraphNode("group-1", "杭州市民", ["Entity", "CityResident"], "", {})) is False
    assert is_location_entity_node(GraphNode("agency-1", "杭州市公安局", ["Entity", "GovernmentAgency"], "", {})) is False
    assert is_location_entity_node(GraphNode("city-1", "杭州市", ["Entity", "City"], "", {})) is True


def test_graph_build_api_passes_project_event_context_to_episodes(monkeypatch, tmp_path):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.api.graph.Config.ZEP_BACKEND", "graphiti")
    monkeypatch.setattr("app.services.graph_builder.time.sleep", lambda seconds: None)

    captured = {}

    class FakeBuilder:
        def __init__(self, api_key=None, backend=None, build_mode=False):
            self.backend = backend
            self.build_mode = build_mode

        def create_graph(self, name):
            return "mirofish_test_graph"

        def set_ontology(self, graph_id, ontology):
            captured["ontology"] = ontology

        def add_text_batches(self, graph_id, chunks, batch_size, progress_callback=None, extraction_context=None, concurrency=1):
            captured["graph_id"] = graph_id
            captured["chunks"] = chunks
            captured["batch_size"] = batch_size
            captured["concurrency"] = concurrency
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
        json={"project_id": project.project_id, "batch_size": 1, "chunk_size": 200, "concurrency": 2},
    )

    assert response.status_code == 200
    assert captured["extraction_context"]["event_topic"] == "张雪机车事件"
    assert captured["extraction_context"]["simulation_requirement"] == "推演赛事争议后续舆情走向"
    assert captured["concurrency"] == 2
    assert "法国车手瓦伦丁·德比斯" in captured["extraction_context"]["entity_hints"]
    assert "网易游戏、阴阳师等无关实体即使出现在材料杂讯中也不要入图" in captured["wrapped_episode"]
    assert "张雪驾驶820RR-RS参加相关赛事讨论" in captured["wrapped_episode"]


def test_graph_build_api_does_not_persist_graph_id_until_success(monkeypatch, tmp_path):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.api.graph.Config.ZEP_BACKEND", "graphiti")

    class FailingBuilder:
        def __init__(self, api_key=None, backend=None, build_mode=False):
            pass

        def create_graph(self, name):
            return "mirofish_partial_graph"

        def set_ontology(self, graph_id, ontology):
            pass

        def add_text_batches(self, *args, **kwargs):
            raise RuntimeError("批次 1 图谱写入失败: Rate limit exceeded. Please try again later.")

    class InlineThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    project = ProjectManager.create_project(name="限流测试")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.ontology = {
        "entity_types": [{"name": "Person", "description": "person", "attributes": []}],
        "edge_types": [],
    }
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(project.project_id, "用于测试图谱构建失败的文本。")

    monkeypatch.setattr("app.api.graph.GraphBuilderService", FailingBuilder)
    monkeypatch.setattr("app.api.graph.threading.Thread", InlineThread)

    app = create_app()
    response = app.test_client().post(
        "/api/graph/build",
        json={"project_id": project.project_id, "batch_size": 1, "chunk_size": 200},
    )

    assert response.status_code == 200
    saved_project = ProjectManager.get_project(project.project_id)
    assert saved_project.status == ProjectStatus.FAILED
    assert saved_project.graph_id is None
    assert "Rate limit exceeded" in saved_project.error
