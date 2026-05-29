"""
图谱相关API路由
采用项目上下文机制，服务端持久化状态
"""

import os
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.type_translation_service import TypeTranslationService
from ..services.seed_analysis_service import SeedAnalysisService
from ..services.web_search_provider import WebSearchProviderFactory
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..utils.neo4j_errors import format_neo4j_auth_error, is_neo4j_auth_error
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# 获取日志器
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


def _get_project_backend_or_404(graph_id: str):
    """按 graph_id 解析项目与 backend，不允许静默回退到全局 backend。"""
    project = ProjectManager.get_project_by_graph_id(graph_id)
    if not project:
        return None, None, (
            jsonify({
                "success": False,
                "error": f"图谱未绑定到任何项目元数据: {graph_id}"
            }),
            404,
        )
    backend = project.graph_backend or Config.ZEP_BACKEND
    return project, backend, None


def _persist_seed_analysis(project, seed_result, sources=None) -> None:
    """把 seed 分析结果同步保存到元数据和独立文件。"""
    source_dicts = []
    for source in sources or []:
        source_dicts.append(source.to_dict() if hasattr(source, "to_dict") else source)

    project.seed_summary_md = seed_result.seed_summary_md
    if project.seed_input_mode == 'web_search':
        project.seed_full_content_md = seed_result.seed_summary_md
    else:
        project.seed_full_content_md = project.seed_full_content_md or seed_result.seed_summary_md
    project.seed_sources = source_dicts
    project.simulation_suggestions = seed_result.simulation_suggestions
    project.entity_hints = seed_result.entity_hints
    project.seed_metadata = seed_result.seed_metadata

    ProjectManager.save_seed_summary(project.project_id, project.seed_summary_md)
    ProjectManager.save_seed_sources(project.project_id, project.seed_sources)


def _extract_and_store_uploaded_files(project, uploaded_files):
    """保存上传文件并提取预处理文本。"""
    document_texts = []
    all_text = ""

    for file in uploaded_files:
        if file and file.filename and allowed_file(file.filename):
            file_info = ProjectManager.save_file_to_project(
                project.project_id,
                file,
                file.filename
            )
            project.files.append({
                "filename": file_info["original_filename"],
                "size": file_info["size"]
            })

            text = FileParser.extract_text(file_info["path"])
            text = TextProcessor.preprocess_text(text)
            document_texts.append(text)
            all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

    return document_texts, all_text


def _save_generated_ontology(project, ontology):
    """保存本体生成结果到项目。"""
    ontology = TypeTranslationService.ensure_ontology_translations(ontology)
    project.ontology = {
        "entity_types": ontology.get("entity_types", []),
        "edge_types": ontology.get("edge_types", [])
    }
    project.analysis_summary = ontology.get("analysis_summary", "")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    ProjectManager.save_project(project)


@graph_bp.route('/type-translations', methods=['GET'])
def get_type_translations():
    """获取实体类型和关系类型翻译表。"""
    return jsonify({
        "success": True,
        "data": TypeTranslationService.get_public_payload()
    })


# ============== 项目管理接口 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    获取项目详情
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"项目不存在: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所有项目
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    删除项目
    """
    project = ProjectManager.get_project(project_id)
    if project and project.graph_id:
        backend = project.graph_backend or Config.ZEP_BACKEND
        try:
            GraphBuilderService(backend=backend).delete_graph(project.graph_id)
        except Exception as exc:
            logger.warning(f"删除项目时清理图谱失败: project_id={project_id}, graph_id={project.graph_id}, error={exc}")

    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"项目不存在或删除失败: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"项目已删除: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置项目状态（用于重新构建图谱）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"项目不存在: {project_id}"
        }), 404
    
    old_graph_id = project.graph_id
    old_backend = project.graph_backend or Config.ZEP_BACKEND

    # 重置到本体已生成状态
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.graph_backend = None
    project.graph_provider = None
    project.graph_schema_version = None
    project.error = None
    ProjectManager.save_project(project)

    if old_graph_id:
        try:
            GraphBuilderService(backend=old_backend).delete_graph(old_graph_id)
        except Exception as exc:
            logger.warning(f"重置项目时清理旧图谱失败: project_id={project_id}, graph_id={old_graph_id}, error={exc}")
    
    return jsonify({
        "success": True,
        "message": f"项目已重置: {project_id}",
        "data": project.to_dict()
    })


# ============== Step1：Web 搜索 seed ==============

@graph_bp.route('/seed/web-search', methods=['POST'])
def create_seed_from_web_search():
    """
    通过配置的联网搜索 provider 创建 seed 项目。
    """
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            return jsonify({
                "success": False,
                "error": "Web 搜索 seed 仅接受 JSON 请求，文件输入请使用 /ontology/generate 的 multipart 阶段"
            }), 400

        data = request.get_json(silent=True) or {}
        query = (data.get('query') or data.get('search_query') or '').strip()
        project_name = data.get('project_name') or query or 'Web Search Seed'
        additional_context = data.get('additional_context')

        if not query:
            return jsonify({
                "success": False,
                "error": "请提供搜索关键词 query"
            }), 400
        if data.get('files'):
            return jsonify({
                "success": False,
                "error": "搜索输入和文件输入互斥，请不要在 Web 搜索 seed 中提交 files"
            }), 400

        provider_name = WebSearchProviderFactory.get_provider_name(data.get('provider'))
        search_service = WebSearchProviderFactory.create(provider_name)
        sources = search_service.search(
            query=query,
            count=data.get('count'),
            freshness=data.get('freshness'),
            summary=data.get('summary', True),
        )
        if not sources:
            return jsonify({
                "success": False,
                "error": "未获得可用搜索结果"
            }), 400

        project = ProjectManager.create_project(name=project_name)
        project.seed_input_mode = 'web_search'
        project.search_query = query

        source_text = SeedAnalysisService._build_search_material(
            [source.to_dict() for source in sources],
            query,
        )
        ProjectManager.save_extracted_text(project.project_id, source_text)
        project.total_text_length = len(source_text)

        seed_result = SeedAnalysisService().analyze_from_sources(
            sources=sources,
            query=query,
            additional_context=additional_context,
        )
        seed_result.seed_metadata["web_search_provider"] = provider_name
        _persist_seed_analysis(project, seed_result, sources=sources)
        ProjectManager.save_extracted_text(project.project_id, project.seed_full_content_md)
        project.total_text_length = len(project.seed_full_content_md or '')
        ProjectManager.save_project(project)

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "seed_input_mode": project.seed_input_mode,
                "search_query": project.search_query,
                "seed_summary_md": project.seed_summary_md,
                "seed_full_content_md": project.seed_full_content_md,
                "seed_sources": project.seed_sources,
                "simulation_suggestions": project.simulation_suggestions,
                "entity_hints": project.entity_hints,
                "seed_metadata": project.seed_metadata,
                "total_text_length": project.total_text_length,
            }
        })

    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 接口1：seed 分析 / 生成本体 ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    multipart/form-data：上传文件并生成 seed 分析，不生成本体。
    application/json：基于已有 project_id 和 simulation_requirement 生成本体。
    """
    try:
        if request.is_json:
            logger.info("=== 开始基于项目生成本体定义 ===")
            data = request.get_json(silent=True) or {}
            project_id = data.get('project_id')
            simulation_requirement = (data.get('simulation_requirement') or '').strip()
            additional_context = data.get('additional_context')

            if data.get('files') or data.get('search_query') or data.get('query'):
                return jsonify({
                    "success": False,
                    "error": "本体生成阶段仅接受 project_id 和 simulation_requirement；文件和搜索输入请先完成 seed 阶段"
                }), 400
            if not project_id:
                return jsonify({
                    "success": False,
                    "error": "请提供 project_id"
                }), 400
            if not simulation_requirement:
                return jsonify({
                    "success": False,
                    "error": "请提供模拟需求描述 (simulation_requirement)"
                }), 400

            project = ProjectManager.get_project(project_id)
            if not project:
                return jsonify({
                    "success": False,
                    "error": f"项目不存在: {project_id}"
                }), 404

            extracted_text = ProjectManager.get_extracted_text(project_id)
            if not extracted_text:
                return jsonify({
                    "success": False,
                    "error": "未找到提取的文本内容，请先完成 seed 分析阶段"
                }), 400

            project.simulation_requirement = simulation_requirement
            logger.info("调用 LLM 生成本体定义...")
            ontology = OntologyGenerator().generate(
                document_texts=[extracted_text],
                simulation_requirement=simulation_requirement,
                additional_context=additional_context if additional_context else None
            )
            _save_generated_ontology(project, ontology)
            logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")

            return jsonify({
                "success": True,
                "data": {
                    "project_id": project.project_id,
                    "project_name": project.name,
                    "ontology": project.ontology,
                    "analysis_summary": project.analysis_summary,
                    "files": project.files,
                    "seed_input_mode": project.seed_input_mode,
                    "total_text_length": project.total_text_length
                }
            })

        logger.info("=== 开始 multipart 文件 seed 分析 ===")
        if request.form.get('search_query') or request.form.get('query'):
            return jsonify({
                "success": False,
                "error": "文件输入和搜索输入互斥；搜索 seed 请使用 /seed/web-search"
            }), 400

        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "请至少上传一个文档文件"
            }), 400

        project = ProjectManager.create_project(name=project_name)
        project.seed_input_mode = 'file_upload'
        simulation_requirement = request.form.get('simulation_requirement', '').strip()
        if simulation_requirement:
            project.simulation_requirement = simulation_requirement
        logger.info(f"创建项目: {project.project_id}")

        document_texts, all_text = _extract_and_store_uploaded_files(project, uploaded_files)
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "没有成功处理任何文档，请检查文件格式"
            }), 400

        project.total_text_length = len(all_text)
        project.seed_full_content_md = all_text
        ProjectManager.save_extracted_text(project.project_id, all_text)
        seed_result = SeedAnalysisService().analyze_from_text(
            text=all_text,
            topic=project_name,
            additional_context=additional_context if additional_context else None,
        )
        _persist_seed_analysis(project, seed_result, sources=[])
        ProjectManager.save_project(project)
        logger.info(f"=== 文件 seed 分析完成 === 项目ID: {project.project_id}")

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "seed_input_mode": project.seed_input_mode,
                "seed_summary_md": project.seed_summary_md,
                "seed_full_content_md": project.seed_full_content_md,
                "seed_sources": project.seed_sources,
                "simulation_suggestions": project.simulation_suggestions,
                "entity_hints": project.entity_hints,
                "seed_metadata": project.seed_metadata,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 接口2：构建图谱 ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    接口2：根据project_id构建图谱
    
    请求（JSON）：
        {
            "project_id": "proj_xxxx",  // 必填，来自接口1
            "graph_name": "图谱名称",    // 可选
            "chunk_size": 1200,         // 可选，默认1200
            "chunk_overlap": 100,       // 可选，默认100
            "batch_size": 5             // 可选，默认5
        }
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "图谱构建任务已启动"
            }
        }
    """
    try:
        logger.info("=== 开始构建图谱 ===")
        
        # 检查配置（仅 cloud 模式需要 ZEP_API_KEY）
        if Config.ZEP_BACKEND == 'cloud' and not Config.ZEP_API_KEY:
            logger.error("配置错误: ZEP_API_KEY未配置")
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY未配置（cloud模式需要）"
            }), 500
        
        # 解析请求
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"请求参数: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "请提供 project_id"
            }), 400
        
        # 获取项目
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"项目不存在: {project_id}"
            }), 404
        
        # 检查项目状态
        force = data.get('force', False)  # 强制重新构建
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "项目尚未生成本体，请先调用 /ontology/generate"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "图谱正在构建中，请勿重复提交。如需强制重建，请添加 force: true",
                "task_id": project.graph_build_task_id
            }), 400
        
        # 如果强制重建，重置状态
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            old_graph_id = project.graph_id
            old_backend = project.graph_backend or Config.ZEP_BACKEND
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.graph_backend = None
            project.graph_provider = None
            project.graph_schema_version = None
            project.error = None
            if old_graph_id:
                try:
                    GraphBuilderService(backend=old_backend).delete_graph(old_graph_id)
                except Exception as exc:
                    logger.warning(f"强制重建前清理旧图谱失败: project_id={project_id}, graph_id={old_graph_id}, error={exc}")
        
        # 获取配置
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = int(data.get('chunk_size') or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = int(data.get('chunk_overlap') or Config.DEFAULT_CHUNK_OVERLAP)
        batch_size = max(1, int(data.get('batch_size') or Config.GRAPH_BUILD_BATCH_SIZE))
        
        # 更新项目配置
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        
        # 获取提取的文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "未找到提取的文本内容"
            }), 400
        
        # 获取本体
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "未找到本体定义"
            }), 400

        extraction_context = {
            "event_topic": project.search_query or project.name or graph_name,
            "simulation_requirement": project.simulation_requirement or "",
            "seed_summary": project.seed_summary_md or project.analysis_summary or "",
            "entity_hints": project.entity_hints or [],
        }
        
        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {graph_name}")
        logger.info(f"创建图谱构建任务: task_id={task_id}, project_id={project_id}")
        
        # 更新项目状态
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        # 启动后台任务
        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] 开始构建图谱...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message="初始化图谱构建服务..."
                )
                
                # 创建图谱构建服务
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY, backend=Config.ZEP_BACKEND)
                
                # 分块
                task_manager.update_task(
                    task_id,
                    message="文本分块中...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                
                # 创建图谱
                task_manager.update_task(
                    task_id,
                    message="创建Zep图谱...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                
                # 更新项目的graph_id
                project.graph_id = graph_id
                project.graph_backend = Config.ZEP_BACKEND
                project.graph_provider = "graphiti" if Config.ZEP_BACKEND == "graphiti" else "zep"
                project.graph_schema_version = "v1"
                ProjectManager.save_project(project)
                
                # 设置本体
                task_manager.update_task(
                    task_id,
                    message="设置本体定义...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                # 添加文本（progress_callback 签名是 (msg, progress_ratio)）
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                task_manager.update_task(
                    task_id,
                    message=f"开始添加 {total_chunks} 个文本块...",
                    progress=15
                )
                
                episode_uuids = builder.add_text_batches(
                    graph_id, 
                    chunks,
                    batch_size=batch_size,
                    progress_callback=add_progress_callback,
                    extraction_context=extraction_context,
                )
                
                # 等待Zep处理完成（查询每个episode的processed状态）
                task_manager.update_task(
                    task_id,
                    message="等待Zep处理数据...",
                    progress=55
                )
                
                def wait_progress_callback(msg, progress_ratio):
                    progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                
                # 获取图谱数据
                task_manager.update_task(
                    task_id,
                    message="获取图谱数据...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                
                # 更新项目状态
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}")
                
                # 完成
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="图谱构建完成",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                # 更新项目状态为失败
                build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"构建失败: {str(e)}",
                    error=traceback.format_exc()
                )
        
        # 启动后台线程
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "图谱构建任务已启动，请通过 /task/{task_id} 查询进度"
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 任务查询接口 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    查询任务状态
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": f"任务不存在: {task_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    列出所有任务
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== 图谱数据接口 ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    获取图谱数据（节点和边）
    """
    try:
        project, backend, error_response = _get_project_backend_or_404(graph_id)
        if error_response:
            return error_response

        if backend == 'cloud' and not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY未配置（cloud模式需要）"
            }), 500

        builder = GraphBuilderService(backend=backend)
        graph_data = builder.get_graph_data(graph_id)
        graph_data = TypeTranslationService.ensure_graph_data_translations(graph_data)
        
        return jsonify({
            "success": True,
            "data": graph_data
        })
        
    except Exception as e:
        if is_neo4j_auth_error(e):
            logger.error(f"获取图谱数据失败：{format_neo4j_auth_error(e)}")
            return jsonify({
                "success": False,
                "error": format_neo4j_auth_error(e)
            }), 503
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    删除Zep图谱
    """
    try:
        project, backend, error_response = _get_project_backend_or_404(graph_id)
        if error_response:
            return error_response

        if backend == 'cloud' and not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY未配置（cloud模式需要）"
            }), 500

        builder = GraphBuilderService(backend=backend)
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": f"图谱已删除: {graph_id}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
