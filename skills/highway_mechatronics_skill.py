from rag.retriever import search_chunks


def search_highway_standard(query: str) -> str:
    chunks = search_chunks(query, include_standards=True, limit=5)
    if not chunks:
        return "当前标准库未找到依据。"
    return "\n\n".join(c["content"][:500] for c in chunks)


def generate_site_test_record(item: str = "测试项目") -> str:
    return f"""# 现场测试记录

- 项目名称：
- 项目地点：
- 日期：
- 天气：
- 参与人员：
- 设备名称：
- 设备编号：
- 测试项目：{item}
- 测试仪器：
- 测试方法：
- 测试结果：
- 是否合格：
- 存在问题：
- 整改建议：
- 备注：
"""


def explain_test_method(item: str) -> str:
    return f"请先在行业标准库导入并索引相关标准。第一阶段可使用关键词查询：{item}"


def generate_quality_inspection_table(item: str = "分项工程") -> str:
    return f"| 检查项目 | 规定值或允许偏差 | 检查方法 | 检查结果 | 评定 |\n|---|---|---|---|---|\n| {item} | 待填写 | 按标准 | 待填写 | 待评定 |"


def generate_bid_technical_response(topic: str = "机电工程质量保证") -> str:
    return f"本项目将围绕{topic}建立质量管理、测试验证、资料归档和整改闭环机制，具体条款需结合招标文件和标准库依据完善。"


def generate_acceptance_checklist(topic: str = "机电工程") -> str:
    return f"- {topic}设备安装检查\n- 单机调试记录\n- 系统联调记录\n- 质量检验评定资料\n- 竣工资料与验收签认"


compare_project_with_standard = search_highway_standard
generate_rectification_report = generate_bid_technical_response
generate_test_report_outline = generate_acceptance_checklist
generate_project_quality_plan = generate_bid_technical_response
generate_construction_technical_plan = generate_bid_technical_response
generate_equipment_debug_record = generate_site_test_record