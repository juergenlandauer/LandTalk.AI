# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - JSON Processor
                                 A QGIS Plugin
 Process AI response JSON and extract detection features
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

from .logging import logger


class AIResponseProcessor:
    """Process AI JSON responses and extract detection features"""

    def __init__(self, confidence_threshold):
        """
        Initialize the processor.

        Args:
            confidence_threshold: Minimum confidence percentage (0-100) to include detections
        """
        self.confidence_threshold = confidence_threshold

    def process_json_response(self, my_json):
        """
        Process JSON data and extract valid features.

        Args:
            my_json: JSON data from AI response (dict or list)

        Returns:
            tuple: (features_data, stats) where:
                - features_data: List of feature dictionaries ready for layer creation
                - stats: Dictionary with processing statistics
        """
        if not my_json:
            logger.info("No JSON data provided")
            return [], self._empty_stats()

        # Extract items from various JSON structures
        items_to_process = self._extract_items_from_json(my_json)

        # Process all items
        features_data = []
        stats = {
            'total': len(items_to_process),
            'processed': 0,
            'skipped_confidence': 0,
            'skipped_missing': 0
        }

        logger.info(f"Processing {stats['total']} items from JSON response")

        for i, item in enumerate(items_to_process):
            # Extract fields from the item
            fields = self._extract_detection_fields(item, i)
            if fields is None:
                stats['skipped_missing'] += 1
                continue

            # Check if we have required data
            if not fields['object_type'] or (not fields['bbox_coords'] and not fields['point_coords']):
                logger.warning(f"Skipping item {i+1}: missing object_type ({fields['object_type']}) or coordinates")
                stats['skipped_missing'] += 1
                continue

            # Apply confidence filtering
            if fields['probability'] is not None and fields['probability'] < self.confidence_threshold:
                logger.info(f"Skipping item {i+1}: {fields['object_type']} with confidence {fields['probability']:.1f}% below threshold {self.confidence_threshold}%")
                stats['skipped_confidence'] += 1
                continue

            # Create feature dictionary
            result_number = i + 1
            feature_dict = self._create_feature_dict(fields, result_number)
            features_data.append(feature_dict)
            stats['processed'] += 1
            logger.info(f"Processed item {i+1}: {feature_dict['label']}")

        # Log processing summary
        self._log_processing_summary(stats)

        return features_data, stats

    def _empty_stats(self):
        """Return empty statistics dictionary"""
        return {
            'total': 0,
            'processed': 0,
            'skipped_confidence': 0,
            'skipped_missing': 0
        }

    def _get_field_case_insensitive(self, obj, *field_names):
        """
        Get value from object using case-insensitive field lookup.

        Args:
            obj: Dictionary to search
            field_names: Possible field names to look for

        Returns:
            tuple: (value, actual_key) or (None, None) if not found
        """
        if not isinstance(obj, dict):
            return None, None

        obj_keys_lower = {k.lower(): k for k in obj.keys()}
        for field_name in field_names:
            field_lower = field_name.lower()
            if field_lower in obj_keys_lower:
                actual_key = obj_keys_lower[field_lower]
                return obj[actual_key], actual_key
        return None, None

    def _extract_items_from_json(self, my_json):
        """
        Extract items list from various JSON structures.

        Args:
            my_json: JSON data (list or dict)

        Returns:
            list: List of items to process
        """
        if isinstance(my_json, list):
            return my_json
        elif isinstance(my_json, dict):
            # Try common container keys
            for key in ['objects', 'detections', 'features']:
                if key in my_json:
                    return my_json[key]
            # Single object, treat as single item
            return [my_json]
        return []

    def _parse_probability(self, prob_value):
        """
        Parse probability value from various formats.

        Args:
            prob_value: Probability value (int, float, str, or None)

        Returns:
            float: Probability as percentage (0-100) or None if invalid
        """
        if prob_value is None:
            return None

        try:
            if isinstance(prob_value, (int, float)):
                probability = float(prob_value)
            elif isinstance(prob_value, str):
                # Handle percentage strings like "85%" or "0.85"
                prob_str = prob_value.replace('%', '').strip()
                probability = float(prob_str)
                # If value is between 0 and 1, convert to percentage
                if probability <= 1.0:
                    probability *= 100
            else:
                return None
            return probability
        except (ValueError, TypeError):
            return None

    def _extract_detection_fields(self, item, i):
        """
        Extract fields from a detection item.

        Args:
            item: Detection item from JSON
            i: Item index (for logging)

        Returns:
            dict: Dictionary with extracted fields or None if invalid
        """
        if not isinstance(item, dict):
            logger.warning(f"Skipping item {i+1}: not a dictionary (type: {type(item)}, value: {item})")
            return None

        # Extract object type/label
        object_type, object_type_field = self._get_field_case_insensitive(
            item, 'label', 'object_type', 'object type'
        )
        if object_type:
            object_type = str(object_type)
            logger.debug(f"Item {i+1}: Found object_type '{object_type}' in field '{object_type_field}'")
        else:
            logger.debug(f"Item {i+1}: No object_type found. Available keys: {list(item.keys())}")

        # Extract probability
        prob_value, prob_field = self._get_field_case_insensitive(
            item, 'probability', 'confidence', 'confidence_score', 'confidence score', 'prob', 'score'
        )
        probability = self._parse_probability(prob_value)

        # Extract point coordinates
        point_coords = None
        point_data, point_field = self._get_field_case_insensitive(item, 'point', 'points', 'coordinates')
        if point_data and isinstance(point_data, list) and len(point_data) >= 2:
            point_coords = tuple(point_data[:2])

        # Extract bounding box
        bbox_coords = None
        bbox_data, bbox_field = self._get_field_case_insensitive(
            item, 'bounding_box', 'bounding box', 'bbox', 'box_2d', 'box2d'
        )
        if bbox_data and isinstance(bbox_data, list) and len(bbox_data) >= 4:
            bbox_coords = tuple(bbox_data[:4])

        # Alternative coordinate formats
        if not bbox_coords and not point_coords:
            # Try x, y, width, height format
            coord_fields = ['x', 'y', 'width', 'height']
            if all(field in item for field in coord_fields):
                x, y, w, h = item['x'], item['y'], item['width'], item['height']
                bbox_coords = (x, y, x + w, y + h)
            else:
                # Try xmin, ymin, xmax, ymax format
                coord_fields = ['xmin', 'ymin', 'xmax', 'ymax']
                if all(field in item for field in coord_fields):
                    bbox_coords = (item['xmin'], item['ymin'], item['xmax'], item['ymax'])

        # Extract reason/explanation
        reason = None
        reason_value, reason_field = self._get_field_case_insensitive(
            item, 'reason', 'explanation', 'description'
        )
        if reason_value:
            reason = str(reason_value)
            logger.debug(f"Item {i+1}: Found reason in field '{reason_field}'")

        return {
            'object_type': object_type,
            'probability': probability,
            'bbox_coords': bbox_coords,
            'point_coords': point_coords,
            'reason': reason
        }

    def _create_feature_dict(self, fields, result_number):
        """
        Create feature dictionary for layer creation.

        Args:
            fields: Dictionary with extracted fields
            result_number: Sequential number for this result

        Returns:
            dict: Feature dictionary with all required fields
        """
        object_type = fields['object_type']
        probability = fields['probability']

        # Create enhanced label
        if probability is not None:
            enhanced_label = f"({result_number}) {object_type} ({probability:.0f}%)"
        else:
            enhanced_label = f"({result_number}) {object_type}"

        feature_dict = {
            'label': enhanced_label,
            'object_type': object_type,
            'probability': probability,
            'result_number': result_number,
            'reason': fields['reason']
        }

        # Add geometry info in raw 0-1000 format
        if fields['bbox_coords']:
            feature_dict['box_2d'] = fields['bbox_coords']
        if fields['point_coords']:
            feature_dict['point'] = fields['point_coords']

        return feature_dict

    def _log_processing_summary(self, stats):
        """
        Log summary of JSON processing.

        Args:
            stats: Dictionary with processing statistics
        """
        logger.info(f"JSON Processing Summary:")
        logger.info(f"  Total items in JSON: {stats['total']}")
        logger.info(f"  Items processed successfully: {stats['processed']}")
        logger.info(f"  Items skipped due to low confidence: {stats['skipped_confidence']}")
        logger.info(f"  Items skipped due to missing fields: {stats['skipped_missing']}")
