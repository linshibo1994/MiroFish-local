from app.services import simulation_manager as manager_module
from app.services.real_entity_resolver import ResolvedRealEntity, UNSUPPORTED
from app.services.simulation_manager import SimulationManager, SimulationState, SimulationStatus
from app.services.simulation_config_generator import SimulationParameters
from app.services.zep_entity_reader import EntityNode, FilteredEntities


def test_prepare_falls_back_when_real_verification_has_zero_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))

    entity = EntityNode(
        uuid="person-1",
        name="Alice Example",
        labels=["Entity", "Person"],
        summary="A candidate person with enough graph context for verification.",
        attributes={},
    )

    class FakeReader:
        def __init__(self, backend=None):
            pass

        def filter_defined_entities(self, graph_id, defined_entity_types=None, enrich_with_edges=True):
            return FilteredEntities(
                entities=[entity],
                entity_types={"Person"},
                total_count=1,
                filtered_count=1,
            )

    resolver_init_args = {}

    class FakeResolver:
        def __init__(self, min_source_count=1, allow_group_agents=True, concurrency=1):
            resolver_init_args["min_source_count"] = min_source_count
            resolver_init_args["allow_group_agents"] = allow_group_agents
            resolver_init_args["concurrency"] = concurrency

        def resolve_entities(self, entities):
            return [
                ResolvedRealEntity(
                    entity_uuid=entities[0].uuid,
                    entity_name=entities[0].name,
                    entity_type="Person",
                    verification_status=UNSUPPORTED,
                    skip_reason="测试：无可验证来源",
                )
            ]

    monkeypatch.setattr(manager_module, "ZepEntityReader", FakeReader)
    monkeypatch.setattr(manager_module, "RealEntityResolver", FakeResolver)

    class FakeProfileGenerator:
        def __init__(self, *args, **kwargs):
            self.profiles = []

        def generate_profiles_from_entities(self, **kwargs):
            assert kwargs["strict_real_mode"] is False
            assert len(kwargs["entities"]) == 1
            assert kwargs["resolved_real_entities"][entity.uuid].verification_status == UNSUPPORTED
            self.profiles = [
                manager_module.OasisAgentProfile(
                    user_id=0,
                    user_name="alice",
                    name=entity.name,
                    bio="基于图谱上下文生成的虚拟人设。",
                    persona="Alice Example 围绕测试事件参与讨论。",
                    source_entity_uuid=entity.uuid,
                    source_entity_type="Person",
                    verification_status=UNSUPPORTED,
                )
            ]
            return self.profiles

        def save_profiles(self, profiles, file_path, platform="reddit"):
            pass

    class FakeConfigGenerator:
        def generate_config(self, **kwargs):
            assert kwargs["entities"] == [entity]
            return SimulationParameters(
                simulation_id=kwargs["simulation_id"],
                project_id=kwargs["project_id"],
                graph_id=kwargs["graph_id"],
                simulation_requirement=kwargs["simulation_requirement"],
            )

    monkeypatch.setattr(manager_module, "OasisProfileGenerator", FakeProfileGenerator)
    monkeypatch.setattr(manager_module, "SimulationConfigGenerator", FakeConfigGenerator)

    manager = SimulationManager()
    state = SimulationState(
        simulation_id="sim_zero_verified",
        project_id="proj_1",
        graph_id="graph_1",
        graph_backend="graphiti",
        status=SimulationStatus.CREATED,
    )
    manager._save_simulation_state(state)

    result = manager.prepare_simulation(
        simulation_id="sim_zero_verified",
        simulation_requirement="测试真实画像",
        document_text="测试文档",
        use_real_profiles=True,
        strict_real_mode=True,
    )

    assert result.status == SimulationStatus.READY
    assert resolver_init_args == {
        "min_source_count": 1,
        "allow_group_agents": True,
        "concurrency": manager_module.Config.REAL_ENTITY_RESOLVE_CONCURRENCY,
    }
    assert result.verification_candidate_count == 1
    assert result.verification_verified_count == 0
    assert result.verification_skipped_count == 1
    assert result.error is None
    assert result.profiles_count == 1
