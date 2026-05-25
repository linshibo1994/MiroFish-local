"""
博查 Web Search 服务封装
"""

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from ..config import Config
from ..utils.logger import get_logger


logger = get_logger("mirofish.bocha_search")


@dataclass
class SearchSource:
    """统一的搜索来源结构"""

    title: str
    url: str
    snippet: str = ""
    summary: str = ""
    site_name: str = ""
    date_published: str = ""
    source_type: str = "web"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BochaSearchService:
    """调用博查 Web Search API 并规范化搜索结果"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[int] = None,
        validate_links: Optional[bool] = None,
    ):
        self.api_key = api_key or Config.BOCHA_API_KEY
        self.base_url = (base_url or Config.BOCHA_BASE_URL).rstrip("/")
        self.endpoint = endpoint or Config.BOCHA_WEB_SEARCH_ENDPOINT
        if not self.endpoint.startswith("/"):
            self.endpoint = f"/{self.endpoint}"
        self.timeout = timeout or Config.BOCHA_WEB_SEARCH_TIMEOUT
        self.validate_links = Config.BOCHA_VALIDATE_LINKS if validate_links is None else validate_links

    def search(
        self,
        query: str,
        count: Optional[int] = None,
        freshness: str = "noLimit",
        summary: bool = True,
    ) -> List[SearchSource]:
        """执行网页搜索并返回标准来源列表"""
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("搜索关键词不能为空")
        if not self.api_key:
            raise ValueError("BOCHA_API_KEY 未配置")

        result_count = count or Config.BOCHA_WEB_SEARCH_MAX_RESULTS
        result_count = max(1, min(int(result_count), 50))
        payload = {
            "query": clean_query,
            "freshness": freshness or "noLimit",
            "summary": bool(summary),
            "count": result_count,
        }

        response_data = self._post_json(payload)
        sources = self.parse_sources(response_data)
        return self._filter_live_sources(sources) if self.validate_links else sources

    def _post_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送 JSON POST 请求"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}{self.endpoint}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"博查搜索请求失败: HTTP {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"博查搜索网络请求失败: {exc.reason}") from exc

        if not resp_body:
            return {}
        return json.loads(resp_body)

    @classmethod
    def parse_sources(cls, response_data: Dict[str, Any]) -> List[SearchSource]:
        """从博查响应的 data.webPages.value[] 中解析标准来源"""
        data = response_data.get("data", response_data) if isinstance(response_data, dict) else {}
        web_pages = data.get("webPages", {}) if isinstance(data, dict) else {}
        values = web_pages.get("value", []) if isinstance(web_pages, dict) else []

        sources: List[SearchSource] = []
        for item in values:
            if not isinstance(item, dict):
                continue

            url = str(item.get("url") or "").strip()
            title = str(item.get("name") or item.get("title") or "").strip()
            if not cls._is_valid_http_url(url):
                continue

            sources.append(
                SearchSource(
                    title=title or url,
                    url=url,
                    snippet=str(item.get("snippet") or "").strip(),
                    summary=str(item.get("summary") or "").strip(),
                    site_name=str(item.get("siteName") or item.get("site_name") or "").strip(),
                    date_published=str(item.get("datePublished") or item.get("date_published") or "").strip(),
                )
            )

        return sources

    def _filter_live_sources(self, sources: List[SearchSource]) -> List[SearchSource]:
        """过滤空链接、重复链接、失效链接和明显已删除页面。"""
        filtered: List[SearchSource] = []
        seen_urls = set()

        for source in sources:
            normalized_url = self._normalize_url(source.url)
            if not normalized_url:
                logger.info(f"过滤博查来源：URL 为空或非法 title={source.title}")
                continue
            if normalized_url in seen_urls:
                logger.info(f"过滤博查来源：重复 URL url={normalized_url}")
                continue
            if self._looks_deleted_from_metadata(source):
                logger.info(f"过滤博查来源：摘要显示已删除或不存在 url={normalized_url}")
                continue

            source.url = normalized_url
            if not self._is_live_source(source):
                logger.info(f"过滤博查来源：链接不可访问或页面失效 url={normalized_url}")
                continue

            seen_urls.add(normalized_url)
            filtered.append(source)

        return filtered

    def _is_live_source(self, source: SearchSource) -> bool:
        """通过轻量请求确认链接仍然可访问，且页面内容不提示已删除。"""
        try:
            status, body = self._request_source_preview(source.url, method="HEAD")
            if status in {405, 501}:
                status, body = self._request_source_preview(source.url, method="GET")
            elif 200 <= status < 400:
                _, body = self._request_source_preview(source.url, method="GET")
        except Exception as exc:
            logger.info(f"过滤博查来源：链接检查异常 url={source.url}, error={exc}")
            return False

        if status < 200 or status >= 400:
            return False
        if self._looks_deleted_from_body(body):
            return False
        return True

    def _request_source_preview(self, url: str, method: str = "GET") -> tuple[int, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MiroFishBot/1.0; +https://mirofish.local)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if method == "GET":
            headers["Range"] = f"bytes=0-{max(Config.BOCHA_LINK_CHECK_MAX_BYTES - 1, 0)}"

        req = request.Request(url=url, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=Config.BOCHA_LINK_CHECK_TIMEOUT) as resp:
                status = getattr(resp, "status", resp.getcode())
                body = ""
                if method == "GET":
                    raw_body = resp.read(Config.BOCHA_LINK_CHECK_MAX_BYTES)
                    body = raw_body.decode("utf-8", errors="ignore")
                return status, body
        except error.HTTPError as exc:
            body = ""
            if method == "GET":
                raw_body = exc.read(Config.BOCHA_LINK_CHECK_MAX_BYTES)
                body = raw_body.decode("utf-8", errors="ignore")
            return exc.code, body

    @classmethod
    def _normalize_url(cls, url: str) -> str:
        clean_url = (url or "").strip()
        if not cls._is_valid_http_url(clean_url):
            return ""
        parsed = parse.urlsplit(clean_url)
        return parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))

    @staticmethod
    def _is_valid_http_url(url: str) -> bool:
        if not url:
            return False
        parsed = parse.urlsplit(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @classmethod
    def _looks_deleted_from_metadata(cls, source: SearchSource) -> bool:
        text = " ".join([source.title, source.snippet, source.summary]).strip()
        return cls._contains_deleted_marker(text)

    @classmethod
    def _looks_deleted_from_body(cls, body: str) -> bool:
        if not body:
            return False
        text = re.sub(r"\s+", " ", body[: Config.BOCHA_LINK_CHECK_MAX_BYTES]).strip()
        return cls._contains_deleted_marker(text)

    @staticmethod
    def _contains_deleted_marker(text: str) -> bool:
        if not text:
            return False

        lowered = text.lower()
        deleted_patterns = [
            "404 not found",
            "page not found",
            "not found",
            "deleted",
            "gone",
            "页面不存在",
            "网页不存在",
            "文件不存在",
            "资源不存在",
            "内容不存在",
            "该内容已被删除",
            "文章已删除",
            "页面已删除",
            "文件已删除",
            "您访问的页面不存在",
            "抱歉，您访问的页面不存在",
            "很抱歉，您访问的页面不存在",
        ]
        return any(pattern in lowered for pattern in deleted_patterns)
