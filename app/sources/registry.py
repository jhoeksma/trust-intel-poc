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
    note: str = ""


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
            ),
            loader="nof",
            default_period="Q1 2026/27",
            note="Q1 2026/27 supplied by Jon as Numbers files (20 Oct 2026), converted to CSV and committed (public, OGL). "
            "Trust data is long format (Metric_ID, Value, rank); league tables add rank and likely ranges. "
            "Adjusted segment is OF5200. Override with SEED_URLS_NOF once official CSV links are known. "
            "The 2026/27 framework changed method; not comparable with 2025/26.",
        ),
        SourceSpec(
            key="rtt",
            name="Referral to treatment (RTT) waiting times: full CSV extract",
            owner="NHS England",
            cadence="Monthly",
            index_urls=("https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2026-27/",),
            link_text_re=r"(?i)full csv data file",
            kind="zip_csv",
            loader="rtt",
            note="Aggregated by us from provider by specialty by commissioner rows; see DATA_DICTIONARY.md.",
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
    ]
}
