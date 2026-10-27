"""Runtime settings, read once from environment variables.

Nothing here is secret by default: the secrets (database URL, basic-auth
password) come from Railway variables and are never committed.
"""
import os


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./trust_intel.db")
    # Railway supplies postgresql:// or postgres://; SQLAlchemy needs the driver named.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings:
    def __init__(self) -> None:
        self.database_url = _database_url()
        self.app_env = os.getenv("APP_ENV", "development")
        # Private by default: the dashboard will hold FHI's proprietary
        # installed-systems data once it is joined in.
        self.basic_auth_user = os.getenv("BASIC_AUTH_USER", "")
        self.basic_auth_password = os.getenv("BASIC_AUTH_PASSWORD", "")
        self.user_agent = os.getenv("FETCH_USER_AGENT", "FHI-trust-intel-poc/0.1")
        self.http_timeout = int(os.getenv("HTTP_TIMEOUT_SECONDS", "60"))
        self.max_download_mb = int(os.getenv("MAX_DOWNLOAD_MB", "250"))
        self.max_metric_rows_per_file = int(os.getenv("MAX_METRIC_ROWS_PER_FILE", "400000"))
        self.auth_required = self.app_env == "production"
        # Registration: only these email domains (and any individually listed addresses) may sign up, and every new account
        # waits for an admin to approve it. There is no email verification, so the approval step is the real gate.
        self.allowed_email_domains = [d.strip().lower() for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "futurehealthintelligence.com").split(",") if d.strip()]
        self.allowed_emails = [e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()]
        self.session_days = int(os.getenv("SESSION_DAYS", "7"))
        self._session_secret = os.getenv("SESSION_SECRET", "")


    @property
    def session_secret(self) -> bytes:
        """SESSION_SECRET if set, else derived from the admin password so sessions survive restarts without extra setup."""
        import hashlib
        return (self._session_secret or hashlib.sha256(("fhi-session|" + self.basic_auth_password).encode()).hexdigest()).encode()


settings = Settings()
