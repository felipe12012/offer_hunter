"""Writes web/src/lib/taxonomy.ts from taxonomy.py so the web lists the same slugs and labels.

    python scripts/gen_web_taxonomy.py          # rewrite the file
    python scripts/gen_web_taxonomy.py --check  # exit 1 if it is out of date (CI/test)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from taxonomy import GROUPS, SUBCATEGORIES  # noqa: E402

TARGET = ROOT / "web" / "src" / "lib" / "taxonomy.ts"


def render() -> str:
    lines = [
        "// GENERADO por scripts/gen_web_taxonomy.py desde taxonomy.py. No editar a mano:",
        "// para cambiar categorías se edita taxonomy.py y se vuelve a generar.",
        "",
        "export const GROUPS = [",
        *[f"  {json.dumps(slug)}," for slug in GROUPS],
        "] as const;",
        "export type Group = (typeof GROUPS)[number];",
        "",
        "export const GROUP_LABELS: Record<string, string> = {",
        *[f"  {json.dumps(slug)}: {json.dumps(label, ensure_ascii=False)}," for slug, label in GROUPS.items()],
        "};",
        "",
        "/** Subcategorías de cada categoría, en el orden en que se muestran. */",
        "export const SUBCATEGORIES: Record<string, Record<string, string>> = {",
    ]
    for group, subs in SUBCATEGORIES.items():
        lines.append(f"  {json.dumps(group)}: {{")
        lines += [f"    {json.dumps(slug)}: {json.dumps(label, ensure_ascii=False)}," for slug, label in subs.items()]
        lines.append("  },")
    lines += ["};", ""]
    return "\n".join(lines)


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        return 0 if TARGET.exists() and TARGET.read_text(encoding="utf-8").replace("\r\n", "\n") == content else 1
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
