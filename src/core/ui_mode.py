"""
UI modes — progressive disclosure for Lucky Patcher style workflows.

Three modes, mirroring the mobile app's beginner-friendly design:

- BEGINNER: only the safest, most common actions are shown. Every visible
  action carries an explanatory tooltip and dangerous operations are hidden
  behind the mode switch.
- MITIGATIVE: recommended actions stay visible but risky ones are annotated
  with a caution badge, and a backup-first reminder is shown before patching.
- ADVANCED: every action and option is available, with no extra hand-holding.

The mode is process-global so dialogs that are created later (Menu of
Patches, Rebuild Tree, ...) automatically follow the current selection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.i18n import t


class UIMode(Enum):
    BEGINNER = "beginner"
    MITIGATIVE = "mitigative"
    ADVANCED = "advanced"

    @classmethod
    def from_str(cls, value: str | None) -> UIMode:
        if not value:
            return cls.MITIGATIVE
        normalized = str(value).strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        return cls.MITIGATIVE

    @property
    def label(self) -> str:
        return t(f"ui_mode.{self.value}")


class RiskLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"


@dataclass(frozen=True)
class ActionMeta:
    """Presentation metadata for a single patch action."""

    key: str
    tooltip_key: str
    risk: RiskLevel = RiskLevel.SAFE
    beginner: bool = True
    mitigative: bool = True
    advanced: bool = True
    reversible: bool = True
    extra: dict = field(default_factory=dict)

    def visible_in(self, mode: UIMode) -> bool:
        return {
            UIMode.BEGINNER: self.beginner,
            UIMode.MITIGATIVE: self.mitigative,
            UIMode.ADVANCED: self.advanced,
        }[mode]

    @property
    def tooltip(self) -> str:
        return t(self.tooltip_key)


# Action registry. Keys must match the action strings emitted by
# MenuOfPatchesDialog / AppController.
ACTION_META: dict[str, ActionMeta] = {
    # --- Primary, beginner-safe actions ---
    "open_rebuild": ActionMeta(
        "open_rebuild", "actions.open_rebuild",
        risk=RiskLevel.SAFE,
    ),
    "remove_license": ActionMeta(
        "remove_license", "actions.remove_license",
        risk=RiskLevel.CAUTION,
    ),
    "remove_ads": ActionMeta(
        "remove_ads", "actions.remove_ads",
        risk=RiskLevel.SAFE,
    ),
    "iap_emulation": ActionMeta(
        "iap_emulation", "actions.iap_emulation",
        risk=RiskLevel.CAUTION,
    ),
    # --- Custom patches: visible in mitigative, hidden for beginners ---
    "apply_custom_patch": ActionMeta(
        "apply_custom_patch", "actions.apply_custom_patch",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        reversible=False,
    ),
    # --- Permission editing: mitigative + advanced ---
    "change_perms": ActionMeta(
        "change_perms", "actions.change_perms",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        reversible=False,
    ),
    # --- Resign: mitigative + advanced ---
    "resign": ActionMeta(
        "resign", "actions.resign",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        reversible=False,
    ),
    # --- Secondary / informational ---
    "backup": ActionMeta(
        "backup", "actions.backup",
        risk=RiskLevel.SAFE,
    ),
    "launch": ActionMeta(
        "launch", "actions.launch",
        risk=RiskLevel.SAFE,
    ),
    "info": ActionMeta(
        "info", "actions.info",
        risk=RiskLevel.SAFE,
    ),
    # --- Rebuild sub-modes reachable through the tree dialog ---
    "license:auto": ActionMeta(
        "license:auto", "actions.license_auto",
        risk=RiskLevel.CAUTION,
    ),
    "ads:remove": ActionMeta(
        "ads:remove", "actions.ads_remove",
        risk=RiskLevel.SAFE,
    ),
    "iap:dex": ActionMeta(
        "iap:dex", "actions.iap_dex",
        risk=RiskLevel.CAUTION,
    ),
    "custom": ActionMeta(
        "custom", "actions.custom",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        mitigative=False,
        reversible=False,
    ),
    "sig_disable": ActionMeta(
        "sig_disable", "actions.sig_disable",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        mitigative=False,
        reversible=False,
    ),
    "sig_integrity": ActionMeta(
        "sig_integrity", "actions.sig_integrity",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        mitigative=False,
        reversible=False,
    ),
    "sig_fake_archive": ActionMeta(
        "sig_fake_archive", "actions.sig_fake_archive",
        risk=RiskLevel.DANGEROUS,
        beginner=False,
        mitigative=False,
        reversible=False,
    ),
    "aidl_proxy": ActionMeta(
        "aidl_proxy", "actions.aidl_proxy",
        risk=RiskLevel.CAUTION,
        beginner=False,
    ),
    "clone": ActionMeta(
        "clone", "actions.clone",
        risk=RiskLevel.CAUTION,
        beginner=False,
    ),
}


def action_meta(action: str) -> ActionMeta:
    """Return metadata for an action, defaulting to a safe, visible entry."""
    return ACTION_META.get(
        action,
        ActionMeta(action, f"actions.{action}", risk=RiskLevel.SAFE),
    )


def action_visible(action: str, mode: UIMode) -> bool:
    return action_meta(action).visible_in(mode)


def action_tooltip(action: str) -> str:
    return action_meta(action).tooltip


def action_risk(action: str) -> RiskLevel:
    return action_meta(action).risk


# ============================================================
# GLOBAL MODE STATE
# ============================================================
_current_mode: UIMode = UIMode.MITIGATIVE


def get_ui_mode() -> UIMode:
    return _current_mode


def set_ui_mode(mode: UIMode | str) -> UIMode:
    global _current_mode
    _current_mode = mode if isinstance(mode, UIMode) else UIMode.from_str(mode)
    return _current_mode


def reset_ui_mode() -> UIMode:
    return set_ui_mode(UIMode.MITIGATIVE)
