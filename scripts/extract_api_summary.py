from __future__ import annotations

import argparse
import json
import re
from html import unescape
from pathlib import Path


def extract_state(html: str) -> dict:
    match = re.search(r"const __redoc_state = (\{.*?\});\s*var container", html, flags=re.S)
    if not match:
        raise ValueError("未找到 Redoc state")
    return json.loads(match.group(1))


def summarize_file(path: Path) -> list[dict[str, str]]:
    html = path.read_text(encoding="utf-8", errors="replace")
    try:
        spec = extract_state(html)["spec"]["data"]
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for route, methods in spec.get("paths", {}).items():
        for method, detail in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            rows.append(
                {
                    "document": path.name,
                    "method": method.upper(),
                    "path": route,
                    "summary": unescape(str(detail.get("summary") or detail.get("operationId") or "")),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Redoc OpenAPI summaries")
    parser.add_argument("--docs-dir", default="RESTfulAPI/文档")
    parser.add_argument("--output", default="docs/openapi-summary.md")
    args = parser.parse_args()
    docs_dir = Path(args.docs_dir)
    all_rows: list[dict[str, str]] = []
    for html_path in sorted(docs_dir.glob("*.html")):
        all_rows.extend(summarize_file(html_path))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# OpenAPI Summary", "", "| Document | Method | Path | Summary |", "| --- | --- | --- | --- |"]
    for row in all_rows:
        lines.append(f"| {row['document']} | {row['method']} | `{row['path']}` | {row['summary']} |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_rows)} endpoints to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

