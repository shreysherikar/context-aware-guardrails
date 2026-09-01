"""Computer-use engine — governed action execution in sandbox."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from domain.enums import RiskLevel
from domain.governance_enums import (
    ComputerPermission,
    GovernanceDecision,
    SecurityEventCategory,
)
from domain.governance_models import (
    AgentRegistryEntry,
    ComputerActionResult,
    GovernedRequest,
    SafeRewriteResult,
)
from services.governance.computer_use.action_log import ComputerActionLogStore
from services.governance.computer_use.environments import get_environment
from services.cyber_safety.darkweb import assess_darkweb_content, extract_text_for_assessment
from services.governance.computer_use.sandbox import ComputerSandbox
from services.governance.computer_use.sessions import ComputerSessionStore
from services.governance.kill_switch import KillSwitch, get_kill_switch
from services.governance.risk import RISK_ORDER

if TYPE_CHECKING:
    from services.governance.approval import ApprovalStore
    from services.governance.security_events import SecurityEventStore

logger = logging.getLogger(__name__)

_SCREEN_CONTENT_KEYS = ("screen_text", "ocr_text", "vision_text", "screenshot_text", "text", "content")


def _extract_screen_content(arguments: dict, *, purpose: str = "") -> str:
    """Extract untrusted visual/screen text — excludes action payloads like command/domain."""
    parts: list[str] = []
    for key in _SCREEN_CONTENT_KEYS:
        val = arguments.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    if not parts and purpose.strip():
        parts.append(purpose)
    return " ".join(parts)

COMPUTER_ACTION_RISK: dict[str, RiskLevel] = {
    ComputerPermission.COMPUTER_VIEW_SCREEN.value: RiskLevel.LOW,
    ComputerPermission.COMPUTER_SCROLL.value: RiskLevel.LOW,
    ComputerPermission.COMPUTER_OPEN_APPLICATION.value: RiskLevel.LOW,
    ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value: RiskLevel.LOW,
    ComputerPermission.COMPUTER_CLICK.value: RiskLevel.MEDIUM,
    ComputerPermission.COMPUTER_TYPE.value: RiskLevel.MEDIUM,
    ComputerPermission.COMPUTER_MOUSE.value: RiskLevel.MEDIUM,
    ComputerPermission.COMPUTER_KEYBOARD.value: RiskLevel.MEDIUM,
    ComputerPermission.COMPUTER_READ_FILE.value: RiskLevel.MEDIUM,
    ComputerPermission.COMPUTER_WRITE_FILE.value: RiskLevel.MEDIUM,
    ComputerPermission.COMPUTER_UPLOAD_FILE.value: RiskLevel.HIGH,
    ComputerPermission.COMPUTER_DOWNLOAD_FILE.value: RiskLevel.HIGH,
    ComputerPermission.COMPUTER_SEND_MESSAGE.value: RiskLevel.HIGH,
    ComputerPermission.COMPUTER_SEND_EMAIL.value: RiskLevel.HIGH,
    ComputerPermission.COMPUTER_SUBMIT_FORM.value: RiskLevel.HIGH,
    ComputerPermission.COMPUTER_EXECUTE_COMMAND.value: RiskLevel.CRITICAL,
    ComputerPermission.COMPUTER_INSTALL_SOFTWARE.value: RiskLevel.CRITICAL,
}

# Per-session rate limit: max actions per minute
_SESSION_RATE_LIMIT = 60


class ComputerUseEngine:
    """Governed computer-use — every action passes policy + rewrite + risk + audit."""

    def __init__(
        self,
        sessions: ComputerSessionStore | None = None,
        action_log: ComputerActionLogStore | None = None,
        kill_switch: KillSwitch | None = None,
        approvals: ApprovalStore | None = None,
        events: SecurityEventStore | None = None,
    ) -> None:
        self._sessions = sessions or ComputerSessionStore()
        self._action_log = action_log or ComputerActionLogStore()
        self._kill_switch = kill_switch or get_kill_switch()
        self._approvals = approvals
        self._events = events
        self._rate_window: dict[str, list[float]] = {}

    @property
    def session_store(self) -> ComputerSessionStore:
        return self._sessions

    @property
    def action_log(self) -> ComputerActionLogStore:
        return self._action_log

    def create_session(
        self,
        agent: AgentRegistryEntry,
        *,
        user_id: str | None = None,
        environment_id: str = "sandbox-default",
        allowed_domains: list[str] | None = None,
        allowed_apps: list[str] | None = None,
        allowed_directories: list[str] | None = None,
        blocked_directories: list[str] | None = None,
        allowed_actions: list[str] | None = None,
        risk_limit: RiskLevel | None = None,
        ttl_minutes: int | None = None,
    ):
        env = get_environment(environment_id)
        perms = set(agent.computer_use_permissions) or {
            p for p in agent.permissions if p.startswith("COMPUTER_")
        }
        default_actions = list(perms) or (env.default_actions if env else [])

        return self._sessions.create(
            agent_id=agent.agent_id,
            user_id=user_id,
            environment_id=environment_id,
            allowed_domains=allowed_domains or (env.allowed_domains if env else []),
            allowed_apps=allowed_apps or (env.allowed_apps if env else []),
            allowed_directories=allowed_directories or (env.allowed_directories if env else []),
            blocked_directories=blocked_directories or (env.blocked_directories if env else []),
            allowed_actions=allowed_actions or default_actions,
            risk_limit=risk_limit or (env.default_risk_limit if env else agent.max_risk_level),
            ttl_minutes=ttl_minutes,
        )

    def execute_action(
        self,
        session_id: str,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        rewrite_result: SafeRewriteResult | None = None,
        approval_id: str | None = None,
    ) -> ComputerActionResult:
        """Validate and execute a computer action — each action is independently governed."""
        request_id = governed.request_id
        action = governed.action
        target = governed.resource or governed.arguments.get("target")
        risk = COMPUTER_ACTION_RISK.get(action, RiskLevel.HIGH)

        def _finish(
            result: ComputerActionResult,
            *,
            executed: bool = False,
        ) -> ComputerActionResult:
            log = self._action_log.append(
                session_id=session_id,
                agent_id=agent.agent_id,
                request_id=request_id,
                action=action,
                target=target,
                decision=result.decision,
                risk_level=risk,
                executed=executed or result.executed,
                reason=result.reason,
                approval_id=result.approval_id,
            )
            result.log_id = log.log_id
            result.risk_level = risk
            if result.decision == GovernanceDecision.BLOCK and self._events:
                self._events.record(
                    agent_id=agent.agent_id,
                    category=SecurityEventCategory.TOOL_ABUSE,
                    description=f"Computer action blocked: {action} — {result.reason}",
                    request_id=request_id,
                    policy_decision=GovernanceDecision.BLOCK,
                    evidence={"session_id": session_id, "target": target},
                )
            return result

        # Kill switch
        allowed, reason = self._kill_switch.check()
        if not allowed:
            return _finish(
                self._blocked(session_id, request_id, action, target, reason or "EMERGENCY_STOP", risk)
            )

        session = self._sessions.get(session_id)
        if session is None:
            return _finish(
                self._blocked(session_id, request_id, action, target, "Session expired or not found", risk)
            )

        if session.agent_id != agent.agent_id:
            return _finish(
                self._blocked(session_id, request_id, action, target, "Session agent mismatch", risk)
            )

        # Rate limiting
        if not self._check_rate_limit(session_id):
            return _finish(
                self._blocked(session_id, request_id, action, target, "Session rate limit exceeded", risk)
            )

        if rewrite_result and rewrite_result.blocked:
            self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
            return _finish(ComputerActionResult(
                session_id=session_id,
                request_id=request_id,
                action=action,
                target=target,
                decision=GovernanceDecision.BLOCK,
                risk_level=risk,
                reason="Safe rewrite blocked action arguments",
                rewrite_result=rewrite_result,
            ))

        # Multimodal screen-content check (visual instructions only — not action payloads)
        screen_text = _extract_screen_content(
            governed.arguments,
            purpose=governed.purpose or "",
        )
        from services.multimodal.classifier import assess_multimodal_content
        if screen_text.strip():
            screen_mm = assess_multimodal_content(
                screen_text,
                source="screen",
                is_screen=True,
            )
            if screen_mm.decision == "BLOCK" or screen_mm.computer_use_manipulation:
                self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
                if self._events and screen_mm.security_event_category:
                    try:
                        cat = SecurityEventCategory(screen_mm.security_event_category)
                    except ValueError:
                        cat = SecurityEventCategory.COMPUTER_USE_MANIPULATION
                    self._events.record(
                        agent_id=agent.agent_id,
                        category=cat,
                        description=f"Screen manipulation blocked: {action}",
                        request_id=request_id,
                        policy_decision=GovernanceDecision.BLOCK,
                        evidence={"session_id": session_id},
                    )
                return _finish(self._blocked(
                    session_id, request_id, action, target,
                    "Multimodal screen content blocked — visual instructions are untrusted", risk,
                ))

        cu_text = extract_text_for_assessment(
            governed.arguments,
            action=action,
            target=target or "",
            resource=governed.resource or "",
        )
        darkweb = assess_darkweb_content(
            cu_text or governed.purpose or action,
            is_computer_action=True,
        )
        if darkweb.decision == "BLOCK":
            self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
            if self._events and darkweb.security_event_category:
                try:
                    cat = SecurityEventCategory(darkweb.security_event_category)
                except ValueError:
                    cat = SecurityEventCategory.DARKWEB_COMPUTER_USE_ATTEMPT
                self._events.record(
                    agent_id=agent.agent_id,
                    category=cat,
                    description=f"Computer action blocked by dark-web policy: {action}",
                    request_id=request_id,
                    policy_decision=GovernanceDecision.BLOCK,
                    evidence={"session_id": session_id, "target": target},
                )
            return _finish(self._blocked(
                session_id, request_id, action, target,
                "DARKWEB_ACCESS_PREVENTION: computer action blocked", risk,
            ))

        computer_perms = set(agent.computer_use_permissions) or {
            p for p in agent.permissions if p.startswith("COMPUTER_")
        }
        if action not in computer_perms:
            self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
            return _finish(self._blocked(
                session_id, request_id, action, target,
                f"Agent lacks computer permission: {action}", risk,
            ))

        if session.allowed_actions and action not in session.allowed_actions:
            self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
            return _finish(self._blocked(
                session_id, request_id, action, target,
                f"Action {action} not allowed in session", risk,
            ))

        if RISK_ORDER.index(risk) > RISK_ORDER.index(session.risk_limit):
            self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
            return _finish(ComputerActionResult(
                session_id=session_id,
                request_id=request_id,
                action=action,
                target=target,
                decision=GovernanceDecision.BLOCK,
                risk_level=risk,
                reason=f"Action risk {risk.value} exceeds session limit {session.risk_limit.value}",
            ))

        sandbox = ComputerSandbox(
            allowed_apps=session.allowed_apps or None,
            allowed_domains=session.allowed_domains or None,
            allowed_directories=session.allowed_directories or None,
            blocked_directories=session.blocked_directories or None,
        )
        sandbox_ok, sandbox_reason = self._validate_sandbox(sandbox, action, target, governed.arguments)
        if not sandbox_ok:
            self._sessions.update_state(session_id, actions_blocked=session.actions_blocked + 1)
            return _finish(self._blocked(session_id, request_id, action, target, sandbox_reason, risk))

        needs_approval = (
            risk == RiskLevel.CRITICAL
            or sandbox.action_requires_approval(action)
            or risk == RiskLevel.HIGH
        )

        if needs_approval:
            if approval_id and self._approvals and self._approvals.is_valid(approval_id):
                approval = self._approvals.get(approval_id)
                if approval and approval.request_id != request_id:
                    return _finish(self._blocked(
                        session_id, request_id, action, target,
                        "Approval not bound to this request", risk,
                    ))
            else:
                created_approval_id = None
                if self._approvals:
                    approval = self._approvals.create(
                        requesting_agent=agent.agent_id,
                        requested_action=action,
                        reason=f"High-risk computer action: {action} on {target or 'unknown target'}",
                        risk_level=risk,
                        affected_resource=target,
                        request_id=request_id,
                        user_id=governed.user_id,
                    )
                    created_approval_id = approval.approval_request_id
                return _finish(ComputerActionResult(
                    session_id=session_id,
                    request_id=request_id,
                    action=action,
                    target=target,
                    decision=GovernanceDecision.HUMAN_APPROVAL_REQUIRED,
                    risk_level=risk,
                    approval_required=True,
                    approval_id=created_approval_id,
                    reason=f"Human approval required for {action} (risk: {risk.value})",
                    rewrite_result=rewrite_result,
                ))

        # Simulated execution in sandbox
        self._sessions.update_state(
            session_id,
            actions_executed=session.actions_executed + 1,
            current_application=governed.arguments.get("application"),
            current_domain=governed.arguments.get("domain") or target,
        )
        logger.info(
            "Computer action executed (sandbox): session=%s action=%s target=%s",
            session_id, action, target,
        )
        return _finish(ComputerActionResult(
            session_id=session_id,
            request_id=request_id,
            action=action,
            target=target,
            decision=GovernanceDecision.ALLOW,
            risk_level=risk,
            executed=True,
            reason="Action permitted in sandbox",
            approval_id=approval_id,
            rewrite_result=rewrite_result,
        ), executed=True)

    def stop_session(self, session_id: str):
        return self._sessions.stop(session_id)

    def get_session(self, session_id: str):
        return self._sessions.get(session_id)

    def list_active_sessions(self):
        return self._sessions.list_active()

    def list_action_log(self, session_id: str | None = None, limit: int = 50):
        if session_id:
            return self._action_log.list_for_session(session_id, limit)
        return self._action_log.list_recent(limit)

    def _validate_sandbox(
        self,
        sandbox: ComputerSandbox,
        action: str,
        target: str | None,
        arguments: dict,
    ) -> tuple[bool, str]:
        if action == ComputerPermission.COMPUTER_OPEN_APPLICATION.value:
            return sandbox.validate_app(target or arguments.get("application", ""))
        if action == ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value:
            domain = target or arguments.get("domain", "") or arguments.get("url", "")
            return sandbox.validate_domain(domain)
        if action in (
            ComputerPermission.COMPUTER_READ_FILE.value,
            ComputerPermission.COMPUTER_WRITE_FILE.value,
            ComputerPermission.COMPUTER_UPLOAD_FILE.value,
            ComputerPermission.COMPUTER_DOWNLOAD_FILE.value,
        ):
            path = target or arguments.get("path", "")
            write = action in (
                ComputerPermission.COMPUTER_WRITE_FILE.value,
                ComputerPermission.COMPUTER_UPLOAD_FILE.value,
            )
            return sandbox.validate_path(path, write=write)
        if action in (
            ComputerPermission.COMPUTER_SEND_EMAIL.value,
            ComputerPermission.COMPUTER_SEND_MESSAGE.value,
        ):
            return sandbox.validate_external_communication(action)
        return True, ""

    def _blocked(
        self,
        session_id: str,
        request_id: str,
        action: str,
        target: str | None,
        reason: str,
        risk: RiskLevel = RiskLevel.MEDIUM,
    ) -> ComputerActionResult:
        return ComputerActionResult(
            session_id=session_id,
            request_id=request_id,
            action=action,
            target=target,
            decision=GovernanceDecision.BLOCK,
            risk_level=risk,
            reason=reason,
        )

    def _check_rate_limit(self, session_id: str) -> bool:
        now = time.time()
        window = self._rate_window.setdefault(session_id, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= _SESSION_RATE_LIMIT:
            return False
        window.append(now)
        return True
