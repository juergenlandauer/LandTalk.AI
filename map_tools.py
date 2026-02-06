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
from qgis.PyQt.QtCore import Qt, QRectF, QSize, pyqtSignal, QPointF, QPoint, QBuffer, QIODevice
from qgis.PyQt.QtGui import QColor, QPixmap, QPainter, QPen, QKeyEvent
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    Qgis, QgsProject, QgsMapSettings,
    QgsRectangle, QgsMapRendererParallelJob, QgsWkbTypes,
    QgsPointXY, QgsDistanceArea
)
from qgis.gui import QgsRubberBand, QgsMapTool
from .logging import logger


class RectangleMapTool(QgsMapTool):
    """Map tool for drawing a rectangle on the map canvas"""

    # Define the signals as class variables
    rectangle_created = pyqtSignal(object)
    selection_cancelled = pyqtSignal()

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
        # The signals are now defined as class variables above
    
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

    def keyPressEvent(self, event):
        """Handle key press events - cancel selection on Escape"""
        try:
            escape_key = Qt.Key.Key_Escape
        except AttributeError:
            escape_key = Qt.Key_Escape

        if event.key() == escape_key:
            logger.info("Escape key pressed - cancelling rectangle selection")
            self.rubber_band.reset()
            self.start_point = None
            self.end_point = None
            self.is_drawing = False
            self.selection_cancelled.emit()
        else:
            event.ignore()

    def get_rectangle(self):
        """Create a QRectF from the start and end points"""
        mapToPixel = self.canvas.mapSettings().mapToPixel()
        start_screen = mapToPixel.transform(self.start_point)
        end_screen = mapToPixel.transform(self.end_point)

        return QRectF(
            QPointF(start_screen.x(), start_screen.y()),
            QPointF(end_screen.x(), end_screen.y())
        ).normalized()


class MapRenderer:
    """Helper class for map rendering operations"""

    # Constants for thumbnail generation
    MAX_THUMBNAIL_WIDTH = 200
    MAX_THUMBNAIL_HEIGHT = 150
    TEMP_IMAGE_FILENAME = "gemini_map_image.png"
    TEMP_THUMBNAIL_FILENAME = "gemini_map_thumbnail.png"
    # Maximum image size that can be sent to AI (8 million pixels)
    MAX_IMAGE_PIXELS = 8_000_000

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

        mapToPixel = self.map_canvas.mapSettings().mapToPixel()
        top_left_map = mapToPixel.toMapCoordinates(
            QPoint(int(selected_rectangle.left()), int(selected_rectangle.top())))
        bottom_right_map = mapToPixel.toMapCoordinates(
            QPoint(int(selected_rectangle.right()), int(selected_rectangle.bottom())))

        map_extent = QgsRectangle(top_left_map.x(), bottom_right_map.y(),
                                   bottom_right_map.x(), top_left_map.y())
        extent_width = abs(bottom_right_map.x() - top_left_map.x())
        extent_height = abs(bottom_right_map.y() - top_left_map.y())

        logger.info(f"Rectangle map coordinates: Top-left: ({top_left_map.x():.6f}, {top_left_map.y():.6f}), "
                   f"Bottom-right: ({bottom_right_map.x():.6f}, {bottom_right_map.y():.6f}), "
                   f"Extent: {extent_width:.6f} x {extent_height:.6f} map units")

        return top_left_map, bottom_right_map, map_extent, extent_width, extent_height

    def filter_canvas_layers(self):
        """Filter out LandTalk.ai analysis layers from canvas layers.

        Returns:
            list: Filtered list of layers excluding LandTalk.ai analysis layers
        """
        canvas_layers = self.map_canvas.layers()
        ai_analysis_group = QgsProject.instance().layerTreeRoot().findGroup("LandTalk.ai")

        logger.info(f"Total canvas layers: {len(canvas_layers)}")

        # Early return if no LandTalk.ai group exists
        if not ai_analysis_group:
            valid_layers = [layer for layer in canvas_layers if layer.isValid()]
            logger.info(f"No LandTalk.ai group found, returning {len(valid_layers)} valid layers")
            return valid_layers

        # Build set of layer IDs in LandTalk.ai group
        landtalk_layer_ids = set()
        self._collect_group_layer_ids(ai_analysis_group, landtalk_layer_ids)

        # Filter layers
        filtered_layers = [layer for layer in canvas_layers
                          if layer.isValid() and layer.id() not in landtalk_layer_ids]

        excluded_count = len(canvas_layers) - len(filtered_layers)
        logger.info(f"Filtered layers: {len(filtered_layers)} (excluded {excluded_count} LandTalk.ai layers)")

        return filtered_layers

    def _collect_group_layer_ids(self, group_node, layer_id_set):
        """Recursively collect all layer IDs within a group and its subgroups."""
        for child in group_node.children():
            if hasattr(child, 'layer') and child.layer():
                layer_id_set.add(child.layer().id())
            elif hasattr(child, 'children'):
                self._collect_group_layer_ids(child, layer_id_set)

    def _calculate_thumbnail_dimensions(self, source_width, source_height):
        """Calculate thumbnail dimensions while preserving aspect ratio."""
        if source_height <= 0:
            return self.MAX_THUMBNAIL_WIDTH, self.MAX_THUMBNAIL_HEIGHT

        aspect_ratio = source_width / source_height
        max_ratio = self.MAX_THUMBNAIL_WIDTH / self.MAX_THUMBNAIL_HEIGHT

        if aspect_ratio >= max_ratio:
            return self.MAX_THUMBNAIL_WIDTH, int(self.MAX_THUMBNAIL_WIDTH / aspect_ratio)
        else:
            return int(self.MAX_THUMBNAIL_HEIGHT * aspect_ratio), self.MAX_THUMBNAIL_HEIGHT

    def _save_thumbnail_to_temp(self, thumbnail_pixmap):
        """Save thumbnail to temporary directory."""
        thumbnail_path = os.path.join(tempfile.gettempdir(), self.TEMP_THUMBNAIL_FILENAME)
        if thumbnail_pixmap.save(thumbnail_path, "PNG"):
            logger.info(f"Thumbnail saved: {thumbnail_path}")
            return thumbnail_path
        logger.warning(f"Failed to save thumbnail to: {thumbnail_path}")
        return None

    def create_and_render_map(self, map_extent, output_width, output_height, high_quality=False):
        """Create map settings and render the map.

        Args:
            map_extent: QgsRectangle defining the map extent
            output_width: Width of output image in pixels
            output_height: Height of output image in pixels
            high_quality: If True, enable high quality rendering (default: False)

        Returns:
            tuple: (QImage, QgsRectangle) - rendered image and actual visible extent,
                   or None if rendering failed. The visible extent may differ from the
                   requested extent because QGIS adjusts it to match the output aspect ratio.
        """
        map_settings = QgsMapSettings()
        map_settings.setLayers(self.filter_canvas_layers())
        map_settings.setExtent(map_extent)
        map_settings.setOutputSize(QSize(output_width, output_height))
        map_settings.setDestinationCrs(self.map_canvas.mapSettings().destinationCrs())
        map_settings.setBackgroundColor(self.map_canvas.canvasColor())

        # Apply quality settings
        map_settings.setFlag(Qgis.MapSettingsFlag.Antialiasing, high_quality)
        map_settings.setFlag(Qgis.MapSettingsFlag.UseRenderingOptimization, True)
        if high_quality:
            map_settings.setFlag(Qgis.MapSettingsFlag.HighQualityImageTransforms, True)

        # Get the actual visible extent after QGIS adjusts for aspect ratio
        actual_extent = map_settings.visibleExtent()
        logger.info(f"Requested extent: {map_extent.toString()}, Actual visible extent: {actual_extent.toString()}")

        # Render the map
        logger.info(f"Starting map rendering ({'high' if high_quality else 'normal'} quality)...")
        start_time = time.time()

        job = QgsMapRendererParallelJob(map_settings)
        job.start()
        job.waitForFinished()

        logger.info(f"Map rendering completed in {time.time() - start_time:.3f} seconds")

        rendered_image = job.renderedImage()
        if rendered_image.isNull():
            logger.warning("Failed to render map image")
            return None

        return rendered_image, actual_extent

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
            # Try to load and scale existing AI image first
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
            result = self.create_and_render_map(map_extent, thumb_w, thumb_h, high_quality=False)
            if result is None:
                return None
            thumbnail_image, _ = result

            thumbnail_pixmap = QPixmap.fromImage(thumbnail_image)
            logger.info(f"Rendered thumbnail: {thumb_w}x{thumb_h}")
            self._save_thumbnail_to_temp(thumbnail_pixmap)
            return thumbnail_pixmap

        except Exception as e:
            logger.error(f"Error in capture_map_thumbnail: {str(e)}")
            return None

    def capture_map_image(self, selected_rectangle, existing_map_extent=None):
        """Capture the selected area of the map as an image at fixed ground resolution

        Args:
            selected_rectangle: QRectF in screen coordinates (required if existing_map_extent is None)
            existing_map_extent: Optional QgsRectangle to use instead of converting from screen coords.
                               When resolution changes, pass the stored extent to avoid re-conversion
                               from screen coordinates which may give different results if the canvas
                               view has changed.

        Returns:
            tuple: (base64_encoded_image, captured_map_extent, captured_top_left_map,
                   captured_bottom_right_map, captured_extent_width, captured_extent_height)
        """
        if not selected_rectangle and not existing_map_extent:
            logger.info("No selected rectangle or existing extent")
            return None, None, None, None, None, None

        # Use existing map extent if provided (for resolution changes)
        # This preserves the exact map area from the original selection
        if existing_map_extent:
            map_extent = existing_map_extent
            extent_width = map_extent.width()
            extent_height = map_extent.height()
            top_left_map = QgsPointXY(map_extent.xMinimum(), map_extent.yMaximum())
            bottom_right_map = QgsPointXY(map_extent.xMaximum(), map_extent.yMinimum())
            logger.info(f"Using existing map extent: {map_extent.toString()}")
        else:
            # Get map coordinates and extent from screen rectangle
            top_left_map, bottom_right_map, map_extent, extent_width, extent_height = self.get_map_coordinates_and_extent(selected_rectangle)
        if map_extent is None:
            return None, None, None, None, None, None

        # Calculate output dimensions based on fixed ground resolution
        output_width, output_height = self._calculate_output_dimensions(
            top_left_map, bottom_right_map, extent_width, extent_height, selected_rectangle
        )

        # Check if image size exceeds the maximum allowed for AI processing
        total_pixels = output_width * output_height
        if total_pixels > self.MAX_IMAGE_PIXELS:
            logger.warning(f"Image size {output_width}x{output_height} ({total_pixels:,} pixels) exceeds maximum of {self.MAX_IMAGE_PIXELS:,} pixels")
            QMessageBox.warning(
                None,
                "Image Too Large",
                f"The selected area would result in an image of {output_width:,} x {output_height:,} pixels "
                f"({total_pixels:,} total pixels).\n\n"
                f"This exceeds the maximum of {self.MAX_IMAGE_PIXELS:,} pixels that can be sent to the AI.\n\n"
                f"Current ground resolution: {self.ground_resolution_m_per_px} m/pixel\n\n"
                f"Please either:\n"
                f"• Select a smaller area, or\n"
                f"• Increase the ground resolution (m/pixel) in settings"
            )
            return None, None, None, None, None, None

        logger.info(f"Capturing map image: {output_width}x{output_height} pixels at {self.ground_resolution_m_per_px}m/px")

        # Render the map
        result = self.create_and_render_map(map_extent, output_width, output_height)
        if result is None:
            return None, None, None, None, None, None
        rendered_image, actual_extent = result

        # Use the actual rendered extent (QGIS adjusts extent to match output aspect ratio)
        map_extent = actual_extent
        extent_width = actual_extent.width()
        extent_height = actual_extent.height()
        top_left_map = QgsPointXY(actual_extent.xMinimum(), actual_extent.yMaximum())
        bottom_right_map = QgsPointXY(actual_extent.xMaximum(), actual_extent.yMinimum())

        # Convert directly to base64 without intermediate file I/O
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        rendered_image.save(buffer, "PNG")
        encoded_image = base64.b64encode(buffer.data()).decode('utf-8')
        buffer.close()

        # Save to temp file for thumbnail use
        pixmap = QPixmap.fromImage(rendered_image)
        image_path = os.path.join(tempfile.gettempdir(), self.TEMP_IMAGE_FILENAME)
        pixmap.save(image_path, "PNG")

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
            # Fallback to screen resolution (only if selected_rectangle is available)
            if selected_rectangle:
                output_width = max(1, int(selected_rectangle.width()))
                output_height = max(1, int(selected_rectangle.height()))
            else:
                # Ultimate fallback: use extent dimensions as-is (map units = pixels)
                output_width = max(1, int(extent_width))
                output_height = max(1, int(extent_height))
            logger.warning("Using fallback resolution (distance calculation failed)")

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
            logger.error(f"Error in debug_render_ai_results: {str(e)}")
            return None

    def _extract_bbox_coordinates(self, result):
        """Extract bounding box coordinates from AI result in various formats.

        Returns:
            tuple: (ymin, xmin, ymax, xmax) or None if not found
        """
        if not isinstance(result, dict):
            return None

        # Try common bbox field names
        for field in ['box_2d', 'box2d', 'bounding_box', 'Bounding Box']:
            if field in result:
                bbox = result[field]
                if isinstance(bbox, list) and len(bbox) >= 4:
                    return tuple(bbox[:4])

        # Try x, y, width, height format
        if all(k in result for k in ['x', 'y', 'width', 'height']):
            return (result['x'], result['y'], result['x'] + result['width'], result['y'] + result['height'])

        # Try xmin, ymin, xmax, ymax format
        if all(k in result for k in ['xmin', 'ymin', 'xmax', 'ymax']):
            return (result['xmin'], result['ymin'], result['xmax'], result['ymax'])

        return None

    def _bbox_to_qrect(self, bbox_coords, image_width, image_height):
        """Convert bounding box coordinates (0-1000 range) to QRectF in image pixels."""
        ymin, xmin, ymax, xmax = bbox_coords
        left = min(xmin, xmax) / 1000.0 * image_width
        top = min(ymin, ymax) / 1000.0 * image_height
        right = max(xmin, xmax) / 1000.0 * image_width
        bottom = max(ymin, ymax) / 1000.0 * image_height
        return QRectF(left, top, right - left, bottom - top)
