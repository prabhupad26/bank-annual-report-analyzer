"""Idempotent annual-report PDF downloader driven by verified source manifest."""
import argparse
import csv
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from bank_analyzer.config import BANKS

def download_manifest(manifest: Path, output: Path) -> None:
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            bank = row["bank"].strip().lower()
            year = int(row["year"])
            url = row["url"].strip()
            if bank not in BANKS or not (2000 <= year <= 2100):
                raise ValueError(f"Invalid bank/year: {bank}/{year}")
            if urlparse(url).scheme != "https":
                raise ValueError(f"HTTPS source required: {url}")
            target = output / bank / f"{year}.pdf"
            if target.exists() and target.stat().st_size > 0:
                print(f"SKIP {target}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(".pdf.part")
            try:
                with requests.get(url, stream=True, timeout=(15, 120), headers={"User-Agent": "BankAnnualReportAnalyzer/0.1"}) as response:
                    response.raise_for_status()
                    digest = hashlib.sha256()
                    with temp.open("wb") as file:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                digest.update(chunk)
                                file.write(chunk)
                with temp.open("rb") as file:
                    if file.read(5) != b"%PDF-":
                        raise ValueError(f"Not a PDF: {url}")
                os.replace(temp, target)
                print(f"OK {target} sha256={digest.hexdigest()}")
            finally:
                temp.unlink(missing_ok=True)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    download_manifest(args.manifest, args.output)

if __name__ == "__main__":
    main()
