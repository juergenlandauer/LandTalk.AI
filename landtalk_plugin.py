# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI
                                 A QGIS Plugin
 Your Landscape Talks With You using AI: Analyze map areas using Google Gemini or ChatGPT multimodal AI.
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
 *                                                                         *
 *   This program is distributed in the hope that it will be useful,       *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU General Public License for more details.                          *
 *                                                                         *
 *   You should have received a copy of the GNU General Public License     *
 *   along with this program. If not, see <https://www.gnu.org/licenses/>. *
 ***************************************************************************/
"""

import os
import tempfile
import base64
import json
from .genai import GenAIHandler
from .logging import logger
from .dock_widget import LandTalkDockWidget
from .ai_worker import AIWorker, ApiKeyDialog
from .map_tools import RectangleMapTool, MapRenderer
from .tutorial_dialog import TutorialDialog
from qgis.PyQt.QtCore import Qt, QRectF, QSize, pyqtSignal, QPointF, QPoint
from qgis.PyQt.QtGui import QIcon, QColor, QPixmap, QCursor
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, 
    QLabel, QTextEdit, QPushButton, QMessageBox,
    QLineEdit, QApplication,
    QDockWidget
)
try:
    from qgis.PyQt.QtGui import QAction  # PyQt6
except Exception:
    from qgis.PyQt.QtWidgets import QAction  # PyQt5

from qgis.core import (
    Qgis, QgsProject, QgsWkbTypes, QgsRectangle,
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsFields,
    QgsPointXY, QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsSingleSymbolRenderer, QgsLayerTreeGroup, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext
)
from qgis.PyQt.QtCore import QVariant, QTimer
from qgis.gui import QgsRubberBand


class LandTalkPlugin:
    """QGIS plugin for analyzing map areas using LandTalk AI (Google Gemini or GPT)."""

    def __init__(self, iface):
        """Initialize the plugin.
        
        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.map_canvas = self.iface.mapCanvas()
        self.rubber_band = None
        self.map_tool = None
        self.dock_widget = None
        self.actions = []
        self.menu = 'LandTalk.ai'
        self.action = None
        self.selected_rectangle = None
        
        # Map coordinates storage for captured image
        self.captured_map_extent = None  # QgsRectangle of the captured area in map coordinates
        self.captured_top_left_map = None  # Top-left corner in map coordinates
        self.captured_bottom_right_map = None  # Bottom-right corner in map coordinates
        self.captured_extent_width = None  # Width of extent in map units
        self.captured_extent_height = None  # Height of extent in map units
        self.captured_image_data = None  # Base64 encoded image data for chat display
        
        # Configure API keys
        self.gemini_api_key = ""  # API key should be entered by user
        self.gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        self.gpt_api_key = ""     # GPT API key
        self.gpt_api_url = "https://api.openai.com/v1/chat/completions"
        
        # API request timeout in seconds
        self.api_timeout = 30
        
        # Fixed ground resolution in meters per pixel (applies to rendered output)
        self.ground_resolution_m_per_px = 1.0
        
        # Initialize map renderer
        self.map_renderer = MapRenderer(self.map_canvas, self.ground_resolution_m_per_px)
        
        # Layer counter for unique numbering
        self.layer_counter = 0
        
        # Chat rules configuration (lazy loaded)
        self.system_prompt = ""
        self.system_prompt_file = os.path.join(self.plugin_dir, 'systemprompt.txt')
        
        # API keys configuration (lazy loaded)
        self.keys_file = os.path.join(self.plugin_dir, 'keys.txt')
        
        # Settings configuration (lazy loaded)
        self.settings_file = os.path.join(self.plugin_dir, 'settings.txt')
        self.default_confidence_threshold = 0
        self.confidence_threshold = self.default_confidence_threshold
        self.custom_analysis_directory = None
        self.auto_clear_on_model_change = True  # Default to True for auto-clearing
        self.last_selected_model = 'gemini-2.5-flash'  # Default model
        self.show_tutorial = True  # Default to showing tutorial for new users
        
        # Initialize GenAI handler lazily to avoid startup delays
        self.genai_handler = None
        
        # Initialize AI worker thread (will be created when needed)
        self.ai_worker = None
        
        # Initialize layer tracking for cleanup
        self.previous_landtalk_layers = {}  # Store previous layer states
        
        # Initialize periodic group check timer
        self.group_check_timer = QTimer()
        self.group_check_timer.timeout.connect(self.check_landtalk_group_status)
        self.group_check_timer.setSingleShot(False)
        self.group_check_timer.start(2000)  # Check every 2 seconds
        
        # Cleanup map tool
        if self.map_tool:
            self.map_canvas.unsetMapTool(self.map_tool)
        
        # Cleanup dock widget if open
        if self.dock_widget:
            self.dock_widget.close()

    def get_genai_handler(self):
        """Get GenAI handler, creating it lazily if needed"""
        if self.genai_handler is None:
            self.genai_handler = GenAIHandler(self.gemini_api_url, self.gpt_api_url, self.api_timeout)
        return self.genai_handler

    def ensure_system_prompt_loaded(self):
        """Ensure chat rules are loaded, loading them lazily if needed"""
        self.load_system_prompt()

    def ensure_keys_loaded(self):
        """Ensure API keys are loaded, loading them lazily if needed"""
        self.load_keys()

    def ensure_settings_loaded(self):
        """Ensure settings are loaded, loading them lazily if needed"""
        self.load_settings()

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(self.plugin_dir, 'icons', 'LT.AI.png')
        self.action = QAction(
            QIcon(icon_path),
            "Analyze with LandTalk.AI",
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)
        self.actions.append(self.action)
        
        # Set status tip and what's this text
        self.action.setStatusTip("Analyze map areas with LandTalk.AI")
        self.action.setWhatsThis("Analyze selected map areas using LandTalk.AI")
        
        # Connect to project signals to handle project open/close events
        project = QgsProject.instance()
        project.readProject.connect(self.on_project_opened)
        project.cleared.connect(self.on_project_closed)
        
        
    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        # Disconnect project signals first
        try:
            project = QgsProject.instance()
            project.readProject.disconnect(self.on_project_opened)
            project.cleared.disconnect(self.on_project_closed)
        except Exception as e:
            logger.warning(f"Could not disconnect project signals: {str(e)}")
        
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        if self.rubber_band:
            self.map_canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None
        if self.map_tool:
            self.map_canvas.unsetMapTool(self.map_tool)
            self.map_tool = None
        
        # Save settings before unloading
        self.save_settings()
        
        # Stop the group check timer
        if hasattr(self, 'group_check_timer'):
            self.group_check_timer.stop()
        
        # Cleanup AI worker thread if running
        if self.ai_worker and self.ai_worker.isRunning():
            logger.info("Terminating AI worker thread during plugin unload")
            self.ai_worker.terminate()
            self.ai_worker.wait()
            self.ai_worker = None
        
        # Cleanup dock widget if open
        if self.dock_widget:
            self.dock_widget.close()

    def is_project_open(self):
        """Check if a QGIS project is currently open"""
        try:
            project = QgsProject.instance()
            # A project is considered open if it has a valid file path or layers
            return (project.fileName() and project.fileName().strip()) or len(project.mapLayers()) > 0
        except Exception:
            return False

    def on_project_opened(self):
        """Handle project opened event"""
        logger.info("Project opened - LandTalk Plugin is now available")
        
        # Show user where analysis files will be saved
        analysis_dir = self.get_analysis_directory()
        if analysis_dir:
            logger.info(f"LandTalk.AI analysis files will be saved to: {analysis_dir}")
        
        # Initialize layer tracking for the current project
        self.initialize_layer_tracking()

    def initialize_layer_tracking(self):
        """Initialize tracking of LandTalk.ai layers for cleanup detection"""
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")
            
            if landtalk_group:
                # Store the current state of LandTalk.ai layers
                self.previous_landtalk_layers = self.get_current_landtalk_layers(landtalk_group)
                logger.info(f"Initialized tracking for {len(self.previous_landtalk_layers)} LandTalk.ai layers")
            else:
                # No LandTalk.ai group exists yet
                self.previous_landtalk_layers = {}
                logger.info("No LandTalk.ai group found - layer tracking initialized")
                
        except Exception as e:
            logger.warning(f"Error initializing layer tracking: {str(e)}")
            self.previous_landtalk_layers = {}

    def on_project_closed(self):
        """Handle project closed event - hide dock widget and cleanup"""
        logger.info("Project closed - hiding LandTalk Plugin GUI")
        
        # Hide and cleanup the dock widget if it exists
        if self.dock_widget:
            self.dock_widget.hide()
            self.dock_widget.close()
            
        # Cleanup any active selection
        self.cleanup_selection()



    def is_landtalk_layer(self, layer):
        """Check if a layer belongs to the LandTalk.ai analysis"""
        try:
            if not layer:
                logger.info("Layer is None, not a LandTalk.ai layer")
                return False
                
            logger.info(f"Checking if layer '{layer.name()}' (ID: {layer.id()}) is a LandTalk.ai layer")
                
            # Method 1: Check if the layer is in the LandTalk.ai group hierarchy
            layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
            if layer_tree_layer:
                logger.info(f"Found layer tree node for layer '{layer.name()}'")
                current_parent = layer_tree_layer.parent()
                level = 0
                while current_parent and level < 10:  # Prevent infinite loops
                    logger.info(f"Checking parent level {level}: {current_parent.name() if hasattr(current_parent, 'name') else 'No name'}")
                    if hasattr(current_parent, 'name') and current_parent.name() == "LandTalk.ai":
                        logger.info(f"Layer '{layer.name()}' is in LandTalk.ai group")
                        return True
                    if hasattr(current_parent, 'parent'):
                        current_parent = current_parent.parent()
                        level += 1
                    else:
                        break
                logger.info(f"Layer '{layer.name()}' is not in LandTalk.ai group hierarchy")
            else:
                logger.info(f"No layer tree node found for layer '{layer.name()}' - trying alternative method")
                
                # Method 2: Check if layer source is in the analysis directory
                layer_source = layer.source()
                if layer_source and layer_source.endswith('.gpkg'):
                    analysis_dir = self.get_analysis_directory()
                    if analysis_dir and layer_source.startswith(analysis_dir):
                        logger.info(f"Layer '{layer.name()}' identified as LandTalk.ai layer by source path")
                        return True
                
                # Method 3: Check if layer was previously tracked as LandTalk.ai layer
                if hasattr(self, 'previous_landtalk_layers') and self.previous_landtalk_layers:
                    if layer.name() in self.previous_landtalk_layers:
                        logger.info(f"Layer '{layer.name()}' was previously tracked as LandTalk.ai layer")
                        return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking if layer is LandTalk.ai layer: {str(e)}")
            import traceback
            logger.warning(f"Full traceback: {traceback.format_exc()}")
            return False

    def is_landtalk_group(self, group):
        """Check if a group is the LandTalk.ai group or a subgroup within it"""
        try:
            if not group:
                return False
                
            group_name = group.name()
            
            # Check if it's the main LandTalk.ai group
            if group_name == "LandTalk.ai":
                return True
                
            # Check if it's a subgroup within LandTalk.ai
            current_parent = group.parent()
            while current_parent:
                if hasattr(current_parent, 'name') and current_parent.name() == "LandTalk.ai":
                    return True
                if hasattr(current_parent, 'parent'):
                    current_parent = current_parent.parent()
                else:
                    break
                    
            return False
            
        except Exception as e:
            logger.warning(f"Error checking if group is LandTalk.ai group: {str(e)}")
            return False

    def collect_gpkg_files_from_group(self, group):
        """Collect all GPKG file paths from layers within a group"""
        gpkg_files = []
        try:
            # Recursively collect files from all child layers and groups
            for child in group.children():
                if hasattr(child, 'layer') and child.layer():
                    # This is a layer
                    layer = child.layer()
                    if layer.source() and layer.source().endswith('.gpkg'):
                        gpkg_files.append(layer.source())
                elif isinstance(child, QgsLayerTreeGroup):
                    # This is a subgroup - recurse
                    gpkg_files.extend(self.collect_gpkg_files_from_group(child))
                    
            logger.info(f"Collected {len(gpkg_files)} GPKG files from group '{group.name()}'")
            return gpkg_files
            
        except Exception as e:
            logger.warning(f"Error collecting GPKG files from group: {str(e)}")
            return []

    def get_current_landtalk_layers(self, landtalk_group):
        """Get current layers in the LandTalk.ai group with their source paths"""
        current_layers = {}
        try:
            # Recursively collect all layers from the group and subgroups
            for child in landtalk_group.children():
                if hasattr(child, 'layer') and child.layer():
                    # This is a layer
                    layer = child.layer()
                    if layer.source() and layer.source().endswith('.gpkg'):
                        current_layers[layer.name()] = {
                            'source': layer.source(),
                            'id': layer.id()
                        }
                elif isinstance(child, QgsLayerTreeGroup):
                    # This is a subgroup - recurse
                    subgroup_layers = self.get_current_landtalk_layers(child)
                    current_layers.update(subgroup_layers)
                    
            return current_layers
            
        except Exception as e:
            logger.warning(f"Error getting current LandTalk.ai layers: {str(e)}")
            return {}


    def update_layer_tracking(self):
        """Update the layer tracking state after new layers are created"""
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")
            
            if landtalk_group:
                # Update the stored state of LandTalk.ai layers
                self.previous_landtalk_layers = self.get_current_landtalk_layers(landtalk_group)
                logger.info(f"Updated layer tracking - now tracking {len(self.previous_landtalk_layers)} LandTalk.ai layers")
            else:
                logger.info("No LandTalk.ai group found during layer tracking update")
                
        except Exception as e:
            logger.warning(f"Error updating layer tracking: {str(e)}")

    def check_landtalk_group_status(self):
        """Periodically check if the LandTalk.ai group has been removed"""
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")
            
            # If group doesn't exist but we were tracking layers, clean up
            if landtalk_group is None and self.previous_landtalk_layers:
                logger.info("LandTalk.ai group has been removed (detected by periodic check) - cleaning up all GPKG files")
                self.cleanup_all_landtalk_gpkg_files()
                self.previous_landtalk_layers = {}
                
        except Exception as e:
            logger.warning(f"Error in periodic group status check: {str(e)}")

    def get_analysis_directory(self):
        """Get or create the LandTalk.AI analysis directory next to the QGZ file"""
        # If custom directory is set, use it
        if self.custom_analysis_directory and os.path.exists(self.custom_analysis_directory):
            analysis_dir = self.custom_analysis_directory
        else:
            # Default behavior: use directory next to QGZ file
            project = QgsProject.instance()
            if not project.fileName():
                # If no project file, use current working directory
                base_dir = os.getcwd()
            else:
                # Use the directory where the QGZ file is located
                base_dir = os.path.dirname(project.fileName())
            
            analysis_dir = os.path.join(base_dir, "LandTalk.AI analysis")
        
        # Create the directory if it doesn't exist
        if not os.path.exists(analysis_dir):
            try:
                os.makedirs(analysis_dir)
                logger.info(f"Created LandTalk.AI analysis directory: {analysis_dir}")
            except Exception as e:
                logger.error(f"Failed to create analysis directory: {str(e)}")
                return None
        
        return analysis_dir

    def start_rectangle_selection(self):
        """Start the rectangle selection workflow"""
        # Check if a project is open before starting rectangle selection
        if not self.is_project_open():
            QMessageBox.warning(
                self.iface.mainWindow(), 
                "No Project Open", 
                "Please open a QGIS project before selecting a map area.\n\n"
                "The plugin requires an active project to analyze map areas."
            )
            return
            
        # Clean up any existing selection when starting new selection
        self.cleanup_selection()
        
        # Also clear any existing thumbnail display
        if self.dock_widget:
            self.dock_widget.clear_thumbnail_display()
                
        # Create a map tool for selecting a rectangle
        self.map_tool = RectangleMapTool(self.map_canvas)
        self.map_canvas.setMapTool(self.map_tool)
        self.map_tool.rectangle_created.connect(self.on_rectangle_created)
        
        logger.info("Rectangle selection tool activated")


    def capture_map_thumbnail(self):
        """Capture a thumbnail of the selected area for display purposes"""
        return self.map_renderer.capture_map_thumbnail(self.selected_rectangle)

    def create_file_based_layer(self, layer_name, crs_authid, ai_provider, features=None):
        """Create a file-based vector layer directly in the LandTalk.ai directory"""
        analysis_dir = self.get_analysis_directory()
        if not analysis_dir:
            logger.error("Could not create analysis directory")
            return None
        
        # Create a safe filename from layer name
        safe_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        
        # Add timestamp to make filename unique
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        provider_suffix = ai_provider.upper() if ai_provider else "UNKNOWN"
        filename = f"{safe_name}_{provider_suffix}_{timestamp}.gpkg"
        file_path = os.path.join(analysis_dir, filename)
        
        try:
            # Create the GeoPackage file directly using QgsVectorFileWriter
            # Use fields from the first feature if available, otherwise create default fields
            if features and len(features) > 0:
                fields = features[0].fields()
                logger.info(f"Using fields from feature: {[field.name() for field in fields]}")
            else:
                # Define the fields for the layer (fallback)
                fields = QgsFields()
                fields.append(QgsField("label", QVariant.String))
                fields.append(QgsField("object_type", QVariant.String))
                fields.append(QgsField("probability", QVariant.Double))
                fields.append(QgsField("result_number", QVariant.Int))
                fields.append(QgsField("reason", QVariant.String))
                logger.info(f"Using default fields: {[field.name() for field in fields]}")
            
            # Create the writer options
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.fileEncoding = "UTF-8"
            
            # Create the writer
            writer = QgsVectorFileWriter.create(
                file_path,
                fields,
                QgsWkbTypes.Polygon,
                QgsCoordinateReferenceSystem(crs_authid),
                QgsCoordinateTransformContext(),
                options
            )
            
            if writer.hasError() != QgsVectorFileWriter.NoError:
                logger.error(f"Failed to create GeoPackage file: {writer.errorMessage()}")
                return None
            
            # Add features if provided
            if features:
                for i, feature in enumerate(features):
                    # Feature should already have fields and attributes set from create_single_layer_with_features
                    logger.info(f"Writing feature {i} to file: attributes = {feature.attributes()}")
                    logger.info(f"Feature {i} label value: '{feature['label']}'")
                    logger.info(f"Feature {i} fields: {[field.name() for field in feature.fields()]}")
                    
                    # Validate that feature has the expected fields
                    if not feature.fields().names():
                        logger.error(f"Feature {i} has no fields!")
                    else:
                        logger.info(f"Feature {i} field names: {feature.fields().names()}")
                    
                    writer.addFeature(feature)
            
            # Close the writer
            del writer
            
            # Create the layer from the file
            layer = QgsVectorLayer(file_path, layer_name, "ogr")
            if not layer.isValid():
                logger.error(f"Failed to create file-based layer from {file_path}")
                return None
            
            logger.info(f"Created file-based layer: {layer_name} at {file_path} with {layer.featureCount()} features")
            
            # Debug: Check what's actually in the created layer
            logger.info(f"Layer fields: {[field.name() for field in layer.fields()]}")
            for i, feature in enumerate(layer.getFeatures()):
                logger.info(f"Created layer feature {i}: attributes = {feature.attributes()}")
                logger.info(f"Created layer feature {i}: label = '{feature['label']}'")
                if i >= 2:  # Only log first few features
                    break
            
            return layer
            
        except Exception as e:
            logger.error(f"Error creating file-based layer {layer_name}: {str(e)}")
            return None

    def run(self):
        """Run method that toggles the plugin GUI"""
        # Check if a project is open before starting
        if not self.is_project_open():
            QMessageBox.warning(
                self.iface.mainWindow(), 
                "No Project Open", 
                "Please open a QGIS project before using the LandTalk Plugin.\n\n"
                "The plugin requires an active project to analyze map areas."
            )
            return
        
        # If dock widget exists and is visible, hide it (toggle off)
        if self.dock_widget and self.dock_widget.isVisible():
            self.dock_widget.hide()
            logger.info("LandTalk dock widget hidden")
            return
        
        # Create the dock widget (if it doesn't exist) for user input
        if not self.dock_widget:
            self.dock_widget = LandTalkDockWidget(self.iface.mainWindow())
            self.dock_widget.setObjectName("LandTalkAIDockWidget")  # Set unique object name for tabifying
            self.dock_widget.parent_plugin = self  # Set reference to parent plugin
            # Initialize ground resolution (no UI sync needed - handled by menu)
            
            # Set the confidence threshold from loaded settings
            if hasattr(self.dock_widget, 'prob_input'):
                self.ensure_settings_loaded()
                self.dock_widget.prob_input.setText(str(int(self.confidence_threshold)))
                logger.info(f"Set confidence threshold in UI to: {int(self.confidence_threshold)}")
            
            # Set the AI model from loaded settings
            if hasattr(self.dock_widget, 'ai_model_combo'):
                self.ensure_settings_loaded()
                self.set_saved_model_in_combo()
                logger.info(f"Set AI model in UI to: {self.last_selected_model}")
            
            # AI model selection change is handled by dock_widget.on_model_changed()
            
            # Connect confidence input field change to save settings
            if hasattr(self.dock_widget, 'prob_input'):
                self.dock_widget.prob_input.textChanged.connect(self.on_confidence_changed)
            
            # Add the dock widget to the main window using tabbed docking
            # Force it to the right dock area to avoid interfering with layers widget
            dock_area_enum = getattr(Qt, 'DockWidgetArea', None)
            if dock_area_enum is not None and hasattr(dock_area_enum, 'RightDockWidgetArea'):
                dock_area = dock_area_enum.RightDockWidgetArea
            else:
                dock_area = getattr(Qt, 'RightDockWidgetArea', None)
            
            # Ensure we always use the right dock area - no fallback to left
            if dock_area is None:
                # Try alternative right area constants
                dock_area = getattr(Qt, 'RightDockWidgetArea', None)
                if dock_area is None:
                    # Last resort: use numeric constant for right area (usually 2)
                    dock_area = 2
                    logger.warning("Using fallback numeric constant for right dock area")
            
            logger.info(f"Adding LandTalk dock widget to right dock area: {dock_area}")
            
            self.iface.mainWindow().addDockWidget(dock_area, self.dock_widget)
            
            # Try to tabify with existing right-side dock widgets to prevent layout interference TODO
            try:
                # Look for common QGIS dock widgets that are typically on the right side
                # Prioritize right-side panels and avoid left-side ones like Layers
                target_dock_names = ["Information", "Browser", "ProcessingToolbox", "LogMessagePanel"]
                target_dock = None
                
                for dock_name in target_dock_names:
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
                    self.iface.mainWindow().tabifyDockWidget(target_dock, self.dock_widget)
                    logger.info("Successfully tabified LandTalk dock widget with right-side panel")
                else:
                    logger.info("No suitable right-side dock widget found for tabifying - using standalone dock on right side")
                    
            except Exception as e:
                logger.warning(f"Could not tabify dock widget: {str(e)} - using standalone dock on right side")
        else:
            # Reset the dock widget's selected rectangle
            self.dock_widget.selected_rectangle = None
        
        # Show the dock widget (toggle on)
        if self.dock_widget:
            self.dock_widget.show()
            self.dock_widget.raise_()
            self.dock_widget.activateWindow()  # Bring it to front and give it focus
            
            # Show tutorial for first-time users
            self.ensure_settings_loaded()
            if self.show_tutorial:
                self.show_tutorial_dialog()
        
        logger.info("Please select a rectangular area on the map.")
        self.iface.messageBar().pushMessage(
            "LandTalk Plugin", 
            "Please select a rectangular area on the map.", 
            level=Qgis.MessageLevel.Info
        )
    
    def load_keys(self):
        """Load API keys from keys.txt file if it exists"""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    keys_data = json.load(f)
                    self.gemini_api_key = keys_data.get('gemini', '')
                    self.gpt_api_key = keys_data.get('gpt', '')
                logger.info("API keys loaded from file.")
            except Exception as e:
                logger.warning(f"Error loading API keys: {str(e)}")
    
    def save_keys(self):
        """Save API keys to keys.txt file"""
        try:
            keys_data = {
                'gemini': self.gemini_api_key,
                'gpt': self.gpt_api_key
            }
            with open(self.keys_file, 'w') as f:
                json.dump(keys_data, f)
            logger.info("API keys saved to file.")
        except Exception as e:
            logger.warning(f"Error saving API keys: {str(e)}")
            self.iface.messageBar().pushMessage(
                "LandTalk Plugin", 
                f"Could not save API keys: {str(e)}", 
                level=Qgis.MessageLevel.Warning,
                duration=5
            )
    
    def load_settings(self):
        """Load plugin settings from settings.txt file if it exists"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    settings_data = json.load(f)
                    self.confidence_threshold = settings_data.get('confidence_threshold', self.default_confidence_threshold)
                    self.custom_analysis_directory = settings_data.get('custom_analysis_directory', None)
                    self.auto_clear_on_model_change = settings_data.get('auto_clear_on_model_change', True)
                    self.last_selected_model = settings_data.get('last_selected_model', 'gemini-2.5-flash')
                    self.show_tutorial = settings_data.get('show_tutorial', True)
                logger.info(f"Plugin settings loaded from file. Confidence threshold: {self.confidence_threshold}, Last model: {self.last_selected_model}")
            except Exception as e:
                logger.warning(f"Error loading plugin settings: {str(e)}")
                self.confidence_threshold = self.default_confidence_threshold
                self.last_selected_model = 'gemini-2.5-flash'  # Default model
        else:
            logger.info("No settings file found, using default values")
            self.confidence_threshold = self.default_confidence_threshold
            self.last_selected_model = 'gemini-2.5-flash'  # Default model
    
    def save_settings(self):
        """Save plugin settings to settings.txt file"""
        try:
            settings_data = {
                'confidence_threshold': self.confidence_threshold,
                'custom_analysis_directory': self.custom_analysis_directory,
                'auto_clear_on_model_change': self.auto_clear_on_model_change,
                'last_selected_model': self.last_selected_model,
                'show_tutorial': self.show_tutorial
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings_data, f, indent=2)
            logger.info(f"Plugin settings saved to file. Confidence threshold: {self.confidence_threshold}, Last model: {self.last_selected_model}")
        except Exception as e:
            logger.warning(f"Error saving plugin settings: {str(e)}")
    
    def set_saved_model_in_combo(self):
        """Set the saved AI model in the combo box"""
        if not self.dock_widget or not hasattr(self.dock_widget, 'ai_model_combo'):
            return
            
        combo = self.dock_widget.ai_model_combo
        # Find the index of the saved model
        for i in range(combo.count()):
            if combo.itemData(i) == self.last_selected_model:
                combo.setCurrentIndex(i)
                logger.info(f"Restored AI model selection to: {self.last_selected_model}")
                return
        
        # If saved model not found, keep the default
        logger.warning(f"Saved model '{self.last_selected_model}' not found in combo box, keeping default")
    
    def on_model_selection_changed(self, model_data):
        """Handle AI model selection changes from the combo box"""
        if model_data and model_data != self.last_selected_model:
            self.last_selected_model = model_data
            self.save_settings()
            logger.info(f"AI model selection changed to: {self.last_selected_model}")
    
    def on_confidence_changed(self, text):
        """Handle confidence threshold input field changes"""
        try:
            # Parse the new confidence value
            if text.strip():
                new_threshold = float(text.strip())
                # Validate range (0-100)
                if 0 <= new_threshold <= 100:
                    self.confidence_threshold = new_threshold
                    self.save_settings()
                    logger.info(f"Confidence threshold updated to: {new_threshold}")
                else:
                    logger.warning(f"Confidence threshold out of range (0-100): {new_threshold}")
            else:
                # Empty field, use default
                self.confidence_threshold = self.default_confidence_threshold
                self.save_settings()
                logger.info(f"Confidence threshold reset to default: {self.default_confidence_threshold}")
        except ValueError:
            # Invalid input, keep current value
            logger.warning(f"Invalid confidence threshold input: {text}")
    
    def get_gemini_key(self):
        """Get Gemini API key from the user"""
        dialog = ApiKeyDialog(
            self.iface.mainWindow(), 
            "Gemini API Key", 
            "gemini",
            self.gemini_api_key
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = dialog.get_text()
            if text:
                self.gemini_api_key = text
                # Save keys to file
                self.save_keys()
                logger.info("Gemini API key has been set.")
                self.iface.messageBar().pushMessage(
                    "LandTalk Plugin", 
                    "Gemini API key has been set and saved.", 
                    level=Qgis.MessageLevel.Success,
                    duration=3
                )
    
    def get_gpt_key(self):
        """Get GPT API key from the user"""
        dialog = ApiKeyDialog(
            self.iface.mainWindow(), 
            "GPT API Key", 
            "openai",
            self.gpt_api_key
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = dialog.get_text()
            if text:
                self.gpt_api_key = text
                # Save keys to file
                self.save_keys()
                logger.info("GPT API key has been set.")
                self.iface.messageBar().pushMessage(
                    "LandTalk Plugin", 
                    "GPT API key has been set and saved.", 
                    level=Qgis.MessageLevel.Success,
                    duration=3
                )
    
    def on_rectangle_created(self, rectangle):
        """Handle rectangle selection on the map"""
        # Capture the selected area as an image
        self.selected_rectangle = rectangle
        
        # Set rubber band to visualize selection
        if self.rubber_band:
            self.map_canvas.scene().removeItem(self.rubber_band)
        
        self.rubber_band = QgsRubberBand(self.map_canvas, QgsWkbTypes.LineGeometry)
        self.rubber_band.setColor(QColor(255, 255, 255, 255))  # White color
        self.rubber_band.setWidth(3)  # Slightly thicker for better visibility
        self.rubber_band.setSecondaryStrokeColor(QColor(0, 0, 0, 255))  # Black outline
        self.rubber_band.setLineStyle(Qt.PenStyle.SolidLine)
        
        # Convert QPointF to map coordinates (using correct QPoint conversion)
        mapToPixel = self.map_canvas.mapSettings().mapToPixel()
        topLeft = mapToPixel.toMapCoordinates(QPoint(int(rectangle.topLeft().x()), int(rectangle.topLeft().y())))
        topRight = mapToPixel.toMapCoordinates(QPoint(int(rectangle.topRight().x()), int(rectangle.topRight().y())))
        bottomRight = mapToPixel.toMapCoordinates(QPoint(int(rectangle.bottomRight().x()), int(rectangle.bottomRight().y())))
        bottomLeft = mapToPixel.toMapCoordinates(QPoint(int(rectangle.bottomLeft().x()), int(rectangle.bottomLeft().y())))
        
        # Add the points to the rubber band
        self.rubber_band.addPoint(topLeft)
        self.rubber_band.addPoint(topRight)
        self.rubber_band.addPoint(bottomRight)
        self.rubber_band.addPoint(bottomLeft)
        self.rubber_band.addPoint(topLeft)  # Close the polygon
     
        # Store a reference to the rectangle in the dock widget as well
        self.dock_widget.selected_rectangle = rectangle
        
        # Clear chat history when new area is selected
        self.dock_widget.chat_history = []
        self.dock_widget.chat_display.clear()
        # Clear the prompt text input field
        self.dock_widget.prompt_text.clear()
        # Clear the thumbnail display
        self.dock_widget.clear_thumbnail_display()
        # Ensure a fresh map image will be captured for the next chat
        self.captured_image_data = None
        self.dock_widget.add_system_message("Click 'Select area' above to choose a new map area and start a new conversation. You can type a message (optional) and click 'Analyze' to analyze this image.")
        
        # Capture and display thumbnail immediately
        thumbnail_pixmap = self.capture_map_thumbnail()
        if thumbnail_pixmap and self.dock_widget:
            self.dock_widget.update_thumbnail_display(thumbnail_pixmap)
        
        # Capture the high-resolution map image immediately after thumbnail
        logger.info("Capturing high-resolution map image immediately after rectangle selection")
        captured_image = self.capture_map_image()
        if captured_image:
            logger.info("High-resolution map image captured successfully during rectangle selection")
            # Update the thumbnail info panel with the newly captured extent data
            if self.dock_widget:
                self.dock_widget.update_thumbnail_info()
        else:
            logger.warning("Failed to capture high-resolution map image during rectangle selection")
        
        # Clean up the map tool's rubber band and reset to default cursor after selection is complete
        if self.map_tool:
            # Clear the map tool's rubber band to avoid duplicate visualization
            if hasattr(self.map_tool, 'rubber_band') and self.map_tool.rubber_band:
                self.map_tool.rubber_band.reset()
            self.map_canvas.unsetMapTool(self.map_tool)
            self.map_tool = None
        
        # Ensure the dock widget is visible
        self.dock_widget.show()
        self.dock_widget.raise_()
    
    def capture_map_image(self):
        """Capture the selected area of the map as an image at fixed ground resolution"""
        # Reset stored coordinates
        self.captured_map_extent = None
        self.captured_top_left_map = None
        self.captured_bottom_right_map = None
        self.captured_extent_width = None
        self.captured_extent_height = None
        
        # Use the map renderer to capture the image
        result = self.map_renderer.capture_map_image(self.selected_rectangle)
        if result[0] is None:  # encoded_image is None
            return None
        
        # Unpack the result and store the captured data
        encoded_image, map_extent, top_left_map, bottom_right_map, extent_width, extent_height = result
        
        # Store calculated coordinates and parameters in class attributes
        self.captured_map_extent = map_extent
        self.captured_top_left_map = top_left_map
        self.captured_bottom_right_map = bottom_right_map
        self.captured_extent_width = extent_width
        self.captured_extent_height = extent_height
        self.captured_image_data = encoded_image
        
        return encoded_image
    
    def on_ai_worker_finished(self, result):
        """Handle the completion of an AI worker thread"""
        try:
            ai_provider = self.dock_widget.current_ai_provider if hasattr(self.dock_widget, 'current_ai_provider') else "unknown"
            
            if result["success"]:
                # Process JSON first if found
                json_data = None
                if result["json_data"]:
                    provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
                    logger.info(f"Processing {provider_name} JSON data: {result['json_data']}")
                    self.process_json_and_create_layers(result["json_data"], ai_provider)
                    json_data = result["json_data"]
                
                # Add AI response to chat and history with JSON data
                self.dock_widget.add_ai_message(result["result_text"], ai_provider, json_data)
                self.dock_widget.add_to_chat_history('assistant', result["result_text"], ai_provider)
            else:
                # Handle different error types
                if result["error_type"] == "interrupted":
                    # Don't show error message for interruption, it's already handled by the interrupt method
                    logger.info("Request was interrupted by user")
                elif result["error_type"] in ["input_required", "api_key_required"]:
                    QMessageBox.warning(self.dock_widget, "Error", result["error"])
                else:
                    self.dock_widget.add_ai_message(result["error"], ai_provider)
                    
                    # Even on error, try to create a layer with the bounding box if we captured an image
                    if result.get("image_data"):
                        try:
                            # Create a layer with only the bounding box feature
                            provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
                            bbox_features_data = [{
                                'label': f"Query extent analyzed by {provider_name}",
                                'object_type': 'query_extent',
                                'probability': None,
                                'result_number': 0,
                                'bbox': self.convert_to_map_coordinates([0, 0, 1000, 1000]),  # Full extent
                                'reason': ''
                            }]
                            self.create_single_layer_with_features(bbox_features_data, ai_provider)
                        except Exception:
                            pass  # Don't let bounding box creation errors mask the original error
                            
        except Exception as e:
            self.dock_widget.add_ai_message(f"Unexpected error: {str(e)}", ai_provider)
        finally:
            # Clean up the worker and restore UI
            self.cleanup_ai_worker()
    
    def on_ai_worker_error(self, error_message):
        """Handle errors from the AI worker thread"""
        ai_provider = self.dock_widget.current_ai_provider if hasattr(self.dock_widget, 'current_ai_provider') else "unknown"
        self.dock_widget.add_ai_message(f"Error: {error_message}", ai_provider)
        self.cleanup_ai_worker()
    
    def on_ai_worker_progress(self, progress_message):
        """Handle progress updates from the AI worker thread"""
        # Update the status or show progress in the UI
        if hasattr(self.dock_widget, 'update_status'):
            self.dock_widget.update_status(progress_message)
        logger.info(f"AI Progress: {progress_message}")
    
    def cleanup_ai_worker(self):
        """Clean up the AI worker thread and restore UI state"""
        if self.ai_worker:
            self.ai_worker.quit()
            self.ai_worker.wait()
            self.ai_worker = None
        
        # Restore cursor and re-enable dock widget
        QApplication.restoreOverrideCursor()
        self.dock_widget.setEnabled(True)
        
        # Re-enable the send button specifically
        if hasattr(self.dock_widget, 'send_button'):
            self.dock_widget.send_button.setEnabled(True)
    
    def analyze_with_ai_ui(self, model):
        """Unified UI wrapper for AI analysis - handles UI interactions and calls the genai handler"""
        # Determine AI provider based on model name
        if model.startswith("gemini"):
            ai_provider = "gemini"
        elif model.startswith("gpt"):
            ai_provider = "gpt"
        else:
            logger.error(f"Unknown model type: {model}")
            QMessageBox.warning(self.dock_widget, "Error", f"Unknown model type: {model}")
            return
            
        logger.info(f"analyze_with_ai_ui called with model: {model} (provider: {ai_provider})")
        
        # Deselect all existing LandTalk.ai layers to ensure only the most recent one is selected
        self.deselect_all_ai_analysis_layers()
        
        # Get prompt text from UI
        prompt_text = self.dock_widget.prompt_text.toPlainText().strip()
        logger.info(f"Prompt text: {prompt_text}")
        
        if not prompt_text:
            QMessageBox.warning(self.dock_widget, "Input Required", "Please enter a message.")
            return
        
        # Always ensure we have a selected rectangle and capture image first
        if not self.selected_rectangle:
            QMessageBox.warning(self.dock_widget, "Error", "Please select a map area first by drawing a rectangle on the map.")
            return
        
        # Use the image that was captured when the rectangle was selected
        if self.captured_image_data:
            logger.info("Using image captured during rectangle selection.")
            image_data = self.captured_image_data
        else:
            # This should not happen if rectangle selection worked properly
            logger.error("No captured image data available. Rectangle selection may have failed.")
            QMessageBox.warning(self.dock_widget, "Error", "No map image available. Please select a map area again.")
            return
        
        # Add user message to chat display (now with captured image data available)
        self.dock_widget.add_user_message(prompt_text)
        self.dock_widget.add_to_chat_history('user', prompt_text)
        
        # Clear the input field
        self.dock_widget.prompt_text.clear()
        
        # Check if there's already an AI request in progress
        if self.ai_worker and self.ai_worker.isRunning():
            QMessageBox.warning(self.dock_widget, "Request in Progress", "Please wait for the current AI request to complete.")
            return
        
        # Set current AI provider for conversation continuity
        self.dock_widget.current_ai_provider = ai_provider
        
        # Get chat context for the AI call
        chat_context = self.dock_widget.get_chat_context()
        
        # Ensure API keys are loaded
        self.ensure_keys_loaded()
        
        # Get the appropriate API key
        if ai_provider == "gemini":
            if not self.gemini_api_key:
                self.get_gemini_key()
                if not self.gemini_api_key:
                    QMessageBox.warning(self.dock_widget, "Error", "Please set your Google Gemini API key first.")
                    return
            api_key = self.gemini_api_key
        else:  # gpt
            if not self.gpt_api_key:
                self.get_gpt_key()
                if not self.gpt_api_key:
                    QMessageBox.warning(self.dock_widget, "Error", "Please set your OpenAI GPT API key first.")
                    return
            api_key = self.gpt_api_key
        
        logger.info(f"Successfully captured image data, length: {len(image_data)} characters")
        
        # Set wait cursor and disable send button (but keep UI responsive)
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor if hasattr(Qt, 'CursorShape') else 4))
        
        # Disable only the send button to prevent multiple requests
        if hasattr(self.dock_widget, 'send_button'):
            self.dock_widget.send_button.setEnabled(False)
        
        # Ensure chat rules are loaded
        self.ensure_system_prompt_loaded()
        
        # Create and start the AI worker thread
        self.ai_worker = AIWorker(
            self.get_genai_handler(), 
            prompt_text, 
            chat_context, 
            model, 
            api_key, 
            image_data, 
            self.system_prompt
        )
        
        # Connect worker signals to handler methods
        self.ai_worker.finished.connect(self.on_ai_worker_finished)
        self.ai_worker.error.connect(self.on_ai_worker_error)
        self.ai_worker.progress.connect(self.on_ai_worker_progress)
        
        # Start the worker thread
        self.ai_worker.start()

    def cleanup_selection(self):
        """Clean up the selection rectangle when dialog is closed"""
        # Clean up the rubber band in the LandTalkPlugin class
        if self.rubber_band:
            self.map_canvas.scene().removeItem(self.rubber_band)
            self.rubber_band = None
        
        # Clean up the rubber band in the map tool if it exists
        if self.map_tool and hasattr(self.map_tool, 'rubber_band'):
            # Remove from scene and reset
            if self.map_tool.rubber_band:
                try:
                    self.map_canvas.scene().removeItem(self.map_tool.rubber_band)
                except:
                    pass  # Ignore if already removed
                self.map_tool.rubber_band.reset()
        
        # Clear the selected rectangle reference
        self.selected_rectangle = None
        
        # Reset the map tool to default
        if self.map_tool:
            self.map_canvas.unsetMapTool(self.map_tool)
            self.map_tool = None
        
        # Do not clear captured image data here; it should persist for the chat session
        
        # Log cleanup
        logger.info("Selection rectangle removed")

    # layer handling functions
    def get_or_create_ai_analysis_group(self):
        """
        Get or create a layer group called 'LandTalk.ai' in the project.
        Returns the QgsLayerTreeGroup object for the 'LandTalk.ai' group.
        """
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        
        # Check if 'LandTalk.ai' group already exists
        ai_analysis_group = root.findGroup("LandTalk.ai")
        if ai_analysis_group:
            logger.info(f"Found existing LandTalk.ai group: {ai_analysis_group.name()}")
            return ai_analysis_group
        
        # Create the 'LandTalk.ai' group if it doesn't exist
        ai_analysis_group = root.insertGroup(0, "LandTalk.ai")
        logger.info(f"Created new LandTalk.ai group: {ai_analysis_group.name()}")
        logger.info("Created 'LandTalk.ai' layer group")
        return ai_analysis_group
    
    def deselect_all_ai_analysis_layers(self):
        """
        Deselect all layers in the LandTalk.ai group to ensure only the most recent layer is selected.
        """
        self.update_ai_analysis_visibility(current_group_name=None)
    
    def disable_all_previous_ai_analysis_groups(self, current_group_name):
        """
        Disable all previous AI analysis layer groups, keeping only the current one enabled.
        """
        self.update_ai_analysis_visibility(current_group_name=current_group_name)

    def update_ai_analysis_visibility(self, current_group_name=None):
        """
        Unified visibility manager for LandTalk.ai content.
        - If current_group_name is None: deselect (hide) all layers in the LandTalk.ai group.
        - If current_group_name is provided: hide all sibling groups except the current; leave current group and its layers unchanged.
        """
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            ai_analysis_group = root.findGroup("LandTalk.ai")

            if not ai_analysis_group:
                logger.info("No LandTalk.ai group found, nothing to update")
                return

            if current_group_name is None:
                # Deselect all individual layers within LandTalk.ai
                deselected_count = 0
                for child in ai_analysis_group.children():
                    if hasattr(child, 'layer') and child.layer():
                        if hasattr(child, 'setItemVisibilityChecked'):
                            child.setItemVisibilityChecked(False)
                            deselected_count += 1
                            logger.info(f"Deselected layer: {child.layer().name()}")
                logger.info(f"Successfully deselected {deselected_count} LandTalk.ai layer(s)")
            else:
                # Hide all groups except the current one
                disabled_count = 0
                for child in ai_analysis_group.children():
                    if isinstance(child, QgsLayerTreeGroup):
                        group_name = child.name()
                        if group_name != current_group_name:
                            child.setItemVisibilityChecked(False)
                            disabled_count += 1
                            logger.info(f"Disabled previous LandTalk.AI analysis group: {group_name}")
                if disabled_count > 0:
                    logger.info(f"Disabled {disabled_count} previous LandTalk.AI analysis group(s)")
                else:
                    logger.info("No previous LandTalk.AI analysis groups to disable")

            # Refresh layer tree view to reflect changes
            if hasattr(self.iface, 'layerTreeView'):
                layer_tree_view = self.iface.layerTreeView()
                layer_tree_view.refresh()

        except Exception as e:
            logger.warning(f"Error updating LandTalk.ai visibility: {str(e)}")
    
    def create_single_layer_with_features(self, features_data, ai_provider):
        """
        Create a group with individual memory vector layers for each feature.

        :param features_data: List of dictionaries with 'label', 'bbox', and 'reason' keys
        :param ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        """
        logger.info(f"create_single_layer_with_features called with ai_provider: {ai_provider}")
        logger.info(f"features_data: {features_data}")
        logger.info(f"features_data type: {type(features_data)}")
        logger.info(f"features_data length: {len(features_data) if isinstance(features_data, list) else 'Not a list'}")
        
        if not features_data:
            logger.info("No features_data provided, returning early")
            return

        # Increment counter and create unique group name
        self.layer_counter += 1
        provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
        group_name = f"{provider_name}_Analysis_{self.layer_counter}"

        # Get the current map canvas CRS for the layers
        map_crs = self.map_canvas.mapSettings().destinationCrs()
        crs_authid = map_crs.authid()

        # Get or create the 'LandTalk.ai' group
        ai_analysis_group = self.get_or_create_ai_analysis_group()
        logger.info(f"Got LandTalk.ai group: {ai_analysis_group.name() if ai_analysis_group else 'None'}")
        
        # Create a new group for this analysis under the LandTalk.ai group
        project = QgsProject.instance()
        analysis_group = ai_analysis_group.addGroup(group_name)
        
        logger.info(f"Created LandTalk.ai group: {group_name}")
        
        # Disable all previous LandTalk.AI analysis groups, keeping only the current one enabled
        self.disable_all_previous_ai_analysis_groups(group_name)

        # Create individual layers for each feature
        created_layers = []
        collected_labels = []  # remember labels for this analysis group
        for feature_data in features_data:
            # Skip query_extent features as they will be handled separately
            if feature_data.get('object_type') == 'query_extent':
                continue
                
            # Create layer name: "1. building (85%)"
            layer_name = feature_data['label']
            
            # Ensure label field matches layer name exactly
            label_value = feature_data['label']
            logger.info(f"Layer name: '{layer_name}' | Label value: '{label_value}' | Match: {layer_name == label_value}")
            if label_value:
                collected_labels.append(str(label_value))
            
            # Create feature for this object first
            xmin, ymin, xmax, ymax = feature_data['bbox']
            rect = QgsRectangle(xmin, ymin, xmax, ymax)
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromRect(rect))
            
            # Create fields first to ensure proper attribute setting
            fields = QgsFields()
            fields.append(QgsField("label", QVariant.String))
            fields.append(QgsField("object_type", QVariant.String))
            fields.append(QgsField("probability", QVariant.Double))
            fields.append(QgsField("result_number", QVariant.Int))
            fields.append(QgsField("reason", QVariant.String))
            
            # Set the fields on the feature before setting attributes
            feature.setFields(fields)
            
            # Set attributes: label, object_type, probability, result_number, reason
            # Ensure the label field uses the exact same value as the layer name
            attributes = [
                layer_name,  # Use layer_name to ensure exact match
                feature_data.get('object_type', ''),
                feature_data.get('probability', None),
                feature_data.get('result_number', 0),
                feature_data.get('reason', '')
            ]
            logger.info(f"Setting attributes for layer '{layer_name}': {attributes}")
            logger.info(f"Feature fields before setting attributes: {[field.name() for field in feature.fields()]}")
            feature.setAttributes(attributes)
            logger.info(f"Feature attributes after setting: {feature.attributes()}")
            logger.info(f"Feature label after setting: '{feature['label']}'")
            logger.info(f"Verification - Layer name: '{layer_name}' | Feature label: '{feature['label']}' | Match: {layer_name == feature['label']}")
            
            # Create a new file-based vector layer with the feature
            layer = self.create_file_based_layer(layer_name, crs_authid, ai_provider, [feature])
            if not layer:
                logger.error(f"Failed to create file-based layer {layer_name}")
                continue

            # Configure layer styling: no fill, only outlines
            renderer = layer.renderer()
            symbol = renderer.symbol()
            if symbol:
                # Get the symbol layer (should be a fill symbol layer for polygons)
                symbol_layer = symbol.symbolLayer(0)
                if symbol_layer:
                    # Set no fill color (transparent)
                    symbol_layer.setFillColor(QColor(0, 0, 0, 0))  # Transparent fill
                    
                    # Set border/outline properties with yellow color for all AI providers
                    symbol_layer.setStrokeColor(QColor(255, 255, 0))  # Yellow color for all providers
                    symbol_layer.setStrokeWidth(0.5)  # Thin border

            # Add the layer to the project first (required before adding to group)
            project.addMapLayer(layer, False)  # False = don't add to legend root
            
            # Add the layer to the analysis group
            analysis_group.addLayer(layer)
            
            # Make the new layer visible
            layer_tree_layer = project.layerTreeRoot().findLayer(layer.id())
            if layer_tree_layer and hasattr(layer_tree_layer, 'setItemVisibilityChecked'):
                layer_tree_layer.setItemVisibilityChecked(True)
                logger.info(f"Made new layer visible: {layer_name}")
            
            created_layers.append(layer)
            
            # Configure labeling to show labels by default - do this after layer is fully added to project
            logger.info(f"Configuring labeling for layer: {layer_name}")
            # Use QTimer to ensure labeling is configured after layer is fully initialized
            # Also try immediate labeling configuration
            QTimer.singleShot(200, lambda l=layer, n=layer_name: self.force_enable_labels(l, n))
        
        # Always add the bounding box rectangle as a separate layer if we captured an extent
        if self.captured_map_extent:
            provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
            bbox_layer_name = f"Query Extent - {provider_name}"
            
            # Create bbox feature first
            bbox_feature = QgsFeature()
            bbox_feature.setGeometry(QgsGeometry.fromRect(self.captured_map_extent))
            
            # Create fields for the bbox feature (same as in create_file_based_layer)
            fields = QgsFields()
            fields.append(QgsField("label", QVariant.String))
            fields.append(QgsField("object_type", QVariant.String))
            fields.append(QgsField("probability", QVariant.Double))
            fields.append(QgsField("result_number", QVariant.Int))
            fields.append(QgsField("reason", QVariant.String))
            
            # Set fields before setting attributes
            bbox_feature.setFields(fields)
            
            # Set attributes for the bounding box feature
            # Create label as concatenation of all other labels remembered during layer creation
            bbox_label_text = "\n".join(collected_labels)

            bbox_attributes = [
                bbox_label_text,  # label
                "query_extent",  # object_type
                None,  # probability
                0,  # result_number
                ''  # reason
            ]
            bbox_feature.setAttributes(bbox_attributes)
            
            # Create the bbox layer with the feature
            bbox_layer = self.create_file_based_layer(bbox_layer_name, crs_authid, ai_provider, [bbox_feature])
            logger.info(f"Created bbox layer: {bbox_layer_name}, isValid: {bbox_layer.isValid() if bbox_layer else False}")
            
            if bbox_layer and bbox_layer.isValid():

                # Configure bbox layer styling with dashed lines and different color
                try:
                    from qgis.core import QgsFillSymbol
                    
                    # Create the bounding box symbol with dashed lines and yellow color
                    bbox_symbol = QgsFillSymbol.createSimple({'outline_color': '255,255,0', 'outline_width': '1.0'})
                    bbox_symbol.setColor(QColor(0, 0, 0, 0))  # Transparent fill
                    
                    # Try to set dashed line style for bounding box
                    try:
                        bbox_symbol_layer = bbox_symbol.symbolLayer(0)
                        
                        # Try different approaches to set dashed line style
                        dash_style_set = False
                        
                        # Method 1: Try Qt.PenStyle.DashLine (PyQt6 style)
                        try:
                            from qgis.PyQt.QtCore import Qt
                            if hasattr(Qt, 'PenStyle') and hasattr(Qt.PenStyle, 'DashLine'):
                                if hasattr(bbox_symbol_layer, 'setPenStyle'):
                                    bbox_symbol_layer.setPenStyle(Qt.PenStyle.DashLine)
                                    dash_style_set = True
                                elif hasattr(bbox_symbol_layer, 'setStrokeStyle'):
                                    bbox_symbol_layer.setStrokeStyle(Qt.PenStyle.DashLine)
                                    dash_style_set = True
                        except:
                            pass
                        
                        # Method 2: Try Qt.DashLine (PyQt5 style)
                        if not dash_style_set:
                            try:
                                from qgis.PyQt.QtCore import Qt
                                if hasattr(Qt, 'DashLine'):
                                    if hasattr(bbox_symbol_layer, 'setPenStyle'):
                                        bbox_symbol_layer.setPenStyle(Qt.DashLine)
                                        dash_style_set = True
                                    elif hasattr(bbox_symbol_layer, 'setStrokeStyle'):
                                        bbox_symbol_layer.setStrokeStyle(Qt.DashLine)
                                        dash_style_set = True
                            except:
                                pass
                        
                        # Method 3: Try using custom dash pattern
                        if not dash_style_set:
                            try:
                                if hasattr(bbox_symbol_layer, 'setUseCustomDashPattern'):
                                    bbox_symbol_layer.setUseCustomDashPattern(True)
                                    bbox_symbol_layer.setCustomDashVector([2.0, 2.0])  # 2 units on, 2 units off
                                    dash_style_set = True
                            except:
                                pass
                        
                        if not dash_style_set:
                            logger.info("Could not set dashed line style - using solid line instead")
                            
                    except Exception as e:
                        logger.warning(f"Could not set dashed line style for bounding box: {str(e)}")
                    
                    bbox_layer.setRenderer(QgsSingleSymbolRenderer(bbox_symbol))
                    logger.info(f"Applied special styling to bbox layer '{bbox_layer_name}'")
                    
                except Exception as e:
                    logger.warning(f"Could not create special styling for bbox layer, using default: {str(e)}")

                # Add the bbox layer to the project and group
                project.addMapLayer(bbox_layer, False)
                analysis_group.addLayer(bbox_layer)
                
                # Make the bbox layer visible
                bbox_layer_tree_layer = project.layerTreeRoot().findLayer(bbox_layer.id())
                if bbox_layer_tree_layer and hasattr(bbox_layer_tree_layer, 'setItemVisibilityChecked'):
                    bbox_layer_tree_layer.setItemVisibilityChecked(True)
                    logger.info(f"Made bbox layer visible: {bbox_layer_name}")
                
                created_layers.append(bbox_layer)

        # Trigger refreshes for all created layers
        for layer in created_layers:
            layer.triggerRepaint()
        
        # Force the layer tree to refresh
        if hasattr(self.iface, 'layerTreeView'):
            try:
                layer_tree_view = self.iface.layerTreeView()
                if hasattr(layer_tree_view, 'refreshLayerSymbology'):
                    for layer in created_layers:
                        layer_tree_view.refreshLayerSymbology(layer.id())
            except Exception as e:
                logger.warning(f"Could not refresh layer tree symbology: {str(e)}")
        
        # Refresh the map canvas to show the new layers
        if self.map_canvas:
            self.map_canvas.refresh()
            self.map_canvas.refreshAllLayers()
        
        # Force project to refresh
        try:
            # Try to emit layer tree changed signal if available
            layer_tree_root = project.layerTreeRoot()
            if hasattr(layer_tree_root, 'layerTreeChanged'):
                layer_tree_root.layerTreeChanged.emit()
            elif hasattr(layer_tree_root, 'visibilityChanged'):
                layer_tree_root.visibilityChanged.emit()
        except Exception as e:
            logger.warning(f"Could not emit layer tree changed signal: {str(e)}")
        
        # Final canvas refresh to ensure everything is visible
        if self.map_canvas:
            # Schedule a delayed refresh to ensure all processing is complete
            QTimer.singleShot(100, lambda: self.map_canvas.refresh())
        
        logger.info(f"Created analysis group '{group_name}' with {len(created_layers)} individual layers in 'LandTalk.ai' group")
        
        # Update layer tracking to include the newly created layers
        self.update_layer_tracking()

    def force_enable_labels(self, layer, layer_name):
        """
        Force enable labels on a layer with a more aggressive approach.
        This method tries multiple techniques to ensure labels are enabled.
        """
        try:
            logger.info(f"Force enabling labels for layer: {layer_name}")
            
            # Method 1: Standard labeling configuration
            self.configure_layer_labeling(layer)
            
            # Method 2: Direct approach - create minimal label settings
            try:
                label_settings = QgsPalLayerSettings()
                label_settings.fieldName = 'label'
                label_settings.enabled = True
                label_settings.drawLabels = True
                
                # Create simple text format with white buffer
                text_format = QgsTextFormat()
                text_format.setSize(10)
                text_format.setColor(QColor(0, 0, 0))  # Black text
                
                # Add white text buffer for better readability
                buffer_settings = QgsTextBufferSettings()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(1)  # 1 pixel buffer for better visibility
                buffer_settings.setColor(QColor(255, 255, 255))  # White buffer
                text_format.setBuffer(buffer_settings)
                
                label_settings.setFormat(text_format)
                
                # Set placement
                label_settings.placement = Qgis.LabelPlacement.OverPoint
                
                # Create and apply labeling
                labeling = QgsVectorLayerSimpleLabeling(label_settings)
                layer.setLabelsEnabled(True)
                layer.setLabeling(labeling)
                layer.commitChanges()
                layer.triggerRepaint()
                
                logger.info(f"Applied direct labeling to layer: {layer_name}")
                
            except Exception as e:
                logger.warning(f"Direct labeling failed for {layer_name}: {str(e)}")
            
            # Method 3: Force refresh and verification
            layer.reload()
            layer.triggerRepaint()
            
            # Verify labels are enabled
            if layer.labelsEnabled():
                logger.info(f"Labels successfully enabled for layer: {layer_name}")
            else:
                logger.warning(f"Labels still not enabled for layer: {layer_name}")
                
        except Exception as e:
            logger.warning(f"Error force enabling labels for {layer_name}: {str(e)}")


    def configure_layer_labeling(self, layer):
        """
        Configure the layer to show labels by default with appropriate styling.
        
        :param layer: QgsVectorLayer to configure labeling for
        """
        logger.info(f"Configuring labeling for layer: {layer.name()}")
        try:
            # Check if the layer has the 'label' field
            field_names = [field.name() for field in layer.fields()]
            if 'label' not in field_names:
                logger.warning(f"Layer '{layer.name()}' does not have a 'label' field. Available fields: {field_names}")
                return
            
            # Create label settings
            label_settings = QgsPalLayerSettings()
            
            # Set the field name to use for labels
            label_settings.fieldName = 'label'
            
            # Enable labeling explicitly
            label_settings.enabled = True
            label_settings.drawLabels = True
            
            # Create text format for the labels
            text_format = QgsTextFormat()
            text_format.setSize(10)  # Slightly larger for better visibility
            text_format.setColor(QColor(0, 0, 0))  # Black text
            
            # Add white text buffer for better readability
            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(2)  # 2 pixel buffer for better visibility
            buffer_settings.setColor(QColor(255, 255, 255))  # White buffer
            text_format.setBuffer(buffer_settings)
            
            # Apply the text format to label settings
            label_settings.setFormat(text_format)
            
            # Set label placement based on geometry type
            geometry_type = layer.wkbType()
            if geometry_type in [QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon]:
                # For polygons, place labels at centroid
                label_settings.placement = Qgis.LabelPlacement.OverPoint
            elif geometry_type in [QgsWkbTypes.Point, QgsWkbTypes.MultiPoint]:
                # For points, place labels around the point
                label_settings.placement = Qgis.LabelPlacement.AroundPoint
            else:
                # For lines, place labels along the line
                label_settings.placement = Qgis.LabelPlacement.Line
            
            # Additional settings to ensure labels are always shown
            label_settings.displayAll = True  # Show all labels
            label_settings.obstacle = False  # Don't treat as obstacle for other labels
            label_settings.priority = 10  # High priority
            
            # Scale-based visibility (always visible)
            label_settings.scaleVisibility = False
            
            # Collision detection settings - allow overlapping labels
            # label_settings.upsidedownLabels = QgsPalLayerSettings.ShowUpright  # Commented out to avoid enum issues
            
            # Additional rendering settings for better visibility
            label_settings.mergeLines = False
            label_settings.limitNumLabels = False
            label_settings.maxNumLabels = 1000  # Allow many labels
            
            # Set label positioning for better visibility
            label_settings.xOffset = 0
            label_settings.yOffset = 0
            
            # Create simple labeling and apply to layer
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            
            # Ensure the layer accepts labeling
            layer.setLabelsEnabled(True)
            layer.setLabeling(labeling)
            
            # Force immediate refresh
            layer.triggerRepaint()
            
            # Force layer to commit changes
            layer.commitChanges()
            
            # Additional verification that labeling is enabled
            if layer.labelsEnabled():
                logger.info(f"Successfully configured and enabled labeling for layer '{layer.name()}' with 'label' field")
                
                # Force a more comprehensive refresh
                if hasattr(self, 'map_canvas') and self.map_canvas:
                    self.map_canvas.refresh()
                    # Schedule a delayed refresh to ensure labels are rendered
                    QTimer.singleShot(200, lambda: self.map_canvas.refresh())
            else:
                logger.warning(f"Labeling may not be properly enabled for layer '{layer.name()}'")
            
        except Exception as e:
            logger.warning(f"Error configuring layer labeling: {str(e)}")
            import traceback
            logger.warning(f"Full traceback: {traceback.format_exc()}")
            
            # Fallback: try to enable basic labeling
            try:
                logger.info(f"Attempting fallback labeling configuration for layer: {layer.name()}")
                layer.setLabelsEnabled(True)
                layer.triggerRepaint()
                if hasattr(self, 'map_canvas') and self.map_canvas:
                    self.map_canvas.refresh()
            except Exception as fallback_e:
                logger.warning(f"Fallback labeling also failed: {str(fallback_e)}")

    def process_json_and_create_layers(self, my_json, ai_provider):
        """
        Process JSON data and create a single memory vector layer with all detected objects in the LandTalk.ai group.
        
        :param my_json: JSON data extracted from AI response
        :param ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        """
        logger.info(f"process_json_and_create_layers called with ai_provider: {ai_provider}")
        logger.info(f"JSON data type: {type(my_json)}")
        logger.info(f"JSON data: {my_json}")
        logger.info(f"JSON data keys (if dict): {my_json.keys() if isinstance(my_json, dict) else 'Not a dict'}")
        logger.info(f"JSON data length (if list): {len(my_json) if isinstance(my_json, list) else 'Not a list'}")
        
        if not my_json:
            logger.info("No JSON data provided, returning")
            return
            
        try:
            # Handle different JSON structures
            if isinstance(my_json, list):
                # JSON is an array of items
                items_to_process = my_json
            elif isinstance(my_json, dict):
                # JSON is a single object or contains nested data
                if 'objects' in my_json:
                    items_to_process = my_json['objects']
                elif 'detections' in my_json:
                    items_to_process = my_json['detections']
                elif 'features' in my_json:
                    items_to_process = my_json['features']
                else:
                    # Single object, treat as single item
                    items_to_process = [my_json]
            
            # Collect all valid features for the single layer
            features_data = []
            total_items = len(items_to_process)
            skipped_confidence = 0
            skipped_missing_fields = 0
            processed_items = 0
            
            logger.info(f"Processing {total_items} items from JSON response")
            
            for i, item in enumerate(items_to_process):
                if not isinstance(item, dict):
                    logger.warning(f"Skipping item {i+1}: not a dictionary (type: {type(item)}, value: {item})")
                    skipped_missing_fields += 1
                    continue
                    
                # Extract object type/label, probability, bounding box, and reason
                object_type = None
                probability = None
                bbox_coords = None
                reason = None
                
                # Try different common field names for object type
                for type_field in ['object_type', 'Object Type']:
                    if type_field in item:
                        object_type = str(item[type_field])
                        logger.debug(f"Item {i+1}: Found object_type '{object_type}' in field '{type_field}'")
                        break
                
                if not object_type:
                    logger.debug(f"Item {i+1}: No object_type found. Available keys: {list(item.keys())}")
                
                # Try different common field names for probability/confidence
                for prob_field in ['probability', 'confidence', 'confidence_score', 'Confidence Score', 'prob', 'score']:
                    if prob_field in item:
                        try:
                            prob_value = item[prob_field]
                            if isinstance(prob_value, (int, float)):
                                probability = float(prob_value)
                            elif isinstance(prob_value, str):
                                # Handle percentage strings like "85%" or "0.85"
                                prob_str = prob_value.replace('%', '').strip()
                                probability = float(prob_str)
                                # If value is between 0 and 1, convert to percentage
                                if probability <= 1.0:
                                    probability *= 100
                            break
                        except (ValueError, TypeError):
                            continue
                
                # Try different common field names for bounding box
                for bbox_field in ['bounding_box', 'Bounding Box']:
                    if bbox_field in item:
                        bbox_data = item[bbox_field]
                        if isinstance(bbox_data, list) and len(bbox_data) >= 4:
                            bbox_coords = tuple(bbox_data[:4])  # Take first 4 values as (xmin, ymin, xmax, ymax)
                        break
                
                # Try different common field names for reason
                for reason_field in ['reason', 'Reason', 'explanation', 'Explanation', 'description', 'Description']:
                    if reason_field in item:
                        reason = str(item[reason_field])
                        logger.debug(f"Item {i+1}: Found reason '{reason}' in field '{reason_field}'")
                        break
                
                # Alternative: look for separate coordinate fields
                if not bbox_coords:
                    coord_fields = ['x', 'y', 'width', 'height']
                    if all(field in item for field in coord_fields):
                        x, y, w, h = item['x'], item['y'], item['width'], item['height']
                        bbox_coords = (x, y, x + w, y + h)
                    else:
                        # Try xmin, ymin, xmax, ymax format
                        coord_fields = ['xmin', 'ymin', 'xmax', 'ymax']
                        if all(field in item for field in coord_fields):
                            bbox_coords = (item['xmin'], item['ymin'], item['xmax'], item['ymax'])
                
                # Add to features list if we have both object type and bounding box
                if object_type and bbox_coords:
                    # Get confidence threshold from UI
                    confidence_threshold = self.get_confidence_threshold()
                    
                    # Apply confidence filtering - skip items below threshold
                    if probability is not None and probability < confidence_threshold:
                        logger.info(f"Skipping item {i+1}: {object_type} with confidence {probability:.1f}% below threshold {confidence_threshold}%")
                        skipped_confidence += 1
                        continue
                    
                    # Convert screen/pixel coordinates to map coordinates if needed
                    map_bbox_coords = self.convert_to_map_coordinates(bbox_coords)
                    
                    # Create enhanced label: "1. building (85%)"
                    result_number = i + 1
                    if probability is not None:
                        enhanced_label = f"({result_number}) {object_type} ({probability:.0f}%)"
                    else:
                        enhanced_label = f"({result_number}) {object_type}"
                    
                    features_data.append({
                        'label': enhanced_label,
                        'object_type': object_type,
                        'probability': probability,
                        'result_number': result_number,
                        'bbox': map_bbox_coords,
                        'reason': reason
                    })
                    processed_items += 1
                    logger.info(f"Processed item {i+1}: {enhanced_label}")
                else:
                    logger.warning(f"Skipping item {i+1}: missing object_type ({object_type}) or bbox_coords ({bbox_coords})")
                    skipped_missing_fields += 1
            
            # Log processing summary
            logger.info(f"JSON Processing Summary:")
            logger.info(f"  Total items in JSON: {total_items}")
            logger.info(f"  Items processed successfully: {processed_items}")
            logger.info(f"  Items skipped due to low confidence: {skipped_confidence}")
            logger.info(f"  Items skipped due to missing fields: {skipped_missing_fields}")
            
            # Create a single layer with all features if we have any valid features
            if features_data:
                confidence_threshold = self.get_confidence_threshold()
                self.create_single_layer_with_features(features_data, ai_provider)
                
                # Create detailed success message
                provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
                success_msg = f"Created layer with {len(features_data)} features from {provider_name} analysis (including query extent)"
                if skipped_confidence > 0 or skipped_missing_fields > 0:
                    success_msg += f" (filtered from {total_items} total)"
                
                logger.info(success_msg)
                self.iface.messageBar().pushMessage(
                    "LandTalk Plugin", 
                    success_msg, 
                    level=Qgis.MessageLevel.Success,
                    duration=7
                )
            else:
                # If no analysis results, still create a layer with just the bounding box
                # Create a layer with only the bounding box feature
                bbox_features_data = [{
                    'object_type': 'query_extent',
                    'probability': None,
                    'result_number': 0,
                    'bbox': self.convert_to_map_coordinates([0, 0, 1000, 1000]),  # Full extent
                    'reason': ''
                }]
                
                self.create_single_layer_with_features(bbox_features_data, ai_provider)
                
                # Create detailed warning message explaining why no features were created
                provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
                warning_msg = f"No features created from {provider_name} analysis"
                if total_items > 0:
                    reasons = []
                    if skipped_confidence > 0:
                        confidence_threshold = self.get_confidence_threshold()
                        reasons.append(f"{skipped_confidence} below {int(confidence_threshold)}% confidence")
                    if skipped_missing_fields > 0:
                        reasons.append(f"{skipped_missing_fields} missing required fields")
                    if reasons:
                        warning_msg += f" ({total_items} items: {', '.join(reasons)})"
                else:
                    warning_msg += " (no items in JSON response)"
                
                logger.info(warning_msg)
                self.iface.messageBar().pushMessage(
                    "LandTalk Plugin", 
                    warning_msg, 
                    level=Qgis.MessageLevel.Warning,
                    duration=8
                )
                
        except Exception as e:
            logger.error(f"Error processing JSON data for layer creation: {str(e)}")

    def get_confidence_threshold(self):
        """
        Get the confidence threshold value from stored settings.
        
        :return: Float confidence threshold value (0-100)
        """
        try:
            # Return the stored confidence threshold value
            threshold = max(0, min(100, self.confidence_threshold))
            logger.info(f"Using confidence threshold: {int(threshold)}%")
            return threshold
        except Exception as e:
            logger.warning(f"Error getting confidence threshold, using default {int(self.default_confidence_threshold)}%: {str(e)}")
            return self.default_confidence_threshold

    def convert_to_map_coordinates(self, bbox_coords):
        """
        Convert bounding box coordinates to map coordinates.
        Assumes input coordinates are relative to the captured map extent and are in 0-1000 range.
        
        :param bbox_coords: Tuple of (xmin, ymin, xmax, ymax) coordinates in 0-1000 range
        :return: Tuple of map coordinates
        """
        logger.info(f"Converting bbox coordinates: {bbox_coords}")
        logger.info(f"Captured map extent: {self.captured_map_extent}")
        logger.info(f"Captured top left: {self.captured_top_left_map}")
        logger.info(f"Captured bottom right: {self.captured_bottom_right_map}")
        
        if not self.captured_map_extent or not self.captured_top_left_map or not self.captured_bottom_right_map:
            logger.warning("No captured map coordinates available, cannot convert bbox coordinates")
            logger.info("No captured map coordinates available")
            return bbox_coords
            
        try:
            xmin, ymin, xmax, ymax = bbox_coords
            
            # Get the captured map extent dimensions
            extent_width = self.captured_extent_width
            extent_height = self.captured_extent_height
            extent_left = self.captured_top_left_map.x()
            extent_top = self.captured_top_left_map.y()
            
            # Convert coordinates from 0-1000 range to relative positions (0-1 range)
            xmin_rel = xmin / 1000.0
            ymin_rel = ymin / 1000.0
            xmax_rel = xmax / 1000.0
            ymax_rel = ymax / 1000.0
            
            # Convert relative positions to map coordinates
            # Note: In map coordinates, Y increases upward, but in image coordinates Y increases downward
            # So we need to flip the Y coordinates
            map_xmin = extent_left + (xmin_rel * extent_width)
            map_ymin = extent_top - (ymin_rel * extent_height)  # Flip Y coordinate
            map_xmax = extent_left + (xmax_rel * extent_width)
            map_ymax = extent_top - (ymax_rel * extent_height)  # Flip Y coordinate
            
            # Ensure min/max are in correct order
            if map_xmin > map_xmax:
                map_xmin, map_xmax = map_xmax, map_xmin
            if map_ymin > map_ymax:
                map_ymin, map_ymax = map_ymax, map_ymin
            
            logger.info(f"Converted bbox from 0-1000 range {bbox_coords} to map coordinates ({map_xmin:.6f}, {map_ymin:.6f}, {map_xmax:.6f}, {map_ymax:.6f})")
            
            logger.info(f"Successfully converted coordinates: {bbox_coords} -> ({map_xmin:.6f}, {map_ymin:.6f}, {map_xmax:.6f}, {map_ymax:.6f})")
            return (map_xmin, map_ymin, map_xmax, map_ymax)
            
        except Exception as e:
            logger.warning(f"Error converting coordinates to map coordinates: {str(e)}, using original coordinates")
            logger.info(f"Error converting coordinates: {str(e)}")
            return bbox_coords

    # chat rules functions
    def load_system_prompt(self):
        """Load chat rules from systemprompt.txt file if it exists"""
        if os.path.exists(self.system_prompt_file):
            try:
                with open(self.system_prompt_file, 'r') as f:
                    self.system_prompt = f.read().strip()
                logger.info("Chat rules loaded from file.")
            except Exception as e:
                logger.warning(f"Error loading chat rules: {str(e)}")
    
    def save_system_prompt(self, prompt_text):
        """Save chat rules to systemprompt.txt file"""
        try:
            with open(self.system_prompt_file, 'w') as f:
                f.write(prompt_text)
            self.system_prompt = prompt_text
            logger.info("Chat rules saved to file.")
            return True
        except Exception as e:
            logger.warning(f"Error saving chat rules: {str(e)}")
            self.iface.messageBar().pushMessage(
                "LandTalk Plugin", 
                f"Could not save chat rules: {str(e)}", 
                level=Qgis.MessageLevel.Warning,
                duration=5
            )
            return False
    
    def edit_system_prompt(self):
        """Open dialog to edit chat rules"""
        # Create a dialog for editing the chat rules
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("Edit Chat Rules")
        dialog.resize(600, 400)
        
        # Create layout
        layout = QVBoxLayout(dialog)
        
        # Add explanation label
        explanation = QLabel("Enter chat rules text that will be added to all AI queries. Do not change the part marked with ####:")
        layout.addWidget(explanation)
        
        # Add text edit for chat rules
        text_edit = QTextEdit(dialog)
        self.ensure_system_prompt_loaded()
        text_edit.setPlainText(self.system_prompt)
        layout.addWidget(text_edit)
        
        # Add buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Connect buttons
        save_button.clicked.connect(lambda: self.save_system_prompt(text_edit.toPlainText()) and dialog.accept())
        cancel_button.clicked.connect(dialog.reject)
        
        # Show dialog
        (getattr(dialog, "exec", None) or getattr(dialog, "exec_", None))()
    
    def show_tutorial_dialog(self):
        """Show the tutorial dialog for first-time users"""
        try:
            tutorial_dialog = TutorialDialog(self.iface.mainWindow())
            result = tutorial_dialog.exec()
            
            # Check if user wants to show tutorial again
            if not tutorial_dialog.should_show_again():
                self.show_tutorial = False
                self.save_settings()
                logger.info("Tutorial disabled - will not show again")
            
        except Exception as e:
            logger.error(f"Error showing tutorial dialog: {str(e)}")
            # Don't show error message for tutorial, just log it


