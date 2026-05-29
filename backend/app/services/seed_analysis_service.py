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
    """基于搜索结果或文件文本生成事件摘要和后续模拟建议"""

    MAX_MATERIAL_LENGTH = 24000
    WEB_SEARCH_SUMMARY_TEMPLATE = """联网搜索材料需要整理成一份可直接作为“完整事件内容”的中文 Markdown 文档，风格参考深度新闻全记录：
1. 标题使用“# 事件/主题全记录”，下设“事件概述”先给出时间、地点、核心主体、关键结果。
2. 按时间线拆成若干阶段，优先使用“## 一、...”和“### 阶段/争议/影响”组织。
3. 单独提炼关键人物、组织机构、产品/技术参数、资本/政策/供应链、舆论争议、官方回应等模块；有结构化数据时使用 Markdown 表格。
4. 每个事实尽量保留可追溯的时间、主体、动作、结果，避免空泛评价。
5. 末尾给出“总结”或“深远影响”，从个人/企业、产业、政府/监管、舆论传播等角度归纳规律。
6. 若搜索材料含来源 URL，末尾保留“参考来源”列表；不得编造材料外的新来源。"""
    FILE_UPLOAD_SUMMARY_TEMPLATE = """上传文件材料只需要生成辅助摘要：提炼核心事实、主要主体、争议变量和后续推演方向即可；完整展示和图谱抽取会使用上传文件解析出的原文。"""

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
        if input_mode == "web_search":
            return self._analyze_web_search_with_llm(
                material=material,
                topic=topic,
                additional_context=additional_context,
            )

        client = self.llm_client or LLMClient()
        style_template = (
            self.WEB_SEARCH_SUMMARY_TEMPLATE
            if input_mode == "web_search"
            else self.FILE_UPLOAD_SUMMARY_TEMPLATE
        )
        prompt = f"""请只基于给定材料生成 Step1 seed 分析，禁止引入材料之外的事实。

输出 JSON，字段：
- seed_summary_md: Markdown 字符串；如果是联网搜索输入，必须整理成可直接展示和后续图谱抽取使用的完整事件文档；如果是上传文件输入，生成辅助摘要即可。材料不足时请明确说明不足。
- simulation_suggestions: 2-3 条可用于后续社会模拟需求的中文建议，每条必须来自材料可支撑的信息。
- entity_hints: 可能进入图谱的主体名称列表，必须是材料中原文出现过的人、组织、机构、平台或媒体名称。

输入类型：{input_mode}
主题：{topic}
额外说明：{additional_context or "无"}
整理模板：
{style_template}

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

    def _analyze_web_search_with_llm(
        self,
        material: str,
        topic: str,
        additional_context: Optional[str],
    ) -> SeedAnalysisResult:
        """联网搜索场景生成完整 Markdown 文档。

        不把长 Markdown 放进 JSON 字符串，避免模型输出被截断后触发 JSON 解析失败。
        """
        client = self.llm_client or LLMClient()
        summary_prompt = f"""请只基于给定联网搜索材料，整理生成一份可直接作为前端“完整事件内容”展示、也可用于后续图谱实体抽取的中文 Markdown 完整文档。

硬性要求：
- 只输出 Markdown 正文，不要输出 JSON，不要包裹代码块。
- 禁止引入材料之外的事实；材料不足或来源可疑时必须在文档中说明。
- 文档要像深度新闻全记录，而不是简单摘录搜索结果。
- 保留关键时间、主体、动作、结果、争议、官方回应、影响和风险。
- 能表格化的信息使用 Markdown 表格。

主题：{topic}
额外说明：{additional_context or "无"}
整理模板：
{self.WEB_SEARCH_SUMMARY_TEMPLATE}

联网搜索材料：
{material}
"""
        summary = client.chat(
            messages=[
                {"role": "system", "content": "你是严谨的中文资料整理助手，只能依据输入材料生成结构化 Markdown 文档。"},
                {"role": "user", "content": summary_prompt},
            ],
            temperature=0.2,
            max_tokens=5000,
        ).strip()

        if not summary:
            raise ValueError("LLM 未返回联网搜索整理文档")

        suggestions, hints = self._generate_web_search_auxiliary(
            client=client,
            summary=summary,
            material=material,
            topic=topic,
        )

        if not suggestions:
            suggestions = self._fallback_suggestions(topic, hints)
        if not hints:
            hints = self._extract_entity_hints(f"{summary}\n{material}")

        return SeedAnalysisResult(
            seed_summary_md=summary,
            simulation_suggestions=suggestions[:3],
            entity_hints=self._filter_entity_hints(hints, f"{summary}\n{material}")[:30],
            seed_metadata={},
        )

    def _generate_web_search_auxiliary(
        self,
        client: LLMClient,
        summary: str,
        material: str,
        topic: str,
    ) -> tuple[List[str], List[str]]:
        """基于已生成文档提取短建议和实体提示，失败时交给调用方兜底。"""
        try:
            data = client.chat_json(
                messages=[
                    {"role": "system", "content": "你是严谨的信息抽取助手，只返回 JSON。"},
                    {
                        "role": "user",
                        "content": f"""请基于以下整理文档返回 JSON：
{{
  "simulation_suggestions": ["2-3条中文推演建议"],
  "entity_hints": ["材料原文出现过的人、组织、机构、平台或媒体名称"]
}}

要求：
- simulation_suggestions 必须适合社会传播推演。
- entity_hints 不超过30个，必须来自文档或材料原文。

主题：{topic}
整理文档：
{summary[:12000]}
""",
                    },
                ],
                temperature=0.2,
                max_tokens=1200,
            )
            suggestions = self._clean_string_list(data.get("simulation_suggestions"), limit=3)
            hints = self._filter_entity_hints(
                self._clean_string_list(data.get("entity_hints"), limit=30),
                f"{summary}\n{material}",
            )
            return suggestions, hints
        except Exception:
            return [], []

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
