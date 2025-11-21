# -*- coding: utf-8 -*-
"""
Platform compatibility utilities for LandTalk.AI plugin

This module provides platform-specific utilities for cross-platform compatibility.
"""

import platform
from qgis.PyQt.QtWidgets import QDockWidget

# Detect macOS for DPI scaling
IS_MACOS = platform.system() == 'Darwin'

# Font size multiplier for macOS high-DPI displays
FONT_SCALE = 1.4 if IS_MACOS else 1.0


def scale_font(base_size):
    """Scale font size based on platform

    Args:
        base_size: Base font size in points

    Returns:
        Scaled font size as string (e.g., "12pt")
    """
    return f"{int(base_size * FONT_SCALE)}pt"


def resolve_dock_widget_features():
    """Resolve dock widget features for PyQt5/PyQt6 compatibility

    Returns:
        Combined dock widget features (movable, floatable, closable) or None
    """
    def _resolve_feature(owner, candidate_names):
        """Helper to resolve a feature by trying multiple names"""
        for name in candidate_names:
            if hasattr(owner, name):
                return getattr(owner, name)
        # Fallback: fuzzy match by substring
        for attr in dir(owner):
            for name in candidate_names:
                if name.lower() in attr.lower():
                    return getattr(owner, attr)
        return None

    feature_owners = [QDockWidget]
    feature_enum = getattr(QDockWidget, 'DockWidgetFeature', None)
    if feature_enum is not None:
        feature_owners.append(feature_enum)

    movable_feature = None
    floatable_feature = None
    closable_feature = None

    for owner in feature_owners:
        if movable_feature is None:
            movable_feature = _resolve_feature(owner, ['DockWidgetMovable', 'Movable'])
        if floatable_feature is None:
            floatable_feature = _resolve_feature(owner, ['DockWidgetFloatable', 'Floatable'])
        if closable_feature is None:
            closable_feature = _resolve_feature(owner, ['DockWidgetClosable', 'Closable'])

    # Combine all available features using bitwise OR
    features_list = []
    if movable_feature is not None:
        features_list.append(movable_feature)
    if floatable_feature is not None:
        features_list.append(floatable_feature)
    if closable_feature is not None:
        features_list.append(closable_feature)

    if features_list:
        combined_features = features_list[0]
        for feature in features_list[1:]:
            combined_features = combined_features | feature
        return combined_features

    return None
