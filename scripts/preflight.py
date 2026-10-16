import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.config import Settings
from app.services.nebius import NebiusClient

async def main():
    settings = Settings()
    client = NebiusClient(settings)
    result = await client.preflight()
    print({
        'mode': settings.infraclaim_llm_mode,
        'key_configured': bool(client._key()),
        'status': result.get('status'),
        'missing_models': result.get('missing_models'),
        'available_nemotron_models': result.get('available_nemotron_models'),
        'execution': result.get('execution'),
    })

if __name__ == '__main__':
    asyncio.run(main())
