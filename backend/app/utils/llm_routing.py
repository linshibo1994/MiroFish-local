"""
LLM 路由工具。

统一管理默认 LLM 与加速 LLM 的选择，避免各业务模块重复散落环境变量判断。
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from openai import OpenAI

from ..config import Config


@dataclass(frozen=True)
class LLMEndpoint:
    """OpenAI-compatible LLM 端点配置。"""

    api_key: str
    base_url: str
    model: str
    is_boost: bool = False


def get_default_llm_endpoint() -> LLMEndpoint:
    """返回默认 LLM 端点。"""
    if not Config.LLM_API_KEY:
        raise ValueError("LLM_API_KEY 未配置")
    return LLMEndpoint(
        api_key=Config.LLM_API_KEY,
        base_url=Config.LLM_BASE_URL,
        model=Config.LLM_MODEL_NAME,
        is_boost=False,
    )


def get_boost_llm_endpoint() -> Optional[LLMEndpoint]:
    """返回加速 LLM 端点；未完整配置时返回 None。"""
    if not all([Config.LLM_BOOST_API_KEY, Config.LLM_BOOST_BASE_URL, Config.LLM_BOOST_MODEL_NAME]):
        return None
    if _is_placeholder(Config.LLM_BOOST_API_KEY):
        return None
    return LLMEndpoint(
        api_key=Config.LLM_BOOST_API_KEY,
        base_url=Config.LLM_BOOST_BASE_URL,
        model=Config.LLM_BOOST_MODEL_NAME,
        is_boost=True,
    )


def get_preferred_llm_endpoint(prefer_boost: bool = True) -> LLMEndpoint:
    """优先返回加速 LLM；未配置加速时回退默认 LLM。"""
    if prefer_boost:
        boost = get_boost_llm_endpoint()
        if boost:
            return boost
    return get_default_llm_endpoint()


def create_openai_client(endpoint: Optional[LLMEndpoint] = None, prefer_boost: bool = True) -> OpenAI:
    """根据端点创建 OpenAI-compatible 客户端。"""
    endpoint = endpoint or get_preferred_llm_endpoint(prefer_boost=prefer_boost)
    return OpenAI(api_key=endpoint.api_key, base_url=endpoint.base_url)


def clamp_concurrency(value: Optional[int], default: int, minimum: int = 1, maximum: int = 16) -> int:
    """把并发数限制在安全范围内。"""
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _is_placeholder(value: str) -> bool:
    """识别示例配置中的占位符，避免误用无效加速 Key。"""
    normalized = str(value or "").strip().lower()
    return not normalized or normalized.startswith("your_") or normalized in {
        "your_boost_api_key",
        "your_boost_api_key_here",
        "your_api_key",
        "your_api_key_here",
    }


@contextmanager
def temporary_graphiti_llm_env(prefer_boost: bool = True) -> Iterator[LLMEndpoint]:
    """
    临时切换 Graphiti 使用的 LLM 环境变量。

    Graphiti 的 OpenAIGenericClient 从 OPENAI_* / GRAPHITI_LLM_MODEL 读取配置。
    该上下文只在调用方创建独立 Graphiti client 前使用，并在退出时恢复原值。
    """
    endpoint = get_preferred_llm_endpoint(prefer_boost=prefer_boost)
    keys = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "GRAPHITI_LLM_MODEL")
    old_values = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["OPENAI_API_KEY"] = endpoint.api_key
        os.environ["OPENAI_BASE_URL"] = endpoint.base_url
        os.environ["GRAPHITI_LLM_MODEL"] = endpoint.model
        yield endpoint
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
