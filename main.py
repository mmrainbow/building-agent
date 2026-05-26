from pathlib import Path

from agent.graph import build_agent


def main():
    agent = build_agent()
    image_path = input("Please enter image path: ").strip()
    if not image_path:
        print("Empty path.")
        return
    if not Path(image_path).exists():
        print(f"File does not exist: {image_path}")
        return

    result = agent.invoke({"image_path": image_path})
    print("\n=== Inspection Result ===\n")
    print(result.get("report", "No report generated."))
    if result.get("error"):
        print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
# 测试git