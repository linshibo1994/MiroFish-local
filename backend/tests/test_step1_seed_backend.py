import io
from datetime import datetime

from app import create_app
from app.models.project import Project, ProjectManager, ProjectStatus
from app.services.bailian_web_search_service import BailianWebSearchService
from app.services.bocha_search_service import BochaSearchService, SearchSource
from app.services.web_search_provider import WebSearchProviderFactory


def test_project_seed_fields_roundtrip():
    project = Project(
        project_id="proj_seed",
        name="seed",
        status=ProjectStatus.CREATED,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        seed_input_mode="web_search",
        search_query="测试检索",
        seed_summary_md="## 摘要",
        seed_sources=[{"title": "来源", "url": "https://example.com"}],
        simulation_suggestions=["模拟建议"],
        entity_hints=["测试公司"],
        seed_metadata={"analysis_mode": "fallback"},
    )

    restored = Project.from_dict(project.to_dict())

    assert restored.seed_input_mode == "web_search"
    assert restored.search_query == "测试检索"
    assert restored.seed_summary_md == "## 摘要"
    assert restored.seed_sources == [{"title": "来源", "url": "https://example.com"}]
    assert restored.simulation_suggestions == ["模拟建议"]
    assert restored.entity_hints == ["测试公司"]
    assert restored.seed_metadata == {"analysis_mode": "fallback"}


def test_project_manager_seed_summary_and_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path))
    project = ProjectManager.create_project(name="seed files")

    ProjectManager.save_seed_summary(project.project_id, "## Seed")
    ProjectManager.save_seed_sources(
        project.project_id,
        [{"title": "A", "url": "https://example.com/a"}],
    )

    assert ProjectManager.get_seed_summary(project.project_id) == "## Seed"
    assert ProjectManager.get_seed_sources(project.project_id) == [
        {"title": "A", "url": "https://example.com/a"}
    ]


def test_web_search_seed_rejects_multipart_input():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/graph/seed/web-search",
        data={"query": "测试", "files": (io.BytesIO(b"hello"), "test.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "仅接受 JSON 请求" in data["error"]


def test_json_ontology_generation_rejects_seed_inputs():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/graph/ontology/generate",
        json={
            "project_id": "proj_test",
            "simulation_requirement": "模拟信息扩散",
            "search_query": "不应同时提交",
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "文件和搜索输入请先完成 seed 阶段" in data["error"]


def test_web_search_provider_defaults_to_bailian(monkeypatch):
    monkeypatch.setattr("app.services.web_search_provider.Config.USE_BOCHA_WEB_SEARCH", False)
    monkeypatch.setattr("app.services.web_search_provider.Config.WEB_SEARCH_PROVIDER", "bailian")

    assert WebSearchProviderFactory.get_provider_name() == "bailian"
    assert isinstance(WebSearchProviderFactory.create(), BailianWebSearchService)


def test_web_search_provider_uses_bocha_when_switch_enabled(monkeypatch):
    monkeypatch.setattr("app.services.web_search_provider.Config.USE_BOCHA_WEB_SEARCH", True)
    monkeypatch.setattr("app.services.web_search_provider.Config.WEB_SEARCH_PROVIDER", "bailian")

    assert WebSearchProviderFactory.get_provider_name() == "bocha"
    assert isinstance(WebSearchProviderFactory.create(), BochaSearchService)


def test_web_search_seed_uses_configured_provider(monkeypatch, tmp_path):
    app = create_app()
    client = app.test_client()
    captured = {}

    class FakeSearchService:
        def search(self, query, count=None, freshness=None, summary=True):
            captured.update({
                "query": query,
                "count": count,
                "freshness": freshness,
                "summary": summary,
            })
            return [SearchSource(title="来源", url="https://example.com/news", snippet="片段")]

    class FakeSeedAnalysisService:
        _build_search_material = staticmethod(
            lambda sources, query: f"检索词：{query}\n来源数：{len(sources)}"
        )

        def analyze_from_sources(self, sources, query, additional_context=None):
            from app.services.seed_analysis_service import SeedAnalysisResult

            return SeedAnalysisResult(
                seed_summary_md="## Seed",
                simulation_suggestions=["建议"],
                entity_hints=["来源"],
                seed_metadata={},
            )

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr("app.api.graph.WebSearchProviderFactory.get_provider_name", lambda provider=None: "bailian")
    monkeypatch.setattr("app.api.graph.WebSearchProviderFactory.create", lambda provider=None: FakeSearchService())
    monkeypatch.setattr("app.api.graph.SeedAnalysisService", FakeSeedAnalysisService)

    response = client.post(
        "/api/graph/seed/web-search",
        json={"search_query": "测试关键词", "count": 2, "summary": False},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert captured == {
        "query": "测试关键词",
        "count": 2,
        "freshness": None,
        "summary": False,
    }
    assert data["seed_metadata"]["web_search_provider"] == "bailian"


def test_bailian_web_search_parses_sources():
    raw_text = """
    {
      "sources": [
        {
          "title": "新闻标题",
          "url": "https://example.com/news",
          "snippet": "新闻片段",
          "summary": "搜索摘要",
          "site_name": "Example",
          "date_published": "2026-05-01"
        },
        {
          "title": "非法链接",
          "url": "javascript:void(0)"
        },
        {
          "title": "重复链接",
          "url": "https://example.com/news"
        }
      ]
    }
    """

    sources = BailianWebSearchService.parse_sources(raw_text)

    assert len(sources) == 1
    assert sources[0].title == "新闻标题"
    assert sources[0].url == "https://example.com/news"
    assert sources[0].snippet == "新闻片段"
    assert sources[0].summary == "搜索摘要"
    assert sources[0].site_name == "Example"
    assert sources[0].date_published == "2026-05-01"


def test_bailian_freshness_maps_bocha_style_values_to_days():
    assert BailianWebSearchService._freshness_to_days("twoMonths") == 60
    assert BailianWebSearchService._freshness_to_days("14") == 14
    assert BailianWebSearchService._freshness_to_days("") is None


def test_bocha_search_service_parses_web_pages(monkeypatch):
    response_payload = {
        "code": 200,
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "新闻标题",
                        "url": "https://example.com/news",
                        "snippet": "新闻片段",
                        "summary": "搜索摘要",
                        "siteName": "Example",
                        "datePublished": "2026-05-01",
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(
        BochaSearchService,
        "_post_json",
        lambda self, payload: response_payload,
    )

    sources = BochaSearchService(api_key="test-key", validate_links=False).search("测试", count=1)

    assert len(sources) == 1
    assert sources[0].title == "新闻标题"
    assert sources[0].url == "https://example.com/news"
    assert sources[0].snippet == "新闻片段"
    assert sources[0].summary == "搜索摘要"
    assert sources[0].site_name == "Example"
    assert sources[0].date_published == "2026-05-01"


def test_bocha_search_uses_two_months_freshness_by_default(monkeypatch):
    captured_payload = {}
    response_payload = {
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "新闻标题",
                        "url": "https://example.com/news",
                    }
                ]
            }
        }
    }

    def fake_post_json(self, payload):
        captured_payload.update(payload)
        return response_payload

    monkeypatch.setattr(BochaSearchService, "_post_json", fake_post_json)

    BochaSearchService(api_key="test-key", validate_links=False).search("测试", count=1)

    assert captured_payload["freshness"] == "twoMonths"
    assert captured_payload["count"] == 3


def test_bocha_search_accepts_explicit_freshness(monkeypatch):
    captured_payload = {}
    response_payload = {
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "新闻标题",
                        "url": "https://example.com/news",
                    }
                ]
            }
        }
    }

    def fake_post_json(self, payload):
        captured_payload.update(payload)
        return response_payload

    monkeypatch.setattr(BochaSearchService, "_post_json", fake_post_json)

    BochaSearchService(api_key="test-key", validate_links=False).search(
        "测试",
        count=1,
        freshness="oneMonth",
    )

    assert captured_payload["freshness"] == "oneMonth"
    assert captured_payload["count"] == 1


def test_bocha_search_filters_old_sources_by_default(monkeypatch):
    response_payload = {
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "近期新闻",
                        "url": "https://example.com/recent",
                        "datePublished": "2026-05-01T00:00:00+08:00",
                    },
                    {
                        "name": "过期新闻",
                        "url": "https://example.com/old",
                        "datePublished": "2026-01-01T00:00:00+08:00",
                    },
                    {
                        "name": "无日期新闻",
                        "url": "https://example.com/no-date",
                    },
                ]
            }
        }
    }

    monkeypatch.setattr(BochaSearchService, "_post_json", lambda self, payload: response_payload)
    class FixedDatetime:
        now = staticmethod(lambda tz=None: datetime(2026, 5, 26, tzinfo=tz))
        fromisoformat = staticmethod(datetime.fromisoformat)
        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr("app.services.bocha_search_service.datetime", FixedDatetime)

    sources = BochaSearchService(api_key="test-key", validate_links=False).search("测试", count=5)

    assert [source.url for source in sources] == [
        "https://example.com/recent",
        "https://example.com/no-date",
    ]


def test_bocha_search_filters_empty_invalid_and_deleted_sources(monkeypatch):
    response_payload = {
        "data": {
            "webPages": {
                "value": [
                    {"name": "空链接", "url": "", "snippet": "无效"},
                    {"name": "非法链接", "url": "javascript:void(0)", "snippet": "无效"},
                    {"name": "已删除文章", "url": "https://example.com/deleted", "snippet": "该内容已被删除"},
                    {"name": "可用来源", "url": "https://example.com/live#fragment", "snippet": "有效新闻"},
                    {"name": "重复来源", "url": "https://example.com/live", "snippet": "重复"},
                    {"name": "不可访问来源", "url": "https://example.com/missing", "snippet": "有效标题"},
                ]
            }
        }
    }

    monkeypatch.setattr(BochaSearchService, "_post_json", lambda self, payload: response_payload)
    monkeypatch.setattr(
        BochaSearchService,
        "_check_live_source",
        lambda self, source: (source.url == "https://example.com/live", "链接不可访问"),
    )

    sources = BochaSearchService(api_key="test-key", validate_links=True).search("测试", count=6)

    assert len(sources) == 1
    assert sources[0].title == "可用来源"
    assert sources[0].url == "https://example.com/live"


def test_bocha_link_check_falls_back_to_get_when_head_is_blocked(monkeypatch):
    calls = []

    def fake_request_source_preview(self, url, method="GET"):
        calls.append(method)
        if method == "HEAD":
            return 403, ""
        return 200, "<html><title>可用新闻</title></html>"

    monkeypatch.setattr(
        BochaSearchService,
        "_request_source_preview",
        fake_request_source_preview,
    )

    service = BochaSearchService(api_key="test-key", validate_links=True)
    is_live, reason = service._check_live_source(
        SearchSource(title="可用新闻", url="https://example.com/news")
    )

    assert is_live is True
    assert reason == ""
    assert calls == ["HEAD", "GET"]


def test_bocha_link_check_falls_back_to_get_when_head_raises(monkeypatch):
    calls = []

    def fake_request_source_preview(self, url, method="GET"):
        calls.append(method)
        if method == "HEAD":
            raise TimeoutError("head timeout")
        return 200, "<html><title>可用新闻</title></html>"

    monkeypatch.setattr(
        BochaSearchService,
        "_request_source_preview",
        fake_request_source_preview,
    )

    service = BochaSearchService(api_key="test-key", validate_links=True)
    is_live, reason = service._check_live_source(
        SearchSource(title="可用新闻", url="https://example.com/news")
    )

    assert is_live is True
    assert reason == ""
    assert calls == ["HEAD", "GET"]


def test_bocha_deleted_marker_does_not_match_common_substrings():
    assert BochaSearchService._looks_deleted_from_body('<a class="gonew">返回新闻频道</a>') is False
    assert BochaSearchService._looks_deleted_from_body("function onthrow(error) {}") is False
    assert BochaSearchService._looks_deleted_from_body("404 Not Found") is True
