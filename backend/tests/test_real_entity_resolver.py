import json

from app.services.real_entity_resolver import RealEntityResolver, RealEntitySource, UNSUPPORTED, VERIFIED
from app.services.zep_entity_reader import EntityNode


class FailingSearchService:
    def search(self, *args, **kwargs):
        raise AssertionError("unsupported 节点不应该调用外部搜索")


def test_default_entity_without_context_is_unsupported():
    entity = EntityNode(
        uuid="entity-1",
        name="Entity",
        labels=["Entity"],
        summary="",
        attributes={},
    )

    resolver = RealEntityResolver(search_service=FailingSearchService())
    result = resolver.resolve_entity(entity)

    assert result.verification_status == UNSUPPORTED
    assert "默认 Entity" in result.skip_reason
    assert result.info_sources == []


def test_group_entities_are_disabled_by_default():
    entity = EntityNode(
        uuid="group-1",
        name="Example Community",
        labels=["Entity", "Group"],
        summary="A group with enough graph context but group agents are disabled by default.",
        attributes={"kind": "group", "region": "test"},
    )

    resolver = RealEntityResolver(search_service=FailingSearchService(), allow_group_agents=False)
    result = resolver.resolve_entity(entity)

    assert result.verification_status == UNSUPPORTED
    assert "allow_group_agents" in result.skip_reason


def test_organization_entities_are_not_blocked_by_group_default(monkeypatch):
    monkeypatch.setattr("app.services.real_entity_resolver.Config.LLM_WEB_SEARCH_API_KEY", "")

    entity = EntityNode(
        uuid="org-1",
        name="Example Organization",
        labels=["Entity", "Organization"],
        summary="An organization with enough graph context should be verified by sources.",
        attributes={"kind": "organization", "region": "test"},
    )

    class EmptySearchService:
        def search(self, *args, **kwargs):
            return []

    resolver = RealEntityResolver(search_service=EmptySearchService())
    result = resolver.resolve_entity(entity)

    assert result.verification_status == UNSUPPORTED
    assert result.skip_reason == "LLM联网查询未返回可引用来源"


def test_group_entities_are_allowed_by_default_with_one_source(monkeypatch):
    monkeypatch.setattr("app.services.real_entity_resolver.Config.LLM_WEB_SEARCH_API_KEY", "")

    entity = EntityNode(
        uuid="group-1",
        name="Example Community",
        labels=["Entity", "Group"],
        summary="A publicly documented community involved in the event.",
        attributes={},
    )

    class OneSourceSearchService:
        def search(self, *args, **kwargs):
            return [
                {
                    "title": "Example Community official profile",
                    "url": "https://example.com/community",
                    "snippet": "Example Community is a publicly documented community involved in the event.",
                }
            ]

    resolver = RealEntityResolver(search_service=OneSourceSearchService())
    result = resolver.resolve_entity(entity)

    assert result.verification_status == VERIFIED
    assert len(result.source_citations) == 1


def test_short_names_are_not_rejected_before_search(monkeypatch):
    monkeypatch.setattr("app.services.real_entity_resolver.Config.LLM_WEB_SEARCH_API_KEY", "")

    entity = EntityNode(
        uuid="short-1",
        name="张",
        labels=["Entity", "Person"],
        summary="A person with a short public name but enough context.",
        attributes={},
    )

    class ShortNameSearchService:
        def search(self, *args, **kwargs):
            return [
                {
                    "title": "张 公开资料",
                    "url": "https://example.com/zhang",
                    "snippet": "张 是公开报道中的真实人物。",
                }
            ]

    resolver = RealEntityResolver(search_service=ShortNameSearchService())
    result = resolver.resolve_entity(entity)

    assert result.verification_status == VERIFIED


def test_default_real_entity_resolution_uses_llm_web_search(monkeypatch):
    entity = EntityNode(
        uuid="person-1",
        name="Alice Example",
        labels=["Entity", "Person"],
        summary="A public person with enough context.",
        attributes={},
    )

    class UnexpectedSearchService:
        def search(self, *args, **kwargs):
            raise AssertionError("LLM联网结果充足时不应该调用显式搜索服务")

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["extra_body"]["enable_search"] is True
            assert kwargs["extra_body"]["search_options"]["forced_search"] is True

            class Response:
                class Choice:
                    class Message:
                        content = json.dumps({
                            "sources": [
                                {
                                    "title": "Alice Example public profile",
                                    "url": "https://example.com/alice",
                                    "snippet": "Alice Example is a public person with enough context.",
                                    "site_name": "Example",
                                    "published_at": "",
                                }
                            ]
                        })

                    message = Message()

                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr("app.services.real_entity_resolver.Config.LLM_WEB_SEARCH_API_KEY", "test-key")
    monkeypatch.setattr("app.services.real_entity_resolver.Config.LLM_WEB_SEARCH_VALIDATE_LINKS", False)
    resolver = RealEntityResolver(
        search_service=UnexpectedSearchService(),
        llm_web_search_client=FakeClient(),
    )
    result = resolver.resolve_entity(entity)

    assert result.verification_status == VERIFIED
    assert result.source_citations[0]["url"] == "https://example.com/alice"


def test_llm_source_validation_only_filters_invalid_urls(monkeypatch):
    monkeypatch.setattr("app.services.real_entity_resolver.Config.LLM_WEB_SEARCH_VALIDATE_LINKS", True)

    resolver = RealEntityResolver(search_service=None)
    validated = resolver._validate_llm_sources(
        [
            RealEntitySource(
                title="Alice Example public profile",
                url="https://example.com/alice",
                snippet="Alice Example is a public person with enough context.",
                site_name="Example",
                published_at="",
            ),
            RealEntitySource(
                title="Alice Example invalid profile",
                url="not-a-url",
                snippet="Alice Example invalid source.",
                site_name="Example",
                published_at="",
            ),
        ]
    )

    assert [source.url for source in validated] == ["https://example.com/alice"]
