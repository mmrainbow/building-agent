"""外立面材质名称标准化。"""

MATERIAL_ZH_MAP = {
    "Unknown1": "未知材质",
    "Unknown2": "未知材质",
    "Unknown3": "未知材质",
    "Unknown4": "未知材质",
    "Stone Hanging": "干挂石材",
    "Mortar": "砂浆",
    "Glass Curtain Wall": "玻璃幕墙",
    "Real Stone Paint": "真石漆",
    "Coating": "涂料",
    "Aluminum Plate": "铝板",
    "Face Brick": "面砖",
    "Mosaic": "马赛克",
}


def material_to_zh(value: str | None) -> str:
    if not value:
        return "未知"
    parts = []
    for raw in str(value).split(","):
        item = raw.strip()
        low_confidence = "(low confidence)" in item
        key = item.replace("(low confidence)", "").strip()
        translated = MATERIAL_ZH_MAP.get(key, key or "未知")
        if low_confidence and translated != "未知材质":
            translated = f"{translated}（低置信度）"
        parts.append(translated)
    return "、".join(dict.fromkeys(p for p in parts if p)) or "未知"


def replace_material_terms(text: str | None) -> str:
    if not text:
        return ""
    result = str(text)
    for en, zh in sorted(MATERIAL_ZH_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(en, zh)
    return result
