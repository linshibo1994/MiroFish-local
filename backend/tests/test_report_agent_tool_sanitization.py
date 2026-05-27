import json

from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportContentSanitizer,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


STRUCTURED_TOOL_RESPONSE = (
    "我需要调用工具。"
    "<|tool_calls_section_begin|>"
    "<|tool_call_begin|>functions.panoramasearch:21<|tool_call_argument_begin|>"
    "{\"query\":\"关系庇护\",\"include_expired\":true}"
    "<|tool_call_end|>"
    "<|tool_call_begin|>functions.quicksearch:22<|tool_call_argument_begin|>"
    "{\"query\":\"驻点干部被收购点拉拢\",\"limit\":10}"
    "<|tool_call_end|>"
    "<|tool_calls_section_end|>"
)


def test_parse_structured_model_tool_calls():
    agent = ReportAgent.__new__(ReportAgent)
    calls = agent._parse_tool_calls(STRUCTURED_TOOL_RESPONSE)

    assert calls == [
        {
            "name": "panorama_search",
            "parameters": {"query": "关系庇护", "include_expired": True},
        },
        {
            "name": "quick_search",
            "parameters": {"query": "驻点干部被收购点拉拢", "limit": 10},
        },
    ]


def test_parse_rendered_structured_model_tool_calls():
    agent = ReportAgent.__new__(ReportAgent)
    response = (
        "<toolcallsection/begin/>"
        "<toolcallbegin/>functions.insightforge:33<toolcallargumentbegin/>"
        "{\"query\":\"公众认知\",\"report_context\":\"第三章\"}"
        "<toolcallend/>"
        "<toolcallbegin/>functions.interviewagents:34<toolcallargumentbegin/>"
        "{\"interview_topic\":\"监管效果\",\"max_agents\":5}"
        "<toolcallend/>"
        "<toolcallsection/end/>"
    )

    calls = agent._parse_tool_calls(response)

    assert calls == [
        {
            "name": "insight_forge",
            "parameters": {"query": "公众认知", "report_context": "第三章"},
        },
        {
            "name": "interview_agents",
            "parameters": {"interview_topic": "监管效果", "max_agents": 5},
        },
    ]


def test_report_content_sanitizer_removes_tool_protocol():
    content = (
        "Final Answer: 我需要继续调用工具获取数据。"
        "<|tool_calls_section_begin|>"
        "<|tool_call_begin|>functions.insightforge:1<|tool_call_argument_begin|>"
        "{\"query\":\"公众认知\"}"
        "<|tool_call_end|>"
        "<|tool_calls_section_end|>\n\n"
        "**公众信任变化**\n\n模拟显示，信任在后期出现损耗。"
    )

    cleaned = ReportContentSanitizer.clean_report_content(content)

    assert "tool_call" not in cleaned
    assert "functions." not in cleaned
    assert "Final Answer" not in cleaned
    assert "**公众信任变化**" in cleaned
    assert "模拟显示，信任在后期出现损耗。" in cleaned


def test_persisted_report_cleaning_does_not_truncate_mid_text_final_answer():
    content = (
        "# 报告\n\n"
        "正文第一段保留。\n\n"
        "这里讨论字符串 Final Answer: 只是模型协议示例，不应该截断前文。\n\n"
        "正文最后一段保留。"
    )

    cleaned = ReportContentSanitizer.clean_report_content(content)

    assert "正文第一段保留。" in cleaned
    assert "模型协议示例" in cleaned
    assert "正文最后一段保留。" in cleaned


def test_force_generation_sanitizes_structured_tool_protocol(monkeypatch):
    class FakeLLM:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, temperature=0.5, max_tokens=4096):
            self.calls += 1
            if self.calls <= 5:
                return "我需要更多数据，但暂时没有最终答案。"
            return (
                "Final Answer: 我需要立即调用工具获取模拟数据。"
                "<|tool_calls_section_begin|>"
                "<|tool_call_begin|>functions.insightforge:33<|tool_call_argument_begin|>"
                "{\"query\":\"公众认知分裂\"}"
                "<|tool_call_end|>"
                "<|tool_calls_section_end|>\n\n"
                "**制度信任损耗**\n\n公众开始质疑监管持续性。"
            )

    agent = ReportAgent.__new__(ReportAgent)
    agent.llm = FakeLLM()
    agent.report_logger = None
    agent.MAX_TOOL_CALLS_PER_SECTION = 4
    agent.simulation_requirement = "测试需求"
    agent._get_tools_description = lambda: "可用工具"
    agent._parse_tool_calls = lambda response: []

    content = agent._generate_section_react(
        section=ReportSection(title="公众认知"),
        outline=ReportOutline(title="报告", summary="摘要", sections=[]),
        previous_sections=[],
        progress_callback=None,
        section_index=1,
    )

    assert "tool_call" not in content
    assert "functions." not in content
    assert "Final Answer" not in content
    assert "**制度信任损耗**" in content


def test_agent_log_response_sanitizes_historical_section_content(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report_id = "report_dirty"
    report_dir = tmp_path / report_id
    report_dir.mkdir()
    log_path = report_dir / "agent_log.jsonl"
    dirty_content = (
        "## 第三章\n\n"
        "我需要立即调用工具获取模拟数据。"
        "<|tool_calls_section_begin|>"
        "<|tool_call_begin|>functions.interviewagents:34<|tool_call_argument_begin|>"
        "{\"interview_topic\":\"45天专项整治\"}"
        "<|tool_call_end|>"
        "<|tool_calls_section_end|>\n\n"
        "公众对监管持续性产生担忧。"
    )
    log_entry = {
        "action": "section_complete",
        "details": {"content": dirty_content, "content_length": len(dirty_content)},
    }
    log_path.write_text(json.dumps(log_entry, ensure_ascii=False) + "\n", encoding="utf-8")

    result = ReportManager.get_agent_log(report_id)

    content = result["logs"][0]["details"]["content"]
    assert "tool_call" not in content
    assert "functions." not in content
    assert "公众对监管持续性产生担忧。" in content


def test_generated_sections_sanitize_historical_markdown_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report_id = "report_dirty"
    report_dir = tmp_path / report_id
    report_dir.mkdir()
    section_path = report_dir / "section_01.md"
    section_path.write_text(
        "## 第一章\n\n"
        "我需要继续调用工具。"
        "<tool_call>{\"name\":\"quick_search\",\"parameters\":{\"query\":\"测试\"}}</tool_call>\n\n"
        "这是干净正文。",
        encoding="utf-8",
    )

    sections = ReportManager.get_generated_sections(report_id)

    assert len(sections) == 1
    assert "tool_call" not in sections[0]["content"]
    assert "这是干净正文。" in sections[0]["content"]


def test_save_report_sanitizes_meta_and_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report = Report(
        report_id="report_dirty",
        simulation_id="sim_1",
        graph_id="graph_1",
        simulation_requirement="测试需求",
        status=ReportStatus.COMPLETED,
        markdown_content=(
            "# 报告\n\n"
            "Final Answer: 我需要继续调用工具。"
            "<|tool_calls_section_begin|>"
            "<|tool_call_begin|>functions.quicksearch:1<|tool_call_argument_begin|>"
            "{\"query\":\"测试\"}"
            "<|tool_call_end|>"
            "<|tool_calls_section_end|>\n\n"
            "这是最终报告正文。"
        ),
    )

    ReportManager.save_report(report)

    meta_data = json.loads((tmp_path / "report_dirty" / "meta.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "report_dirty" / "full_report.md").read_text(encoding="utf-8")

    assert "tool_call" not in meta_data["markdown_content"]
    assert "Final Answer" not in meta_data["markdown_content"]
    assert "tool_call" not in markdown
    assert "这是最终报告正文。" in markdown
