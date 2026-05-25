"""
Step1 seed 分析服务
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from ..utils.llm_client import LLMClient
from .bocha_search_service import SearchSource


@dataclass
class SeedAnalysisResult:
    """seed 分析结果"""

    seed_summary_md: str
    simulation_suggestions: List[str] = field(default_factory=list)
    entity_hints: List[str] = field(default_factory=list)
    seed_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SeedAnalysisService:
    """基于搜索结果或文件文本生成 seed 摘要和后续模拟建议"""

    MAX_MATERIAL_LENGTH = 24000

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    def analyze_from_sources(
        self,
        sources: List[SearchSource],
        query: str,
        additional_context: Optional[str] = None,
    ) -> SeedAnalysisResult:
        source_dicts = [source.to_dict() if hasattr(source, "to_dict") else source for source in sources]
        material = self._build_search_material(source_dicts, query)
        return self._analyze(
            material=material,
            input_mode="web_search",
            topic=query,
            source_count=len(source_dicts),
            additional_context=additional_context,
        )

    def analyze_from_text(
        self,
        text: str,
        topic: str = "上传文档",
        additional_context: Optional[str] = None,
    ) -> SeedAnalysisResult:
        material = (text or "").strip()
        return self._analyze(
            material=material,
            input_mode="file_upload",
            topic=topic,
            source_count=1 if material else 0,
            additional_context=additional_context,
        )

    def _analyze(
        self,
        material: str,
        input_mode: str,
        topic: str,
        source_count: int,
        additional_context: Optional[str],
    ) -> SeedAnalysisResult:
        clean_material = (material or "").strip()
        if not clean_material:
            return SeedAnalysisResult(
                seed_summary_md="## Seed 摘要\n\n暂无可分析的材料。",
                simulation_suggestions=[],
                entity_hints=[],
                seed_metadata={
                    "input_mode": input_mode,
                    "source_count": source_count,
                    "analysis_mode": "fallback",
                },
            )

        try:
            result = self._analyze_with_llm(
                material=clean_material[: self.MAX_MATERIAL_LENGTH],
                input_mode=input_mode,
                topic=topic,
                additional_context=additional_context,
            )
            result.seed_metadata.update({
                "input_mode": input_mode,
                "source_count": source_count,
                "analysis_mode": "llm",
            })
            return result
        except Exception as exc:
            fallback = self._fallback_analysis(clean_material, input_mode, topic, source_count)
            fallback.seed_metadata["llm_error"] = str(exc)
            return fallback

    def _analyze_with_llm(
        self,
        material: str,
        input_mode: str,
        topic: str,
        additional_context: Optional[str],
    ) -> SeedAnalysisResult:
        client = self.llm_client or LLMClient()
        prompt = f"""请只基于给定材料生成 Step1 seed 分析，禁止引入材料之外的事实。

输出 JSON，字段：
- seed_summary_md: Markdown 字符串，概括关键事实、主体、争议/变量；如果材料不足，请明确说明不足。
- simulation_suggestions: 2-3 条可用于后续社会模拟需求的中文建议，每条必须来自材料可支撑的信息。
- entity_hints: 可能进入图谱的主体名称列表，必须是材料中原文出现过的人、组织、机构、平台或媒体名称。

输入类型：{input_mode}
主题：{topic}
额外说明：{additional_context or "无"}

材料：
{material}
"""
        data = client.chat_json(
            messages=[
                {"role": "system", "content": "你是严谨的中文资料分析助手，只能依据输入材料作答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1800,
        )

        summary = str(data.get("seed_summary_md") or "").strip()
        suggestions = self._clean_string_list(data.get("simulation_suggestions"), limit=3)
        hints = self._filter_entity_hints(
            self._clean_string_list(data.get("entity_hints"), limit=30),
            material,
        )

        if not summary:
            raise ValueError("LLM 未返回 seed_summary_md")

        return SeedAnalysisResult(
            seed_summary_md=summary,
            simulation_suggestions=suggestions[:3],
            entity_hints=hints,
            seed_metadata={},
        )

    def _fallback_analysis(
        self,
        material: str,
        input_mode: str,
        topic: str,
        source_count: int,
    ) -> SeedAnalysisResult:
        excerpts = self._pick_excerpts(material)
        entity_hints = self._extract_entity_hints(material)
        summary_lines = [
            "## Seed 摘要",
            "",
            f"- 输入方式：{input_mode}",
            f"- 主题：{topic or '未提供'}",
            f"- 可用来源数：{source_count}",
            "",
            "## 材料摘录",
        ]
        summary_lines.extend([f"- {excerpt}" for excerpt in excerpts] or ["- 材料内容较少，暂无法提炼稳定摘录。"])

        suggestions = self._fallback_suggestions(topic, entity_hints)
        return SeedAnalysisResult(
            seed_summary_md="\n".join(summary_lines),
            simulation_suggestions=suggestions,
            entity_hints=entity_hints,
            seed_metadata={
                "input_mode": input_mode,
                "source_count": source_count,
                "analysis_mode": "fallback",
            },
        )

    @staticmethod
    def _build_search_material(sources: List[Dict[str, Any]], query: str) -> str:
        lines = [f"检索词：{query}", ""]
        for idx, source in enumerate(sources, 1):
            title = source.get("title") or "未命名来源"
            url = source.get("url") or ""
            snippet = source.get("snippet") or ""
            summary = source.get("summary") or ""
            site_name = source.get("site_name") or ""
            date_published = source.get("date_published") or ""
            lines.append(f"### 来源 {idx}: {title}")
            if site_name:
                lines.append(f"站点：{site_name}")
            if date_published:
                lines.append(f"发布时间：{date_published}")
            if url:
                lines.append(f"URL：{url}")
            if snippet:
                lines.append(f"摘要片段：{snippet}")
            if summary:
                lines.append(f"搜索摘要：{summary}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _clean_string_list(value: Any, limit: int) -> List[str]:
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text)
            if len(cleaned) >= limit:
                break
        return cleaned

    @staticmethod
    def _filter_entity_hints(hints: Iterable[str], material: str) -> List[str]:
        filtered = []
        for hint in hints:
            if hint and hint in material and hint not in filtered:
                filtered.append(hint)
        return filtered

    @classmethod
    def _extract_entity_hints(cls, material: str) -> List[str]:
        patterns = [
            r"[\u4e00-\u9fffA-Za-z0-9·（）()]{2,30}(?:公司|集团|大学|学院|政府|委员会|协会|机构|平台|媒体|日报|时报|新闻|法院|部门|医院|学校)",
            r"\b[A-Z][A-Za-z0-9&.\- ]{1,40}(?:Inc|Ltd|LLC|University|College|Agency|Court|Media|News|Platform)\b",
        ]
        hints: List[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, material):
                candidate = match.strip(" ，。；;:：、\n\t")
                if 2 <= len(candidate) <= 40 and candidate not in hints:
                    hints.append(candidate)
                if len(hints) >= 20:
                    return hints
        return hints

    @staticmethod
    def _pick_excerpts(material: str) -> List[str]:
        compact = re.sub(r"\s+", " ", material).strip()
        if not compact:
            return []
        sentences = re.split(r"(?<=[。！？.!?])\s+", compact)
        excerpts = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 12:
                continue
            excerpts.append(sentence[:220])
            if len(excerpts) >= 5:
                break
        if not excerpts and compact:
            excerpts.append(compact[:220])
        return excerpts

    @staticmethod
    def _fallback_suggestions(topic: str, entity_hints: List[str]) -> List[str]:
        subject = topic or "当前材料"
        if entity_hints:
            joined = "、".join(entity_hints[:3])
            return [
                f"围绕“{subject}”，模拟 {joined} 等主体的信息发布、回应与互动路径。",
                f"比较“{subject}”中不同主体在事实披露、立场表达和传播节奏上的影响差异。",
                f"追踪“{subject}”相关信息在关键主体之间扩散、澄清或争议升级的过程。",
            ]
        return [
            f"围绕“{subject}”，模拟材料中已出现主体的信息发布、回应与互动路径。",
            f"比较“{subject}”中不同主体在事实披露、立场表达和传播节奏上的影响差异。",
        ]
