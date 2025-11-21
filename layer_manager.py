# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI
                                 A QGIS Plugin
 Layer Management for LandTalk Plugin
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

Layer Management Module for LandTalk Plugin

This module handles all QGIS layer operations including creation, styling,
group management, and layer tracking.
"""

import os
import tempfile
from datetime import datetime
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsProject, QgsWkbTypes, QgsRectangle,
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsFields,
    QgsPointXY, QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsSingleSymbolRenderer, QgsLayerTreeGroup, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
    QgsSymbol, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol
)
from .logging import logger


class LayerManager:
    """Manages QGIS layer operations for the LandTalk plugin"""

    GROUP_NAME = "LandTalk.ai"

    def __init__(self, plugin):
        """Initialize the layer manager

        Args:
            plugin: LandTalkPlugin instance to access settings and configuration
        """
        self.plugin = plugin
        self.plugin_dir = plugin.plugin_dir
        self.layer_counter = 0

    @staticmethod
    def sanitize_layer_name(name):
        """Sanitize layer name to be compatible with OGR/GDAL
        
        Removes or replaces special characters that OGR doesn't allow:
        - Parentheses, brackets, braces
        - Percent signs
        - Other special characters
        - Multiple consecutive spaces
        
        Args:
            name: Original layer name
            
        Returns:
            str: Sanitized layer name safe for use with OGR
        """
        if not name:
            return "unnamed_layer"
        
        # Replace problematic characters with underscores or remove them
        # Keep: alphanumeric, spaces, hyphens, underscores
        sanitized = ""
        for char in name:
            if char.isalnum() or char in (' ', '-', '_'):
                sanitized += char
            elif char in ('(', ')', '[', ']', '{', '}', '%', '/', '\\', ':', ';', ',', '.'):
                sanitized += '_'
            # Skip other special characters
        
        # Replace multiple consecutive spaces or underscores with single underscore
        import re
        sanitized = re.sub(r'[\s_]+', '_', sanitized)
        
        # Remove leading/trailing underscores and spaces
        sanitized = sanitized.strip('_').strip()
        
        # Ensure name is not empty after sanitization
        if not sanitized:
            sanitized = "unnamed_layer"
        
        return sanitized
    
    def get_analysis_directory(self):
        """Get the analysis directory for storing layer files"""
        # Use custom directory if set, otherwise use temp directory
        custom_dir = self.plugin.config_manager.custom_analysis_directory
        if custom_dir and os.path.exists(custom_dir):
            analysis_dir = custom_dir
        else:
            analysis_dir = os.path.join(tempfile.gettempdir(), "landtalk_analysis")
        
        # Create directory if it doesn't exist
        if not os.path.exists(analysis_dir):
            try:
                os.makedirs(analysis_dir)
                logger.info(f"Created analysis directory: {analysis_dir}")
            except Exception as e:
                logger.error(f"Failed to create analysis directory: {str(e)}")
                return None
        
        return analysis_dir

    def _is_in_landtalk_hierarchy(self, node):
        """Check if a node (layer or group) is within the LandTalk.ai hierarchy

        Args:
            node: QgsLayerTreeLayer or QgsLayerTreeGroup to check

        Returns:
            bool: True if node is within LandTalk.ai hierarchy
        """
        try:
            if not node:
                return False

            # Check if this is the main LandTalk.ai group
            if hasattr(node, 'name') and node.name() == self.GROUP_NAME:
                return True

            # Walk up the parent hierarchy
            current_parent = node.parent() if hasattr(node, 'parent') else None
            while current_parent:
                if hasattr(current_parent, 'name') and current_parent.name() == self.GROUP_NAME:
                    return True
                current_parent = current_parent.parent() if hasattr(current_parent, 'parent') else None

            return False

        except Exception as e:
            logger.error(f"Error checking LandTalk hierarchy: {str(e)}")
            return False

    def is_landtalk_layer(self, layer):
        """Check if a layer belongs to the LandTalk.ai analysis"""
        try:
            if not layer:
                return False

            project = QgsProject.instance()
            layer_tree_layer = project.layerTreeRoot().findLayer(layer.id())

            if not layer_tree_layer:
                return False

            return self._is_in_landtalk_hierarchy(layer_tree_layer)

        except Exception as e:
            logger.error(f"Error checking if layer is LandTalk layer: {str(e)}")
            return False

    def is_landtalk_group(self, group):
        """Check if a group is the LandTalk.ai group or a subgroup within it"""
        return self._is_in_landtalk_hierarchy(group)
    
    def collect_gpkg_files_from_group(self, group):
        """Collect all GPKG file paths from layers within a group"""
        gpkg_files = []
        try:
            # Check layers in this group
            for layer_tree_layer in group.findLayers():
                layer = layer_tree_layer.layer()
                if layer and layer.isValid():
                    source = layer.source()
                    if source.endswith('.gpkg'):
                        # Extract the file path (remove layer name if present)
                        file_path = source.split('|')[0] if '|' in source else source
                        if file_path not in gpkg_files:
                            gpkg_files.append(file_path)
            
            # Recursively check subgroups
            for child in group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    gpkg_files.extend(self.collect_gpkg_files_from_group(child))
                    
        except Exception as e:
            logger.error(f"Error collecting GPKG files from group: {str(e)}")
        
        return gpkg_files

    def get_or_create_ai_analysis_group(self):
        """
        Get or create a layer group called 'LandTalk.ai' in the project.
        Returns the QgsLayerTreeGroup object for the 'LandTalk.ai' group.
        """
        project = QgsProject.instance()
        root = project.layerTreeRoot()

        # Check if the group already exists
        ai_analysis_group = root.findGroup(self.GROUP_NAME)
        if ai_analysis_group:
            logger.info(f"Found existing {self.GROUP_NAME} group")
            return ai_analysis_group

        # Create the group if it doesn't exist
        ai_analysis_group = root.insertGroup(0, self.GROUP_NAME)
        logger.info(f"Created new {self.GROUP_NAME} group")

        return ai_analysis_group
    
    def update_ai_analysis_visibility(self, current_group_name=None):
        """
        Unified visibility manager for LandTalk.ai content.
        - If current_group_name is None: hide all layers in the LandTalk.ai group.
        - If current_group_name is provided: hide all groups except the current one.
        """
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()

            ai_analysis_group = root.findGroup(self.GROUP_NAME)
            if not ai_analysis_group:
                logger.info(f"No {self.GROUP_NAME} group found")
                return

            logger.info(f"Managing visibility for {self.GROUP_NAME} group, current_group_name: {current_group_name}")

            # Walk through all children of the LandTalk.ai group
            for child in ai_analysis_group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    group_name = child.name()
                    should_show = current_group_name is not None and group_name == current_group_name
                    child.setItemVisibilityChecked(should_show)
                    logger.info(f"{'Enabled' if should_show else 'Hidden'} group: {group_name}")
                elif hasattr(child, 'layer') and current_group_name is None:
                    # Hide direct layers only when no specific group is current
                    layer_name = child.layer().name() if child.layer() else "Unknown"
                    child.setItemVisibilityChecked(False)
                    logger.info(f"Hidden direct layer: {layer_name}")

        except Exception as e:
            logger.warning(f"Error updating {self.GROUP_NAME} visibility: {str(e)}")
    
    def create_file_based_layer(self, layer_name, crs_authid, ai_provider, features=None):
        """Create a file-based vector layer directly in the LandTalk.ai directory"""
        analysis_dir = self.get_analysis_directory()
        if not analysis_dir:
            logger.error("Cannot create file-based layer: no analysis directory available")
            return None

        try:
            # Create unique file path
            safe_name = self.sanitize_layer_name(layer_name)
            file_name = f"{safe_name}.gpkg"
            file_path = os.path.join(analysis_dir, file_name)

            # Ensure unique filename
            counter = 1
            while os.path.exists(file_path):
                file_name = f"{safe_name}_{counter}.gpkg"
                file_path = os.path.join(analysis_dir, file_name)
                counter += 1
            
            # Create fields for the layer
            fields = QgsFields()
            fields.append(QgsField("id", QVariant.Int))
            fields.append(QgsField("label", QVariant.String))
            fields.append(QgsField("reason", QVariant.String))
            fields.append(QgsField("confidence", QVariant.Double))
            fields.append(QgsField("ai_provider", QVariant.String))
            
            # Get CRS
            crs = QgsCoordinateReferenceSystem(crs_authid)
            
            # Write to GeoPackage
            writer = QgsVectorFileWriter(
                file_path,
                "UTF-8",
                fields,
                QgsWkbTypes.Polygon,
                crs,
                "GPKG"
            )
            
            if writer.hasError() != QgsVectorFileWriter.NoError:
                logger.error(f"Error creating GeoPackage: {writer.errorMessage()}")
                return None
            
            # Add features if provided
            if features:
                for feature in features:
                    writer.addFeature(feature)
            
            del writer  # Ensure file is closed
            
            # Load the layer into QGIS
            layer = QgsVectorLayer(file_path, layer_name, "ogr")
            if not layer.isValid():
                logger.error(f"Failed to create valid layer from {file_path}")
                return None
            
            logger.info(f"Created file-based layer: {layer_name} at {file_path}")
            return layer
            
        except Exception as e:
            logger.error(f"Error creating file-based layer: {str(e)}")
            return None

    @staticmethod
    def _get_field_case_insensitive(obj, *field_names):
        """Get value from dict using case-insensitive field lookup

        Args:
            obj: Dictionary to search
            *field_names: Field names to try (in order of priority)

        Returns:
            Value if found, None otherwise
        """
        if not isinstance(obj, dict):
            return None
        obj_keys_lower = {k.lower(): k for k in obj.keys()}
        for field_name in field_names:
            field_lower = field_name.lower()
            if field_lower in obj_keys_lower:
                return obj[obj_keys_lower[field_lower]]
        return None

    def create_single_layer_with_features(self, features_data, ai_provider, captured_map_extent,
                                        captured_extent_width, captured_extent_height):
        """
        Create a group with individual memory vector layers for each feature.
        Supports both point and polygon (bounding box) geometries.

        :param features_data: List of dictionaries with 'label', 'bbox'/'point', and 'reason' keys
        :param ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        :param captured_map_extent: QgsRectangle of the captured area
        :param captured_extent_width: Width of extent in map units
        :param captured_extent_height: Height of extent in map units
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
        project = QgsProject.instance()
        map_crs = project.crs()
        crs_authid = map_crs.authid()

        # Get or create the 'LandTalk.ai' group
        ai_analysis_group = self.get_or_create_ai_analysis_group()
        logger.info(f"Got LandTalk.ai group: {ai_analysis_group.name() if ai_analysis_group else 'None'}")

        # Create a new group for this analysis under the LandTalk.ai group
        analysis_group = ai_analysis_group.addGroup(group_name)

        logger.info(f"Created LandTalk.ai group: {group_name}")

        # Disable all previous LandTalk.AI analysis groups, keeping only the current one enabled
        self.update_ai_analysis_visibility(current_group_name=group_name)

        # Create individual layers for each feature
        created_layers = []
        collected_labels = []  # remember labels for this analysis group

        for i, feature_info in enumerate(features_data):
            logger.info(f"Processing feature {i+1}: {feature_info}")

            # Extract feature information
            if isinstance(feature_info, dict):
                # Extract label/object type (prioritize 'label' as it's the new format)
                label = (self._get_field_case_insensitive(feature_info, 'label', 'object_type', 'object type') or
                        f'Feature_{i+1}')

                # Extract reason
                reason = (self._get_field_case_insensitive(feature_info, 'reason', 'explanation') or
                         'No reason provided')

                # Extract confidence (prioritize 'probability' as it's the new format)
                confidence_raw = (self._get_field_case_insensitive(feature_info, 'probability', 'confidence',
                                                                   'confidence_score', 'confidence score', 'prob') or 50.0)
                try:
                    confidence = float(confidence_raw)
                except (ValueError, TypeError):
                    confidence = 50.0

                # Check for point coordinates (various field names)
                point_coords = (self._get_field_case_insensitive(feature_info, 'point', 'points', 'coordinates') or [])

                # Check for bounding box (prioritize box_2d as it's the new format)
                bbox_coords = (self._get_field_case_insensitive(feature_info, 'box_2d', 'box2d', 'bounding_box',
                                                                'bounding box', 'bbox') or [])
            else:
                logger.warning(f"Feature {i+1} is not a dictionary: {feature_info}")
                continue

            # Determine geometry type and create geometry
            # Create separate layers for both point and bbox if both are present
            try:
                layers_to_create = []

                # Create point layer if point coordinates exist
                if point_coords and len(point_coords) >= 2:
                    logger.info(f"Creating point geometry for feature {i+1}")
                    map_point = self._convert_point_to_map_coordinates(
                        point_coords, captured_map_extent, captured_extent_width, captured_extent_height
                    )
                    if map_point:
                        point_geometry = self._create_point_from_coords(map_point)
                        if point_geometry:
                            layers_to_create.append(("Point", point_geometry))

                # Create bbox layer if bounding box coordinates exist
                if bbox_coords and len(bbox_coords) >= 4:
                    logger.info(f"Creating polygon geometry for feature {i+1}")
                    map_coords = self._convert_bbox_to_map_coordinates(
                        bbox_coords, captured_map_extent, captured_extent_width, captured_extent_height
                    )
                    if map_coords:
                        bbox_geometry = self._create_polygon_from_coords(map_coords)
                        if bbox_geometry:
                            layers_to_create.append(("Polygon", bbox_geometry))

                # Skip if no valid geometry could be created
                if not layers_to_create:
                    logger.warning(f"No valid geometry for feature {i+1} (point: {point_coords}, bbox: {bbox_coords})")
                    continue

                # Create layers for all geometries
                for geom_idx, (geometry_type, geometry) in enumerate(layers_to_create):
                    # Create layer name - add suffix if multiple geometries
                    if len(layers_to_create) > 1:
                        suffix = "_point" if geometry_type == "Point" else "_bbox"
                        layer_name = f"{label}{suffix}"
                    else:
                        layer_name = label

                    layer = self._create_feature_layer(
                        layer_name, crs_authid, geometry, geometry_type,
                        label, reason, confidence, ai_provider
                    )

                    if layer:
                        # Add layer to the analysis group
                        project.addMapLayer(layer, False)
                        analysis_group.addLayer(layer)
                        created_layers.append(layer)

                        # Only add label once even if multiple layers
                        if geom_idx == 0:
                            collected_labels.append(label)

                        # Configure layer styling and labeling
                        self.configure_layer_style(layer)
                        self.configure_layer_labeling(layer)

                        logger.info(f"Successfully created {geometry_type} layer: {layer_name}")
                    else:
                        logger.warning(f"Failed to create layer for feature {i+1}")

            except Exception as e:
                logger.error(f"Error processing feature {i+1}: {str(e)}")
                continue

        logger.info(f"Created {len(created_layers)} layers in group {group_name}")
        logger.info(f"Collected labels: {collected_labels}")

        # Handle layer persistence based on mode
        if hasattr(self.plugin, 'config_manager'):
            persistence_mode = self.plugin.config_manager.get_layer_persistence_mode()
            logger.info(f"Layer persistence mode: {persistence_mode}")

            if persistence_mode == 'auto_save':
                # Save the group to GeoPackage and convert layers to file-based
                logger.info("Auto-saving layers to GeoPackage")
                gpkg_path = self.save_group_to_geopackage(analysis_group)

                if gpkg_path:
                    # Convert memory layers to file-based layers
                    success = self.convert_memory_layers_to_file_based(analysis_group, gpkg_path)
                    if success:
                        logger.info(f"Successfully auto-saved and converted layers to: {gpkg_path}")
                        # Show message to user
                        if hasattr(self.plugin, 'iface'):
                            self.plugin.iface.messageBar().pushMessage(
                                "LandTalk Plugin",
                                f"Analysis saved to: {os.path.basename(gpkg_path)}",
                                level=Qgis.MessageLevel.Info,
                                duration=5
                            )
                    else:
                        logger.warning("Failed to convert memory layers to file-based")
                else:
                    logger.warning("Failed to auto-save layers to GeoPackage")

            elif persistence_mode == 'temporary':
                # In temporary mode, layers remain as memory layers
                # They will be prompted for saving when project is saved/closed
                logger.info("Temporary layer mode: layers created as memory-only")
                if hasattr(self.plugin, 'iface'):
                    self.plugin.iface.messageBar().pushMessage(
                        "LandTalk Plugin",
                        "Analysis layers created as temporary (will prompt to save on project save)",
                        level=Qgis.MessageLevel.Info,
                        duration=3
                    )

        return created_layers
    
    def _convert_point_to_map_coordinates(self, point_coords, captured_map_extent, extent_width, extent_height):
        """Convert relative point coordinates to map coordinates"""
        try:
            if len(point_coords) < 2:
                return None

            x, y = point_coords[:2]

            # Convert from 0-1000 range to 0-1 range
            x_norm = x / 1000.0
            y_norm = y / 1000.0

            # Convert to map coordinates
            map_x = captured_map_extent.xMinimum() + (x_norm * extent_width)
            map_y = captured_map_extent.yMaximum() - (y_norm * extent_height)

            return [map_x, map_y]

        except Exception as e:
            logger.error(f"Error converting point coordinates: {str(e)}")
            return None

    def _convert_bbox_to_map_coordinates(self, bbox_coords, captured_map_extent, extent_width, extent_height):
        """Convert relative bounding box coordinates to map coordinates

        The AI returns bounding boxes in format: [ymin, xmin, ymax, xmax] where:
        - Coordinates are in 0-1000 range
        - In IMAGE coordinates (Y increases top→bottom):
          * ymin = TOP edge of box (smaller Y value in image, e.g., 100)
          * ymax = BOTTOM edge of box (larger Y value in image, e.g., 900)
          * xmin = LEFT edge of box
          * xmax = RIGHT edge of box

        Returns: [left, top, right, bottom] in map coordinates
        """
        try:
            if len(bbox_coords) < 4:
                return None

            # Extract coordinates from AI format [ymin, xmin, ymax, xmax]
            # Note: In image coords, ymin is the TOP, ymax is the BOTTOM
            ymin_img, xmin_img, ymax_img, xmax_img = bbox_coords[:4]

            # Convert from 0-1000 range to 0-1 normalized range
            xmin_norm = xmin_img / 1000.0
            ymin_norm = ymin_img / 1000.0
            xmax_norm = xmax_img / 1000.0
            ymax_norm = ymax_img / 1000.0

            # Convert to map coordinates
            # Map coordinate system: Y increases from south to north (yMin at bottom, yMax at top)
            # Image coordinate system: Y increases from top to bottom (0 at top, 1000 at bottom)
            #
            # Conversion:
            # - Image Y=0 (top) → Map yMaximum (north/top)
            # - Image Y=1000 (bottom) → Map yMinimum (south/bottom)
            #
            # X coordinates: both systems increase left to right (no flip needed)
            left = captured_map_extent.xMinimum() + (xmin_norm * extent_width)
            right = captured_map_extent.xMinimum() + (xmax_norm * extent_width)

            # Y coordinates: need to flip because image Y increases downward, map Y increases upward
            # ymin_img (small value, top of image) → large map Y (near yMaximum)
            # ymax_img (large value, bottom of image) → small map Y (near yMinimum)
            top_map = captured_map_extent.yMaximum() - (ymin_norm * extent_height)
            bottom_map = captured_map_extent.yMaximum() - (ymax_norm * extent_height)

            logger.info(f"Converted bbox: image[ymin={ymin_img},xmin={xmin_img},ymax={ymax_img},xmax={xmax_img}] → map[L={left:.2f},T={top_map:.2f},R={right:.2f},B={bottom_map:.2f}]")
            return [left, top_map, right, bottom_map]

        except Exception as e:
            logger.error(f"Error converting bbox coordinates: {str(e)}")
            return None
    
    def _create_point_from_coords(self, coords):
        """Create a QgsGeometry point from coordinates"""
        try:
            x, y = coords
            point = QgsPointXY(x, y)
            return QgsGeometry.fromPointXY(point)

        except Exception as e:
            logger.error(f"Error creating point: {str(e)}")
            return None

    def _create_polygon_from_coords(self, coords):
        """Create a QgsGeometry polygon from coordinates"""
        try:
            left, top, right, bottom = coords

            # Create polygon points (clockwise)
            points = [
                QgsPointXY(left, top),      # Top-left
                QgsPointXY(right, top),     # Top-right
                QgsPointXY(right, bottom),  # Bottom-right
                QgsPointXY(left, bottom),   # Bottom-left
                QgsPointXY(left, top)       # Close polygon
            ]

            return QgsGeometry.fromPolygonXY([points])

        except Exception as e:
            logger.error(f"Error creating polygon: {str(e)}")
            return None
    
    def _create_feature_layer(self, layer_name, crs_authid, geometry, geometry_type, label, reason, confidence, ai_provider):
        """Create a memory layer with a single feature

        :param layer_name: Name of the layer
        :param crs_authid: CRS authority ID (e.g., 'EPSG:4326')
        :param geometry: QgsGeometry object
        :param geometry_type: Type of geometry ('Point' or 'Polygon')
        :param label: Feature label
        :param reason: Feature reason/description
        :param confidence: Confidence score
        :param ai_provider: AI provider name
        """
        try:
            # Create memory layer with appropriate geometry type
            layer = QgsVectorLayer(f"{geometry_type}?crs={crs_authid}", layer_name, "memory")
            if not layer.isValid():
                logger.error(f"Failed to create memory layer: {layer_name}")
                return None

            # Add fields
            provider = layer.dataProvider()
            provider.addAttributes([
                QgsField("label", QVariant.String),
                QgsField("reason", QVariant.String),
                QgsField("confidence", QVariant.Double),
                QgsField("ai_provider", QVariant.String)
            ])
            layer.updateFields()

            # Create and add feature
            feature = QgsFeature()
            feature.setGeometry(geometry)
            feature.setAttributes([label, reason, float(confidence), ai_provider])

            provider.addFeature(feature)
            layer.updateExtents()

            return layer

        except Exception as e:
            logger.error(f"Error creating feature layer: {str(e)}")
            return None
    
    def configure_layer_labeling(self, layer):
        """Configure the layer to show labels with appropriate styling"""
        try:
            # Create label settings
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "label"
            label_settings.enabled = True

            # Text format with high visibility
            text_format = QgsTextFormat()
            text_format.setSize(10)
            text_format.setColor(QColor(0, 0, 0))  # Black text

            # Text buffer for contrast
            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(1.5)
            buffer_settings.setColor(QColor(255, 255, 255))  # White buffer
            text_format.setBuffer(buffer_settings)

            label_settings.setFormat(text_format)

            # Apply labeling
            labeling = QgsVectorLayerSimpleLabeling(label_settings)
            layer.setLabeling(labeling)
            layer.setLabelsEnabled(True)

            # Force refresh
            layer.triggerRepaint()

            logger.info(f"Configured labeling for layer: {layer.name()}")

        except Exception as e:
            logger.error(f"Error configuring layer labeling: {str(e)}")

    def configure_layer_style(self, layer):
        """Configure the layer style with yellow edges and no fill"""
        try:
            geometry_type = layer.geometryType()

            style_configs = {
                QgsWkbTypes.PointGeometry: (QgsMarkerSymbol, {
                    'name': 'circle',
                    'color': '255,255,0,0',
                    'outline_color': '255,255,0,255',
                    'outline_width': '0.5',
                    'size': '3'
                }),
                QgsWkbTypes.PolygonGeometry: (QgsFillSymbol, {
                    'color': '255,255,0,0',
                    'outline_color': '255,255,0,255',
                    'outline_width': '0.5',
                    'outline_style': 'solid'
                }),
                QgsWkbTypes.LineGeometry: (QgsLineSymbol, {
                    'color': '255,255,0,255',
                    'width': '0.5'
                })
            }

            if geometry_type not in style_configs:
                logger.warning(f"Unknown geometry type for layer: {layer.name()}")
                return

            symbol_class, config = style_configs[geometry_type]
            symbol = symbol_class.createSimple(config)

            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()

            logger.info(f"Configured style for layer: {layer.name()} (geometry type: {geometry_type})")

        except Exception as e:
            logger.error(f"Error configuring layer style: {str(e)}")

    def get_project_directory(self):
        """Get the directory where the QGIS project is saved

        Returns:
            str: Project directory path, or None if project is not saved
        """
        project = QgsProject.instance()
        project_path = project.fileName()

        if not project_path:
            logger.warning("Project is not saved, cannot determine project directory")
            return None

        project_dir = os.path.dirname(project_path)
        return project_dir

    def save_group_to_geopackage(self, group, output_path=None):
        """Save all layers in a group to a GeoPackage file

        Args:
            group: QgsLayerTreeGroup to save
            output_path: Optional path for the GeoPackage. If None, auto-generates timestamped name

        Returns:
            str: Path to the created GeoPackage, or None on error
        """
        try:
            # Get project directory
            project_dir = self.get_project_directory()
            if not project_dir:
                logger.error("Cannot save layers: project is not saved")
                return None

            # Create LandTalk_Analysis directory if it doesn't exist
            analysis_dir = os.path.join(project_dir, "LandTalk_Analysis")
            if not os.path.exists(analysis_dir):
                os.makedirs(analysis_dir)
                logger.info(f"Created analysis directory: {analysis_dir}")

            # Generate output path if not provided
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                group_name = group.name() if hasattr(group, 'name') else 'analysis'
                safe_name = self.sanitize_layer_name(group_name)
                filename = f"landtalk_{safe_name}_{timestamp}.gpkg"
                output_path = os.path.join(analysis_dir, filename)

            # Collect all layers from the group
            layers_to_save = []
            for layer_tree_layer in group.findLayers():
                layer = layer_tree_layer.layer()
                if layer and layer.isValid():
                    layers_to_save.append(layer)

            if not layers_to_save:
                logger.warning("No valid layers to save in group")
                return None

            logger.info(f"Saving {len(layers_to_save)} layers to {output_path}")

            # Save each layer to the GeoPackage
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.fileEncoding = "UTF-8"

            for idx, layer in enumerate(layers_to_save):
                # First layer creates the file, subsequent layers append
                if idx == 0:
                    save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
                else:
                    save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

                # Sanitize layer name for OGR compatibility
                original_name = layer.name()
                sanitized_name = self.sanitize_layer_name(original_name)
                save_options.layerName = sanitized_name
                
                logger.info(f"Saving layer '{original_name}' as '{sanitized_name}'")

                # Write the layer
                error = QgsVectorFileWriter.writeAsVectorFormatV2(
                    layer,
                    output_path,
                    QgsCoordinateTransformContext(),
                    save_options
                )

                if error[0] != QgsVectorFileWriter.NoError:
                    logger.error(f"Error saving layer {original_name}: {error}")
                else:
                    logger.info(f"Successfully saved layer: {original_name} -> {sanitized_name}")

            logger.info(f"Successfully saved group to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error saving group to GeoPackage: {str(e)}")
            return None

    def convert_memory_layers_to_file_based(self, group, geopackage_path):
        """Convert memory layers in a group to file-based layers from a GeoPackage

        Args:
            group: QgsLayerTreeGroup containing the layers
            geopackage_path: Path to the GeoPackage file

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            project = QgsProject.instance()
            layers_to_replace = []

            # Collect all memory layers
            for layer_tree_layer in group.findLayers():
                layer = layer_tree_layer.layer()
                if layer and layer.isValid() and layer.providerType() == "memory":
                    layers_to_replace.append((layer_tree_layer, layer))

            if not layers_to_replace:
                logger.info("No memory layers to convert")
                return True

            # Replace each memory layer with file-based layer
            for layer_tree_layer, old_layer in layers_to_replace:
                original_layer_name = old_layer.name()
                # Use sanitized name to match what was saved in the GeoPackage
                sanitized_layer_name = self.sanitize_layer_name(original_layer_name)

                # Create new file-based layer from GeoPackage using sanitized name
                gpkg_layer_uri = f"{geopackage_path}|layername={sanitized_layer_name}"
                # Display with original name for consistency
                new_layer = QgsVectorLayer(gpkg_layer_uri, original_layer_name, "ogr")

                if not new_layer.isValid():
                    logger.error(f"Failed to load file-based layer for: {original_layer_name} (sanitized: {sanitized_layer_name})")
                    continue

                # Copy styling from old layer to new layer
                new_layer.setRenderer(old_layer.renderer().clone())
                if old_layer.labelsEnabled():
                    new_layer.setLabeling(old_layer.labeling().clone())
                    new_layer.setLabelsEnabled(True)

                # Add new layer to project (but not to layer tree yet)
                project.addMapLayer(new_layer, False)

                # Replace the old layer with the new one in the layer tree
                parent = layer_tree_layer.parent()
                if parent:
                    # Insert new layer at the same position
                    index = parent.children().index(layer_tree_layer)
                    parent.insertLayer(index, new_layer)

                    # Remove old layer
                    parent.removeChildNode(layer_tree_layer)
                    project.removeMapLayer(old_layer.id())

                    logger.info(f"Converted memory layer to file-based: {original_layer_name}")

            return True

        except Exception as e:
            logger.error(f"Error converting memory layers: {str(e)}")
            return False

    def export_landtalk_group_to_geopackage(self, output_path=None):
        """Export all layers from the LandTalk.ai group to a GeoPackage

        Args:
            output_path: Optional path for the GeoPackage. If None, prompts user or auto-generates

        Returns:
            str: Path to the created GeoPackage, or None on error
        """
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup(self.GROUP_NAME)

            if not landtalk_group:
                logger.warning(f"No {self.GROUP_NAME} group found")
                return None

            return self.save_group_to_geopackage(landtalk_group, output_path)

        except Exception as e:
            logger.error(f"Error exporting {self.GROUP_NAME} group: {str(e)}")
            return None
