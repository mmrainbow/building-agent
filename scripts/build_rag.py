"""
构建 RAG 向量库（独立运行脚本）

用法:
    python scripts/build_rag.py                # 自动扫描根目录的 docx/pdf
    python scripts/build_rag.py <文件路径>      # 指定文档路径
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 确定目标文件
if len(sys.argv) > 1:
    target = sys.argv[1]
else:
    doc_files = list(ROOT.glob("*.docx")) + list(ROOT.glob("*.pdf"))
    if not doc_files:
        print("[ERROR] 未在项目根目录找到 .docx 或 .pdf 文件")
        sys.exit(1)
    target = str(doc_files[0])

print(f"[INFO] 目标文档: {target}")

from agent.rag import build_vectorstore

try:
    vs = build_vectorstore(target)
    count = vs._collection.count()
    print(f"[OK] 向量库构建完成，共 {count} 个文档块")
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
