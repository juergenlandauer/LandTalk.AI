# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - Map Capture State
                                 A QGIS Plugin
 Manage map capture state data
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


class MapCaptureState:
    """Manage state data for captured map images and extents"""

    def __init__(self):
        """Initialize empty capture state"""
        self.extent = None  # QgsRectangle of the captured area in map coordinates
        self.top_left = None  # Top-left corner in map coordinates (tuple)
        self.bottom_right = None  # Bottom-right corner in map coordinates (tuple)
        self.width = None  # Width of extent in map units
        self.height = None  # Height of extent in map units
        self.image_data = None  # Base64 encoded image data for chat display

    def clear(self):
        """Reset all state to None"""
        self.extent = None
        self.top_left = None
        self.bottom_right = None
        self.width = None
        self.height = None
        self.image_data = None

    def set_capture_data(self, extent, top_left, bottom_right, width, height, image_data):
        """
        Set all capture data at once.

        Args:
            extent: QgsRectangle of the captured area
            top_left: Top-left corner coordinates (tuple)
            bottom_right: Bottom-right corner coordinates (tuple)
            width: Width in map units
            height: Height in map units
            image_data: Base64 encoded image string
        """
        self.extent = extent
        self.top_left = top_left
        self.bottom_right = bottom_right
        self.width = width
        self.height = height
        self.image_data = image_data

    def has_capture(self):
        """
        Check if capture state contains valid data.

        Returns:
            bool: True if capture data is available
        """
        return self.image_data is not None

    def get_all(self):
        """
        Get all capture data as a tuple.

        Returns:
            tuple: (extent, top_left, bottom_right, width, height, image_data)
        """
        return (self.extent, self.top_left, self.bottom_right,
                self.width, self.height, self.image_data)
