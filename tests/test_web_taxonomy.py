import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_web_taxonomy_matches_taxonomy_py():
    """web/src/lib/taxonomy.ts is generated: editing taxonomy.py without regenerating it breaks the filters."""
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_web_taxonomy.py"), "--check"])
    assert result.returncode == 0, "run: python scripts/gen_web_taxonomy.py"
