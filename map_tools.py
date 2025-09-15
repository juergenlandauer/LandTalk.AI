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

Map Tools Module for LandTalk Plugin

This module contains classes and functions for handling map interactions,
selection tools, and map image rendering.
"""

import os
import tempfile
import base64
from qgis.PyQt.QtCore import Qt, QRectF, QSize, pyqtSignal, QPointF, QPoint
from qgis.PyQt.QtGui import QColor, QPixmap
from qgis.core import (
    Qgis, QgsProject, QgsMapSettings, 
    QgsRectangle, QgsMapRendererParallelJob, QgsWkbTypes,
    QgsPointXY, QgsDistanceArea
)
from qgis.gui import QgsRubberBand, QgsMapTool
from .logging import logger


class RectangleMapTool(QgsMapTool):
    """Map tool for drawing a rectangle on the map canvas"""
    
    # Define the signal as a class variable
    rectangle_created = pyqtSignal(object)
    
    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.rubber_band.setColor(QColor(255, 255, 255, 255))  # White color
        self.rubber_band.setWidth(2)  # Slightly thicker for better visibility
        self.rubber_band.setSecondaryStrokeColor(QColor(0, 0, 0, 255))  # Black outline
        self.rubber_band.setLineStyle(Qt.PenStyle.SolidLine)
        self.start_point = None
        self.end_point = None
        self.is_drawing = False
        # The signal is now defined as a class variable above
        
    def canvasPressEvent(self, event):
        self.start_point = self.toMapCoordinates(event.pos())
        self.end_point = self.start_point
        self.is_drawing = True
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)
        
    def canvasMoveEvent(self, event):
        if not self.start_point or not self.is_drawing:
            return
        
        self.end_point = self.toMapCoordinates(event.pos())
        
        # Update the rubber band
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)
        
        # Get the rectangle in pixels
        rect = self.get_rectangle()
        
        # Convert QPointF to map coordinates (using correct QPoint conversion)
        topLeft = self.toMapCoordinates(QPoint(int(rect.topLeft().x()), int(rect.topLeft().y())))
        topRight = self.toMapCoordinates(QPoint(int(rect.topRight().x()), int(rect.topRight().y())))
        bottomRight = self.toMapCoordinates(QPoint(int(rect.bottomRight().x()), int(rect.bottomRight().y())))
        bottomLeft = self.toMapCoordinates(QPoint(int(rect.bottomLeft().x()), int(rect.bottomLeft().y())))
        
        # Add the points to the rubber band
        self.rubber_band.addPoint(topLeft)
        self.rubber_band.addPoint(topRight)
        self.rubber_band.addPoint(bottomRight)
        self.rubber_band.addPoint(bottomLeft)
        self.rubber_band.addPoint(topLeft)  # Close the polygon
        
    def canvasReleaseEvent(self, event):
        self.is_drawing = False
        self.end_point = self.toMapCoordinates(event.pos())
        
        # Create the final rectangle
        rect = self.get_rectangle()
        self.rectangle_created.emit(rect)
        
    def get_rectangle(self):
        """Create a QRectF from the start and end points"""
        # Get the map canvas transform
        mapToPixel = self.canvas.mapSettings().mapToPixel()
        
        # Convert map coordinates to screen coordinates
        start_point_screen = mapToPixel.transform(self.start_point)
        end_point_screen = mapToPixel.transform(self.end_point)
        
        # Create QPointF objects for screen coordinates
        start_point = QPointF(start_point_screen.x(), start_point_screen.y())
        end_point = QPointF(end_point_screen.x(), end_point_screen.y())
        
        # Create and return the rectangle
        return QRectF(
            start_point if start_point.x() < end_point.x() else end_point,
            end_point if start_point.x() < end_point.x() else start_point
        )


class MapRenderer:
    """Helper class for map rendering operations"""
    
    def __init__(self, map_canvas, ground_resolution_m_per_px=1.0):
        self.map_canvas = map_canvas
        self.ground_resolution_m_per_px = ground_resolution_m_per_px
    
    def get_map_coordinates_and_extent(self, selected_rectangle):
        """Convert selected rectangle to map coordinates and extent.
        
        Args:
            selected_rectangle: QRectF in screen coordinates
            
        Returns:
            tuple: (top_left_map, bottom_right_map, map_extent, extent_width, extent_height)
                   Returns (None, None, None, None, None) if no selected rectangle
        """
        if not selected_rectangle:
            return None, None, None, None, None
        
        # Convert screen coordinates to map coordinates
        mapToPixel = self.map_canvas.mapSettings().mapToPixel()
        top_left_point = QPoint(int(selected_rectangle.topLeft().x()), int(selected_rectangle.topLeft().y()))
        bottom_right_point = QPoint(int(selected_rectangle.bottomRight().x()), int(selected_rectangle.bottomRight().y()))
        
        top_left_map = mapToPixel.toMapCoordinates(top_left_point)
        bottom_right_map = mapToPixel.toMapCoordinates(bottom_right_point)
        
        # Create map extent from coordinates
        map_extent = QgsRectangle(top_left_map.x(), bottom_right_map.y(), bottom_right_map.x(), top_left_map.y())
        
        # Calculate the extent in map units
        extent_width = abs(bottom_right_map.x() - top_left_map.x())
        extent_height = abs(bottom_right_map.y() - top_left_map.y())
        
        return top_left_map, bottom_right_map, map_extent, extent_width, extent_height

    def filter_canvas_layers(self):
        """Filter out LandTalk.ai analysis layers from canvas layers.
        
        Returns:
            list: Filtered list of layers excluding LandTalk.ai analysis layers
        """
        canvas_layers = self.map_canvas.layers()
        filtered_layers = []
        ai_analysis_group = QgsProject.instance().layerTreeRoot().findGroup("LandTalk.ai")
        
        logger.info(f"Total canvas layers: {len(canvas_layers)}")
        logger.info(f"LandTalk.ai group found: {ai_analysis_group is not None}")
        
        for layer in canvas_layers:
            if layer.isValid():
                # Check if layer is in the LandTalk.ai group or any of its subgroups
                layer_tree_layer = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                if layer_tree_layer and ai_analysis_group:
                    # Check if this layer is anywhere within the LandTalk.ai group hierarchy
                    current_parent = layer_tree_layer.parent()
                    is_in_landtalk_group = False
                    
                    # Walk up the parent hierarchy to check if we're in the LandTalk.ai group
                    while current_parent:
                        if current_parent == ai_analysis_group:
                            is_in_landtalk_group = True
                            break
                        # Check if current parent is a group and get its parent
                        if hasattr(current_parent, 'parent'):
                            current_parent = current_parent.parent()
                        else:
                            break
                    
                    if is_in_landtalk_group:
                        logger.info(f"Excluding LandTalk.ai layer: {layer.name()}")
                        continue
                
                filtered_layers.append(layer)
        
        logger.info(f"Filtered layers count: {len(filtered_layers)} (excluded {len(canvas_layers) - len(filtered_layers)} LandTalk.ai layers)")
        return filtered_layers

    def create_and_render_map(self, map_extent, output_width, output_height):
        """Create map settings and render the map.
        
        Args:
            map_extent: QgsRectangle defining the map extent
            output_width: Width of output image in pixels
            output_height: Height of output image in pixels
            
        Returns:
            QImage: The rendered map image, or None if rendering failed
        """
        # Create map settings
        map_settings = QgsMapSettings()
        map_settings.setLayers(self.filter_canvas_layers())
        map_settings.setExtent(map_extent)
        map_settings.setOutputSize(QSize(output_width, output_height))
        map_settings.setDestinationCrs(self.map_canvas.mapSettings().destinationCrs())
        map_settings.setBackgroundColor(self.map_canvas.canvasColor())
        map_settings.setFlag(Qgis.MapSettingsFlag.Antialiasing, True)
        
        # Render the map
        job = QgsMapRendererParallelJob(map_settings)
        job.start()
        job.waitForFinished()
        
        # Get the rendered image
        rendered_image = job.renderedImage()
        if rendered_image.isNull():
            logger.warning("Failed to render map image")
            return None
        
        return rendered_image

    def capture_map_thumbnail(self, selected_rectangle):
        """Capture a thumbnail of the selected area for display purposes"""
        if not selected_rectangle:
            logger.info("No selected rectangle for thumbnail")
            return None
        
        try:
            # Get map coordinates and extent using common helper
            top_left_map, bottom_right_map, map_extent, extent_width, extent_height = self.get_map_coordinates_and_extent(selected_rectangle)
            if map_extent is None:
                logger.info("No selected rectangle for thumbnail")
                return None
            
            # Calculate aspect ratio from selected rectangle to preserve it in thumbnail
            rect_width = abs(selected_rectangle.width())
            rect_height = abs(selected_rectangle.height())
            aspect_ratio = rect_width / rect_height if rect_height > 0 else 1.0
            
            # Set thumbnail dimensions while preserving aspect ratio
            max_thumbnail_width = 200
            max_thumbnail_height = 150
            
            if aspect_ratio >= (max_thumbnail_width / max_thumbnail_height):
                # Rectangle is wider, constrain by width
                thumbnail_width = max_thumbnail_width
                thumbnail_height = int(max_thumbnail_width / aspect_ratio)
            else:
                # Rectangle is taller, constrain by height
                thumbnail_height = max_thumbnail_height
                thumbnail_width = int(max_thumbnail_height * aspect_ratio)
            
            logger.info(f"Rectangle dimensions: {rect_width:.1f}x{rect_height:.1f}, aspect ratio: {aspect_ratio:.3f}")
            logger.info(f"Thumbnail dimensions: {thumbnail_width}x{thumbnail_height}")
            
            # Render the map using common helper
            thumbnail_image = self.create_and_render_map(map_extent, thumbnail_width, thumbnail_height)
            if thumbnail_image is None:
                return None
            
            # Convert to QPixmap
            thumbnail_pixmap = QPixmap.fromImage(thumbnail_image)
            logger.info(f"Created thumbnail pixmap, size: {thumbnail_pixmap.width()}x{thumbnail_pixmap.height()}")
            
            # Save thumbnail to temp directory for logging purposes
            try:
                thumbnail_path = os.path.join(tempfile.gettempdir(), "gemini_map_thumbnail.png")
                thumbnail_pixmap.save(thumbnail_path, "PNG")
                logger.info(f"Thumbnail saved to temp directory: {thumbnail_path}")
            except Exception as e:
                logger.warning(f"Failed to save thumbnail to temp directory: {str(e)}")
            
            return thumbnail_pixmap
            
        except Exception as e:
            logger.error(f"Error in capture_map_thumbnail: {str(e)}")
            return None

    def capture_map_image(self, selected_rectangle):
        """Capture the selected area of the map as an image at fixed ground resolution
        
        Returns:
            tuple: (base64_encoded_image, captured_map_extent, captured_top_left_map, 
                   captured_bottom_right_map, captured_extent_width, captured_extent_height)
        """
        logger.info(f"capture_map_image called, selected_rectangle: {selected_rectangle}")
        if not selected_rectangle:
            logger.info("No selected rectangle, returning None")
            return None, None, None, None, None, None
        
        # Get map coordinates and extent using common helper
        top_left_map, bottom_right_map, map_extent, extent_width, extent_height = self.get_map_coordinates_and_extent(selected_rectangle)
        if map_extent is None:
            logger.info("No selected rectangle, returning None")
            return None, None, None, None, None, None
        
        logger.info(f"Map coordinates in capture_map_image:")
        logger.info(f"  Top-left: ({top_left_map.x():.6f}, {top_left_map.y():.6f})")
        logger.info(f"  Bottom-right: ({bottom_right_map.x():.6f}, {bottom_right_map.y():.6f})")
        logger.info(f"  Extent: {extent_width:.6f} x {extent_height:.6f} map units")
        
        # Compute output dimensions from fixed ground resolution (meters/pixel)
        # Calculate map-units-per-meter at the AOI center using QgsDistanceArea
        distance_calc = QgsDistanceArea()
        distance_calc.setSourceCrs(self.map_canvas.mapSettings().destinationCrs(), QgsProject.instance().transformContext())
        try:
            distance_calc.setEllipsoid(QgsProject.instance().ellipsoid())
        except Exception:
            pass
        center_x = (top_left_map.x() + bottom_right_map.x()) / 2.0
        center_y = (top_left_map.y() + bottom_right_map.y()) / 2.0
        meters_per_mapunit_x = distance_calc.measureLine(QgsPointXY(center_x, center_y), QgsPointXY(center_x + 1.0, center_y))
        meters_per_mapunit_y = distance_calc.measureLine(QgsPointXY(center_x, center_y), QgsPointXY(center_x, center_y + 1.0))
        map_units_per_meter_x = 1.0 / meters_per_mapunit_x if meters_per_mapunit_x and meters_per_mapunit_x > 0 else 0.0
        map_units_per_meter_y = 1.0 / meters_per_mapunit_y if meters_per_mapunit_y and meters_per_mapunit_y > 0 else 0.0
        pixel_size_x = self.ground_resolution_m_per_px * map_units_per_meter_x if map_units_per_meter_x > 0 else None
        pixel_size_y = self.ground_resolution_m_per_px * map_units_per_meter_y if map_units_per_meter_y > 0 else None
        
        if not pixel_size_x or not pixel_size_y:
            # Fallback to screen resolution if conversion failed
            output_width = int(selected_rectangle.width())
            output_height = int(selected_rectangle.height())
            logger.warning("Could not compute map-units per meter; using screen resolution for output size")
        else:
            output_width = max(1, int(round(extent_width / pixel_size_x)))
            output_height = max(1, int(round(extent_height / pixel_size_y)))
            logger.info(f"Using fixed ground resolution: {self.ground_resolution_m_per_px:.3f} m/pixel -> pixel size {pixel_size_x:.6f} x {pixel_size_y:.6f} map units/pixel")
            logger.info(f"Output dimensions based on fixed ground resolution: {output_width} x {output_height} pixels")
        
        logger.info(f"Final map_extent: {map_extent}")
        
        # Render the map using common helper
        rendered_image = self.create_and_render_map(map_extent, output_width, output_height)
        if rendered_image is None:
            return None, None, None, None, None, None
        
        # Log which layers are being rendered
        filtered_layers = self.filter_canvas_layers()
        canvas_layers = self.map_canvas.layers()  # Use consistent method with filter_canvas_layers
        filtered_layer_names = [layer.name() for layer in filtered_layers if layer.isValid()]
        logger.info(f"Rendering {len(filtered_layers)} filtered layers (excluding LandTalk.ai): {', '.join(filtered_layer_names)}")
        
        # Log original count for comparison
        original_count = len([layer for layer in canvas_layers if layer.isValid()])
        if len(filtered_layers) < original_count:
            logger.info(f"Excluded {original_count - len(filtered_layers)} LandTalk.ai layer(s) from capture")
        
        # Convert to QPixmap and save to file
        pixmap = QPixmap.fromImage(rendered_image)
        image_path = os.path.join(tempfile.gettempdir(), "gemini_map_image.png")
        pixmap.save(image_path, "PNG")
        
        # Read the image and convert to base64
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        logger.info(f"Image captured successfully, size: {len(encoded_image)} characters")
        return encoded_image, map_extent, top_left_map, bottom_right_map, extent_width, extent_height
