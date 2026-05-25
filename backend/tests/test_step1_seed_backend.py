import io

from app import create_app
from app.models.project import Project, ProjectManager, ProjectStatus
from app.services.bocha_search_service import BochaSearchService


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
        "_is_live_source",
        lambda self, source: source.url == "https://example.com/live",
    )

    sources = BochaSearchService(api_key="test-key", validate_links=True).search("测试", count=6)

    assert len(sources) == 1
    assert sources[0].title == "可用来源"
    assert sources[0].url == "https://example.com/live"
