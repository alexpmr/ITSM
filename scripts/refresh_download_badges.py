#!/usr/bin/env python3
"""Create cumulative, per-asset Shields.io badges from published GitHub Releases."""
import json
import os
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "alexpmr/ITSM")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
ASSET_MAP = {
    "instalador": "PT2VHF-ITSM-Windows-x64-Setup.exe",
    "portatil": "PT2VHF-ITSM-Windows-x64-Portable.exe",
}
LABELS = {"instalador": "Instalador Windows", "portatil": "Portátil Windows", "total": "Total downloads"}

def releases():
    if not TOKEN:
        raise RuntimeError("Token GitHub não configurado")
    page = 1
    while True:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": f"Bearer {TOKEN}",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "itsm-download-badges"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, list):
            raise ValueError("Resposta inesperada do GitHub")
        for item in data:
            if not item.get("draft"):
                yield item
        if len(data) < 100:
            return
        page += 1

def main():
    counts = {"instalador": 0, "portatil": 0, "total": 0}
    for release in releases():
        for asset in release.get("assets", []):
            n = int(asset.get("download_count", 0))
            if n < 0:
                raise ValueError("Contagem inválida")
            counts["total"] += n
            for typ, filename in ASSET_MAP.items():
                if asset.get("name") == filename:
                    counts[typ] += n
    dest = Path(__file__).resolve().parents[1] / "badges"
    dest.mkdir(exist_ok=True)
    for typ, n in counts.items():
        payload = {"schemaVersion": 1, "label": LABELS[typ], "message": str(n),
                   "color": "blue" if n else "lightgrey"}
        (dest / f"downloads-{typ}.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
    print(counts)

if __name__ == "__main__":
    main()
