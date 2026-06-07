def defect_types(defects):
    values = []
    for defect in defects:
        defect_type = str(defect.get("type", "")).strip()
        if defect_type and defect_type not in values:
            values.append(defect_type)
    return values


def defect_type_summary(defects):
    values = defect_types(defects)
    return "、".join(values) if values else "未检出明显隐患"


def priority_defect(defects):
    priority = ["渗水", "脱落", "裂缝", "空鼓"]
    values = defect_types(defects)
    for item in priority:
        if any(item in value for value in values):
            return item
    return values[0] if values else "无明显隐患"


def has_extension(row):
    return "有" in str(row.get("has_extension", ""))


def render_template(template, row, defects):
    return template.format(
        material=row.get("material", "未知"),
        floor=row.get("floor", "未知"),
        extension=row.get("has_extension", "未知"),
        defects=defect_type_summary(defects),
        priority_defect=priority_defect(defects),
    )


def build_report_task_pool(row, defects):
    pool = [
        ("standard_report", "生成一份综合巡检报告，覆盖巡检结论、主要风险和处置建议。"),
        ("management_report", "面向住建管理人员生成巡检参考意见，突出监管记录、复核重点和后续处置。"),
        ("public_report", "面向普通用户生成通俗易懂的巡检说明，说明当前风险和建议上报方式。"),
        ("review_report", "生成现场复核建议，重点说明需要复查的部位、依据和注意事项。"),
        ("maintenance_report", "生成后续维护建议，重点说明日常巡查、维修和跟踪观察要求。"),
    ]

    if defects:
        pool.extend(
            [
                ("risk_report", "围绕{defects}隐患生成风险分析报告，说明处置优先级和潜在影响。"),
                ("defect_report", "针对{priority_defect}等隐患生成专项巡检结论和处置建议。"),
                ("repair_report", "生成维修处置建议，说明如何复核、修复和跟踪{defects}隐患。"),
            ]
        )
    else:
        pool.extend(
            [
                ("no_defect_report", "生成未检出明显隐患场景下的巡检结论，强调周期性复查和记录留存。"),
                ("low_risk_report", "生成低风险巡检说明，说明当前结论和后续常规维护重点。"),
            ]
        )

    if has_extension(row):
        pool.append(("extension_report", "围绕疑似加层情况生成合规性复核建议和管理处置意见。"))

    material_text = str(row.get("material", ""))
    if "Glass" in material_text or "玻璃" in material_text:
        pool.append(("material_report", "针对玻璃幕墙类外立面生成专项巡检报告。"))
    elif "Stone" in material_text or "石" in material_text:
        pool.append(("material_report", "针对石材干挂类外立面生成专项巡检报告。"))
    elif "Coating" in material_text or "涂" in material_text:
        pool.append(("material_report", "针对涂料类外立面生成专项巡检报告。"))

    return pool


def build_question_pool(row, defects):
    pool = [
        ("summary", "请给出该建筑外立面的巡检结论与后续复核建议。"),
        ("summary", "从住建管理角度看，本次检测结果应如何记录和处置？"),
        ("summary", "该建筑的材质为{material}、楼层为{floor}，巡检结论应如何表述？"),
        ("risk", "该建筑是否需要安排现场复核？请说明判断依据。"),
        ("risk", "本次检测结果中最需要关注的风险是什么？为什么？"),
        ("maintenance", "后续日常巡检应重点关注哪些部位或现象？"),
        ("maintenance", "请给出适合普通用户理解的安全提示和上报建议。"),
    ]

    if defects:
        pool.extend(
            [
                ("defect_priority", "图中主要风险为{defects}，应如何优先处置？"),
                ("defect_priority", "如果只能先处理一类隐患，是否应优先处理{priority_defect}？为什么？"),
                ("defect_repair", "针对{defects}隐患，后续维修和复查应关注哪些环节？"),
                ("defect_risk", "该隐患可能带来哪些外立面安全或耐久性风险？"),
                ("defect_review", "现场复核时应如何确认{defects}隐患的范围和成因？"),
                ("defect_review", "如果该隐患持续扩大，应采取哪些升级处置措施？"),
            ]
        )
    else:
        pool.extend(
            [
                ("no_defect", "当前未检出明显隐患，后续巡检应重点关注什么？"),
                ("no_defect", "未发现明显隐患时，是否还需要定期复查？请说明原因。"),
                ("no_defect", "该建筑当前风险较低，住建管理记录中应如何表述？"),
                ("no_defect", "未检出隐患时，普通用户是否仍需要保留巡检记录？为什么？"),
            ]
        )

    if has_extension(row):
        pool.extend(
            [
                ("extension", "检测结果显示存在加层，后续合规性核查应关注什么？"),
                ("extension", "加层情况会对巡检结论和管理建议产生什么影响？"),
                ("extension", "针对疑似加层，住建管理部门应如何进一步核验？"),
            ]
        )
    else:
        pool.extend(
            [
                ("extension", "检测结果显示无加层，报告中还需要提示哪些常规巡检事项？"),
                ("extension", "无加层情况下，外立面维护重点应放在哪些方面？"),
            ]
        )

    material_text = str(row.get("material", ""))
    if "Glass" in material_text or "玻璃" in material_text:
        pool.extend(
            [
                ("material", "玻璃幕墙类外立面后续巡检应重点关注哪些安全问题？"),
                ("material", "针对玻璃幕墙材质，如何判断是否需要专项检查？"),
            ]
        )
    elif "Stone" in material_text or "石" in material_text:
        pool.extend(
            [
                ("material", "石材干挂类外立面后续巡检应重点关注哪些安全问题？"),
                ("material", "针对石材饰面，如何判断是否存在脱落风险？"),
            ]
        )
    elif "Coating" in material_text or "涂" in material_text:
        pool.extend(
            [
                ("material", "涂料类外立面后续巡检应重点关注哪些老化现象？"),
                ("material", "针对涂料外墙，如何判断渗水或开裂风险？"),
            ]
        )

    return pool


