import csv
import json

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.real_entity_resolver import ResolvedRealEntity
from app.services.zep_entity_reader import EntityNode


def test_real_profile_preserves_provenance_in_reddit_and_twitter(tmp_path):
    entity = EntityNode(
        uuid="person-1",
        name="Alice Example",
        labels=["Entity", "Person"],
        summary="图谱摘要：Alice Example 在本次事件中负责核验报道线索。",
        attributes={},
        related_edges=[
            {
                "fact": "Alice Example 参与了本次事件的信息核验工作",
                "edge_name": "INVESTIGATES",
                "direction": "outgoing",
            }
        ],
    )
    resolved = ResolvedRealEntity(
        entity_uuid="person-1",
        entity_name="Alice Example",
        entity_type="Person",
        verification_status="verified",
        info_confidence=0.9,
        info_sources=[
            {
                "title": "Alice Example profile",
                "url": "https://example.com/alice",
                "snippet": "Alice Example is a verified public profile.",
            }
        ],
        source_citations=[
            {
                "title": "Alice Example profile",
                "url": "https://example.com/alice",
                "snippet": "Alice Example is a verified public profile.",
            }
        ],
        real_identity_summary="Alice Example is a verified public profile.",
        verified_facts=["Alice Example is a verified public profile."],
    )

    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)
    profile = generator.generate_profile_from_entity(
        entity=entity,
        user_id=0,
        use_llm=False,
        resolved_real_entity=resolved,
        strict_real_mode=True,
    )

    assert profile.verification_status == "verified"
    assert profile.real_identity_summary == resolved.real_identity_summary
    assert profile.runtime_traits["note"].startswith("OASIS运行必需默认字段")
    assert "图谱摘要" in profile.persona
    assert "信息核验" in profile.persona
    assert "资料来源" not in profile.persona
    assert "https://example.com/alice" not in profile.persona
    assert "https://example.com/alice" not in profile.bio

    reddit_path = tmp_path / "reddit_profiles.json"
    twitter_path = tmp_path / "twitter_profiles.csv"
    generator._save_reddit_json([profile], str(reddit_path))
    generator._save_twitter_csv([profile], str(twitter_path))

    reddit_data = json.loads(reddit_path.read_text(encoding="utf-8"))
    assert reddit_data[0]["verification_status"] == "verified"
    assert reddit_data[0]["provenance"]["source_citations"][0]["url"] == "https://example.com/alice"
    assert reddit_data[0]["runtime_traits"]["note"].startswith("OASIS运行必需默认字段")

    with twitter_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    twitter_provenance = json.loads(rows[0]["provenance"])
    assert rows[0]["verification_status"] == "verified"
    assert twitter_provenance["source_citations"][0]["url"] == "https://example.com/alice"


def test_profile_bio_truncates_on_sentence_boundary_when_saved(tmp_path):
    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)
    profile = generator.generate_profile_from_entity(
        entity=EntityNode(
            uuid="media-1",
            name="重庆日报",
            labels=["Entity", "MediaOutlet"],
            summary=(
                "重庆日报是重庆本地重要新闻媒体机构，长期报道政务、民生与公共事件。"
                "在本次事件中，重庆日报持续跟进泡药杨梅报道，并对公众关切进行解释。"
                "编辑部还围绕监管部门回应、消费者投诉、市场主体说法和行业背景进行了连续梳理。"
                "这些信息共同构成了模拟讨论中媒体账号的事实记忆与发言边界。"
                "媒体账号还需要在模拟过程中保持谨慎措辞，避免把未经核实的市场传闻当作结论。"
                "评论互动时应优先引用既有事实、采访对象和公开回应，减少情绪化表达。"
                "值班编辑需要区分已确认事实、待核实线索和公众情绪，并在后续推演中保持一致口径。"
                "账号对外发言还要兼顾地方媒体的公共服务属性、舆情引导职责和新闻专业边界。"
                "这是一段用于验证保存阶段不会半句硬截断的补充说明。"
            ),
            attributes={},
        ),
        user_id=0,
        use_llm=False,
    )

    reddit_path = tmp_path / "reddit_profiles.json"
    generator._save_reddit_json([profile], str(reddit_path))
    reddit_data = json.loads(reddit_path.read_text(encoding="utf-8"))

    assert reddit_data[0]["bio"].endswith("。")
    assert "补充说明" not in reddit_data[0]["bio"]
