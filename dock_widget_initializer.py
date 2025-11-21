# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - Dock Widget Initializer
                                 A QGIS Plugin
 Initialize and configure the dock widget
                              -------------------
        begin                : 2025-01-15
        copyright            : (C) 2025 by Juergen Landauer
        email                : juergen@landauer-ai.de
 ***************************************************************************/

/***************************************************************************
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 3 of the License, or     *
 *   (at your option) any later version.                                   *
 ***************************************************************************/
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDockWidget
from .logging import logger
from .dock_widget import LandTalkDockWidget
from .constants import PluginConstants


class DockWidgetInitializer:
    """Initialize and configure the dock widget for the plugin"""

    def __init__(self, iface, config_manager, plugin_dir):
        """
        Initialize the dock widget initializer.

        Args:
            iface: QGIS interface
            config_manager: PluginConfigManager instance
            plugin_dir: Plugin directory path
        """
        self.iface = iface
        self.config_manager = config_manager
        self.plugin_dir = plugin_dir

    def create_and_setup(self, parent_plugin):
        """
        Create dock widget and configure it completely.

        Args:
            parent_plugin: Reference to the main LandTalkPlugin instance

        Returns:
            LandTalkDockWidget: Configured dock widget instance
        """
        # Create the dock widget
        dock = LandTalkDockWidget(self.iface.mainWindow())
        dock.setObjectName("LandTalkAIDockWidget")
        dock.parent_plugin = parent_plugin

        # Initialize settings from saved configuration
        self._initialize_settings(dock, parent_plugin)

        # Add to main window
        dock_area = self._get_right_dock_widget_area()
        logger.info(f"Adding LandTalk dock widget to right dock area: {dock_area}")
        self.iface.mainWindow().addDockWidget(dock_area, dock)

        # Try to tabify with existing dock widgets
        self._try_tabify_dock_widget(dock)

        return dock

    def _initialize_settings(self, dock, parent_plugin):
        """
        Initialize dock widget settings from saved configuration.

        Args:
            dock: LandTalkDockWidget instance
            parent_plugin: Reference to the main plugin
        """
        # Set the confidence threshold from loaded settings
        if hasattr(dock, 'prob_input'):
            dock.prob_input.setText(str(int(self.config_manager.confidence_threshold)))
            logger.info(f"Set confidence threshold in UI to: {int(self.config_manager.confidence_threshold)}")

        # Set the AI model from loaded settings
        if hasattr(dock, 'ai_model_combo'):
            self._set_saved_model_in_combo(dock)
            # If no saved model was present, adopt the combo's current data as the initial selection
            if not self.config_manager.last_selected_model:
                try:
                    combo = dock.ai_model_combo
                    current = combo.currentData()
                    if current:
                        self.config_manager.set_last_selected_model(current)
                        logger.info(f"No saved model - using combo default and saving: {self.config_manager.last_selected_model}")
                    else:
                        logger.info("No saved model and combo has no data - leaving last_selected_model empty")
                except Exception:
                    logger.info("Could not read combo currentData to initialize last_selected_model")
            else:
                logger.info(f"Set AI model in UI to: {self.config_manager.last_selected_model}")

        # Update persistence mode UI to reflect current settings
        if hasattr(dock, 'update_persistence_mode_ui'):
            dock.update_persistence_mode_ui()

        # Connect confidence input field change to save settings
        if hasattr(dock, 'prob_input'):
            dock.prob_input.textChanged.connect(parent_plugin.on_confidence_changed)

    def _set_saved_model_in_combo(self, dock):
        """
        Set the saved AI model in the combo box.

        Args:
            dock: LandTalkDockWidget instance
        """
        if not hasattr(dock, 'ai_model_combo'):
            return

        combo = dock.ai_model_combo
        # Find the index of the saved model
        for i in range(combo.count()):
            if combo.itemData(i) == self.config_manager.last_selected_model:
                combo.setCurrentIndex(i)
                logger.info(f"Restored AI model selection to: {self.config_manager.last_selected_model}")
                return

        # If saved model not found, keep the default
        logger.warning(f"Saved model '{self.config_manager.last_selected_model}' not found in combo box, keeping default")

    def _get_right_dock_widget_area(self):
        """
        Get the right dock widget area constant.

        Returns:
            int: Right dock widget area constant
        """
        dock_area_enum = getattr(Qt, 'DockWidgetArea', None)
        if dock_area_enum is not None and hasattr(dock_area_enum, 'RightDockWidgetArea'):
            return dock_area_enum.RightDockWidgetArea

        dock_area = getattr(Qt, 'RightDockWidgetArea', None)
        if dock_area is None:
            # Last resort: use numeric constant for right area
            dock_area = 2
            logger.warning("Using fallback numeric constant for right dock area")
        return dock_area

    def _try_tabify_dock_widget(self, dock):
        """
        Try to tabify with existing right-side dock widgets.

        Args:
            dock: LandTalkDockWidget instance
        """
        try:
            # Look for common QGIS dock widgets that are typically on the right side
            target_dock = None

            for dock_name in PluginConstants.DOCK_WIDGET_NAMES:
                target_dock = self.iface.mainWindow().findChild(QDockWidget, dock_name)
                if target_dock:
                    # Verify the dock is actually in the right area
                    dock_area = self.iface.mainWindow().dockWidgetArea(target_dock)
                    right_area_enum = getattr(Qt, 'RightDockWidgetArea', 2)
                    if dock_area == right_area_enum or dock_area == 2:
                        logger.info(f"Found right-side dock widget '{dock_name}' - tabifying LandTalk dock with it")
                        break
                    else:
                        logger.info(f"Dock widget '{dock_name}' is not in right area (area: {dock_area}) - skipping")
                        target_dock = None

            if target_dock:
                self.iface.mainWindow().tabifyDockWidget(target_dock, dock)
                logger.info("Successfully tabified LandTalk dock widget with right-side panel")
            else:
                logger.info("No suitable right-side dock widget found for tabifying - using standalone dock on right side")

        except Exception as e:
            logger.warning(f"Could not tabify dock widget: {str(e)} - using standalone dock on right side")
