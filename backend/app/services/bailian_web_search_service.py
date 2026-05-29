"""
阿里百炼 WebSearch 服务封装
"""

import json
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .bocha_search_service import SearchSource


logger = get_logger("mirofish.bailian_web_search")


class BailianWebSearchService:
    """通过百炼 OpenAI 兼容模式调用模型联网搜索并规范化来源。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.api_key = api_key or Config.LLM_WEB_SEARCH_API_KEY
        self.base_url = base_url or Config.LLM_WEB_SEARCH_BASE_URL
        self.model = model or Config.LLM_WEB_SEARCH_MODEL
        self.client = client

    def search(
        self,
        query: str,
        count: Optional[int] = None,
        freshness: Optional[str] = None,
        summary: bool = True,
    ) -> List[SearchSource]:
        """执行百炼联网搜索，并返回统一来源结构。"""
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("搜索关键词不能为空")
        if not self.api_key:
            raise ValueError("LLM_WEB_SEARCH_API_KEY/LLM_API_KEY 未配置")

        requested_count = max(1, min(int(count or Config.BOCHA_WEB_SEARCH_MAX_RESULTS), 20))
        client = self.client or OpenAI(api_key=self.api_key, base_url=self.base_url)
        search_options = {
            "forced_search": True,
            "search_strategy": Config.LLM_WEB_SEARCH_STRATEGY,
        }
        freshness_days = self._freshness_to_days(freshness)
        if freshness_days:
            search_options["freshness"] = freshness_days

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是严谨的联网资料检索助手。必须基于联网搜索结果返回可公开引用的网页来源；"
                        "禁止编造事实、标题或链接。"
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(clean_query, requested_count, freshness, summary),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            extra_body={
                "enable_search": True,
                "search_options": search_options,
            },
        )
        raw_text = self._extract_response_text(response)
        sources = self.parse_sources(raw_text)
        return sources[:requested_count]

    @staticmethod
    def _build_prompt(query: str, count: int, freshness: Optional[str], summary: bool) -> str:
        freshness_hint = f"时间范围偏好：{freshness}" if freshness else "时间范围偏好：优先近期、权威、可访问来源"
        summary_hint = "每条来源需要提供简短摘要。" if summary else "每条来源只需提供摘要片段。"
        return f"""请联网搜索并围绕关键词整理可引用来源。

关键词：{query}
来源数量：最多 {count} 条
{freshness_hint}
{summary_hint}

请只输出 JSON，格式：
{{
  "sources": [
    {{
      "title": "网页标题",
      "url": "https://...",
      "snippet": "原网页或搜索结果中的关键片段",
      "summary": "基于该来源的简短中文摘要",
      "site_name": "站点名称",
      "date_published": "YYYY-MM-DD 或空字符串"
    }}
  ]
}}

要求：
- sources 必须来自真实联网搜索结果。
- url 必须是 http 或 https 开头的完整链接。
- 不确定发布时间时 date_published 返回空字符串。
"""

    @classmethod
    def parse_sources(cls, raw_text: str) -> List[SearchSource]:
        """解析模型返回的 JSON 来源列表。"""
        data = cls._loads_json(raw_text)
        raw_sources = data.get("sources") or data.get("results") or []
        if not isinstance(raw_sources, list):
            return []

        sources: List[SearchSource] = []
        seen_urls = set()
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "").strip()
            if not cls._is_valid_http_url(url) or url in seen_urls:
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            sources.append(
                SearchSource(
                    title=title or url,
                    url=url,
                    snippet=str(item.get("snippet") or item.get("content") or "").strip(),
                    summary=str(item.get("summary") or "").strip(),
                    site_name=str(item.get("site_name") or item.get("siteName") or "").strip(),
                    date_published=str(
                        item.get("date_published")
                        or item.get("datePublished")
                        or item.get("published_at")
                        or ""
                    ).strip(),
                    source_type="web",
                )
            )
            seen_urls.add(url)
        return sources

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        try:
            return response.choices[0].message.content or ""
        except Exception:
            logger.warning("百炼联网搜索响应结构异常: %s", response)
            return ""

    @staticmethod
    def _loads_json(raw_text: str) -> Dict[str, Any]:
        clean_text = (raw_text or "").strip()
        if not clean_text:
            return {}
        try:
            parsed = json.loads(clean_text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", clean_text)
            if not match:
                return {}
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _is_valid_http_url(url: str) -> bool:
        return url.startswith("http://") or url.startswith("https://")

    @staticmethod
    def _freshness_to_days(freshness: Optional[str]) -> Optional[int]:
        if freshness is None:
            return None
        if isinstance(freshness, int):
            return freshness if freshness > 0 else None
        clean_value = str(freshness).strip()
        if not clean_value:
            return None
        if clean_value.isdigit():
            days = int(clean_value)
            return days if days > 0 else None
        return {
            "oneDay": 1,
            "oneWeek": 7,
            "oneMonth": 30,
            "twoMonths": 60,
            "threeMonths": 90,
            "oneYear": 365,
        }.get(clean_value)
