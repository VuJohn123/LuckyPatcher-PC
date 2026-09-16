"""
Backward-compat shim — re-export từ classifier + analyzer.
Code cũ import từ scanner.app_classifier vẫn hoạt động.
"""
from scanner.classifier import AppClassifier
from scanner.analyzer import AppDeepAnalyzer

__all__ = ["AppClassifier", "AppDeepAnalyzer"]