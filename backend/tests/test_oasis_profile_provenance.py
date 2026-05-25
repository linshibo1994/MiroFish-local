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
        summary="Graph summary should not be used as the real dossier.",
        attributes={},
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
    assert "Graph summary" not in profile.persona

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
