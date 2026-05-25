import csv
import json

from app.services.simulation_manager import SimulationManager, SimulationState, SimulationStatus


def test_get_profiles_reads_twitter_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))

    manager = SimulationManager()
    state = SimulationState(
        simulation_id="sim_twitter",
        project_id="proj_1",
        graph_id="graph_1",
        graph_backend="graphiti",
        status=SimulationStatus.READY,
    )
    manager._save_simulation_state(state)

    sim_dir = tmp_path / "sim_twitter"
    csv_path = sim_dir / "twitter_profiles.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["user_id", "name", "username", "user_char", "description"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "user_id": "0",
                "name": "Alice",
                "username": "alice",
                "user_char": "persona",
                "description": "bio",
            }
        )

    profiles = manager.get_profiles("sim_twitter", platform="twitter")

    assert len(profiles) == 1
    assert profiles[0]["username"] == "alice"
    assert profiles[0]["description"] == "bio"


def test_get_profiles_supports_legacy_twitter_json(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))

    manager = SimulationManager()
    state = SimulationState(
        simulation_id="sim_legacy",
        project_id="proj_1",
        graph_id="graph_1",
        graph_backend="cloud",
        status=SimulationStatus.READY,
    )
    manager._save_simulation_state(state)

    sim_dir = tmp_path / "sim_legacy"
    legacy_path = sim_dir / "twitter_profiles.json"
    with legacy_path.open("w", encoding="utf-8") as f:
        json.dump([{"username": "legacy_user"}], f, ensure_ascii=False)

    profiles = manager.get_profiles("sim_legacy", platform="twitter")

    assert profiles == [{"username": "legacy_user"}]
