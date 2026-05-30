"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: MiroFish/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv()

# Graphiti 需要 OPENAI_* 环境变量，从 LLM_* 映射
# 仅在未显式设置时才映射，避免覆盖用户的显式配置
if not os.environ.get('OPENAI_API_KEY') and os.environ.get('LLM_API_KEY'):
    os.environ['OPENAI_API_KEY'] = os.environ['LLM_API_KEY']
if not os.environ.get('OPENAI_BASE_URL') and os.environ.get('LLM_BASE_URL'):
    os.environ['OPENAI_BASE_URL'] = os.environ['LLM_BASE_URL']


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    LLM_BOOST_API_KEY = os.environ.get('LLM_BOOST_API_KEY')
    LLM_BOOST_BASE_URL = os.environ.get('LLM_BOOST_BASE_URL')
    LLM_BOOST_MODEL_NAME = os.environ.get('LLM_BOOST_MODEL_NAME')
    LLM_WEB_SEARCH_API_KEY = os.environ.get('LLM_WEB_SEARCH_API_KEY') or LLM_API_KEY
    LLM_WEB_SEARCH_BASE_URL = os.environ.get('LLM_WEB_SEARCH_BASE_URL') or LLM_BASE_URL
    LLM_WEB_SEARCH_MODEL = os.environ.get('LLM_WEB_SEARCH_MODEL') or LLM_MODEL_NAME
    LLM_WEB_SEARCH_STRATEGY = os.environ.get('LLM_WEB_SEARCH_STRATEGY', 'max')
    LLM_WEB_SEARCH_VALIDATE_LINKS = os.environ.get('LLM_WEB_SEARCH_VALIDATE_LINKS', 'true').lower() in {'1', 'true', 'yes', 'on'}
    REAL_ENTITY_BATCH_SIZE = int(os.environ.get('REAL_ENTITY_BATCH_SIZE', '30'))
    REAL_ENTITY_RESOLVE_CONCURRENCY = int(os.environ.get('REAL_ENTITY_RESOLVE_CONCURRENCY', '3'))

    # 联网搜索 provider 配置
    # 默认优先使用阿里百炼 OpenAI 兼容模式的 websearch 能力；博查仅在显式启用时使用。
    USE_BOCHA_WEB_SEARCH = os.environ.get('USE_BOCHA_WEB_SEARCH', 'false').lower() in {'1', 'true', 'yes', 'on'}
    WEB_SEARCH_PROVIDER = os.environ.get('WEB_SEARCH_PROVIDER', 'bailian').strip().lower()
    DEFAULT_WEB_SEARCH_PROVIDER = 'bocha' if USE_BOCHA_WEB_SEARCH else (WEB_SEARCH_PROVIDER or 'bailian')
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    ZEP_BACKEND = os.environ.get('ZEP_BACKEND', 'cloud')  # 'cloud' | 'graphiti'

    # 博查 Web Search 配置（仅在调用搜索 seed 时按需校验）
    BOCHA_API_KEY = os.environ.get('BOCHA_API_KEY')
    BOCHA_BASE_URL = os.environ.get('BOCHA_BASE_URL', 'https://api.bochaai.com/v1')
    BOCHA_WEB_SEARCH_ENDPOINT = os.environ.get('BOCHA_WEB_SEARCH_ENDPOINT', '/web-search')
    BOCHA_WEB_SEARCH_MAX_RESULTS = int(
        os.environ.get('BOCHA_WEB_SEARCH_MAX_RESULTS')
        or os.environ.get('BOCHA_DEFAULT_COUNT', '8')
    )
    BOCHA_WEB_SEARCH_TIMEOUT = int(
        os.environ.get('BOCHA_WEB_SEARCH_TIMEOUT')
        or os.environ.get('BOCHA_TIMEOUT_SECONDS', '30')
    )
    BOCHA_WEB_SEARCH_FRESHNESS = os.environ.get('BOCHA_WEB_SEARCH_FRESHNESS', 'twoMonths')
    BOCHA_WEB_SEARCH_RECENT_DAYS = int(os.environ.get('BOCHA_WEB_SEARCH_RECENT_DAYS', '60'))
    BOCHA_VALIDATE_LINKS = os.environ.get('BOCHA_VALIDATE_LINKS', 'true').lower() in {'1', 'true', 'yes', 'on'}
    BOCHA_LINK_CHECK_TIMEOUT = int(os.environ.get('BOCHA_LINK_CHECK_TIMEOUT', '5'))
    BOCHA_LINK_CHECK_MAX_BYTES = int(os.environ.get('BOCHA_LINK_CHECK_MAX_BYTES', '16384'))
    # 兼容早期实现中的内部命名
    BOCHA_DEFAULT_COUNT = BOCHA_WEB_SEARCH_MAX_RESULTS
    BOCHA_TIMEOUT_SECONDS = BOCHA_WEB_SEARCH_TIMEOUT

    # Graphiti / Neo4j 配置（本地部署时使用）
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = int(os.environ.get('DEFAULT_CHUNK_SIZE', '1200'))  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get('DEFAULT_CHUNK_OVERLAP', '100'))  # 默认重叠大小
    GRAPH_BUILD_BATCH_SIZE = int(os.environ.get('GRAPH_BUILD_BATCH_SIZE', '5'))  # 图谱构建批次大小
    GRAPH_BUILD_CONCURRENCY = int(os.environ.get('GRAPH_BUILD_CONCURRENCY', '3'))  # 图谱构建并发批次数
    GRAPH_BUILD_BATCH_DELAY_SECONDS = float(os.environ.get('GRAPH_BUILD_BATCH_DELAY_SECONDS', '0'))  # 批次节流延迟
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    REPORT_TOOL_CONCURRENCY = int(os.environ.get('REPORT_TOOL_CONCURRENCY', '3'))
    REPORT_SECTION_CONCURRENCY = int(os.environ.get('REPORT_SECTION_CONCURRENCY', '2'))
    SIMULATION_CONFIG_CONCURRENCY = int(os.environ.get('SIMULATION_CONFIG_CONCURRENCY', '3'))
    PROFILE_GENERATION_CONCURRENCY = int(os.environ.get('PROFILE_GENERATION_CONCURRENCY', '5'))
    
    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        # 根据后端类型验证配置
        if cls.ZEP_BACKEND == 'cloud':
            if not cls.ZEP_API_KEY:
                errors.append("ZEP_API_KEY 未配置（ZEP_BACKEND=cloud 时必需）")
        elif cls.ZEP_BACKEND == 'graphiti':
            if not all([cls.NEO4J_URI, cls.NEO4J_USER, cls.NEO4J_PASSWORD]):
                errors.append("Neo4j 配置不完整（ZEP_BACKEND=graphiti 时必需）")
        return errors
