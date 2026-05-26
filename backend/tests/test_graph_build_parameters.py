from app.config import Config
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
