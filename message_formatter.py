# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - Message Formatter
                                 A QGIS Plugin
 Format user messages consistently
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


class MessageFormatter:
    """Format messages for display to the user"""

    @staticmethod
    def get_provider_name(ai_provider):
        """
        Get formatted provider name.

        Args:
            ai_provider: Provider string ('gemini', 'gpt', or other)

        Returns:
            str: Uppercase provider name or "UNKNOWN"
        """
        return ai_provider.upper() if ai_provider else "UNKNOWN"

    @staticmethod
    def format_success_message(features_count, ai_provider, stats):
        """
        Format success message for layer creation.

        Args:
            features_count: Number of features created
            ai_provider: AI provider string
            stats: Statistics dictionary with 'total', 'skipped_confidence', 'skipped_missing'

        Returns:
            str: Formatted success message
        """
        provider_name = MessageFormatter.get_provider_name(ai_provider)
        msg = f"Created layer with {features_count} features from {provider_name} analysis (including query extent)"

        if stats['skipped_confidence'] > 0 or stats['skipped_missing'] > 0:
            msg += f" (filtered from {stats['total']} total)"

        return msg

    @staticmethod
    def format_warning_message(ai_provider, stats, confidence_threshold):
        """
        Format warning message when no features were created.

        Args:
            ai_provider: AI provider string
            stats: Statistics dictionary
            confidence_threshold: Current confidence threshold value

        Returns:
            str: Formatted warning message
        """
        provider_name = MessageFormatter.get_provider_name(ai_provider)
        msg = f"No features created from {provider_name} analysis"

        if stats['total'] > 0:
            reasons = []
            if stats['skipped_confidence'] > 0:
                reasons.append(f"{stats['skipped_confidence']} below {int(confidence_threshold)}% confidence")
            if stats['skipped_missing'] > 0:
                reasons.append(f"{stats['skipped_missing']} missing required fields")
            if reasons:
                msg += f" ({stats['total']} items: {', '.join(reasons)})"
        else:
            msg += " (no items in JSON response)"

        return msg
