"""Project registry and defaults."""
from pathlib import Path

BANKS = {
    "barclays": "Barclays",
    "bnp_paribas": "BNP Paribas",
    "deutsche_bank": "Deutsche Bank",
    "hsbc": "HSBC",
    "ing": "ING",
    "intesa_sanpaolo": "Intesa Sanpaolo",
    "lloyds": "Lloyds Banking Group",
    "santander": "Banco Santander",
    "ubs": "UBS",
    "unicredit": "UniCredit",
}
YEARS = range(2021, 2026)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
