import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.config import Settings
from app.services.case_engine import CaseEngine
from app.services.nebius import NebiusClient
from app.services.repository import load_contract, load_incidents

async def main():
    settings=Settings()
    case=await CaseEngine(NebiusClient(settings), settings).investigate(load_contract(), load_incidents()[0])
    print({'state':case.state.value,'confidence':case.confidence,'reasoning':case.reasoning.model_dump(exclude={'inference'}) if case.reasoning else None,
           'inference':case.reasoning.inference if case.reasoning else None,'policy_reasons':case.policy_decisions[-1]['reasons'] if case.policy_decisions else []})

asyncio.run(main())
