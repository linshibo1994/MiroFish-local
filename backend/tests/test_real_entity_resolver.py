from app.services.real_entity_resolver import RealEntityResolver, UNSUPPORTED
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
