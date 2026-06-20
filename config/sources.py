"""SOURCES — every official entity Dream Arabia may scrape, cite, or hand off to.

Single source of truth, transcribed from the Excel "Master URL Index" tab
(Tier, Entity, URL, Access Note, persona membership) and cross-checked against
each persona tab's URL list. The Excel wins over the PDF (which listed only
three sources).

Each source is keyed by its NAMESPACE — the tag injected into every graph node
id (e.g. ``misa::investor_license``). Persona membership here is what
PERSONA_NAMESPACE_MAP consumes: it defines the *entry* namespaces for a persona,
not a hard filter (traversal still follows cross-source edges).

Access:
- "saudi_ip": live scraping requires a Saudi egress IP/proxy (see scraper config).
- "open": reachable from anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    namespace: str
    name: str
    url: str
    access: str           # "saudi_ip" | "open"
    tier: str             # "T1".."T4"
    personas: tuple[str, ...]  # e.g. ("P1", "P2")

    @property
    def requires_saudi_ip(self) -> bool:
        return self.access == "saudi_ip"


def _s(ns, name, url, access, tier, personas):
    return Source(ns, name, url, access, tier, tuple(personas))


# Persona order used by the Excel index: P1..P6
_SOURCE_ROWS = [
    # ns, name, url, access, tier, personas
    ("misa", "MISA — Ministry of Investment", "https://misa.gov.sa/en", "saudi_ip", "T1", ["P1", "P2", "P4"]),
    ("investsaudi", "Invest Saudi", "https://investsaudi.sa/en", "saudi_ip", "T1", ["P1", "P2", "P4"]),
    ("mim", "MIM — Ministry of Industry & Mineral Resources", "https://www.mim.gov.sa/en", "saudi_ip", "T1", ["P1", "P2"]),
    ("pif", "PIF — Public Investment Fund", "https://www.pif.gov.sa/en", "saudi_ip", "T1", ["P1"]),
    ("ecza", "ECZA — Special Economic Zones", "https://ecza.gov.sa/en", "saudi_ip", "T1", ["P1", "P2"]),
    ("monshaat", "Monshaat — SME Authority", "https://www.monshaat.gov.sa/en", "saudi_ip", "T1", ["P2"]),
    ("svc", "SVC — Saudi Venture Capital", "https://www.svc.com.sa/en", "saudi_ip", "T1", ["P1", "P2"]),
    ("sdaia", "SDAIA — Data & AI Authority", "https://www.sdaia.gov.sa/en", "saudi_ip", "T1", ["P2"]),
    ("pr", "Premium Residency Center", "https://pr.gov.sa", "saudi_ip", "T1", ["P1", "P2", "P4"]),
    ("hrsd", "HRSD — Human Resources & Social Development", "https://hrsd.gov.sa/en", "saudi_ip", "T1", ["P2", "P4", "P6"]),
    ("sta", "Saudi Tourism Authority (STA)", "https://www.sta.gov.sa/en/home", "saudi_ip", "T1", ["P3"]),
    ("visitsaudi", "Visit Saudi", "https://www.visitsaudi.com/en", "saudi_ip", "T1", ["P3", "P4"]),
    ("mt", "Ministry of Tourism", "https://mt.gov.sa/en", "saudi_ip", "T1", ["P3"]),
    ("vision2030", "Vision 2030 Portal", "https://www.vision2030.gov.sa/en", "saudi_ip", "T1", ["P1", "P2", "P4", "P5"]),
    ("datasaudi", "DataSaudi (Statistics)", "https://datasaudi.sa/en", "open", "T1", ["P1", "P2", "P3", "P4"]),
    ("nusuk", "Nusuk (Pilgrimage Logistics)", "https://nusuk.sa", "saudi_ip", "T1", ["P3"]),
    ("absher", "Absher (Citizen / Resident Services)", "https://absher.sa", "saudi_ip", "T1", ["P4", "P6"]),
    ("mygov", "National Portal (my.gov.sa)", "https://my.gov.sa/en", "saudi_ip", "T1", ["P2", "P6"]),
    ("moe", "Ministry of Education", "https://moe.gov.sa/en", "saudi_ip", "T1", ["P5", "P6"]),
    ("moh", "Ministry of Health (MoH)", "https://www.moh.gov.sa/en", "saudi_ip", "T1", ["P6"]),
    ("zatca", "ZATCA — Zakat, Tax & Customs Authority", "https://zatca.gov.sa/en", "saudi_ip", "T1", ["P1", "P2", "P6"]),
    # Tier 2 — giga-projects / precincts
    ("neom", "NEOM", "https://www.neom.com/en-us", "open", "T2", ["P1", "P3"]),
    ("redseaglobal", "Red Sea Global", "https://www.redseaglobal.com", "open", "T2", ["P1", "P3"]),
    ("diriyah", "Diriyah Gate", "https://www.diriyah.sa/en", "saudi_ip", "T2", ["P3"]),
    ("qiddiya", "Qiddiya", "https://qiddiya.com", "open", "T2", ["P3"]),
    ("experiencealula", "Experience AlUla", "https://www.experiencealula.com", "open", "T2", ["P3"]),
    ("amaala", "AMAALA", "https://www.amaala.com", "open", "T2", ["P3"]),
    ("kafd", "KAFD — King Abdullah Financial District", "https://www.kafd.sa/en", "saudi_ip", "T2", ["P1", "P4"]),
    # Tier 3 — universities
    ("kfupm", "KFUPM — King Fahd University of Petroleum & Minerals", "https://www.kfupm.edu.sa/en", "open", "T3", ["P4", "P5"]),
    ("kaust", "KAUST — King Abdullah University of Science & Technology", "https://www.kaust.edu.sa/en", "open", "T3", ["P4", "P5"]),
    ("ksu", "KSU — King Saud University", "https://www.ksu.edu.sa/en", "open", "T3", ["P5"]),
    ("kau", "KAU — King Abdulaziz University", "https://www.kau.edu.sa/en", "open", "T3", ["P5"]),
    ("pnu", "PNU — Princess Nourah University", "https://pnu.edu.sa/en", "open", "T3", ["P5"]),
    ("iau", "IAU — Imam Abdulrahman Bin Faisal University", "https://www.iau.edu.sa/en", "open", "T3", ["P5"]),
    ("seu", "SEU — Saudi Electronic University", "https://seu.edu.sa/en", "open", "T3", ["P5"]),
    # Tier 4 — ecosystem / media / transport
    ("webook", "Webook (Events & Ticketing)", "https://webook.com/en", "open", "T4", ["P3"]),
    ("arabnews", "Arab News (Business)", "https://www.arabnews.com/saudiarabia/business", "open", "T4", ["P1", "P2"]),
    ("saudigazette", "Saudi Gazette (Business)", "https://saudigazette.com.sa/section/BUSINESS", "open", "T4", ["P1", "P2"]),
    ("magnitt", "MAGNiTT (MENA VC data)", "https://magnitt.com", "open", "T4", ["P1", "P2"]),
    ("zawya", "Zawya (Financial News)", "https://www.zawya.com/en/economy/saudi-arabia", "open", "T4", ["P1"]),
    ("saudia", "Saudia Airlines", "https://www.saudia.com", "open", "T4", ["P3"]),
    ("flynas", "flynas", "https://www.flynas.com", "open", "T4", ["P3"]),
]

SOURCES: dict[str, Source] = {row[0]: _s(*row) for row in _SOURCE_ROWS}


@dataclass(frozen=True)
class PdfDoc:
    pdf_id: str
    title: str
    url: str
    publisher: str
    year: str
    priority: str
    personas: tuple[str, ...]


def _p(pid, title, url, publisher, year, priority, personas):
    return PdfDoc(pid, title, url, publisher, year, priority, tuple(personas))


# Master PDF Library tab. Note: P5 and P6 have no persona-specific PDFs.
PDF_LIBRARY: dict[str, PdfDoc] = {
    d.pdf_id: d for d in [
        _p("PDF-01", "MISA Investor Guide — 12th Edition", "https://misa.gov.sa/app/uploads/2025/03/Investor-Guide.pdf", "Ministry of Investment", "Jan 2025", "CRITICAL", ["P1", "P2", "P4"]),
        _p("PDF-02", "MISA Service Manual — Edition 12.2", "https://investsaudi.sa/medias/MISA-Service-manual-12-2-edition-english.pdf", "MISA / Invest Saudi", "2025", "CRITICAL", ["P1", "P2", "P4"]),
        _p("PDF-03", "RHQ Investor Manual", "https://catalyzesaudi.sa/RHQ/wp-content/uploads/2024/08/Investor-Manual-English.pdf", "MISA / RCRC", "Feb 2024", "CRITICAL", ["P1"]),
        _p("PDF-04", "MISA FDI Statistical Report", "https://misa.gov.sa/app/uploads/2024/04/saudi-arabia-foreign-direct-investment-report-january-2024.pdf", "Ministry of Investment", "Jan 2024", "HIGH", ["P1"]),
        _p("PDF-05", "Visit Saudi — AlUla Winter Guide", "https://www.visitsaudi.com/content/dam/documents/alula-winter-guide-en.pdf", "STA / Visit Saudi", "2024", "HIGH", ["P3"]),
        _p("PDF-06", "ECZA Special Economic Zones Brochure", "https://ecza.gov.sa/sites/default/files/2023-04/br.pdf", "ECZA", "2023", "HIGH", ["P1", "P2"]),
        _p("PDF-07", "Visit Saudi — Riyadh City Guide", "https://www.visitsaudi.com/content/dam/saudi-tourism/media/guides/riyadh-guidebook.pdf", "STA / Visit Saudi", "2024", "HIGH", ["P3"]),
        _p("PDF-08", "Visit Saudi — Jeddah City Guide", "https://www.visitsaudi.com/content/dam/saudi-tourism/media/guides/jeddah-guidebook.pdf", "STA / Visit Saudi", "2024", "HIGH", ["P3"]),
        _p("PDF-09", "Visit Saudi — Aseer Region Guide", "https://www.visitsaudi.com/content/dam/saudi-tourism/media/guides/aseer-guidebook.pdf", "STA / Visit Saudi", "2024", "MEDIUM", ["P3"]),
        _p("PDF-10", "Visit Saudi — Eastern Province Guide", "https://www.visitsaudi.com/content/dam/documents/dammam-guide-english.pdf", "STA / Visit Saudi", "2024", "MEDIUM", ["P3"]),
    ]
}


def source(namespace: str) -> Source:
    """Look up a source by namespace, raising a clear error if unknown."""
    try:
        return SOURCES[namespace]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"Unknown source namespace: {namespace!r}") from exc


def namespaces_for_personas(*persona_ids: str) -> list[str]:
    """All namespaces that list any of the given personas as a member."""
    wanted = set(persona_ids)
    return [ns for ns, s in SOURCES.items() if wanted & set(s.personas)]
