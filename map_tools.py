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
import time
from qgis.PyQt.QtCore import Qt, QRectF, QSize, pyqtSignal, QPointF, QPoint
from qgis.PyQt.QtGui import QColor, QPixmap, QPainter, QPen
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
    
    def _convert_screen_rect_to_map_points(self, rect):
        """Convert screen rectangle to map coordinate points.
        
        Args:
            rect: QRectF in screen coordinates
            
        Returns:
            tuple: (topLeft, topRight, bottomRight, bottomLeft) as map coordinates
        """
        # Convert QPointF to map coordinates (using correct QPoint conversion)
        topLeft = self.toMapCoordinates(QPoint(int(rect.topLeft().x()), int(rect.topLeft().y())))
        topRight = self.toMapCoordinates(QPoint(int(rect.topRight().x()), int(rect.topRight().y())))
        bottomRight = self.toMapCoordinates(QPoint(int(rect.bottomRight().x()), int(rect.bottomRight().y())))
        bottomLeft = self.toMapCoordinates(QPoint(int(rect.bottomLeft().x()), int(rect.bottomLeft().y())))
        
        return topLeft, topRight, bottomRight, bottomLeft
        
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
        
        # Convert screen rectangle to map points using helper method
        topLeft, topRight, bottomRight, bottomLeft = self._convert_screen_rect_to_map_points(rect)
        
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

    # Constants for thumbnail generation
    MAX_THUMBNAIL_WIDTH = 200
    MAX_THUMBNAIL_HEIGHT = 150
    TEMP_IMAGE_FILENAME = "gemini_map_image.png"
    TEMP_THUMBNAIL_FILENAME = "gemini_map_thumbnail.png"

    # Rendering quality levels
    QUALITY_FAST = 0    # No antialiasing, simplified rendering
    QUALITY_NORMAL = 1  # Standard antialiasing
    QUALITY_HIGH = 2    # High quality with all features

    def __init__(self, map_canvas, ground_resolution_m_per_px=1.0):
        self.map_canvas = map_canvas
        self.ground_resolution_m_per_px = ground_resolution_m_per_px
        self._cached_filtered_layers = None
        self._cached_layer_count = None
    
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
        
        # Log the map coordinates of the rectangle
        logger.info(f"Rectangle map coordinates: Top-left: ({top_left_map.x():.6f}, {top_left_map.y():.6f}), Bottom-right: ({bottom_right_map.x():.6f}, {bottom_right_map.y():.6f}), Extent: {extent_width:.6f} x {extent_height:.6f} map units")
        
        return top_left_map, bottom_right_map, map_extent, extent_width, extent_height

    def filter_canvas_layers(self, use_cache=True):
        """Filter out LandTalk.ai analysis layers from canvas layers.

        Args:
            use_cache: If True, use cached result when layer count hasn't changed

        Returns:
            list: Filtered list of layers excluding LandTalk.ai analysis layers
        """
        canvas_layers = self.map_canvas.layers()
        current_layer_count = len(canvas_layers)

        # Return cached result if layer count hasn't changed
        if use_cache and self._cached_filtered_layers is not None and self._cached_layer_count == current_layer_count:
            logger.debug(f"Using cached filtered layers ({len(self._cached_filtered_layers)} layers)")
            return self._cached_filtered_layers

        ai_analysis_group = QgsProject.instance().layerTreeRoot().findGroup("LandTalk.ai")

        logger.info(f"Total canvas layers: {len(canvas_layers)}")
        logger.info(f"LandTalk.ai group found: {ai_analysis_group is not None}")

        # Early return if no LandTalk.ai group exists - no filtering needed
        if not ai_analysis_group:
            valid_layers = [layer for layer in canvas_layers if layer.isValid()]
            logger.info(f"No LandTalk.ai group found, returning {len(valid_layers)} valid layers")
            # Cache the result
            self._cached_filtered_layers = valid_layers
            self._cached_layer_count = current_layer_count
            return valid_layers

        # Build set of layer IDs in LandTalk.ai group for faster lookup
        landtalk_layer_ids = set()
        self._collect_group_layer_ids(ai_analysis_group, landtalk_layer_ids)

        # Filter layers using the prebuilt set for O(1) lookup
        filtered_layers = []
        excluded_count = 0

        for layer in canvas_layers:
            if not layer.isValid():
                continue

            if layer.id() in landtalk_layer_ids:
                logger.info(f"Excluding LandTalk.ai layer: {layer.name()}")
                excluded_count += 1
            else:
                filtered_layers.append(layer)

        logger.info(f"Filtered layers count: {len(filtered_layers)} (excluded {excluded_count} LandTalk.ai layers)")

        # Cache the result
        self._cached_filtered_layers = filtered_layers
        self._cached_layer_count = current_layer_count

        return filtered_layers
    
    def invalidate_layer_cache(self):
        """Invalidate the cached filtered layers. Call this when layers are added/removed."""
        self._cached_filtered_layers = None
        self._cached_layer_count = None
        logger.debug("Layer cache invalidated")

    def _collect_group_layer_ids(self, group_node, layer_id_set):
        """Recursively collect all layer IDs within a group and its subgroups.

        Args:
            group_node: QgsLayerTreeGroup to process
            layer_id_set: Set to add layer IDs to
        """
        for child in group_node.children():
            if hasattr(child, 'layer') and child.layer():
                # This is a layer node
                layer_id_set.add(child.layer().id())
            elif hasattr(child, 'children'):
                # This is a group node, recurse into it
                self._collect_group_layer_ids(child, layer_id_set)

    def _calculate_thumbnail_dimensions(self, source_width, source_height):
        """Calculate thumbnail dimensions while preserving aspect ratio.
        
        Args:
            source_width: Original width (pixels or any unit)
            source_height: Original height (pixels or any unit)
            
        Returns:
            tuple: (thumbnail_width, thumbnail_height)
        """
        if source_height <= 0:
            return self.MAX_THUMBNAIL_WIDTH, self.MAX_THUMBNAIL_HEIGHT
            
        aspect_ratio = source_width / source_height
        max_ratio = self.MAX_THUMBNAIL_WIDTH / self.MAX_THUMBNAIL_HEIGHT
        
        if aspect_ratio >= max_ratio:
            # Image is wider, constrain by width
            thumbnail_width = self.MAX_THUMBNAIL_WIDTH
            thumbnail_height = int(self.MAX_THUMBNAIL_WIDTH / aspect_ratio)
        else:
            # Image is taller, constrain by height
            thumbnail_height = self.MAX_THUMBNAIL_HEIGHT
            thumbnail_width = int(self.MAX_THUMBNAIL_HEIGHT * aspect_ratio)
            
        return thumbnail_width, thumbnail_height

    def _save_thumbnail_to_temp(self, thumbnail_pixmap):
        """Save thumbnail to temporary directory with standardized error handling.
        
        Args:
            thumbnail_pixmap: QPixmap to save
            
        Returns:
            str: Path to saved thumbnail, or None if failed
        """
        try:
            thumbnail_path = os.path.join(tempfile.gettempdir(), self.TEMP_THUMBNAIL_FILENAME)
            if thumbnail_pixmap.save(thumbnail_path, "PNG"):
                logger.info(f"Thumbnail saved to temp directory: {thumbnail_path}")
                return thumbnail_path
            else:
                logger.warning(f"Failed to save thumbnail to: {thumbnail_path}")
                return None
        except Exception as e:
            logger.warning(f"Failed to save thumbnail to temp directory: {str(e)}")
            return None

    def _handle_operation_error(self, operation_name, error, return_value=None):
        """Standardized error handling for map operations.
        
        Args:
            operation_name: Name of the operation for logging
            error: Exception that occurred
            return_value: Value to return on error (default: None)
            
        Returns:
            The specified return_value
        """
        logger.error(f"Error in {operation_name}: {str(error)}")
        return return_value

    def create_and_render_map(self, map_extent, output_width, output_height, quality=None):
        """Create map settings and render the map.

        Args:
            map_extent: QgsRectangle defining the map extent
            output_width: Width of output image in pixels
            output_height: Height of output image in pixels
            quality: Rendering quality level (QUALITY_FAST/NORMAL/HIGH), defaults to NORMAL

        Returns:
            QImage: The rendered map image, or None if rendering failed
        """
        if quality is None:
            quality = self.QUALITY_NORMAL

        # Create map settings
        map_settings = QgsMapSettings()
        map_settings.setLayers(self.filter_canvas_layers())
        map_settings.setExtent(map_extent)
        map_settings.setOutputSize(QSize(output_width, output_height))
        map_settings.setDestinationCrs(self.map_canvas.mapSettings().destinationCrs())
        map_settings.setBackgroundColor(self.map_canvas.canvasColor())

        # Apply quality settings
        if quality == self.QUALITY_FAST:
            # Fast rendering: disable antialiasing and other expensive features
            map_settings.setFlag(Qgis.MapSettingsFlag.Antialiasing, False)
            map_settings.setFlag(Qgis.MapSettingsFlag.RenderPartialOutput, True)
            map_settings.setFlag(Qgis.MapSettingsFlag.UseRenderingOptimization, True)
        elif quality == self.QUALITY_HIGH:
            # High quality: enable all features
            map_settings.setFlag(Qgis.MapSettingsFlag.Antialiasing, True)
            map_settings.setFlag(Qgis.MapSettingsFlag.HighQualityImageTransforms, True)
        else:
            # Normal quality: standard antialiasing
            map_settings.setFlag(Qgis.MapSettingsFlag.Antialiasing, True)
            map_settings.setFlag(Qgis.MapSettingsFlag.UseRenderingOptimization, True)

        # Render the map
        quality_names = {self.QUALITY_FAST: "FAST", self.QUALITY_NORMAL: "NORMAL", self.QUALITY_HIGH: "HIGH"}
        logger.info(f"Starting map rendering (quality: {quality_names.get(quality, 'UNKNOWN')})...")
        start_time = time.time()

        job = QgsMapRendererParallelJob(map_settings)
        job.start()

        # QGIS waitForFinished() blocks until complete, no timeout support
        # For now, just wait - timeout implementation would require threading
        job.waitForFinished()

        elapsed_time = time.time() - start_time
        logger.info(f"Map rendering completed in {elapsed_time:.3f} seconds")

        # Get the rendered image
        rendered_image = job.renderedImage()
        if rendered_image.isNull():
            logger.warning("Failed to render map image")
            return None

        return rendered_image

    def capture_map_thumbnail(self, selected_rectangle):
        """Create a thumbnail by scaling the AI image if it exists, otherwise render a new one.

        Args:
            selected_rectangle: QRectF in screen coordinates

        Returns:
            QPixmap: Thumbnail image, or None if failed
        """
        if not selected_rectangle:
            logger.info("No selected rectangle for thumbnail")
            return None

        try:
            # Try to load and scale existing AI image first (faster and ensures consistency)
            ai_image_path = os.path.join(tempfile.gettempdir(), self.TEMP_IMAGE_FILENAME)
            if os.path.exists(ai_image_path):
                ai_pixmap = QPixmap(ai_image_path)
                if not ai_pixmap.isNull():
                    thumb_w, thumb_h = self._calculate_thumbnail_dimensions(ai_pixmap.width(), ai_pixmap.height())
                    thumbnail_pixmap = ai_pixmap.scaled(thumb_w, thumb_h, Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)
                    logger.info(f"Thumbnail from AI image: {ai_pixmap.width()}x{ai_pixmap.height()} -> {thumb_w}x{thumb_h}")
                    self._save_thumbnail_to_temp(thumbnail_pixmap)
                    return thumbnail_pixmap

            # Fallback: Render thumbnail directly
            logger.info("AI image not found, rendering thumbnail directly")
            _, _, map_extent, _, _ = self.get_map_coordinates_and_extent(selected_rectangle)
            if map_extent is None:
                return None

            thumb_w, thumb_h = self._calculate_thumbnail_dimensions(abs(selected_rectangle.width()),
                                                                    abs(selected_rectangle.height()))
            thumbnail_image = self.create_and_render_map(map_extent, thumb_w, thumb_h, quality=self.QUALITY_FAST)
            if thumbnail_image is None:
                return None

            thumbnail_pixmap = QPixmap.fromImage(thumbnail_image)
            logger.info(f"Rendered thumbnail: {thumb_w}x{thumb_h}")
            self._save_thumbnail_to_temp(thumbnail_pixmap)
            return thumbnail_pixmap

        except Exception as e:
            return self._handle_operation_error("capture_map_thumbnail", e)

    def capture_map_image(self, selected_rectangle):
        """Capture the selected area of the map as an image at fixed ground resolution

        Returns:
            tuple: (base64_encoded_image, captured_map_extent, captured_top_left_map,
                   captured_bottom_right_map, captured_extent_width, captured_extent_height)
        """
        if not selected_rectangle:
            logger.info("No selected rectangle")
            return None, None, None, None, None, None

        # Get map coordinates and extent
        top_left_map, bottom_right_map, map_extent, extent_width, extent_height = self.get_map_coordinates_and_extent(selected_rectangle)
        if map_extent is None:
            return None, None, None, None, None, None

        # Calculate output dimensions based on fixed ground resolution
        output_width, output_height = self._calculate_output_dimensions(
            top_left_map, bottom_right_map, extent_width, extent_height, selected_rectangle
        )
        logger.info(f"Capturing map image: {output_width}x{output_height} pixels at {self.ground_resolution_m_per_px}m/px")

        # Render the map
        rendered_image = self.create_and_render_map(map_extent, output_width, output_height)
        if rendered_image is None:
            return None, None, None, None, None, None

        # Save to file and encode to base64
        pixmap = QPixmap.fromImage(rendered_image)
        image_path = os.path.join(tempfile.gettempdir(), self.TEMP_IMAGE_FILENAME)
        pixmap.save(image_path, "PNG")

        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

        logger.info(f"Map image captured: {len(encoded_image)} chars")
        return encoded_image, map_extent, top_left_map, bottom_right_map, extent_width, extent_height

    def _calculate_output_dimensions(self, top_left_map, bottom_right_map, extent_width, extent_height, selected_rectangle):
        """Calculate output image dimensions based on ground resolution.

        Returns:
            tuple: (output_width, output_height) in pixels
        """
        # Calculate map-units-per-meter at center of area
        distance_calc = QgsDistanceArea()
        distance_calc.setSourceCrs(self.map_canvas.mapSettings().destinationCrs(),
                                   QgsProject.instance().transformContext())
        try:
            distance_calc.setEllipsoid(QgsProject.instance().ellipsoid())
        except Exception:
            pass

        center_x = (top_left_map.x() + bottom_right_map.x()) / 2.0
        center_y = (top_left_map.y() + bottom_right_map.y()) / 2.0
        meters_per_mapunit_x = distance_calc.measureLine(QgsPointXY(center_x, center_y),
                                                         QgsPointXY(center_x + 1.0, center_y))
        meters_per_mapunit_y = distance_calc.measureLine(QgsPointXY(center_x, center_y),
                                                         QgsPointXY(center_x, center_y + 1.0))

        # Convert to pixel dimensions
        if meters_per_mapunit_x and meters_per_mapunit_x > 0 and meters_per_mapunit_y and meters_per_mapunit_y > 0:
            map_units_per_meter_x = 1.0 / meters_per_mapunit_x
            map_units_per_meter_y = 1.0 / meters_per_mapunit_y
            pixel_size_x = self.ground_resolution_m_per_px * map_units_per_meter_x
            pixel_size_y = self.ground_resolution_m_per_px * map_units_per_meter_y
            output_width = max(1, int(round(extent_width / pixel_size_x)))
            output_height = max(1, int(round(extent_height / pixel_size_y)))
        else:
            # Fallback to screen resolution
            output_width = int(selected_rectangle.width())
            output_height = int(selected_rectangle.height())
            logger.warning("Using screen resolution as fallback")

        return output_width, output_height

    def debug_render_ai_results(self, ai_results, captured_image_path, plugin_directory):
        """Render AI detection results as yellow rectangles on the captured image for debugging.

        Args:
            ai_results: List of AI detection results with bounding box coordinates
            captured_image_path: Path to the original captured image
            plugin_directory: Directory where to save the debug image

        Returns:
            str: Path to the debug image file, or None if failed
        """
        try:
            # Load the captured image
            if not os.path.exists(captured_image_path):
                logger.error(f"Image not found: {captured_image_path}")
                return None

            pixmap = QPixmap(captured_image_path)
            if pixmap.isNull():
                logger.error(f"Failed to load image: {captured_image_path}")
                return None

            # Draw rectangles on the image
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(255, 255, 0, 255), 3))  # Yellow, 3px

            rectangles_drawn = 0
            for i, result in enumerate(ai_results):
                bbox_coords = self._extract_bbox_coordinates(result)
                if bbox_coords:
                    rect = self._bbox_to_qrect(bbox_coords, pixmap.width(), pixmap.height())
                    painter.drawRect(rect)
                    rectangles_drawn += 1
                    logger.debug(f"Drew rectangle {rectangles_drawn}: {rect}")
                else:
                    logger.warning(f"No bbox found for result {i+1}")

            painter.end()

            # Save the debug image
            debug_path = os.path.join(plugin_directory, "debug_ai_results.png")
            if pixmap.save(debug_path, "PNG"):
                logger.info(f"Debug image saved: {debug_path} ({rectangles_drawn} rectangles)")
                return debug_path
            else:
                logger.error(f"Failed to save debug image: {debug_path}")
                return None

        except Exception as e:
            return self._handle_operation_error("debug_render_ai_results", e)

    def _extract_bbox_coordinates(self, result):
        """Extract bounding box coordinates from AI result in various formats.

        Returns:
            tuple: (x1, y1, x2, y2) or None if not found
        """
        if not isinstance(result, dict):
            return None

        # Try bounding_box or Bounding Box field
        for bbox_field in ['bounding_box', 'Bounding Box']:
            if bbox_field in result:
                bbox_data = result[bbox_field]
                if isinstance(bbox_data, list) and len(bbox_data) >= 4:
                    return tuple(bbox_data[:4])

        # Try x, y, width, height format
        if all(field in result for field in ['x', 'y', 'width', 'height']):
            x, y, w, h = result['x'], result['y'], result['width'], result['height']
            return (x, y, x + w, y + h)

        # Try xmin, ymin, xmax, ymax format
        if all(field in result for field in ['xmin', 'ymin', 'xmax', 'ymax']):
            return (result['xmin'], result['ymin'], result['xmax'], result['ymax'])

        return None

    def _bbox_to_qrect(self, bbox_coords, image_width, image_height):
        """Convert bounding box coordinates (0-1000 range) to QRectF in image pixels.

        Args:
            bbox_coords: tuple of (x1, y1, x2, y2) in 0-1000 range
            image_width: Image width in pixels
            image_height: Image height in pixels

        Returns:
            QRectF: Rectangle in image pixel coordinates
        """
        x1, y1, x2, y2 = bbox_coords
        # Convert from 0-1000 range to pixel coordinates
        left = min(x1, x2) / 1000.0 * image_width
        top = min(y1, y2) / 1000.0 * image_height
        right = max(x1, x2) / 1000.0 * image_width
        bottom = max(y1, y2) / 1000.0 * image_height
        return QRectF(left, top, right - left, bottom - top)
