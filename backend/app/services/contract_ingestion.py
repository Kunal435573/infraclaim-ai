import hashlib
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from app.schemas import ContractIngestionResult, SLAClause, VendorContract
from app.services.nebius import NebiusClient

_PDF_SLOTS = threading.BoundedSemaphore(2)


class ContractIngestor:
    def __init__(self, nebius: NebiusClient | None = None) -> None:
        self.nebius = nebius or NebiusClient()

    @staticmethod
    def _extract_pages(pdf_bytes: bytes) -> list[str]:
        if not _PDF_SLOTS.acquire(blocking=False):
            raise ValueError('PDF parser is busy; retry shortly.')
        try:
            environment = {key: value for key, value in os.environ.items()
                           if not re.search(r'KEY|TOKEN|SECRET|PASSWORD', key, re.I)}
            worker = subprocess.run([sys.executable, '-m', 'app.services.pdf_worker'],
                                    input=pdf_bytes, capture_output=True, timeout=12,
                                    cwd=Path(__file__).resolve().parents[2], env=environment,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if worker.returncode or len(worker.stdout) > 2500000:
                raise ValueError('PDF parser limit or invalid document')
            return json.loads(worker.stdout)
        except Exception as exc:
            raise ValueError('PDF could not be read within the supported size, page, or time limits.') from exc
        finally:
            _PDF_SLOTS.release()

    @staticmethod
    def _find(pattern: str, text: str, default: str | None = None) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else default

    def _deterministic_extract(self, pages: list[str], filename: str, digest: str) -> VendorContract:
        text = "\n".join(pages)
        contract_id = self._find(r"Contract ID:\s*([^\n]+)", text, "contract_uploaded")
        customer = self._find(r"Customer:\s*([^\n]+)", text, "Unknown Customer")
        vendor = self._find(r"Vendor:\s*([^\n]+)", text, "Unknown Vendor")
        effective_raw = self._find(r"Effective Date:\s*([^\n]+)", text, "January 1, 2026")
        try:
            effective = datetime.strptime(effective_raw, "%B %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError('Invalid contract effective date; manual extraction required') from exc

        section_page = 1
        source_quote = None
        for idx, page in enumerate(pages, start=1):
            if "Section 7.4" in page and "Critical Cooling Incident" in page:
                section_page = idx
                lines = page.splitlines()
                section_lines: list[str] = []
                capture = False
                for line in lines:
                    if "Section 7.4" in line:
                        capture = True
                    if capture:
                        if section_lines and line.startswith("Section 7.5"):
                            break
                        section_lines.append(line)
                source_quote = " ".join(section_lines)[:1200]
                break

        service = self._find(r"Service:\s*([^\n]+)", text, "critical_cooling_loop_b")
        response = int(self._find(r"acknowledge[\s\S]*?within\s+(\d+)\s+minutes", text))
        restore_match = re.search(r"restore[^.]*?within\s+(\d+)\s+minutes", text, flags=re.IGNORECASE | re.DOTALL)
        if restore_match is None:
            raise ValueError('Missing restoration SLA; manual extraction required')
        repair = int(restore_match.group(1))
        rate = float(self._find(r"USD\s*([\d,]+)\s+per eligible hour", text, "10000").replace(",", ""))
        cap = float(self._find(r"capped at USD\s*([\d,]+)", text, "50000").replace(",", ""))
        claim_days = int(self._find(r"within\s+(\d+)\s+calendar days", text, "30"))

        exclusions = []
        lowered = re.sub(r'\s+', ' ', text).lower()
        for candidate in ["planned maintenance", "customer-caused events", "force majeure"]:
            if candidate in lowered:
                exclusions.append(candidate.rstrip("s") if candidate != "force majeure" else candidate)

        return VendorContract(
            id=contract_id,
            customer=customer,
            vendor=vendor,
            effective_date=effective,
            source_filename=filename,
            source_text_sha256=digest,
            sla=SLAClause(
                id="sla.cooling.7.4",
                title="Critical Cooling Incident — Section 7.4",
                service=service,
                response_minutes=response,
                repair_minutes=repair,
                rate_per_eligible_hour_usd=rate,
                cap_usd=cap,
                claim_window_days=claim_days,
                exclusions=exclusions,
                source_page=section_page,
                source_section="Section 7.4",
                source_quote=source_quote,
            ),
        )

    async def ingest_pdf(self, pdf_bytes: bytes, filename: str = "contract.pdf") -> ContractIngestionResult:
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Uploaded file is not a PDF")
        pages = await asyncio.to_thread(self._extract_pages, pdf_bytes)
        if not any(pages):
            raise ValueError("No extractable text found in PDF")
        digest = hashlib.sha256("\n".join(pages).encode("utf-8")).hexdigest()
        warnings: list[str] = []

        # This parser supports the supplied template only. Unknown PDFs must not
        # acquire fabricated defaults, and LLM output never overwrites money terms.
        text = "\n".join(pages)
        required = [r"Contract ID:\s*[^\n]+", r"Customer:\s*[^\n]+", r"Vendor:\s*[^\n]+",
                    r"Effective Date:\s*[^\n]+", r"acknowledge[^.]*within\s+\d+\s+minutes",
                    r"restore[^.]*within\s+\d+\s+minutes",
                    r"Service:\s*[^\n]+", r"Section 7\.4", r"Critical Cooling Incident",
                    r"USD\s*[\d,]+\s+per eligible hour", r"capped at USD\s*[\d,]+",
                    r"within\s+\d+\s+calendar days"]
        if not all(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in required):
            raise ValueError("Unsupported contract template or missing SLA terms; manual extraction required")
        contract = self._deterministic_extract(pages, filename, digest)
        warnings.append("Template-specific extraction; verify every contract term against the original PDF before saving.")

        preview = "\n".join(pages)[:1800]
        return ContractIngestionResult(contract=contract, extracted_text_preview=preview, pages=len(pages), warnings=warnings)


def load_demo_contract_pdf() -> bytes:
    path = Path(__file__).resolve().parents[1] / "data" / "contracts" / "ThermaCore_Master_Service_Agreement_2026.pdf"
    return path.read_bytes()
