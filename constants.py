# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - Constants
                                 A QGIS Plugin
 Configuration constants for the LandTalk Plugin
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


class PluginConstants:
    """Configuration constants for the LandTalk Plugin"""

    # API URLs
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
    GPT_API_URL = "https://api.openai.com/v1/chat/completions"

    # Timeouts
    API_TIMEOUT = 120  # seconds

    # Ground resolution
    DEFAULT_GROUND_RESOLUTION_M_PER_PX = 1.0  # meters per pixel

    # Detection coordinate range
    DETECTION_COORD_RANGE = [0, 0, 1000, 1000]  # Full extent in normalized coordinates

    # Dock widget names to tabify with
    DOCK_WIDGET_NAMES = ["Information", "Browser", "ProcessingToolbox", "LogMessagePanel"]

    # Default prompt
    DEFAULT_ANALYSIS_PROMPT = "analyze this image"

    # Message durations
    SUCCESS_MESSAGE_DURATION = 7  # seconds
    WARNING_MESSAGE_DURATION = 8  # seconds

    # UI feature flags
    ENABLE_ADD_EXAMPLES_BUTTON = True  # Show/hide the "Add examples" button
    ENABLE_WIKIDATA_BUTTON = False  # Show/hide the "Wikidata" button
