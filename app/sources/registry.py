"""The source registry: where each dataset lives and how to find its latest file.

NHS file URLs carry date folders and random suffixes, so we never guess them.
Discovery reads an index page and picks links by pattern. `seed_urls` are
file URLs confirmed by hand on 20 October 2026; they are a fallback if discovery
finds nothing, and are flagged as such in the source inventory.

To add a source: add a SourceSpec here, then (if the generic loader cannot cope)
a specialised loader in loaders.py. Document it in docs/SOURCES.md.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    owner: str
    cadence: str
    index_urls: tuple
    child_href_re: str | None = None  # find the latest publication page from a series page
    link_href_re: str | None = None  # pick file links by href...
    link_text_re: str | None = None  # ...and/or by link text (both must match if both set)
    seed_urls: tuple = ()
    kind: str = "csv"  # csv | zip_csv
    loader: str = "generic"  # generic | rtt
    default_period: str | None = None
    licence: str = "Open Government Licence v3.0 (confirm on each publication page)"
    snapshot: bool = False  # every file is a full snapshot: a new file replaces earlier rows with the same (org, metric, period)
    note: str = ""


_NOF_Q4 = "https://www.england.nhs.uk/wp-content/uploads/2026/06/nhs-oversight-framework-"
# Q4 2025/26 files hold all four 2025/26 quarters (Q1 to Q4) for every trust, so these three trust-data files give the
# history; the league tables carry Q4 only. Addresses read from NHS England's "csv metadata file" page for Q4 2025/26.
NOF_2025_26 = tuple(_NOF_Q4 + n + ".csv" for n in (
    "acute-trust-data", "mental-health-and-community-trust-data", "ambulance-trust-data",
    "acute-trust-league-table", "mental-health-and-community-trust-league-table", "ambulance-trust-league-table"))

_RTT_BASE = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/"
# Monthly Full CSV zips, September 2024 to July 2026 (August 2026 is the committed local seed). The hashed names cannot
# be guessed: they were read from the RTT pages for 2024-25, 2025-26 and 2026-27. Re-read them when a month is revised.
RTT_HISTORY = tuple(_RTT_BASE + f for f in (
    "2025/02/Full-CSV-data-file-Sep24-ZIP-4M-revised.zip", "2025/07/Full-CSV-data-file-Oct24-ZIP-4M-revised.zip",
    "2025/07/Full-CSV-data-file-Nov24-ZIP-4M-revised.zip", "2025/07/Full-CSV-data-file-Dec24-ZIP-4M-revised.zip",
    "2025/07/Full-CSV-data-file-Jan25-ZIP-4M-revised.zip", "2025/07/Full-CSV-data-file-Feb25-ZIP-4M-revised.zip",
    "2025/07/Full-CSV-data-file-Mar25-ZIP-4M-revised.zip", "2026/02/Full-CSV-data-file-Apr25-ZIP-4M-revised.zip",
    "2026/02/Full-CSV-data-file-May25-ZIP-4M-revised.zip", "2026/02/Full-CSV-data-file-Jun25-ZIP-4M-revised.zip",
    "2026/02/Full-CSV-data-file-Jul25-ZIP-4M-revised-2.zip", "2026/02/Full-CSV-data-file-Aug25-ZIP-4M-revised-2.zip",
    "2026/02/Full-CSV-data-file-Sep25-ZIP-4M-revised.zip", "2025/12/Full-CSV-data-file-Oct25-ZIP-4M-SrRW6y.zip",
    "2026/01/Full-CSV-data-file-Nov25-ZIP-4M-1Xmjkk.zip", "2026/07/Full-CSV-data-file-Dec25-ZIP-3M-revised.zip",
    "2026/03/Full-CSV-data-file-Jan26-ZIP-4M-WL5BiP.zip", "2026/04/Full-CSV-data-file-Feb26-ZIP-4M-9j03fJT.zip",
    "2026/07/Full-CSV-data-file-Mar26-ZIP-3M-revised.zip", "2026/06/Full-CSV-data-file-Apr26-ZIP-3M-X7gGnn.zip",
    "2026/07/Full-CSV-data-file-May26-ZIP-3M-3jBgba.zip", "2026/08/Full-CSV-data-file-Jun26-ZIP-3M-6jPlxd.zip",
    "2026/09/Full-CSV-data-file-Jul26-ZIP-4M-97ylx5.zip",
))


SOURCES: dict[str, SourceSpec] = {
    s.key: s
    for s in [
        SourceSpec(
            key="nof",
            name="NHS Oversight Framework: trust data and league tables",
            owner="NHS England",
            cadence="Quarterly",
            index_urls=(
                "https://www.england.nhs.uk/nhs-oversight-framework/segmentation-and-league-tables",
                "https://www.england.nhs.uk/publication/nhs-oversight-framework-nhs-trust-performance-league-tables-process-and-results/",
            ),
            link_href_re=r"(?i)oversight-framework.*(trust-data|league-table).*\.csv",
            seed_urls=tuple(
                "file://data/manual/NOF%20-%20Q1%202026_27%20-%20" + n.replace(" ", "%20") + ".csv.gz"
                for n in ("Trust data - Acute", "Trust data - Ambulance", "Trust data - Mental health and community",
                          "League table - Acute", "League table - Ambulance", "League table - Mental health and community")
            ) + NOF_2025_26,
            loader="nof",
            default_period="Q1 2026/27",
            note="Q1 2026/27 supplied by Jon as Numbers files (20 Oct 2026), converted to CSV and committed (public, OGL). "
            "Trust data is long format (Metric_ID, Value, rank); league tables add rank and likely ranges. "
            "Adjusted segment is OF5200. Override with SEED_URLS_NOF once official CSV links are known. "
            "2025/26 history (Q1 to Q4) comes from the Q4 2025/26 CSVs by URL; its composite scores and segments are mapped onto the 2026/27 IDs "
            "(see ALIAS_2025_26 in nof.py) but the 2026/27 framework changed method, so charts mark a method break between Q4 2025/26 and Q1 2026/27.",
        ),
        SourceSpec(
            key="rtt",
            name="Referral to treatment (RTT) waiting times: full CSV extract",
            owner="NHS England",
            cadence="Monthly",
            index_urls=("https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2026-27/",),
            link_text_re=r"(?i)full csv data file",
            seed_urls=("file://data/manual/RTT%20-%20Aug%202026%20-%20Full%20CSV%20data%20file.zip",) + RTT_HISTORY,
            kind="zip_csv",
            loader="rtt",
            note="Aggregated by us from provider by specialty by commissioner rows; see DATA_DICTIONARY.md. "
            "August 2026 full extract supplied by Jon (20 Oct 2026) and committed as a seed (public, OGL, 3.4MB zip). The 23 months before it (September 2024 to July 2026) are seeded by URL, read from NHS England's RTT pages on 20 Oct 2026 (revised files where NHS England published one); Railway downloads them, nothing is committed.",
        ),
        SourceSpec(
            key="workforce",
            name="NHS Workforce Statistics: trusts and core organisations (CSV)",
            owner="NHS England",
            cadence="Monthly",
            index_urls=("https://digital.nhs.uk/data-and-information/publications/statistical/nhs-workforce-statistics",),
            child_href_re=r"(?i)/nhs-workforce-statistics/[a-z]+-20\d{2}$",
            link_text_re=r"(?i)trusts and core organisations.*csv data files",
            seed_urls=(
                "https://files.digital.nhs.uk/EA/63063B/NHS%20HCHS%20Workforce%20Statistics%2C%20Trusts%20and%20core%20organisations%20-%20CSV%20data%20files%2C%20July%202026.zip",
            ),
            kind="zip_csv",
            note="The zip holds many CSVs; every CSV with an organisation code column is profiled and loaded.",
        ),
        SourceSpec(
            key="eric",
            name="Estates Returns Information Collection (ERIC): trust data",
            owner="NHS England",
            cadence="Annual",
            index_urls=("https://digital.nhs.uk/data-and-information/publications/statistical/estates-returns-information-collection",),
            child_href_re=r"(?i)summary-page-and-dataset-for-eric-20\d{2}-\d{2}$",
            link_text_re=r"(?i)trust data",
            seed_urls=("https://files.digital.nhs.uk/9A/DF80E7/ERIC%20-%202024_25%20-%20Trust%20data.csv",),
            note="Some fields are flagged unreliable by the publisher; see its data quality worksheets.",
        ),
        SourceSpec(
            key="eric_site",
            name="ERIC site-level return, rolled up to trust (2025/26)",
            owner="NHS England",
            cadence="Annual",
            index_urls=(),
            seed_urls=("file://data/manual/ERIC%20-%202025_26%20-%20Site%20data.csv.gz",),
            loader="eric_site",
            default_period="2025/26",
            note="Supplied by Jon as a Numbers file (20 Oct 2026), converted to CSV and committed (public data, OGL). "
            "Replace with the official CSV link via SEED_URLS_ERIC_SITE when available.",
        ),
        SourceSpec(
            key="hes",
            name="Hospital Episode Statistics, admitted patient care: provider level analysis",
            owner="NHS England",
            cadence="Annual",
            index_urls=("https://digital.nhs.uk/data-and-information/publications/statistical/hospital-admitted-patient-care-activity",),
            child_href_re=r"(?i)/hospital-admitted-patient-care-activity/20\d{2}-\d{2}$",
            link_text_re=r"(?i)provider level analysis",
            seed_urls=("https://files.digital.nhs.uk/3C/145B13/hosp-epis-stat-admi-pla-2024-25.csv",),
            note="Counts episodes, not patients. Publisher notes a data error at RMC (Bolton) in 2024-25.",
        ),
        SourceSpec(
            key="cqc",
            name="CQC latest ratings: provider-level quality ratings",
            owner="Care Quality Commission",
            cadence="Monthly",
            index_urls=("https://www.cqc.org.uk/about-us/transparency/using-cqc-data",),
            link_href_re=r"(?i)Latest_ratings\.ods$",
            seed_urls=("https://www.cqc.org.uk/system/files/2026-10/01_October_2026_Latest_ratings.ods",),
            loader="cqc",
            snapshot=True,
            licence="Open Government Licence v3.0; acknowledge CQC as the data source",
            note="Ratings stored 1 Inadequate to 4 Outstanding. Most NHS providers carry no ODS code in the file, so they are matched by name "
            "(flagged name_match); fixes go in data/reference/cqc_overrides.csv. Load after the other sources.",
        ),
        SourceSpec(
            key="dma",
            name="Digital Maturity Assessment 2024 and 2025: trust digital maturity scores",
            owner="NHS England",
            cadence="Annual",
            index_urls=(),
            seed_urls=("file://data/manual/DMA%20-%202025%20-%20Results%20data%20file%20v2.xlsx",),
            loader="dma",
            licence="Open Government Licence v3.0; NHS England",
            note="Supplied by Jon (21 Oct 2026), published 30 March 2026, committed (public data). The file has no ODS codes, so "
            "providers are matched by name (fixes in data/reference/dma_overrides.csv). Overall score is for comparable domains only. "
            "Multi-service trusts have one row per care setting; the headline uses the primary setting. Load after the other sources.",
        ),
    ]
}
