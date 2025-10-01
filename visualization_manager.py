# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI
                                 A QGIS Plugin
 Map Visualization Manager for LandTalk Plugin
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

Map Visualization Manager Module for LandTalk Plugin

This module handles map interactions, rectangle selection, rubber band visualization,
and coordinate transformations.
"""

from qgis.PyQt.QtCore import Qt, QRectF, QSize, pyqtSignal, QPointF, QPoint, QObject
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.core import QgsWkbTypes, QgsPointXY
from qgis.gui import QgsRubberBand
from .map_tools import RectangleMapTool, MapRenderer
from .logging import logger


class MapVisualizationManager(QObject):
    """Manages map visualization, interaction, and coordinate transformations"""
    
    # Signals
    rectangle_selected = pyqtSignal(object)  # Emitted when a rectangle is selected
    
    def __init__(self, map_canvas, config_manager):
        """Initialize the visualization manager
        
        Args:
            map_canvas: QGIS map canvas
            config_manager: PluginConfigManager instance
        """
        super().__init__()
        self.map_canvas = map_canvas
        self.config_manager = config_manager
        
        # Map interaction components
        self.map_tool = None
        self.rubber_band = None
        self.selected_rectangle = None
        
        # Map coordinates storage for captured image
        self.captured_map_extent = None
        self.captured_top_left_map = None
        self.captured_bottom_right_map = None
        self.captured_extent_width = None
        self.captured_extent_height = None
        self.captured_image_data = None
        
        # Initialize map renderer
        self.map_renderer = MapRenderer(
            self.map_canvas, 
            self.config_manager.ground_resolution_m_per_px if hasattr(self.config_manager, 'ground_resolution_m_per_px') else 1.0
        )
    
    def start_rectangle_selection(self):
        """Start the rectangle selection tool"""
        try:
            logger.info("Starting rectangle selection")
            
            # Clean up any existing selection
            self.cleanup_selection()
            
            # Create and set the rectangle selection tool
            self.map_tool = RectangleMapTool(self.map_canvas)
            self.map_tool.rectangle_created.connect(self.on_rectangle_created)
            self.map_canvas.setMapTool(self.map_tool)
            
            # Change cursor to crosshair
            self.map_canvas.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            
            logger.info("Rectangle selection tool activated")
            
        except Exception as e:
            logger.error(f"Error starting rectangle selection: {str(e)}")
    
    def on_rectangle_created(self, rectangle):
        """Handle rectangle selection on the map"""
        try:
            logger.info(f"Rectangle created: {rectangle}")
            
            # Store the selected rectangle
            self.selected_rectangle = rectangle
            
            # Create rubber band visualization
            self._create_rubber_band_visualization(rectangle)
            
            # Clean up the map tool's rubber band after selection is complete
            if hasattr(self.map_tool, 'rubber_band') and self.map_tool.rubber_band:
                self.map_tool.rubber_band.reset()
            
            # Emit signal for other components
            self.rectangle_selected.emit(rectangle)
            
            logger.info("Rectangle selection completed")
            
        except Exception as e:
            logger.error(f"Error handling rectangle creation: {str(e)}")
    
    def _create_rubber_band_visualization(self, rectangle):
        """Create rubber band visualization for the selected rectangle"""
        try:
            # Clean up existing rubber band
            if self.rubber_band:
                self.map_canvas.scene().removeItem(self.rubber_band)
            
            # Create new rubber band
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
            
            logger.info("Rubber band visualization created")
            
        except Exception as e:
            logger.error(f"Error creating rubber band visualization: {str(e)}")
    
    def capture_map_image(self):
        """Capture the selected area of the map as an image"""
        try:
            logger.info("Capturing map image")
            
            if not self.selected_rectangle:
                logger.warning("No rectangle selected for image capture")
                return None, None, None, None, None, None
            
            # Capture the map image using the map renderer
            result = self.map_renderer.capture_map_image(self.selected_rectangle)
            
            if result[0]:  # If capture was successful
                # Store the captured data
                (self.captured_image_data, self.captured_map_extent, 
                 self.captured_top_left_map, self.captured_bottom_right_map, 
                 self.captured_extent_width, self.captured_extent_height) = result
                
                logger.info("Map image captured successfully")
            else:
                logger.warning("Failed to capture map image")
            
            return result
            
        except Exception as e:
            logger.error(f"Error capturing map image: {str(e)}")
            return None, None, None, None, None, None
    
    def capture_map_thumbnail(self):
        """Capture a thumbnail of the selected area for display purposes"""
        try:
            if not self.selected_rectangle:
                logger.warning("No rectangle selected for thumbnail capture")
                return None
            
            thumbnail = self.map_renderer.capture_map_thumbnail(self.selected_rectangle)
            logger.info("Map thumbnail captured" if thumbnail else "Failed to capture thumbnail")
            return thumbnail
            
        except Exception as e:
            logger.error(f"Error capturing map thumbnail: {str(e)}")
            return None
    
    def convert_to_map_coordinates(self, bbox_coords):
        """
        Convert bounding box coordinates to map coordinates.
        Assumes input coordinates are relative to the captured map extent and are in 0-1000 range.
        
        :param bbox_coords: Tuple of (xmin, ymin, xmax, ymax) coordinates in 0-1000 range
        :return: Tuple of map coordinates
        """
        try:
            if not self.captured_map_extent or not bbox_coords or len(bbox_coords) < 4:
                logger.warning("Cannot convert coordinates: missing captured extent or invalid bbox")
                return None
            
            x1, y1, x2, y2 = bbox_coords[:4]
            
            # Convert from 0-1000 range to 0-1 range
            x1_norm = x1 / 1000.0
            y1_norm = y1 / 1000.0
            x2_norm = x2 / 1000.0
            y2_norm = y2 / 1000.0
            
            # Convert to map coordinates
            left = self.captured_map_extent.xMinimum() + (x1_norm * self.captured_extent_width)
            top = self.captured_map_extent.yMaximum() - (y1_norm * self.captured_extent_height)
            right = self.captured_map_extent.xMinimum() + (x2_norm * self.captured_extent_width)
            bottom = self.captured_map_extent.yMaximum() - (y2_norm * self.captured_extent_height)
            
            logger.info(f"Converted bbox {bbox_coords} to map coordinates: ({left}, {top}, {right}, {bottom})")
            return (left, top, right, bottom)
            
        except Exception as e:
            logger.error(f"Error converting coordinates: {str(e)}")
            return None
    
    def cleanup_selection(self):
        """Clean up the current selection and reset the map tool"""
        try:
            logger.info("Cleaning up map selection")
            
            # Clean up the rubber band
            if self.rubber_band:
                self.map_canvas.scene().removeItem(self.rubber_band)
                self.rubber_band = None
            
            # Clean up the map tool's rubber band if it exists
            if self.map_tool and hasattr(self.map_tool, 'rubber_band'):
                try:
                    if self.map_tool.rubber_band:
                        self.map_canvas.scene().removeItem(self.map_tool.rubber_band)
                except Exception as e:
                    logger.warning(f"Error removing map tool rubber band: {str(e)}")
                self.map_tool.rubber_band.reset()
            
            # Reset cursor
            self.map_canvas.unsetCursor()
            
            # Reset map tool
            if self.map_tool:
                self.map_canvas.unsetMapTool(self.map_tool)
                self.map_tool = None
            
            # Clear selection data
            self.selected_rectangle = None
            
            logger.info("Map selection cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during selection cleanup: {str(e)}")
    
    def reset_captured_data(self):
        """Reset all captured map data"""
        try:
            self.captured_map_extent = None
            self.captured_top_left_map = None
            self.captured_bottom_right_map = None
            self.captured_extent_width = None
            self.captured_extent_height = None
            self.captured_image_data = None
            
            logger.info("Captured map data reset")
            
        except Exception as e:
            logger.error(f"Error resetting captured data: {str(e)}")
    
    def has_selection(self):
        """Check if there is a current rectangle selection"""
        return self.selected_rectangle is not None
    
    def has_captured_data(self):
        """Check if map data has been captured"""
        return (self.captured_map_extent is not None and 
                self.captured_image_data is not None)
    
    def get_captured_extent(self):
        """Get the captured map extent"""
        return self.captured_map_extent
    
    def get_captured_image_data(self):
        """Get the captured image data (base64 encoded)"""
        return self.captured_image_data
    
    def get_captured_dimensions(self):
        """Get the captured area dimensions in map units"""
        return self.captured_extent_width, self.captured_extent_height
    
    def get_captured_corners(self):
        """Get the captured area corner coordinates"""
        return self.captured_top_left_map, self.captured_bottom_right_map
    
    def get_map_renderer(self):
        """Get the map renderer instance"""
        return self.map_renderer
