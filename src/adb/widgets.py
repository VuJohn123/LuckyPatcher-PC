"""
ADB Widget Manager — deploy home screen widgets (LP mobile feature).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .orchestrator import ADBOperation, ADBOrchestrator, ADBResult
from .shell import ADBShell

logger = logging.getLogger(__name__)


@dataclass
class ADBWidgetResult:
    """Result of Widget deployment."""
    success: bool
    widget_apk_path: str = ""
    package_name: str = "ru.aaaaaban.installer.widget"
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __bool__(self) -> bool:
        return self.success


class ADBWidgetManager:
    """
    Widget Manager — deploys Lucky Patcher widgets to home screen (LP mobile feature).

    This implements the LP mobile "Widgets" feature:
    1. Build/install widget provider APK (AppWidgetProvider)
    2. Widgets provide quick access to:
       - Patch selected app
       - View patch status
       - Enable/disable patches
       - Open LP main app
    3. Widgets communicate with main LP app via broadcasts/intents

    Note: Widgets are Android UI components. Deploying them requires:
    - Installing a widget provider APK
    - User manually adding widget to home screen
    - Main LP app must be installed to handle widget actions
    """

    def __init__(self, orchestrator: ADBOrchestrator, log_callback: Callable[[str], None] = print):
        self.orchestrator = orchestrator
        self.log = log_callback
        self.device = orchestrator.device
        self.shell = ADBShell(self.device.serial, self.orchestrator.adb_path)
        self.working_dir = "/data/local/tmp/lp_widgets"

    def check_requirements(self) -> ADBResult:
        """Check if widgets can be deployed."""
        self.log("[*] [Widgets] Checking requirements...")

        # Need main LP app installed for widgets to work
        pm_result = self.orchestrator.shell("pm list packages | grep luckypatcher")
        if not pm_result.success or not pm_result.stdout.strip():
            self.log("[i] [Widgets] Lucky Patcher main app not found - widgets need LP installed")

        self.log("[*] [Widgets] Requirements OK")
        return ADBResult(success=True, operation=ADBOperation.SHELL)

    def prepare_dirs(self) -> ADBResult:
        """Create working directory."""
        return self.orchestrator.shell(f"mkdir -p {self.working_dir}", require_root=True)

    def build_widget_apk(self) -> ADBResult:
        """
        Build widget provider APK.

        Note: In real implementation, this would be a pre-built APK
        included with LP-PC Suite. For now, we generate a minimal one.
        """
        self.log("[*] [Widgets] Building widget APK...")

        # This is a placeholder - real implementation would:
        # 1. Have a pre-built widget APK in assets/
        # 2. Or build it dynamically with aapt2/zipalign
        # 3. Push to device

        self.log("[!] [Widgets] Widget APK must be pre-built and provided")
        self.log("[!] [Widgets] Expected: assets/lp_widget.apk")

        return ADBResult(success=False, operation=ADBOperation.SHELL,
                       error="Widget APK not provided")

    def install_widget_apk(self, apk_path: str) -> ADBResult:
        """Install widget provider APK."""
        self.log(f"[*] [Widgets] Installing widget APK: {apk_path}")

        # Install with -r (replace) and -g (grant permissions)
        result = self.orchestrator.install(apk_path, replace=True, grant_permissions=True)

        if result.success:
            self.log("[+] [Widgets] Widget provider installed")
        else:
            self.log(f"[!] [Widgets] Install failed: {result.error}")

        return result

    def enable_widget(self, component_name: str) -> ADBResult:
        """Enable widget component (usually automatic after install)."""
        return self.orchestrator.shell(f"pm enable {component_name}")

    def list_widgets(self) -> ADBResult:
        """List installed widgets."""
        return self.orchestrator.shell("pm list packages -d | grep widget")

    def send_widget_update(self, action: str, package: str | None = None, mode: str | None = None) -> ADBResult:
        """Send broadcast to update widget state."""
        intent = f"am broadcast -a {action}"
        if package:
            intent += f" --es package {package}"
        if mode:
            intent += f" --es mode {mode}"
        return self.orchestrator.shell(intent)

    def create_widget_apk_source(self) -> str:
        """
        Generate widget provider source code (for reference).

        Returns Kotlin/Java source for AppWidgetProvider.
        """
        kotlin_source = """
// Lucky Patcher Widget Provider
// Place in: app/src/main/java/com/luckypatcher/widget/LPWidgetProvider.kt

package com.luckypatcher.widget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

class LPWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId)
        }
    }

    private fun updateWidget(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
        val views = RemoteViews(context.packageName, R.layout.lp_widget)

        // Set click listeners for widget buttons
        val patchIntent = Intent(context, LPWidgetProvider::class.java)
        patchIntent.action = "com.luckypatcher.widget.PATCH_SELECTED"
        patchIntent.putExtra("widget_id", appWidgetId)
        val patchPending = PendingIntent.getBroadcast(context, 0, patchIntent, PendingIntent.FLAG_IMMUTABLE)
        views.setOnClickPendingIntent(R.id.btn_patch, patchPending)

        val statusIntent = Intent(context, LPWidgetProvider::class.java)
        statusIntent.action = "com.luckypatcher.widget.SHOW_STATUS"
        val statusPending = PendingIntent.getBroadcast(context, 1, statusIntent, PendingIntent.FLAG_IMMUTABLE)
        views.setOnClickPendingIntent(R.id.btn_status, statusPending)

        val openIntent = Intent("com.luckypatcher.MAIN")
        openIntent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
        val openPending = PendingIntent.getActivity(context, 2, openIntent, PendingIntent.FLAG_IMMUTABLE)
        views.setOnClickPendingIntent(R.id.btn_open, openPending)

        appWidgetManager.updateAppWidget(appWidgetId, views)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            "com.luckypatcher.widget.PATCH_SELECTED" -> {
                // Show app picker to select target app
                showAppPicker(context)
            }
            "com.luckypatcher.widget.SHOW_STATUS" -> {
                // Show patch status notification
                showStatus(context)
            }
        }
    }

    private fun showAppPicker(context: Context) {
        // Launch LP app with app picker
        val intent = Intent("com.luckypatcher.PICK_APP")
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
        context.startActivity(intent)
    }

    private fun showStatus(context: Context) {
        // Show notification with patch status
    }
}
"""
        return kotlin_source.strip()

    def create_widget_layout(self) -> str:
        """Generate widget layout XML."""
        xml_layout = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="8dp"
    android:background="@drawable/widget_bg">

    <TextView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Lucky Patcher"
        android:textStyle="bold"
        android:textSize="16sp"
        android:gravity="center"
        android:textColor="#FFFFFF"/>

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal"
        android:layout_marginTop="8dp">

        <Button
            android:id="@+id/btn_patch"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="Patch App"
            android:background="@drawable/widget_btn"
            android:textColor="#FFFFFF"/>

        <Button
            android:id="@+id/btn_status"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:layout_marginStart="4dp"
            android:text="Status"
            android:background="@drawable/widget_btn"
            android:textColor="#FFFFFF"/>

    </LinearLayout>

    <Button
        android:id="@+id/btn_open"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="4dp"
        android:text="Open Lucky Patcher"
        android:background="@drawable/widget_btn"
        android:textColor="#FFFFFF"/>

</LinearLayout>
"""
        return xml_layout.strip()

    def deploy(self, widget_apk_path: str | None = None) -> ADBWidgetResult:
        """
        Deploy widgets to device.

        Args:
            widget_apk_path: Path to widget APK on device or PC (if local, will be pushed)
        """
        import time
        start = time.monotonic()

        result = ADBWidgetResult(success=False)

        # 1. Check requirements
        req = self.check_requirements()
        if not req.success:
            result.errors.append(req.error)
            return result

        # 2. Prepare dirs
        self.prepare_dirs()

        # 3. Get widget APK
        if widget_apk_path:
            # Check if local file - push to device
            if Path(widget_apk_path).exists():
                push_result = self.orchestrator.push(widget_apk_path, "/data/local/tmp/lp_widget.apk")
                if not push_result.success:
                    result.errors.append("Failed to push widget APK")
                    return result
                widget_apk_path = "/data/local/tmp/lp_widget.apk"
        else:
            # Try to build (will fail without pre-built APK)
            build_result = self.build_widget_apk()
            if not build_result.success:
                result.errors.append("Widget APK not provided and build failed")
                return result
            widget_apk_path = "/data/local/tmp/lp_widget.apk"

        # 4. Install widget APK
        install_result = self.install_widget_apk(widget_apk_path)
        if not install_result.success:
            result.errors.append(install_result.error or "Widget install failed")
            return result

        result.widget_apk_path = widget_apk_path
        result.success = True
        result.duration_ms = (time.monotonic() - start) * 1000

        self.log("[+] [Widgets] Widget provider deployed")
        self.log("[!] [Widgets] User must add widget to home screen manually")
        self.log("[!] [Widgets] Long-press home screen -> Widgets -> Lucky Patcher")

        return result

    def remove(self) -> ADBResult:
        """Remove widget provider."""
        self.log("[*] [Widgets] Removing widget provider...")

        # Uninstall widget package
        result = self.orchestrator.uninstall("com.luckypatcher.widget")

        if result.success:
            self.log("[+] [Widgets] Removed")
        return result


def deploy_widgets(orchestrator: ADBOrchestrator, widget_apk_path: str | None = None,
                    log_callback: Callable[[str], None] = print) -> ADBWidgetResult:
    """Convenience function for widget deployment."""
    manager = ADBWidgetManager(orchestrator, log_callback)
    return manager.deploy(widget_apk_path)
