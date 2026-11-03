"""Run the deliberately failing synthetic example without a key or network."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = ROOT / "skills" / "caseprobe" / "scripts" / "caseprobe.py"
OUT = ROOT / "results" / "refund-demo"


def invoke(expected, *args):
    result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)])
    if result.returncode != expected:
        raise SystemExit(f"Unexpected exit code {result.returncode}; expected {expected}")


OUT.mkdir(parents=True, exist_ok=True)
common = ["--cases", HERE / "cases.jsonl", "--prompt", HERE / "system-prompt.txt", "--backend", "mock"]
invoke(0, "run", *common, "--mock-responses", HERE / "mock-baseline.json", "--out", OUT / "baseline.json")
invoke(1, "run", *common, "--mock-responses", HERE / "mock-candidate.json", "--out", OUT / "candidate.json")
invoke(1, "compare", "--baseline", OUT / "baseline.json", "--candidate", OUT / "candidate.json", "--out", OUT / "comparison.md")
print(f"Offline demonstration completed. Open {OUT / 'comparison.md'}")
