# -*- coding: utf-8 -*-
"""
Dimension calculation utilities for LandTalk.AI plugin

This module provides utilities for calculating real-world dimensions from map extents.
"""

from .logging import logger


def calculate_ground_dimensions(parent_plugin):
    """Calculate real-world dimensions in meters from captured extent and ground resolution

    Args:
        parent_plugin: Reference to the parent plugin with map data

    Returns:
        tuple: (width_meters, height_meters, ground_resolution) or (None, None, resolution) on error
    """
    if not parent_plugin:
        logger.warning("No parent plugin available for dimension calculation")
        return None, None, None

    # Get the ground resolution from parent plugin
    ground_resolution = getattr(parent_plugin, 'ground_resolution_m_per_px', 1.0)

    # Get captured extent information from capture_state object
    capture_state = getattr(parent_plugin, 'capture_state', None)
    if not capture_state:
        logger.warning("No capture_state available for dimension calculation")
        return None, None, ground_resolution

    extent_width = capture_state.width
    extent_height = capture_state.height

    logger.debug(f"Calculating dimensions - extent_width: {extent_width}, extent_height: {extent_height}, ground_resolution: {ground_resolution}")

    if extent_width is None or extent_height is None:
        logger.warning("No captured extent dimensions available for calculation")
        return None, None, ground_resolution

    # Calculate dimensions based on extent and ground resolution
    # The extent is in map units, but we need to convert to meters based on the map's CRS
    try:
        from qgis.core import QgsDistanceArea, QgsProject, QgsPointXY

        # Get the captured coordinates from capture_state
        top_left_map = capture_state.top_left
        bottom_right_map = capture_state.bottom_right

        if top_left_map and bottom_right_map:
            # Use QgsDistanceArea to calculate real distances
            distance_calc = QgsDistanceArea()
            if hasattr(parent_plugin, 'map_canvas'):
                distance_calc.setSourceCrs(
                    parent_plugin.map_canvas.mapSettings().destinationCrs(),
                    QgsProject.instance().transformContext()
                )
                try:
                    distance_calc.setEllipsoid(QgsProject.instance().ellipsoid())
                except Exception:
                    pass

            # Calculate width (horizontal distance)
            width_meters = distance_calc.measureLine(
                QgsPointXY(top_left_map.x(), top_left_map.y()),
                QgsPointXY(bottom_right_map.x(), top_left_map.y())
            )

            # Calculate height (vertical distance)
            height_meters = distance_calc.measureLine(
                QgsPointXY(top_left_map.x(), top_left_map.y()),
                QgsPointXY(top_left_map.x(), bottom_right_map.y())
            )

            logger.info(f"Calculated dimensions: {width_meters:.1f}m x {height_meters:.1f}m (resolution: {ground_resolution}m/px)")
            return width_meters, height_meters, ground_resolution
        else:
            logger.warning("No captured coordinates available for dimension calculation")
            return None, None, ground_resolution

    except Exception as e:
        logger.error(f"Error calculating ground dimensions: {str(e)}")
        return None, None, ground_resolution


def format_dimension(dimension_meters):
    """Format dimension in meters to human-readable string

    Args:
        dimension_meters: Dimension value in meters

    Returns:
        str: Formatted dimension string (e.g., "1.5 km", "450 m")
    """
    if dimension_meters is None:
        return "Unknown"

    if dimension_meters >= 1000:
        return f"{dimension_meters/1000:.1f} km"
    elif dimension_meters >= 10:
        return f"{dimension_meters:.0f} m"
    else:
        return f"{dimension_meters:.1f} m"
