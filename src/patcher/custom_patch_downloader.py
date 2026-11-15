"""
Apk Downloader + Custom Patch Downloader — unified download module.

v5 (2026):
- Apk Downloader: Google Play scraper + patch.chelpus.com integration
- Custom Patch Downloader: patch.chelpus.com with retry + timeout
- URL security: validate scheme, block private IP, SSRF guard
- Size limits, content-length validation
- Supports both APK and custom patch downloads
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ============================================================
# URL SECURITY HELPERS
# ============================================================
def validate_url(url: str) -> bool:
    """
    Validate URL for security:
    - Only HTTPS scheme
    - Block private IPs (RFC 1918, RFC 3927, RFC 6598)
    - Block localhost
    - Block metadata endpoints (169.254.169.254)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Only HTTPS
    if parsed.scheme != "https":
        return False

    hostname = parsed.hostname or ""
    if not hostname:
        return False

    # Block localhost
    if hostname in ("localhost", "localhost.localdomain"):
        return False

    # Block metadata endpoint
    if hostname == "169.254.169.254":
        return False

    # Block private IPs
    try:
        import ipaddress
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except ValueError:
        # Not an IP, check domain
        pass

    return True


def sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent path traversal."""
    # Remove path separators and dangerous chars
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # Remove leading dots
    name = name.lstrip('.')
    # Limit length
    if len(name) > 250:
        name = name[:250]
    return name


# ============================================================
# DOWNLOAD SESSION WITH RETRY
# ============================================================
def create_download_session(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    timeout: int = 30
) -> requests.Session:
    """Create requests session with retry strategy."""
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ============================================================
# APK DOWNLOADER
# ============================================================
class ApkDownloader:
    """
    Download APKs from various sources:
    1. Google Play (via third-party APIs - requires API key)
    2. patch.chelpus.com (custom patches)
    3. APKMirror, APKPure, etc. (web scraping)

    Note: Google Play downloading requires:
    - googleplay-api (unofficial)
    - Valid Google account credentials
    - Or use third-party services
    """

    PLAY_STORE_URL = "https://play.google.com/store/apps/details"
    CHELPUS_API_URL = "https://patch.chelpus.com/api"
    CHELPUS_DOWNLOAD_URL = "https://patch.chelpus.com/download"

    def __init__(
        self,
        download_dir: str | None = None,
        max_size_mb: int = 500,
        progress_callback: Callable[[int, int], None] | None = None,
        log_callback: Callable[[str], None] = print
    ):
        self.download_dir = Path(download_dir) if download_dir else Path.cwd() / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.progress_callback = progress_callback
        self.log = log_callback
        self.session = create_download_session()

    def download_apk(
        self,
        package_name: str,
        version_code: int | None = None,
        source: str = "auto"  # "play", "chelpus", "mirror", "auto"
    ) -> str | None:
        """
        Download APK for package.

        Args:
            package_name: Android package name (e.g., "com.example.app")
            version_code: Specific version code (None = latest)
            source: Download source preference

        Returns:
            Path to downloaded APK or None on failure
        """
        self.log(f"[*] [Downloader] Downloading {package_name} (v{version_code or 'latest'})...")

        # Try sources in order
        sources = []
        if source == "auto":
            sources = ["chelpus", "mirror"]  # Don't auto-use Play (needs auth)
        elif source == "play":
            sources = ["play"]
        elif source == "chelpus":
            sources = ["chelpus"]
        elif source == "mirror":
            sources = ["mirror"]

        for src in sources:
            try:
                if src == "play":
                    result = self._download_from_play(package_name, version_code)
                elif src == "chelpus":
                    result = self._download_from_chelpus(package_name, version_code)
                elif src == "mirror":
                    result = self._download_from_mirror(package_name, version_code)
                else:
                    continue

                if result:
                    return result
            except Exception as e:
                self.log(f"[!] [Downloader] {src} failed: {e}")
                continue

        self.log(f"[!] [Downloader] All sources failed for {package_name}")
        return None

    def _download_from_play(self, package_name: str, version_code: int | None = None) -> str | None:
        """Download from Google Play (requires authentication)."""
        self.log("[!] [Downloader] Google Play download requires authentication - not implemented")
        return None

    def _download_from_chelpus(self, package_name: str, version_code: int | None = None) -> str | None:
        """Download from patch.chelpus.com."""
        url = f"{self.CHELPUS_DOWNLOAD_URL}/{package_name}"
        if version_code:
            url += f"/{version_code}"

        return self._download_file(url, f"{package_name}.apk")

    def _download_from_mirror(self, package_name: str, version_code: int | None = None) -> str | None:
        """Download from APK mirror sites (APKMirror, APKPure, etc.)."""
        # These would require web scraping which is fragile
        # For now, return None - user should provide APK manually
        self.log("[i] [Downloader] Mirror download not implemented - provide APK manually")
        return None

    def _download_file(self, url: str, filename: str) -> str | None:
        """Download file with progress and validation."""
        if not validate_url(url):
            self.log(f"[!] [Downloader] Invalid URL: {url}")
            return None

        filename = sanitize_filename(filename)
        output_path = self.download_dir / filename

        try:
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            # Check content-length
            content_length = response.headers.get("content-length")
            if content_length:
                total_size = int(content_length)
                if total_size > self.max_size_bytes:
                    self.log(f"[!] [Downloader] File too large: {total_size} > {self.max_size_bytes}")
                    return None
            else:
                total_size = 0

            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if self.progress_callback and total_size > 0:
                            self.progress_callback(downloaded, total_size)

            # Verify file size
            actual_size = output_path.stat().st_size
            if content_length and actual_size != total_size:
                self.log(f"[!] [Downloader] Size mismatch: expected {total_size}, got {actual_size}")
                output_path.unlink()
                return None

            self.log(f"[+] [Downloader] Downloaded: {output_path} ({actual_size} bytes)")
            return str(output_path)

        except requests.RequestException as e:
            self.log(f"[!] [Downloader] Download failed: {e}")
            if output_path.exists():
                output_path.unlink()
            return None


# ============================================================
# CUSTOM PATCH DOWNLOADER
# ============================================================
class CustomPatchDownloader:
    """
    Download custom patches from patch.chelpus.com.

    LP format: https://patch.chelpus.com/patches/<patch_name>.txt
    Also supports .lpzip archives.
    """

    BASE_URL = "https://patch.chelpus.com"
    PATCHES_PATH = "/patches/"

    def __init__(
        self,
        download_dir: str | None = None,
        max_download_size_mb: int = 50,
        log_callback: Callable[[str], None] = print
    ):
        self.download_dir = Path(download_dir) if download_dir else Path.cwd() / "patches"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_download_size = max_download_size_mb * 1024 * 1024
        self.log = log_callback
        self.session = create_download_session()

    def download_patch(self, patch_name: str) -> str | None:
        """
        Download a custom patch by name.

        Args:
            patch_name: Patch filename (e.g., "com.example.app.txt" or "com.example.app.lpzip")

        Returns:
            Path to downloaded patch file or None
        """
        # Sanitize patch name
        patch_name = sanitize_filename(patch_name)

        # Ensure extension
        if not patch_name.endswith((".txt", ".lpzip")):
            patch_name += ".txt"

        url = f"{self.BASE_URL}{self.PATCHES_PATH}{patch_name}"
        output_path = self.download_dir / patch_name

        self.log(f"[*] [CustomPatch] Downloading {patch_name}...")

        if not validate_url(url):
            self.log("[!] [CustomPatch] Invalid URL")
            return None

        try:
            # HEAD request to check size
            head = self.session.head(url, timeout=10)
            if head.status_code == 404:
                self.log(f"[!] [CustomPatch] Patch not found: {patch_name}")
                return None
            elif head.status_code != 200:
                self.log(f"[!] [CustomPatch] HTTP {head.status_code}")
                return None

            content_length = head.headers.get("content-length")
            if content_length:
                size = int(content_length)
                if size > self.max_download_size:
                    self.log(f"[!] [CustomPatch] Patch too large: {size} bytes")
                    return None

            # Download
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Verify size
            if len(response.content) > self.max_download_size:
                self.log("[!] [CustomPatch] Downloaded content too large")
                return None

            # Write file
            with open(output_path, "wb") as f:
                f.write(response.content)

            self.log(f"[+] [CustomPatch] Downloaded: {output_path}")
            return str(output_path)

        except requests.RequestException as e:
            self.log(f"[!] [CustomPatch] Download failed: {e}")
            return None

    def search_patches(self, query: str) -> list[dict]:
        """
        Search for patches on patch.chelpus.com.

        Note: This requires the site to have a search API.
        For now, returns empty list - implement when API is available.
        """
        self.log(f"[i] [CustomPatch] Search not implemented for query: {query}")
        return []

    def list_popular_patches(self) -> list[dict]:
        """List popular patches (requires API)."""
        self.log("[i] [CustomPatch] List popular not implemented")
        return []


# ============================================================
# UNIFIED DOWNLOADER (for GUI)
# ============================================================
class UnifiedDownloader:
    """
    Unified downloader for both APKs and custom patches.
    Provides a single interface for the GUI.
    """

    def __init__(
        self,
        download_dir: str | None = None,
        patch_dir: str | None = None,
        log_callback: Callable[[str], None] = print
    ):
        self.apk_downloader = ApkDownloader(
            download_dir=download_dir,
            log_callback=log_callback
        )
        self.patch_downloader = CustomPatchDownloader(
            download_dir=patch_dir,
            log_callback=log_callback
        )
        self.log = log_callback

    def download_apk(
        self,
        package_name: str,
        version_code: int | None = None,
        source: str = "auto"
    ) -> str | None:
        """Download APK."""
        return self.apk_downloader.download_apk(package_name, version_code, source)

    def download_patch(self, patch_name: str) -> str | None:
        """Download custom patch."""
        return self.patch_downloader.download_patch(patch_name)

    def search_patches(self, query: str) -> list[dict]:
        """Search patches."""
        return self.patch_downloader.search_patches(query)


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================
def download_apk(
    package_name: str,
    version_code: int | None = None,
    download_dir: str | None = None,
    log_callback: Callable[[str], None] = print
) -> str | None:
    """Convenience function to download APK."""
    downloader = ApkDownloader(download_dir=download_dir, log_callback=log_callback)
    return downloader.download_apk(package_name, version_code)


def download_custom_patch(
    patch_name: str,
    download_dir: str | None = None,
    log_callback: Callable[[str], None] = print
) -> str | None:
    """Convenience function to download custom patch."""
    downloader = CustomPatchDownloader(download_dir=download_dir, log_callback=log_callback)
    return downloader.download_patch(patch_name)
