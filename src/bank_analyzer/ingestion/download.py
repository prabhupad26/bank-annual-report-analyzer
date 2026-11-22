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
        reader = csv.DictReader(
            line for line in handle if line.strip() and not line.lstrip().startswith("#")
        )
        required_fields = {"bank", "year", "url"}
        if reader.fieldnames is None:
            raise ValueError(f"Manifest has no header: {manifest}")
        missing_fields = required_fields - set(reader.fieldnames)
        if missing_fields:
            raise ValueError(
                f"Manifest is missing required columns: {', '.join(sorted(missing_fields))}"
            )

        report_count = 0
        for row_number, row in enumerate(reader, start=2):
            report_count += 1
            if None in row:
                raise ValueError(f"Manifest row {row_number} has too many columns")
            missing_values = [
                field for field in ("bank", "year", "url")
                if row[field] is None or not row[field].strip()
            ]
            if missing_values:
                raise ValueError(
                    f"Manifest row {row_number} is missing values for: "
                    f"{', '.join(missing_values)}"
                )

            bank = row["bank"].strip().lower()
            try:
                year = int(row["year"])
            except ValueError as exc:
                raise ValueError(
                    f"Manifest row {row_number} has an invalid year: {row['year']!r}"
                ) from exc
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
        if report_count == 0:
            raise ValueError(f"Manifest has no report entries: {manifest}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    download_manifest(args.manifest, args.output)

if __name__ == "__main__":
    main()
