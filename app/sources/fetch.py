"""Download files politely, with retries and a size cap."""
import hashlib
import io
import time
import zipfile

import requests

from app.config import settings


def download(url: str, retries: int = 3) -> bytes:
    cap = settings.max_download_mb * 1024 * 1024
    last = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, headers={"User-Agent": settings.user_agent}, timeout=settings.http_timeout, stream=True) as resp:
                resp.raise_for_status()
                buf = bytearray()
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    buf.extend(chunk)
                    if len(buf) > cap:
                        raise ValueError(f"download exceeds {settings.max_download_mb} MB cap")
                return bytes(buf)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed after {retries} attempts: {last}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def csv_members(zip_bytes: bytes) -> list[tuple[str, bytes]]:
    """All CSV files inside a zip, largest first."""
    out = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.filename.lower().endswith(".csv") and not info.is_dir():
                out.append((info.filename, zf.read(info)))
    out.sort(key=lambda t: len(t[1]), reverse=True)
    return out
