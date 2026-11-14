"""Baseline PDF page extraction. Complex tables/charts require a separate pipeline."""
import argparse
import json
from pathlib import Path

import fitz

def parse_pdf(pdf: Path, output_root: Path, input_root: Path) -> None:
    relative = pdf.relative_to(input_root)
    out = output_root / relative.with_suffix("")
    out.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text", sort=True).strip()
            markdown = f"<!-- source: {relative.as_posix()} | page: {i + 1} -->\n\n# Page {i + 1}\n\n{text}\n"
            (out / f"page_{i + 1:04d}.md").write_text(markdown, encoding="utf-8")
        metadata = {"source": relative.as_posix(), "pages": len(doc), "extraction": "pymupdf_text_baseline"}
        (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    for pdf in sorted(args.input.rglob("*.pdf")):
        parse_pdf(pdf, args.output, args.input)
        print(f"PARSED {pdf}")

if __name__ == "__main__":
    main()
