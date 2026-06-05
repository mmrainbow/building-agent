"""OpenAI function call schema 定义。"""

_IMAGE_INDICES_PARAM = {
    "image_indices": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "Image indices to analyze (1-based). Omit to analyze all uploaded images. Example: [1,2] for first two, [2] for second only.",
    },
}

MATERIAL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "classify_material",
        "description": "Identify building facade material type. Returns e.g. Face Brick, Coating, Stone Hanging, Glass Curtain Wall, Aluminum Plate, Real Stone Paint.",
        "parameters": {
            "type": "object",
            "properties": {**_IMAGE_INDICES_PARAM},
        },
    },
}

FLOOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_floors",
        "description": "Estimate number of floors based on window arrangement on building facade. Returns e.g. '5 floors'.",
        "parameters": {
            "type": "object",
            "properties": {**_IMAGE_INDICES_PARAM},
        },
    },
}

EXTENSION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "detect_extension",
        "description": "Detect illegal roof extensions or added floors on building. Returns 'has extension' or 'no extension'.",
        "parameters": {
            "type": "object",
            "properties": {**_IMAGE_INDICES_PARAM},
        },
    },
}

DEFECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "detect_defects",
        "description": "Detect building facade defects: hollowing, water seepage, spalling, cracks. Returns defect list with id, type, area, and bounding box coordinates.",
        "parameters": {
            "type": "object",
            "properties": {**_IMAGE_INDICES_PARAM},
        },
    },
}

KNOWLEDGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": "Search building codes, inspection standards, defect criteria, and treatment methods to assist report generation.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords or question, e.g. 'spalling causes', 'crack width safety threshold', 'water seepage treatment'",
                }
            },
            "required": ["query"],
        },
    },
}

REPORT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": (
            "Call the local Report Agent (fine-tuned Qwen2.5-VL model) to generate a formal building inspection report. "
            "Call this tool after collecting sufficient detection data, instead of writing the report yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "material": {
                    "type": "string",
                    "description": "Material detection result, e.g. 'Face Brick', 'Coating'",
                },
                "floor": {
                    "type": "string",
                    "description": "Floor count result, e.g. '18 floors'",
                },
                "has_extension": {
                    "type": "string",
                    "description": "Extension detection result, e.g. 'has extension' or 'no extension'",
                },
                "defects_summary": {
                    "type": "string",
                    "description": "Summary of detected defects including types and counts",
                },
            },
            "required": [],
        },
    },
}
