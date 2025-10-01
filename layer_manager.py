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
from qgis.PyQt.QtCore import QVariant, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsProject, QgsWkbTypes, QgsRectangle,
    QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsFields,
    QgsPointXY, QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsSingleSymbolRenderer, QgsLayerTreeGroup, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext
)
from .logging import logger


class LayerManager:
    """Manages QGIS layer operations for the LandTalk plugin"""
    
    def __init__(self, plugin_dir, config_manager):
        """Initialize the layer manager
        
        Args:
            plugin_dir: Path to the plugin directory
            config_manager: PluginConfigManager instance
        """
        self.plugin_dir = plugin_dir
        self.config_manager = config_manager
        self.layer_counter = 0
        
        # Layer tracking for cleanup detection
        self.previous_landtalk_layers = {}
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.check_landtalk_group_status)
        self.cleanup_timer.start(5000)  # Check every 5 seconds
        
        # Initialize layer tracking
        self.initialize_layer_tracking()
    
    def get_analysis_directory(self):
        """Get the analysis directory for storing layer files"""
        # Use custom directory if set, otherwise use temp directory
        if self.config_manager.get_custom_analysis_directory():
            analysis_dir = self.config_manager.get_custom_analysis_directory()
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
    
    def initialize_layer_tracking(self):
        """Initialize tracking of LandTalk.ai layers for cleanup detection"""
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")
            
            if landtalk_group:
                self.previous_landtalk_layers = self.get_current_landtalk_layers(landtalk_group)
                logger.info(f"Initialized layer tracking with {len(self.previous_landtalk_layers)} layers")
            else:
                self.previous_landtalk_layers = {}
                logger.info("No LandTalk.ai group found, initialized empty layer tracking")
                
        except Exception as e:
            logger.error(f"Error initializing layer tracking: {str(e)}")
            self.previous_landtalk_layers = {}
    
    def is_landtalk_layer(self, layer):
        """Check if a layer belongs to the LandTalk.ai analysis"""
        try:
            if not layer:
                return False
            
            # Get the layer tree for this layer
            project = QgsProject.instance()
            layer_tree_layer = project.layerTreeRoot().findLayer(layer.id())
            
            if not layer_tree_layer:
                return False
            
            # Walk up the parent hierarchy to check if we're in the LandTalk.ai group
            current_parent = layer_tree_layer.parent()
            while current_parent:
                if hasattr(current_parent, 'name') and current_parent.name() == "LandTalk.ai":
                    return True
                
                # Check if current parent is a group and get its parent
                if hasattr(current_parent, 'parent'):
                    current_parent = current_parent.parent()
                else:
                    break
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if layer is LandTalk layer: {str(e)}")
            return False
    
    def is_landtalk_group(self, group):
        """Check if a group is the LandTalk.ai group or a subgroup within it"""
        try:
            if not group:
                return False
            
            # Check if this is the main LandTalk.ai group
            if hasattr(group, 'name') and group.name() == "LandTalk.ai":
                return True
            
            # Check if this group is within the LandTalk.ai group hierarchy
            current_parent = group.parent() if hasattr(group, 'parent') else None
            while current_parent:
                if hasattr(current_parent, 'name') and current_parent.name() == "LandTalk.ai":
                    return True
                
                # Get the parent of the current parent
                current_parent = current_parent.parent() if hasattr(current_parent, 'parent') else None
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if group is LandTalk group: {str(e)}")
            return False
    
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
    
    def get_current_landtalk_layers(self, landtalk_group):
        """Get current layers in the LandTalk.ai group with their source paths"""
        current_layers = {}
        try:
            for layer_tree_layer in landtalk_group.findLayers():
                layer = layer_tree_layer.layer()
                if layer and layer.isValid():
                    current_layers[layer.id()] = {
                        'name': layer.name(),
                        'source': layer.source()
                    }
            
            # Also check subgroups
            for child in landtalk_group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    subgroup_layers = self.get_current_landtalk_layers(child)
                    current_layers.update(subgroup_layers)
                    
        except Exception as e:
            logger.error(f"Error getting current LandTalk layers: {str(e)}")
        
        return current_layers
    
    def update_layer_tracking(self):
        """Update the layer tracking state after new layers are created"""
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")
            
            if landtalk_group:
                self.previous_landtalk_layers = self.get_current_landtalk_layers(landtalk_group)
                logger.info(f"Updated layer tracking with {len(self.previous_landtalk_layers)} layers")
            else:
                self.previous_landtalk_layers = {}
                logger.info("No LandTalk.ai group found during update")
                
        except Exception as e:
            logger.error(f"Error updating layer tracking: {str(e)}")
    
    def check_landtalk_group_status(self):
        """Periodically check if the LandTalk.ai group has been removed"""
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")
            
            if not landtalk_group and self.previous_landtalk_layers:
                logger.info("LandTalk.ai group has been removed by user")
                # The group was removed, clear our tracking
                self.previous_landtalk_layers = {}
                
        except Exception as e:
            logger.error(f"Error checking LandTalk group status: {str(e)}")
    
    def get_or_create_ai_analysis_group(self):
        """
        Get or create a layer group called 'LandTalk.ai' in the project.
        Returns the QgsLayerTreeGroup object for the 'LandTalk.ai' group.
        """
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        
        # Check if the group already exists
        ai_analysis_group = root.findGroup("LandTalk.ai")
        if ai_analysis_group:
            logger.info("Found existing LandTalk.ai group")
            return ai_analysis_group
        
        # Create the group if it doesn't exist
        ai_analysis_group = root.insertGroup(0, "LandTalk.ai")
        logger.info("Created new LandTalk.ai group")
        
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
        - If current_group_name is provided: hide all groups except the current one.
        """
        try:
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            
            # Find the LandTalk.ai group
            ai_analysis_group = root.findGroup("LandTalk.ai")
            if not ai_analysis_group:
                logger.info("No LandTalk.ai group found")
                return
            
            logger.info(f"Managing visibility for LandTalk.ai group, current_group_name: {current_group_name}")
            
            # Walk through all children of the LandTalk.ai group
            for child in ai_analysis_group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    # This is a subgroup (analysis group)
                    group_name = child.name()
                    
                    if current_group_name is None:
                        # Hide all groups when no current group is specified
                        child.setItemVisibilityChecked(False)
                        logger.info(f"Hidden group: {group_name}")
                    elif group_name == current_group_name:
                        # Show the current group
                        child.setItemVisibilityChecked(True)
                        logger.info(f"Enabled group: {group_name}")
                    else:
                        # Hide all other groups
                        child.setItemVisibilityChecked(False)
                        logger.info(f"Disabled group: {group_name}")
                        
                elif hasattr(child, 'layer'):
                    # This is a direct layer (not in a subgroup)
                    layer_name = child.layer().name() if child.layer() else "Unknown"
                    
                    if current_group_name is None:
                        # Hide all direct layers when no current group is specified
                        child.setItemVisibilityChecked(False)
                        logger.info(f"Hidden direct layer: {layer_name}")
                    # Note: We don't enable direct layers when a specific group is current,
                    # as they should be managed within their groups
        
        except Exception as e:
            logger.warning(f"Error updating LandTalk.ai visibility: {str(e)}")
    
    def create_file_based_layer(self, layer_name, crs_authid, ai_provider, features=None):
        """Create a file-based vector layer directly in the LandTalk.ai directory"""
        analysis_dir = self.get_analysis_directory()
        if not analysis_dir:
            logger.error("Cannot create file-based layer: no analysis directory available")
            return None
        
        try:
            # Create the layer file path
            safe_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).strip()
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
    
    def create_single_layer_with_features(self, features_data, ai_provider, captured_map_extent, 
                                        captured_top_left_map, captured_bottom_right_map, 
                                        captured_extent_width, captured_extent_height):
        """
        Create a group with individual memory vector layers for each feature.

        :param features_data: List of dictionaries with 'label', 'bbox', and 'reason' keys
        :param ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        :param captured_map_extent: QgsRectangle of the captured area
        :param captured_top_left_map: Top-left corner in map coordinates
        :param captured_bottom_right_map: Bottom-right corner in map coordinates
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
        self.disable_all_previous_ai_analysis_groups(group_name)

        # Create individual layers for each feature
        created_layers = []
        collected_labels = []  # remember labels for this analysis group
        
        for i, feature_info in enumerate(features_data):
            logger.info(f"Processing feature {i+1}: {feature_info}")
            
            # Extract feature information
            if isinstance(feature_info, dict):
                label = feature_info.get('label', f'Feature_{i+1}')
                bbox_coords = feature_info.get('bounding_box', feature_info.get('Bounding Box', []))
                reason = feature_info.get('reason', feature_info.get('Reason', 'No reason provided'))
                confidence = feature_info.get('confidence', feature_info.get('Confidence', 50.0))
            else:
                logger.warning(f"Feature {i+1} is not a dictionary: {feature_info}")
                continue
            
            if not bbox_coords or len(bbox_coords) < 4:
                logger.warning(f"Invalid bounding box coordinates for feature {i+1}: {bbox_coords}")
                continue
            
            # Convert bounding box to map coordinates
            try:
                map_coords = self._convert_bbox_to_map_coordinates(
                    bbox_coords, captured_map_extent, captured_extent_width, captured_extent_height
                )
                if not map_coords:
                    logger.warning(f"Failed to convert coordinates for feature {i+1}")
                    continue
                
                # Create polygon geometry
                polygon = self._create_polygon_from_coords(map_coords)
                if not polygon:
                    logger.warning(f"Failed to create polygon for feature {i+1}")
                    continue
                
                # Create layer for this feature
                layer_name = f"{label}_{i+1}"
                layer = self._create_feature_layer(layer_name, crs_authid, polygon, label, reason, confidence, ai_provider)
                
                if layer:
                    # Add layer to the analysis group
                    project.addMapLayer(layer, False)
                    analysis_group.addLayer(layer)
                    created_layers.append(layer)
                    collected_labels.append(label)
                    
                    # Configure layer styling and labeling
                    self.configure_layer_labeling(layer)
                    self.force_enable_labels(layer, layer_name)
                    
                    logger.info(f"Successfully created layer: {layer_name}")
                else:
                    logger.warning(f"Failed to create layer for feature {i+1}")
                    
            except Exception as e:
                logger.error(f"Error processing feature {i+1}: {str(e)}")
                continue
        
        # Update layer tracking
        self.update_layer_tracking()
        
        logger.info(f"Created {len(created_layers)} layers in group {group_name}")
        logger.info(f"Collected labels: {collected_labels}")
        
        return created_layers
    
    def _convert_bbox_to_map_coordinates(self, bbox_coords, captured_map_extent, extent_width, extent_height):
        """Convert relative bounding box coordinates to map coordinates"""
        try:
            if len(bbox_coords) < 4:
                return None
            
            x1, y1, x2, y2 = bbox_coords[:4]
            
            # Convert from 0-1000 range to 0-1 range
            x1_norm = x1 / 1000.0
            y1_norm = y1 / 1000.0
            x2_norm = x2 / 1000.0
            y2_norm = y2 / 1000.0
            
            # Convert to map coordinates
            left = captured_map_extent.xMinimum() + (x1_norm * extent_width)
            top = captured_map_extent.yMaximum() - (y1_norm * extent_height)
            right = captured_map_extent.xMinimum() + (x2_norm * extent_width)
            bottom = captured_map_extent.yMaximum() - (y2_norm * extent_height)
            
            return [left, top, right, bottom]
            
        except Exception as e:
            logger.error(f"Error converting bbox coordinates: {str(e)}")
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
    
    def _create_feature_layer(self, layer_name, crs_authid, geometry, label, reason, confidence, ai_provider):
        """Create a memory layer with a single feature"""
        try:
            # Create memory layer
            layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", layer_name, "memory")
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
        """
        Configure the layer to show labels by default with appropriate styling.
        """
        try:
            # Create label settings
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "label"
            label_settings.enabled = True
            
            # Text format
            text_format = QgsTextFormat()
            text_format.setFont(text_format.font())
            text_format.setSize(10)
            text_format.setColor(QColor(0, 0, 0))  # Black text
            
            # Text buffer (outline)
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
            
            logger.info(f"Configured labeling for layer: {layer.name()}")
            
        except Exception as e:
            logger.error(f"Error configuring layer labeling: {str(e)}")
    
    def force_enable_labels(self, layer, layer_name):
        """
        Force enable labels on a layer with a more aggressive approach.
        This method tries multiple techniques to ensure labels are enabled.
        """
        try:
            logger.info(f"Force enabling labels for layer: {layer_name}")
            
            # Method 1: Basic labeling setup
            if not layer.labelsEnabled():
                layer.setLabelsEnabled(True)
                logger.info(f"Enabled labels using setLabelsEnabled for {layer_name}")
            
            # Method 2: Ensure labeling configuration exists
            if not layer.labeling():
                # Create and apply simple labeling
                label_settings = QgsPalLayerSettings()
                label_settings.fieldName = "label"
                label_settings.enabled = True
                
                # Create text format with good visibility
                text_format = QgsTextFormat()
                text_format.setSize(12)
                text_format.setColor(QColor(255, 0, 0))  # Red for high visibility
                
                # Add white buffer for contrast
                buffer_settings = QgsTextBufferSettings()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(2.0)
                buffer_settings.setColor(QColor(255, 255, 255, 200))  # Semi-transparent white
                text_format.setBuffer(buffer_settings)
                
                label_settings.setFormat(text_format)
                
                # Apply the labeling
                labeling = QgsVectorLayerSimpleLabeling(label_settings)
                layer.setLabeling(labeling)
                layer.setLabelsEnabled(True)
                
                logger.info(f"Created and applied labeling configuration for {layer_name}")
            
            # Method 3: Trigger layer refresh
            layer.triggerRepaint()
            
            # Method 4: Force update
            if hasattr(layer, 'reload'):
                layer.reload()
            
            logger.info(f"Labels force-enabled for layer: {layer_name}")
            
        except Exception as e:
            logger.error(f"Error force enabling labels for {layer_name}: {str(e)}")
    
    def cleanup_timer_stop(self):
        """Stop the cleanup timer"""
        if self.cleanup_timer:
            self.cleanup_timer.stop()
    
    def get_layer_counter(self):
        """Get the current layer counter value"""
        return self.layer_counter
    
    def increment_layer_counter(self):
        """Increment and return the layer counter"""
        self.layer_counter += 1
        return self.layer_counter
