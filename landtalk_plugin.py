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
from datetime import datetime
from .genai import GenAIHandler
from .logging import logger
from .dock_widget import LandTalkDockWidget
from .map_tools import RectangleMapTool, MapRenderer
from .tutorial_dialog import TutorialDialog
from .layer_manager import LayerManager
from .config_manager import PluginConfigManager
from .constants import PluginConstants
from .json_processor import AIResponseProcessor
from .analysis_coordinator import AnalysisCoordinator
from .dock_widget_initializer import DockWidgetInitializer
from .map_capture_state import MapCaptureState
from .message_formatter import MessageFormatter
from qgis.PyQt.QtCore import Qt, QRectF, QSize, pyqtSignal, QPointF, QPoint
from qgis.PyQt.QtGui import QIcon, QColor, QPixmap
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QMessageBox,
    QLineEdit, QDockWidget, QFileDialog
)
try:
    from qgis.PyQt.QtGui import QAction  # PyQt6
except Exception:
    from qgis.PyQt.QtWidgets import QAction  # PyQt5

from qgis.core import (
    Qgis, QgsProject, QgsWkbTypes, QgsRectangle,
    QgsSingleSymbolRenderer, QgsLayerTreeGroup
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

        # Map capture state - consolidated state management
        self.capture_state = MapCaptureState()

        # API URLs and timeout
        self.gemini_api_url = PluginConstants.GEMINI_API_URL
        self.gpt_api_url = PluginConstants.GPT_API_URL
        self.api_timeout = PluginConstants.API_TIMEOUT

        # Fixed ground resolution in meters per pixel (applies to rendered output)
        self.ground_resolution_m_per_px = PluginConstants.DEFAULT_GROUND_RESOLUTION_M_PER_PX

        # Initialize map renderer
        self.map_renderer = MapRenderer(self.map_canvas, self.ground_resolution_m_per_px)

        # Initialize GenAI handler lazily to avoid startup delays
        self.genai_handler = None

        # Initialize AI worker thread (will be created when needed)
        self.ai_worker = None

        # Initialize LayerManager to handle all layer operations
        self.layer_manager = LayerManager(self)

        # Initialize ConfigManager to handle all configuration operations
        self.config_manager = PluginConfigManager(self.plugin_dir, self.iface)

        # Initialize AnalysisCoordinator to handle AI analysis workflow
        self.analysis_coordinator = AnalysisCoordinator(self)

        # Initialize DockWidgetInitializer for UI setup
        self.dock_initializer = DockWidgetInitializer(self.iface, self.config_manager, self.plugin_dir)

    def get_genai_handler(self):
        """Get GenAI handler, creating it lazily if needed"""
        if self.genai_handler is None:
            self.genai_handler = GenAIHandler(self.gemini_api_url, self.gpt_api_url, self.api_timeout)
        return self.genai_handler

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

        # Connect to writeProject to auto-convert memory layers before project is saved
        project.writeProject.connect(self.on_project_about_to_be_saved)
        logger.info("Connected to writeProject signal - will auto-convert memory layers before save")

        # Connect to cleared signal for cleanup
        project.cleared.connect(self.on_project_closed)

        # Connect to layer tree view context menu for right-click export
        self.setup_layer_tree_context_menu()


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        # Disconnect project signals first
        try:
            project = QgsProject.instance()
            project.readProject.disconnect(self.on_project_opened)
            project.writeProject.disconnect(self.on_project_about_to_be_saved)
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
        self.config_manager.save_settings()

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
        analysis_dir = self.layer_manager.get_analysis_directory()
        if analysis_dir:
            logger.info(f"LandTalk.AI analysis files will be saved to: {analysis_dir}")

    def on_project_about_to_be_saved(self):
        """Handle project about to be saved - auto-convert memory layers to file-based before save"""
        logger.info("Project about to be saved - checking for memory layers to convert")

        try:
            # Check if there are any LandTalk memory layers
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")

            if not landtalk_group:
                return

            # Check for memory layers
            memory_layers_exist = False
            for layer_tree_layer in landtalk_group.findLayers():
                layer = layer_tree_layer.layer()
                if layer and layer.isValid() and layer.providerType() == "memory":
                    memory_layers_exist = True
                    break

            if not memory_layers_exist:
                logger.info("No memory layers found in LandTalk.ai group")
                return

            # Get persistence mode
            mode = self.config_manager.get_layer_persistence_mode()
            logger.info(f"Found memory layers. Persistence mode: {mode}")

            # For temporary mode, auto-save and convert before project save
            # (auto_save mode already converts layers immediately after analysis)
            if mode == 'temporary':
                logger.info("Auto-converting memory layers to file-based before project save")

                # Save to GeoPackage
                output_path = self.layer_manager.export_landtalk_group_to_geopackage()

                if output_path:
                    # Convert memory layers to file-based
                    success = self.layer_manager.convert_memory_layers_to_file_based(landtalk_group, output_path)
                    if success:
                        logger.info(f"Successfully converted memory layers to file-based: {output_path}")
                        # Show a brief notification
                        from qgis.core import Qgis
                        self.iface.messageBar().pushMessage(
                            "LandTalk.AI",
                            f"Memory layers auto-saved to: {os.path.basename(output_path)}",
                            level=Qgis.MessageLevel.Info,
                            duration=3
                        )
                    else:
                        logger.warning("Failed to convert some memory layers to file-based")
                else:
                    logger.warning("Failed to save memory layers to GeoPackage")

        except Exception as e:
            logger.error(f"Error in on_project_about_to_be_saved: {str(e)}")

    def on_project_closed(self):
        """Handle project closed event - hide dock widget and cleanup"""
        logger.info("Project closed - hiding LandTalk Plugin GUI")
        
        # Hide and cleanup the dock widget if it exists
        if self.dock_widget:
            self.dock_widget.hide()
            self.dock_widget.close()
            
        # Cleanup any active selection
        self.cleanup_selection()


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

        # Save the current map tool before setting the rectangle selection tool
        self.previous_map_tool = self.map_canvas.mapTool()
        logger.info(f"Saving previous map tool: {self.previous_map_tool}")

        # Create a map tool for selecting a rectangle
        self.map_tool = RectangleMapTool(self.map_canvas)
        self.map_canvas.setMapTool(self.map_tool)
        self.map_tool.rectangle_created.connect(self.on_rectangle_created)
        self.map_tool.selection_cancelled.connect(self.on_selection_cancelled)

        logger.info("Rectangle selection tool activated")


    def capture_map_thumbnail(self):
        """Capture a thumbnail of the selected area for display purposes"""
        return self.map_renderer.capture_map_thumbnail(self.selected_rectangle)

    def _create_dock_widget(self):
        """Create and configure the dock widget using DockWidgetInitializer"""
        self.dock_widget = self.dock_initializer.create_and_setup(self)

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
            self._create_dock_widget()
        else:
            # Reset the dock widget's selected rectangle
            self.dock_widget.selected_rectangle = None

        # Show the dock widget (toggle on)
        if self.dock_widget:
            self.dock_widget.show()
            self.dock_widget.raise_()
            self.dock_widget.activateWindow()  # Bring it to front and give it focus

            # Show tutorial for first-time users
            if self.config_manager.show_tutorial:
                self.show_tutorial_dialog()

        logger.info("Please select a rectangular area on the map.")
        self.iface.messageBar().pushMessage(
            "LandTalk Plugin",
            "Please select a rectangular area on the map.",
            level=Qgis.MessageLevel.Info
        )

    def setup_layer_tree_context_menu(self):
        """Setup context menu for layer tree to add export functionality"""
        try:
            # Get the layer tree view
            layer_tree_view = self.iface.layerTreeView()
            if layer_tree_view:
                # Connect to the context menu signal
                layer_tree_view.contextMenuAboutToShow.connect(self.on_layer_tree_context_menu)
                logger.info("Connected layer tree context menu")
        except Exception as e:
            logger.error(f"Error setting up layer tree context menu: {str(e)}")

    def on_layer_tree_context_menu(self, menu):
        """Handle layer tree context menu to add export option for LandTalk groups

        Args:
            menu: QMenu object to add items to
        """
        try:
            # Get the currently selected layer tree node
            layer_tree_view = self.iface.layerTreeView()
            if not layer_tree_view:
                return

            current_node = layer_tree_view.currentNode()
            if not current_node:
                return

            # Check if the current node is a LandTalk.ai group or within it
            if isinstance(current_node, QgsLayerTreeGroup):
                # Check if this is the main LandTalk.ai group or a subgroup
                if self.layer_manager.is_landtalk_group(current_node):
                    # Add separator
                    menu.addSeparator()

                    # Add export action
                    export_action = menu.addAction("Export to GeoPackage...")
                    export_action.triggered.connect(lambda: self.export_group_to_geopackage(current_node))

                    logger.info(f"Added export menu item for group: {current_node.name()}")

        except Exception as e:
            logger.error(f"Error in layer tree context menu handler: {str(e)}")

    def export_group_to_geopackage(self, group):
        """Export a layer group to GeoPackage file

        Args:
            group: QgsLayerTreeGroup to export
        """
        try:
            # Prompt user for output file location
            # Generate default filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            group_name = group.name() if hasattr(group, 'name') else 'analysis'
            safe_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '-', '_')).strip()
            default_filename = f"landtalk_{safe_name}_{timestamp}.gpkg"

            # Get project directory as default location
            project_dir = self.layer_manager.get_project_directory()
            if project_dir:
                analysis_dir = os.path.join(project_dir, "LandTalk_Analysis")
                if not os.path.exists(analysis_dir):
                    os.makedirs(analysis_dir)
                default_path = os.path.join(analysis_dir, default_filename)
            else:
                default_path = default_filename

            # Show save file dialog
            output_path, _ = QFileDialog.getSaveFileName(
                self.iface.mainWindow(),
                "Export Layer Group to GeoPackage",
                default_path,
                "GeoPackage Files (*.gpkg);;All Files (*)"
            )

            if not output_path:
                logger.info("Export cancelled by user")
                return

            # Ensure .gpkg extension
            if not output_path.lower().endswith('.gpkg'):
                output_path += '.gpkg'

            # Save the group to GeoPackage
            result_path = self.layer_manager.save_group_to_geopackage(group, output_path)

            if result_path:
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Export Successful",
                    f"Layer group '{group.name()}' has been exported to:\n{result_path}"
                )
                logger.info(f"Successfully exported group to: {result_path}")
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Export Failed",
                    f"Failed to export layer group '{group.name()}'"
                )

        except Exception as e:
            logger.error(f"Error exporting group to GeoPackage: {str(e)}")
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"An error occurred while exporting:\n{str(e)}"
            )

    def on_model_selection_changed(self, model_data):
        """Handle AI model selection changes from the combo box"""
        if model_data and model_data != self.config_manager.last_selected_model:
            self.config_manager.set_last_selected_model(model_data)
            logger.info(f"AI model selection changed to: {model_data}")

    def on_confidence_changed(self, text):
        """Handle confidence threshold input field changes"""
        try:
            # Parse the new confidence value
            if text.strip():
                new_threshold = float(text.strip())
                # Validate range (0-100)
                if 0 <= new_threshold <= 100:
                    self.config_manager.set_confidence_threshold(new_threshold)
                    logger.info(f"Confidence threshold updated to: {new_threshold}")
                else:
                    logger.warning(f"Confidence threshold out of range (0-100): {new_threshold}")
            else:
                # Empty field, use default
                self.config_manager.set_confidence_threshold(self.config_manager.default_confidence_threshold)
                logger.info(f"Confidence threshold reset to default: {self.config_manager.default_confidence_threshold}")
        except ValueError:
            # Invalid input, keep current value
            logger.warning(f"Invalid confidence threshold input: {text}")
    
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
        
        # Convert screen coordinates to map coordinates using proper QGIS API
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
        self.capture_state.image_data = None
        self.dock_widget.add_system_message("Click 'Select area' above to choose a new map area and start a new conversation. Type a message (optional) and click 'Analyze'. CAUTION: resulting bounding boxes are only precise with Gemini-robotics and Gemini-3.")
        
        # Capture the high-resolution map image first (so thumbnail can be created from it)
        logger.info("Capturing high-resolution map image immediately after rectangle selection")
        captured_image = self.capture_map_image()
        if captured_image:
            logger.info("High-resolution map image captured successfully during rectangle selection")
            
            # Now capture and display thumbnail from the AI image for consistency
            thumbnail_pixmap = self.capture_map_thumbnail()
            if thumbnail_pixmap and self.dock_widget:
                self.dock_widget.update_thumbnail_display(thumbnail_pixmap)
            
            # Update the thumbnail info panel with the newly captured extent data
            if self.dock_widget:
                self.dock_widget.update_thumbnail_info()
        else:
            logger.warning("Failed to capture high-resolution map image during rectangle selection")
        
        # Clean up the map tool's rubber band and restore the previous map tool
        if self.map_tool:
            # Clear the map tool's rubber band to avoid duplicate visualization
            if hasattr(self.map_tool, 'rubber_band') and self.map_tool.rubber_band:
                self.map_tool.rubber_band.reset()
            # Restore the previous map tool instead of unsetting
            if hasattr(self, 'previous_map_tool') and self.previous_map_tool:
                logger.info(f"Restoring previous map tool: {self.previous_map_tool}")
                self.map_canvas.setMapTool(self.previous_map_tool)
            else:
                self.map_canvas.unsetMapTool(self.map_tool)
            self.map_tool = None

        # Ensure the dock widget is visible
        self.dock_widget.show()
        self.dock_widget.raise_()

    def on_selection_cancelled(self):
        """Handle cancelled rectangle selection (e.g., Escape key pressed)"""
        logger.info("Rectangle selection cancelled by user")

        # Clean up the map tool's rubber band
        if self.map_tool:
            if hasattr(self.map_tool, 'rubber_band') and self.map_tool.rubber_band:
                self.map_tool.rubber_band.reset()

            # Restore the previous map tool
            if hasattr(self, 'previous_map_tool') and self.previous_map_tool:
                logger.info(f"Restoring previous map tool after cancellation: {self.previous_map_tool}")
                self.map_canvas.setMapTool(self.previous_map_tool)
            else:
                self.map_canvas.unsetMapTool(self.map_tool)

            self.map_tool = None

    def capture_map_image(self):
        """Capture the selected area of the map as an image at fixed ground resolution"""
        # Reset stored coordinates
        self.capture_state.clear()

        # Use the map renderer to capture the image
        result = self.map_renderer.capture_map_image(self.selected_rectangle)
        if result[0] is None:  # encoded_image is None
            return None

        # Unpack the result and store the captured data
        encoded_image, map_extent, top_left_map, bottom_right_map, extent_width, extent_height = result

        # Store all capture data in the state object
        self.capture_state.set_capture_data(
            map_extent, top_left_map, bottom_right_map,
            extent_width, extent_height, encoded_image
        )

        return encoded_image
    
    def on_ai_worker_finished(self, result):
        """Handle the completion of an AI worker thread - delegates to AnalysisCoordinator"""
        self.analysis_coordinator.handle_result(result)

    def on_ai_worker_error(self, error_message):
        """Handle errors from the AI worker thread - delegates to AnalysisCoordinator"""
        self.analysis_coordinator.handle_error(error_message)

    def on_ai_worker_progress(self, progress_message):
        """Handle progress updates from the AI worker thread - delegates to AnalysisCoordinator"""
        self.analysis_coordinator.handle_progress(progress_message)

    def cleanup_ai_worker(self):
        """Clean up the AI worker thread and restore UI state - delegates to AnalysisCoordinator"""
        self.analysis_coordinator.cleanup_worker()

    def analyze_with_ai_ui(self, model):
        """Unified UI wrapper for AI analysis - delegates to AnalysisCoordinator"""
        self.analysis_coordinator.start_analysis(model)

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

    def _create_query_extent_layer(self, ai_provider):
        """Create a layer with only the query extent bounding box"""
        bbox_features_data = [{
            'object_type': 'query_extent',
            'probability': None,
            'result_number': 0,
            'box_2d': PluginConstants.DETECTION_COORD_RANGE,
            'reason': ''
        }]

        # Unpack capture state for layer creation (only need extent, width, height)
        extent, _, _, width, height, _ = self.capture_state.get_all()
        self.layer_manager.create_single_layer_with_features(
            bbox_features_data, ai_provider,
            extent, width, height
        )

    # layer handling functions
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
            # Use the JSON processor to extract features
            processor = AIResponseProcessor(self.config_manager.get_confidence_threshold())
            features_data, stats = processor.process_json_response(my_json)

            # Unpack capture state for layer creation (only need extent, width, height)
            extent, _, _, width, height, _ = self.capture_state.get_all()

            # Create a single layer with all features if we have any valid features
            if features_data:
                self.layer_manager.create_single_layer_with_features(
                    features_data, ai_provider,
                    extent, width, height
                )

                # Create and display success message
                success_msg = MessageFormatter.format_success_message(len(features_data), ai_provider, stats)
                logger.info(success_msg)
                self.iface.messageBar().pushMessage(
                    "LandTalk Plugin",
                    success_msg,
                    level=Qgis.MessageLevel.Success,
                    duration=PluginConstants.SUCCESS_MESSAGE_DURATION
                )
            else:
                # If no analysis results, still create a layer with just the bounding box
                self._create_query_extent_layer(ai_provider)

                # Create and display warning message
                warning_msg = MessageFormatter.format_warning_message(
                    ai_provider, stats, self.config_manager.get_confidence_threshold()
                )
                logger.info(warning_msg)
                self.iface.messageBar().pushMessage(
                    "LandTalk Plugin",
                    warning_msg,
                    level=Qgis.MessageLevel.Warning,
                    duration=PluginConstants.WARNING_MESSAGE_DURATION
                )

            # Debug: Render AI results as yellow rectangles on captured image
            # Extract items for debug rendering
            if isinstance(my_json, list):
                items_to_process = my_json
            elif isinstance(my_json, dict):
                for key in ['objects', 'detections', 'features']:
                    if key in my_json:
                        items_to_process = my_json[key]
                        break
                else:
                    items_to_process = [my_json]
            else:
                items_to_process = []
            self.debug_render_ai_results_on_image(items_to_process, ai_provider)

        except Exception as e:
            logger.error(f"Error processing JSON data for layer creation: {str(e)}")

    def debug_render_ai_results_on_image(self, ai_results, ai_provider):
        """
        Debug function to render AI results as yellow rectangles on the captured image.

        Args:
            ai_results: List of AI detection results with bounding box coordinates
            ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        """
        logger.info(f"Entering debug_render_ai_results_on_image with {len(ai_results) if ai_results else 0} AI results from {ai_provider}")
        try:
            # Check if we have captured image data
            if not self.capture_state.has_capture():
                logger.info("No captured image data available for debug rendering")
                return
            
            # Get the temp directory
            import tempfile
            temp_dir = tempfile.gettempdir()
            
            # Create a temporary file for the captured image
            temp_image_path = os.path.join(temp_dir, "debug_captured_image.png")
            
            # Decode and save the base64 image data
            import base64
            with open(temp_image_path, "wb") as f:
                f.write(base64.b64decode(self.capture_state.image_data))
            
            # Call the debug render function from MapRenderer
            debug_path = self.map_renderer.debug_render_ai_results(ai_results, temp_image_path, temp_dir)
            
            if debug_path:
                logger.info(f"Debug image created successfully: {debug_path}")
            else:
                logger.warning("Failed to create debug image")
            
            # Clean up temporary file
            try:
                os.remove(temp_image_path)
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Error in debug_render_ai_results_on_image: {str(e)}")
        finally:
            logger.info("Exiting debug_render_ai_results_on_image")

    # chat rules functions - delegated to config_manager
    def edit_system_prompt(self):
        """Open dialog to edit chat rules - delegates to config_manager"""
        self.config_manager.edit_system_prompt()

    def show_tutorial_dialog(self):
        """Show the tutorial dialog for first-time users"""
        try:
            tutorial_dialog = TutorialDialog(self.iface.mainWindow())
            result = tutorial_dialog.exec()

            # Check if user wants to show tutorial again
            if not tutorial_dialog.should_show_again():
                self.config_manager.set_show_tutorial(False)
                logger.info("Tutorial disabled - will not show again")

        except Exception as e:
            logger.error(f"Error showing tutorial dialog: {str(e)}")
            # Don't show error message for tutorial, just log it


