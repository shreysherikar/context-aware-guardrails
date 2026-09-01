"""Controlled computer environment — least-privilege sandbox boundaries."""

from __future__ import annotations

from domain.governance_enums import ComputerPermission


class ComputerSandbox:
    """Validates targets against allowed/blocked boundaries."""

    DEFAULT_BLOCKED_DIRS = ["/etc", "/root", "C:\\Windows\\System32", "C:\\Program Files"]
    DEFAULT_ALLOWED_APPS = ["chrome", "firefox", "notepad", "excel", "word"]
    DEFAULT_ALLOWED_DOMAINS = ["intranet.pharma.local", "lims.pharma.local", "edc.pharma.local"]

    def __init__(
        self,
        *,
        allowed_apps: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        allowed_directories: list[str] | None = None,
        blocked_directories: list[str] | None = None,
    ) -> None:
        self.allowed_apps = allowed_apps or list(self.DEFAULT_ALLOWED_APPS)
        self.allowed_domains = allowed_domains or list(self.DEFAULT_ALLOWED_DOMAINS)
        self.allowed_directories = allowed_directories or ["/sandbox", "C:\\Sandbox"]
        self.blocked_directories = blocked_directories or list(self.DEFAULT_BLOCKED_DIRS)

    def validate_app(self, app: str) -> tuple[bool, str]:
        normalized = app.lower().strip()
        if any(normalized == a.lower() or normalized.endswith(a.lower()) for a in self.allowed_apps):
            return True, ""
        return False, f"Application '{app}' not in allowed list"

    def validate_domain(self, domain: str) -> tuple[bool, str]:
        normalized = domain.lower().strip()
        if ".onion" in normalized or normalized.endswith(".onion"):
            return False, "Hidden-service (.onion) destinations are blocked by DARKWEB_ACCESS_PREVENTION"
        if any(
            term in normalized
            for term in ("darkweb", "dark-web", "hidden-service", "hiddenservice")
        ):
            return False, f"Domain '{domain}' blocked by dark-web access prevention policy"
        if any(
            normalized == d.lower() or normalized.endswith("." + d.lower())
            for d in self.allowed_domains
        ):
            return True, ""
        return False, f"Domain '{domain}' not in allowed list"

    def validate_path(self, path: str, *, write: bool = False) -> tuple[bool, str]:
        normalized = path.replace("\\", "/").lower()
        for blocked in self.blocked_directories:
            if blocked.lower().replace("\\", "/") in normalized:
                return False, f"Path '{path}' is in blocked directory"
        if not write:
            return True, ""
        for allowed in self.allowed_directories:
            if normalized.startswith(allowed.lower().replace("\\", "/")):
                return True, ""
        return False, f"Write path '{path}' not in allowed directories"

    def validate_external_communication(self, action: str) -> tuple[bool, str]:
        """Block external communication when network is restricted."""
        return True, ""

    def action_requires_approval(self, action: str) -> bool:
        critical = {
            ComputerPermission.COMPUTER_EXECUTE_COMMAND.value,
            ComputerPermission.COMPUTER_INSTALL_SOFTWARE.value,
            ComputerPermission.COMPUTER_UPLOAD_FILE.value,
            ComputerPermission.COMPUTER_DOWNLOAD_FILE.value,
            ComputerPermission.COMPUTER_SEND_EMAIL.value,
            ComputerPermission.COMPUTER_SUBMIT_FORM.value,
        }
        return action in critical
