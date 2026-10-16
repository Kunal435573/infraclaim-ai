import json
from pathlib import Path
from app.schemas import InfrastructureIncident, VendorContract

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_contract() -> VendorContract:
    return VendorContract.model_validate(json.loads((DATA_DIR / "contract.json").read_text()))


def load_incidents() -> list[InfrastructureIncident]:
    payload = json.loads((DATA_DIR / "incidents.json").read_text())
    return [InfrastructureIncident.model_validate(x) for x in payload]
