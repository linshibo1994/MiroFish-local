"""
图谱构建服务
接口2：使用Zep API构建Standalone Graph

支持双后端：
- Zep Cloud (默认)
- Graphiti + Neo4j 本地部署
"""

import os
import uuid
import time
import threading
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from .text_processor import TextProcessor
from .zep_factory import create_zep_client, get_zep_client
from .zep_adapter import ZepClientAdapter
from .location_entity_filter import (
    filter_location_entities,
    strip_location_entity_types_from_ontology,
)
from ..utils.llm_routing import clamp_concurrency, get_preferred_llm_endpoint

logger = logging.getLogger("mirofish.graph_builder")


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


@dataclass(frozen=True)
class GraphBatchPlan:
    """图谱写入批次计划。"""
    batch_size: int
    concurrency: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "batch_size": self.batch_size,
            "concurrency": self.concurrency,
        }


class GraphBuilderService:
    """
    图谱构建服务
    负责调用Zep API构建知识图谱

    支持双后端：
    - Zep Cloud: 使用 zep-cloud SDK
    - Graphiti: 使用 graphiti-core + Neo4j
    """

    INTERNAL_ATTRIBUTE_KEYS = {
        "name_embedding",
        "embedding",
        "embeddings",
    }
    GENERIC_NODE_LABELS = {"Entity", "Node"}

    def __init__(
        self,
        api_key: Optional[str] = None,
        backend: Optional[str] = None,
        build_mode: bool = False,
    ):
        """
        初始化图谱构建服务

        Args:
            api_key: Zep API Key（仅 cloud 模式需要，可选）
        """
        self._backend = backend or Config.ZEP_BACKEND
        if self._backend == 'graphiti' and build_mode:
            self._llm_endpoint = get_preferred_llm_endpoint(prefer_boost=True)
            self.client: ZepClientAdapter = create_zep_client(
                backend=self._backend,
                use_singleton=False,
                llm_endpoint=self._llm_endpoint,
            )
        else:
            self._llm_endpoint = None
            self.client: ZepClientAdapter = get_zep_client(backend=self._backend)
        self.task_manager = TaskManager()
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = Config.DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = Config.DEFAULT_CHUNK_OVERLAP,
        batch_size: int = Config.GRAPH_BUILD_BATCH_SIZE,
        concurrency: int = Config.GRAPH_BUILD_CONCURRENCY,
        extraction_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        异步构建图谱
        
        Args:
            text: 输入文本
            ontology: 本体定义（来自接口1的输出）
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小
            batch_size: 每批发送的块数量
            
        Returns:
            任务ID
        """
        # 创建任务
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
                "batch_size": batch_size,
                "concurrency": concurrency,
                "llm_model": self._llm_endpoint.model if self._llm_endpoint else None,
                "llm_boost_enabled": bool(self._llm_endpoint and self._llm_endpoint.is_boost),
            }
        )
        
        # 在后台线程中执行构建
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, concurrency, extraction_context)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        concurrency: int,
        extraction_context: Optional[Dict[str, Any]] = None,
    ):
        """图谱构建工作线程"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="开始构建图谱..."
            )
            
            # 1. 创建图谱
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"图谱已创建: {graph_id}"
            )
            
            # 2. 设置本体
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="本体已设置"
            )
            
            # 3. 文本分块
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"文本已分割为 {total_chunks} 个块"
            )
            
            # 4. 分批发送数据
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                ),
                extraction_context=extraction_context or {"event_topic": graph_name},
                concurrency=concurrency,
            )
            
            # 5. 等待Zep处理完成
            self.task_manager.update_task(
                task_id,
                progress=60,
                message="等待Zep处理数据..."
            )
            
            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )
            
            # 6. 获取图谱信息
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="获取图谱信息..."
            )
            
            graph_info = self._get_graph_info(graph_id)
            
            # 完成
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """创建图谱（公开方法）"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"

        self.client.create_graph(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )

        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        设置图谱本体（公开方法）

        根据后端类型选择处理方式：
        - Zep Cloud: 动态创建 Pydantic 模型，调用 Zep API
        - Graphiti: 归一化并缓存 ontology，供 episode 抽取时注入自定义实体/边类型
        """
        ontology = strip_location_entity_types_from_ontology(ontology)

        if self._backend == 'graphiti':
            # Graphiti 后端：直接传递原始 ontology，适配器会归一化并在写入时注入
            self.client.set_ontology(
                graph_ids=[graph_id],
                entities=ontology.get("entity_types", []),
                edges=ontology.get("edge_types", []),
            )
            return

        # Zep Cloud 后端：需要动态创建 Pydantic 模型
        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel
        from zep_cloud import EntityEdgeSourceTarget

        # 抑制 Pydantic v2 关于 Field(default=None) 的警告
        # 这是 Zep SDK 要求的用法，警告来自动态类创建，可以安全忽略
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')

        # Zep 保留名称，不能作为属性名
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}

        def safe_attr_name(attr_name: str) -> str:
            """将保留名称转换为安全名称"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name

        # 动态创建实体类型
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")

            # 创建属性字典和类型注解（Pydantic v2 需要）
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 使用安全名称
                attr_desc = attr_def.get("description", attr_name)
                # Zep API 需要 Field 的 description，这是必需的
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # 类型注解

            attrs["__annotations__"] = annotations

            # 动态创建类
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class

        # 动态创建边类型
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")

            # 创建属性字典和类型注解
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 使用安全名称
                attr_desc = attr_def.get("description", attr_name)
                # Zep API 需要 Field 的 description，这是必需的
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # 边属性用str类型

            attrs["__annotations__"] = annotations

            # 动态创建类
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description

            # 构建source_targets
            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )

            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)

        # 调用适配器设置本体
        if entity_types or edge_definitions:
            self.client.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = Config.GRAPH_BUILD_BATCH_SIZE,
        progress_callback: Optional[Callable] = None,
        extraction_context: Optional[Dict[str, Any]] = None,
        concurrency: int = Config.GRAPH_BUILD_CONCURRENCY,
    ) -> List[str]:
        """分批添加文本到图谱，返回所有 episode 的 uuid 列表"""
        total_chunks = len(chunks)
        if total_chunks == 0:
            return []

        backend = getattr(self, "_backend", Config.ZEP_BACKEND)
        batch_plan = self.resolve_batch_plan(
            batch_size=batch_size,
            concurrency=concurrency,
            backend=backend,
        )
        batch_size = batch_plan.batch_size
        concurrency = batch_plan.concurrency

        batch_specs = []
        total_batches = (total_chunks + batch_size - 1) // batch_size
        for start in range(0, total_chunks, batch_size):
            batch_chunks = chunks[start:start + batch_size]
            batch_specs.append((len(batch_specs), start, batch_chunks))

        # Cloud add_batch 自身是批量异步处理，保守串行提交；Graphiti 本地抽取才启用并发写入。
        use_worker_clients = (
            backend == 'graphiti'
            and concurrency > 1
            and hasattr(self.client, "set_ontology_from_cache")
        )

        completed_batches = 0
        episode_uuids_by_batch: Dict[int, List[str]] = {}
        progress_lock = threading.Lock()
        failure_event = threading.Event()
        max_reported_ratio = 0.0

        def build_episodes(batch_chunks: List[str]) -> List[Dict[str, Any]]:
            return [
                {
                    "data": self._wrap_chunk_with_event_constraints(chunk, extraction_context),
                    "type": "text",
                    "reference_time": None,
                }
                for chunk in batch_chunks
            ]

        def report_progress(message: str, ratio: float) -> None:
            """并发批次完成顺序不固定，确保对外进度只向前推进。"""
            nonlocal max_reported_ratio
            if not progress_callback:
                return
            safe_ratio = max(0.0, min(1.0, float(ratio or 0)))
            with progress_lock:
                max_reported_ratio = max(max_reported_ratio, safe_ratio)
                reported_ratio = max_reported_ratio
            progress_callback(message, reported_ratio)

        def iter_exception_messages(exc: Exception) -> List[str]:
            messages: List[str] = []
            seen = set()
            current = exc
            while current is not None and id(current) not in seen:
                seen.add(id(current))
                messages.append(str(current) or current.__class__.__name__)
                current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
            return messages

        def raise_batch_error(batch_num: int, exc: Exception) -> None:
            if isinstance(exc, TimeoutError) or isinstance(exc, FutureTimeoutError):
                message = f"批次 {batch_num} 写入超过 Graphiti 超时限制"
            else:
                exception_text = " ".join(iter_exception_messages(exc)).lower()
                if (
                    "insufficient_quota" in exception_text
                    or "exceeded your current quota" in exception_text
                    or "check your plan and billing" in exception_text
                ):
                    message = "LLM 服务额度不足或账单配额已耗尽，请检查 API Key、套餐/余额，或切换 Graphiti 使用的模型后重试"
                elif "429" in exception_text or ("rate" in exception_text and "limit" in exception_text):
                    message = "LLM 服务触发限流，请稍后重试；若频繁出现，请降低 GRAPHITI_LLM_CONCURRENCY 或调大 GRAPHITI_LLM_MIN_INTERVAL_SECONDS"
                else:
                    message = str(exc) or exc.__class__.__name__
            report_progress(f"批次 {batch_num} 发送失败: {message}", 0)
            raise RuntimeError(f"批次 {batch_num} 图谱写入失败: {message}") from exc

        def create_worker_client() -> ZepClientAdapter:
            worker_client = create_zep_client(
                backend=backend,
                use_singleton=False,
                llm_endpoint=getattr(self, "_llm_endpoint", None),
            )
            if hasattr(worker_client, "set_ontology_from_cache"):
                worker_client.set_ontology_from_cache(graph_id, self.client)
            return worker_client

        def submit_batch(batch_index: int, start_index: int, batch_chunks: List[str]) -> List[str]:
            batch_num = batch_index + 1
            report_progress(
                f"发送第 {batch_num}/{total_batches} 批数据 ({len(batch_chunks)} 块)...",
                min(start_index / total_chunks, completed_batches / total_batches),
            )

            worker_client = create_worker_client() if use_worker_clients else self.client
            try:
                logger.info(
                    "图谱批次写入开始: graph_id=%s, batch=%s/%s, chunks=%s, concurrency=%s, worker_client=%s",
                    graph_id,
                    batch_num,
                    total_batches,
                    len(batch_chunks),
                    concurrency,
                    worker_client is not self.client,
                )
                batch_uuids = worker_client.add_episode_batch(
                    graph_id=graph_id,
                    episodes=build_episodes(batch_chunks),
                )
                if failure_event.is_set():
                    logger.info(
                        "图谱批次写入完成但任务已失败，结果丢弃: graph_id=%s, batch=%s/%s, episodes=%s",
                        graph_id,
                        batch_num,
                        total_batches,
                        len(batch_uuids),
                    )
                else:
                    logger.info(
                        "图谱批次写入完成: graph_id=%s, batch=%s/%s, episodes=%s",
                        graph_id,
                        batch_num,
                        total_batches,
                        len(batch_uuids),
                    )
                delay = max(0.0, float(Config.GRAPH_BUILD_BATCH_DELAY_SECONDS or 0))
                if delay:
                    time.sleep(delay)
                return batch_uuids
            except Exception:
                failure_event.set()
                logger.exception(
                    "图谱批次写入异常: graph_id=%s, batch=%s/%s",
                    graph_id,
                    batch_num,
                    total_batches,
                )
                raise
            finally:
                if worker_client is not self.client and hasattr(worker_client, "close"):
                    try:
                        worker_client.close()
                    except Exception:
                        pass

        if concurrency <= 1 or total_batches == 1:
            for batch_index, start_index, batch_chunks in batch_specs:
                try:
                    episode_uuids_by_batch[batch_index] = submit_batch(batch_index, start_index, batch_chunks)
                    completed_batches += 1
                    report_progress(
                        f"已完成第 {completed_batches}/{total_batches} 批数据写入",
                        completed_batches / total_batches,
                    )
                except Exception as e:
                    raise_batch_error(batch_index + 1, e)
        else:
            with ThreadPoolExecutor(max_workers=min(concurrency, total_batches)) as executor:
                future_to_batch = {
                    executor.submit(submit_batch, batch_index, start_index, batch_chunks): batch_index
                    for batch_index, start_index, batch_chunks in batch_specs
                }
                for future in as_completed(future_to_batch):
                    batch_index = future_to_batch[future]
                    try:
                        episode_uuids_by_batch[batch_index] = future.result()
                    except Exception as e:
                        for pending_future in future_to_batch:
                            if pending_future is not future:
                                pending_future.cancel()
                        raise_batch_error(batch_index + 1, e)

                    with progress_lock:
                        completed_batches += 1
                        current_completed = completed_batches

                    report_progress(
                        f"已完成第 {current_completed}/{total_batches} 批数据写入",
                        current_completed / total_batches,
                    )

        episode_uuids: List[str] = []
        for batch_index in range(total_batches):
            episode_uuids.extend(episode_uuids_by_batch.get(batch_index, []))
        return episode_uuids

    @staticmethod
    def resolve_batch_plan(
        batch_size: int = Config.GRAPH_BUILD_BATCH_SIZE,
        concurrency: int = Config.GRAPH_BUILD_CONCURRENCY,
        backend: Optional[str] = None,
    ) -> GraphBatchPlan:
        """计算图谱写入实际生效的批次大小和并发数。"""
        resolved_batch_size = max(1, int(batch_size or 1))
        resolved_concurrency = clamp_concurrency(
            concurrency,
            Config.GRAPH_BUILD_CONCURRENCY,
            maximum=8,
        )

        if (backend or Config.ZEP_BACKEND) == 'graphiti':
            graphiti_batch_size = max(1, int(Config.GRAPHITI_EPISODE_BATCH_SIZE or 1))
            graphiti_ingest_concurrency = max(1, int(Config.GRAPHITI_INGEST_CONCURRENCY or 1))
            resolved_batch_size = min(resolved_batch_size, graphiti_batch_size)
            resolved_concurrency = min(resolved_concurrency, graphiti_ingest_concurrency)
        else:
            resolved_concurrency = 1

        return GraphBatchPlan(
            batch_size=resolved_batch_size,
            concurrency=resolved_concurrency,
        )

    @classmethod
    def _wrap_chunk_with_event_constraints(
        cls,
        chunk: str,
        extraction_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """为每个文本块补充事件锚点，约束图谱抽取只保留事件相关主体。"""
        if not extraction_context:
            return chunk

        event_topic = cls._compact_context_value(extraction_context.get("event_topic"), 200)
        simulation_requirement = cls._compact_context_value(
            extraction_context.get("simulation_requirement"),
            300,
        )
        seed_summary = cls._compact_context_value(extraction_context.get("seed_summary"), 1200)
        entity_hints = cls._compact_context_list(extraction_context.get("entity_hints"), 30, 600)

        context_lines = []
        if event_topic:
            context_lines.append(f"- 事件主题：{event_topic}")
        if simulation_requirement:
            context_lines.append(f"- 推演方向：{simulation_requirement}")
        if entity_hints:
            context_lines.append(f"- 已知关键主体提示：{entity_hints}")
        if seed_summary:
            context_lines.append(f"- 事件摘要：{seed_summary}")

        context_block = "\n".join(context_lines) or "- 事件主题：未提供"
        return f"""# 图谱实体抽取约束（仅用于判断相关性，不是事实来源）
{context_block}

硬性规则：
1. 只抽取“文档文本块”中明确出现，且与事件主题、事件事实或推演方向存在真实关联的实体节点。
2. 优先覆盖政府/监管、单位、机构、企业/品牌、媒体、组织/协会、意见领袖/网红、社区、公众、主配角、网民/个人、事件本身等关键主体。
3. 实体关系必须能从文档文本块中的事实支撑；只有背景、广告、推荐、相似案例或无关段落里的实体不要抽取。
4. 如果某个名称虽然出现在文本块中，但无法说明它和事件或推演方向的关系，必须忽略。
5. 不要把本约束中的类别词、规则文本或示例当作实体；实体事实只能来自“文档文本块”。
6. 不要抽取纯地点、位置、地址、城市、地区、场所作为实体节点；地点只能作为事件背景或主体属性。若名称指向可发声组织（如政府机构、学校、医院、公司、媒体等），按组织主体抽取。
7. 例如“张雪机车事件”应保留张雪、张雪机车、法国车手瓦伦丁·德比斯、WSBK、820RR-RS等真实相关主体；网易游戏、阴阳师等无关实体即使出现在材料杂讯中也不要入图。

# 文档文本块（唯一事实来源）
{chunk}"""

    @staticmethod
    def _compact_context_value(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = " ".join(text.split())
        return text[:limit]

    @classmethod
    def _compact_context_list(cls, values: Any, max_items: int, limit: int) -> str:
        if not values:
            return ""
        if isinstance(values, str):
            items = [values]
        else:
            items = [str(item).strip() for item in values if str(item).strip()]
        text = "、".join(items[:max_items])
        return cls._compact_context_value(text, limit)
    
    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """等待所有 episode 处理完成（通过查询每个 episode 的 processed 状态）"""
        if not episode_uuids:
            if progress_callback:
                progress_callback("无需等待（没有 episode）", 1.0)
            return

        # Graphiti 同步处理，直接返回
        if self._backend == 'graphiti':
            if progress_callback:
                progress_callback(f"处理完成: {len(episode_uuids)}/{len(episode_uuids)}", 1.0)
            return

        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)

        if progress_callback:
            progress_callback(f"开始等待 {total_episodes} 个文本块处理...", 0)

        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"部分文本块超时，已完成 {completed_count}/{total_episodes}",
                        completed_count / total_episodes
                    )
                break

            # 检查每个 episode 的处理状态
            for ep_uuid in list(pending_episodes):
                try:
                    status = self.client.get_episode_status(ep_uuid)
                    if status.processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1

                except Exception as e:
                    # 忽略单个查询错误，继续
                    pass

            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"处理中... {completed_count}/{total_episodes} 完成, {len(pending_episodes)} 待处理 ({elapsed}秒)",
                    completed_count / total_episodes if total_episodes > 0 else 0
                )

            if pending_episodes:
                time.sleep(3)  # 每3秒检查一次

        if progress_callback:
            progress_callback(f"处理完成: {completed_count}/{total_episodes}", 1.0)
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息"""
        # 使用适配器获取节点和边
        nodes = self.client.get_all_nodes(graph_id)
        edges = self.client.get_all_edges(graph_id)
        nodes, edges = self._coalesce_duplicate_entities(nodes, edges)
        nodes, edges = filter_location_entities(nodes, edges)

        # 统计实体类型
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in self.GENERIC_NODE_LABELS:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        获取完整图谱数据（包含详细信息）

        Args:
            graph_id: 图谱ID

        Returns:
            包含nodes和edges的字典，包括时间信息、属性等详细数据
        """
        # 使用适配器获取节点和边
        nodes = self.client.get_all_nodes(graph_id)
        edges = self.client.get_all_edges(graph_id)
        nodes, edges = self._coalesce_duplicate_entities(nodes, edges)
        nodes, edges = filter_location_entities(nodes, edges)

        # 创建节点映射用于获取节点名称
        node_map = {}
        for node in nodes:
            node_map[node.uuid] = node.name or ""

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": node.uuid,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": self._sanitize_display_attributes(node.attributes),
                "created_at": node.created_at,
            })

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": edge.uuid,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": edge.name or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": self._sanitize_display_attributes(edge.attributes),
                "created_at": edge.created_at,
                "valid_at": edge.valid_at,
                "invalid_at": edge.invalid_at,
                "expired_at": edge.expired_at,
                "episodes": edge.episodes or [],
            })

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    @classmethod
    def _sanitize_display_attributes(cls, attributes: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """过滤不适合前端展示的内部属性。"""
        if not attributes:
            return {}
        return {
            key: value for key, value in attributes.items()
            if str(key).lower() not in cls.INTERNAL_ATTRIBUTE_KEYS
        }

    @classmethod
    def _coalesce_duplicate_entities(
        cls,
        nodes: List[Any],
        edges: List[Any],
    ) -> tuple[List[Any], List[Any]]:
        """按实体名称和主类型归并 Graphiti 重复抽取出的同名节点。"""
        if not nodes:
            return nodes, edges

        canonical_by_key: Dict[tuple[str, str], Any] = {}
        uuid_to_canonical: Dict[str, str] = {}
        merged_sources_by_uuid: Dict[str, set[str]] = {}
        canonical_nodes: List[Any] = []

        for node in nodes:
            node_uuid = getattr(node, "uuid", "") or ""
            node_name = getattr(node, "name", "") or ""
            merge_key = (cls._normalize_entity_name(node_name), cls._primary_entity_label(getattr(node, "labels", []) or []))
            if not merge_key[0]:
                if node_uuid:
                    uuid_to_canonical[node_uuid] = node_uuid
                    merged_sources_by_uuid.setdefault(node_uuid, set()).add(node_uuid)
                canonical_nodes.append(node)
                continue

            canonical = canonical_by_key.get(merge_key)
            if not canonical:
                canonical_by_key[merge_key] = node
                canonical_nodes.append(node)
                if node_uuid:
                    uuid_to_canonical[node_uuid] = node_uuid
                    merged_sources_by_uuid.setdefault(node_uuid, set()).add(node_uuid)
                continue

            canonical_uuid = getattr(canonical, "uuid", "") or node_uuid
            if node_uuid:
                uuid_to_canonical[node_uuid] = canonical_uuid
                merged_sources_by_uuid.setdefault(canonical_uuid, set()).add(node_uuid)
            if canonical_uuid:
                merged_sources_by_uuid.setdefault(canonical_uuid, set()).add(canonical_uuid)
            cls._merge_node_into_canonical(canonical, node)

        for node in canonical_nodes:
            node_uuid = getattr(node, "uuid", "") or ""
            if not node_uuid:
                continue
            source_uuids = sorted(merged_sources_by_uuid.get(node_uuid, {node_uuid}))
            if len(source_uuids) <= 1:
                continue
            attributes = dict(getattr(node, "attributes", {}) or {})
            attributes["merged_duplicate_uuids"] = source_uuids
            setattr(node, "attributes", attributes)

        redirected_edges = cls._redirect_edges_to_canonical(edges, uuid_to_canonical)
        return canonical_nodes, redirected_edges

    @classmethod
    def _normalize_entity_name(cls, name: str) -> str:
        """实体名称归一化，用于识别 Graphiti 跨批次重复实体。"""
        normalized = str(name or "").strip().casefold()
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"[《》“”\"'‘’`·•・,，.。:：;；!！?？\\-—_()（）\\[\\]【】{}<>]+", "", normalized)
        return normalized

    @classmethod
    def _primary_entity_label(cls, labels: List[str]) -> str:
        """提取实体主类型；没有主类型时回退到 Entity。"""
        for label in labels or []:
            if label not in cls.GENERIC_NODE_LABELS:
                return str(label)
        return "Entity"

    @classmethod
    def _merge_node_into_canonical(cls, canonical: Any, duplicate: Any) -> None:
        """把重复节点的信息合并到 canonical 节点。"""
        canonical.labels = cls._merge_unique_values(getattr(canonical, "labels", []) or [], getattr(duplicate, "labels", []) or [])

        canonical_summary = getattr(canonical, "summary", "") or ""
        duplicate_summary = getattr(duplicate, "summary", "") or ""
        if len(duplicate_summary) > len(canonical_summary):
            canonical.summary = duplicate_summary

        canonical.attributes = cls._merge_attribute_dicts(
            getattr(canonical, "attributes", {}) or {},
            getattr(duplicate, "attributes", {}) or {},
        )

        canonical_created_at = getattr(canonical, "created_at", None)
        duplicate_created_at = getattr(duplicate, "created_at", None)
        if duplicate_created_at and (not canonical_created_at or str(duplicate_created_at) < str(canonical_created_at)):
            canonical.created_at = duplicate_created_at

    @classmethod
    def _merge_attribute_dicts(cls, first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
        """合并节点属性，保留非空信息并对冲突值做列表化。"""
        merged = dict(first or {})
        for key, value in (second or {}).items():
            if value in (None, "", [], {}):
                continue
            if key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = value
                continue
            if merged[key] == value:
                continue
            merged[key] = cls._merge_unique_values(
                merged[key] if isinstance(merged[key], list) else [merged[key]],
                value if isinstance(value, list) else [value],
            )
        return merged

    @classmethod
    def _merge_unique_values(cls, first: List[Any], second: List[Any]) -> List[Any]:
        """按字符串表示保持顺序去重。"""
        values = []
        seen = set()
        for value in [*(first or []), *(second or [])]:
            marker = str(value)
            if marker in seen:
                continue
            seen.add(marker)
            values.append(value)
        return values

    @classmethod
    def _redirect_edges_to_canonical(cls, edges: List[Any], uuid_to_canonical: Dict[str, str]) -> List[Any]:
        """把边端点改写到 canonical 节点，并去掉完全重复边。"""
        redirected = []
        seen = set()
        for edge in edges or []:
            source_uuid = uuid_to_canonical.get(getattr(edge, "source_node_uuid", ""), getattr(edge, "source_node_uuid", ""))
            target_uuid = uuid_to_canonical.get(getattr(edge, "target_node_uuid", ""), getattr(edge, "target_node_uuid", ""))
            if not source_uuid or not target_uuid:
                continue

            edge.source_node_uuid = source_uuid
            edge.target_node_uuid = target_uuid
            edge_key = (
                source_uuid,
                target_uuid,
                getattr(edge, "name", "") or getattr(edge, "fact_type", ""),
                getattr(edge, "fact", "") or "",
            )
            if edge_key in seen:
                continue
            seen.add(edge_key)
            redirected.append(edge)
        return redirected
    
    def delete_graph(self, graph_id: str):
        """删除图谱"""
        self.client.delete_graph(graph_id)
