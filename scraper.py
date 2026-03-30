"""IDX financial report scraper - core library.

Provides functions to fetch report metadata from the IDX API
and download individual attachment files.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Optional

import requests

PERIOD_MAP = {
    "tw1": "tw1",
    "tw2": "tw2",
    "tw3": "tw3",
    "tahunan": "audit",
}

IDX_BASE_URL = "https://idx.co.id"
API_URL = f"{IDX_BASE_URL}/primary/ListedCompany/GetFinancialReport"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

ProgressCallback = Optional[Callable[[str], None]]


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_reports(
    session: requests.Session, year: str, period: str, page_size: int = 1000
) -> dict:
    """Fetch the report listing from the IDX API.

    Returns the full JSON response containing ResultCount and Results[].
    Retries up to 3 times on transient failures.
    """
    api_period = PERIOD_MAP.get(period.lower(), period.lower())
    params = {
        "indexFrom": 1,
        "pageSize": page_size,
        "year": year,
        "reportType": "rdf",
        "EmitenType": "s",
        "periode": api_period,
        "kodeEmiten": "",
        "SortColumn": "KodeEmiten",
        "SortOrder": "asc",
    }

    for attempt in range(1, 4):
        response = session.get(API_URL, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        if attempt < 3:
            time.sleep(attempt * 5)
    response.raise_for_status()
    return {}


def download_file(
    session: requests.Session,
    company: str,
    file_name: str,
    file_path: str,
    download_dir: str,
    year: str,
    period: str,
    max_retries: int = 5,
    retry_delay: int = 5,
    on_progress: ProgressCallback = None,
    cancelled: Callable[[], bool] | None = None,
) -> bool:
    """Download a single attachment file.

    Args:
        cancelled: callable returning True if the download should be aborted.
        on_progress: callable receiving status message strings.

    Returns True on success, False on failure or cancellation.
    """
    full_url = f"{IDX_BASE_URL}{file_path}"

    for attempt in range(1, max_retries + 1):
        if cancelled and cancelled():
            if on_progress:
                on_progress(f"Cancelled: {file_name}")
            return False

        try:
            response = session.get(full_url, allow_redirects=True, timeout=60)

            if response.status_code == 200:
                safe_filename = file_name.replace("/", "-").replace("\\", "-")
                output_dir = os.path.join(download_dir, company, year, period)
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, safe_filename)

                with open(output_path, "wb") as f:
                    f.write(response.content)
                if on_progress:
                    on_progress(f"Downloaded: {company}/{safe_filename}")
                return True
            else:
                msg = f"HTTP {response.status_code} for {file_name} (attempt {attempt}/{max_retries})"
                if on_progress:
                    on_progress(msg)
        except Exception as e:
            msg = f"Error: {e} for {file_name} (attempt {attempt}/{max_retries})"
            if on_progress:
                on_progress(msg)

        if attempt < max_retries:
            time.sleep(retry_delay)

    if on_progress:
        on_progress(f"Failed after {max_retries} attempts: {file_name}")
    return False
