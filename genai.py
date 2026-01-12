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
"""

import base64
import threading
import json
from .logging import logger
from .simple_network_handler import SimpleNetworkHandler, NetworkError, TimeoutError

# Global variable to control full request/response logging
FULL_REQUEST = False

class GenAIHandler:
    """Handler for GenAI API interactions (Gemini and GPT)"""

    # Model mappings
    GPT_MODEL_MAPPING = {
        "gpt5-mini": "gpt-5-mini",
        "gpt-4o-mini": "gpt-4o-mini"
    }

    def __init__(self, gemini_api_url, gpt_api_url, api_timeout):
        """Initialize with reference to the main plugin instance and API configuration"""
        self.gemini_api_url = gemini_api_url
        self.gpt_api_url = gpt_api_url
        self.api_timeout = api_timeout
        self.interrupt_flag = threading.Event()
        self.current_request = None
        self.network_handler = SimpleNetworkHandler(timeout=api_timeout)

    def interrupt_request(self):
        """Interrupt the current AI request"""
        logger.info("Request interruption requested by user")
        self.interrupt_flag.set()
        logger.info("Interrupt flag set - request will be cancelled when checked")

    def reset_interrupt(self):
        """Reset the interrupt flag for new requests"""
        self.interrupt_flag.clear()

    def _check_interruption(self):
        """Check if request was interrupted and return error response if so"""
        if self.interrupt_flag.is_set():
            logger.info("Request interrupted by user")
            return {"success": False, "error": "Request interrupted by user", "error_type": "interrupted"}
        return None

    def _get_provider_from_model(self, model):
        """Determine provider from model name"""
        if model.startswith("gemini"):
            return "gemini"
        elif model.startswith("gpt"):
            return "gpt"
        return None

    def _sanitize_payload_for_logging(self, payload, provider):
        """Create a copy of payload with image data replaced by placeholders for logging"""
        import copy
        sanitized = copy.deepcopy(payload)
        
        if provider == "gemini":
            # Remove inline_data from Gemini contents
            if 'contents' in sanitized:
                for content in sanitized['contents']:
                    if 'parts' in content:
                        for part in content['parts']:
                            if 'inline_data' in part:
                                part['inline_data'] = {"mime_type": part['inline_data'].get('mime_type', 'image/png'), "data": "[IMAGE_DATA_EXCLUDED]"}
        elif provider == "gpt":
            # Remove image URLs from GPT messages
            if 'messages' in sanitized:
                for message in sanitized['messages']:
                    if isinstance(message.get('content'), list):
                        for item in message['content']:
                            if isinstance(item, dict) and item.get('type') == 'image_url':
                                if 'image_url' in item and 'url' in item['image_url']:
                                    item['image_url']['url'] = "[IMAGE_DATA_EXCLUDED]"
        
        return sanitized

    def _log_request_messages(self, messages, provider):
        """Log message contents for debugging (consolidated for both providers)"""
        logger.info(f"=== {provider.upper()} Request Messages ===")
        for i, msg in enumerate(messages):
            if provider == "gemini":
                role = msg.get('role', 'unknown')
                parts = msg.get('parts', [])
                logger.info(f"  Message {i+1} [{role}]:")
                for j, part in enumerate(parts):
                    if 'text' in part:
                        text = part['text'][:497] + "..." if len(part['text']) > 500 else part['text']
                        logger.info(f"    Part {j+1} [text]: {text}")
                    elif 'inline_data' in part:
                        logger.info(f"    Part {j+1} [image]: [IMAGE_DATA_EXCLUDED]")
            else:  # gpt
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                logger.info(f"  Message {i+1} [{role}]:")
                if isinstance(content, list):
                    for j, part in enumerate(content):
                        if isinstance(part, dict) and part.get('type') == 'text':
                            text = part.get('text', '')[:497] + "..." if len(part.get('text', '')) > 500 else part.get('text', '')
                            logger.info(f"    Part {j+1} [text]: {text}")
                        elif isinstance(part, dict) and part.get('type') == 'image_url':
                            logger.info(f"    Part {j+1} [image]: [IMAGE_DATA_EXCLUDED]")
                elif isinstance(content, str):
                    text = content[:497] + "..." if len(content) > 500 else content
                    logger.info(f"    Content: {text}")
        logger.info(f"=== End {provider.upper()} Request Messages ===")

    def analyze_with_ai(self, prompt_text, chat_context, model, api_key, image_data=None, system_prompt=None):
        """Unified method to send message to AI API (Gemini or GPT) and return results"""
        # Reset interrupt flag for new request
        self.reset_interrupt()

        # Determine provider from model name
        provider = self._get_provider_from_model(model)
        if not provider:
            return {"success": False, "error": f"Unknown model type: {model}", "error_type": "invalid_model"}

        logger.info(f"analyze_with_ai called - model: {model}, provider: {provider}")
        
        # Validate inputs
        if not prompt_text:
            return {"success": False, "error": "Please enter a message.", "error_type": "input_required"}
        
        if chat_context is None:
            return {"success": False, "error": "Chat context is required.", "error_type": "invalid_input"}
        
        # Check if API key is provided
        if not api_key:
            provider_name = "Google Gemini" if provider == "gemini" else "OpenAI GPT"
            return {"success": False, "error": f"Please set your {provider_name} API key first.", "error_type": "api_key_required"}
        
        try:
            logger.info(f"Making API call with provider: {provider} and model: {model}")
            logger.info(f"Chat history length: {len(chat_context) if chat_context else 0}")

            # Prepare provider-specific request data
            if provider == "gemini":
                headers, url, payload = self._prepare_gemini_request(image_data, prompt_text, chat_context, model, system_prompt, api_key)
            elif provider == "gpt":
                headers, url, payload = self._prepare_gpt_request(image_data, prompt_text, chat_context, model, system_prompt, api_key)

            # Log full request if FULL_REQUEST is enabled
            if FULL_REQUEST:
                sanitized_payload = self._sanitize_payload_for_logging(payload, provider)
                logger.info(f"=== FULL {provider.upper()} REQUEST ===")
                logger.info(f"URL: {url}")
                logger.info(f"Headers: {headers}")
                logger.info(f"Payload: {json.dumps(sanitized_payload, indent=2, ensure_ascii=False)}")
                logger.info(f"=== END FULL {provider.upper()} REQUEST ===")

            # Check for interruption before making the request
            interrupt_result = self._check_interruption()
            if interrupt_result:
                return interrupt_result
            
            # Use QGIS network handler for proxy support
            try:
                network_response = self.network_handler.post_json(url, headers, payload)

                # Check for interruption after the request
                interrupt_result = self._check_interruption()
                if interrupt_result:
                    return interrupt_result
                
                if not network_response['success']:
                    raise NetworkError(network_response.get('error', 'Unknown network error'))
                
                response_json = network_response['data']
                logger.info(f"API response: {response_json}")
                
                # Log full response if FULL_REQUEST is enabled
                if FULL_REQUEST:
                    logger.info(f"=== FULL {provider.upper()} RESPONSE ===")
                    logger.info(f"Response: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
                    logger.info(f"=== END FULL {provider.upper()} RESPONSE ===")
            except NetworkError as e:
                logger.error(f"Network error occurred while calling {provider.upper()} API: {str(e)}")
                return {"success": False, "error": f"Network error occurred while calling {provider.upper()} API: {str(e)}", "error_type": "network_error"}
            except TimeoutError as e:
                # Check if this was actually an interruption
                interrupt_result = self._check_interruption()
                if interrupt_result:
                    return interrupt_result
                logger.warning(f"API request to {provider.upper()} timed out after {self.api_timeout} seconds")
                return {"success": False, "error": f"Request to {provider.upper()} API timed out after {self.api_timeout} seconds. Please try again.", "error_type": "timeout"}
            
            # Parse provider-specific response
            response = self._parse_gemini_response(response_json) if provider == "gemini" else self._parse_gpt_response(response_json)
            logger.info(f"{provider.upper()} parsed response received")
                

            if 'error' in response:
                error_message = response.get('error', {}).get('message', "Unknown error")
                return {"success": False, "error": f"Error: {error_message}", "error_type": "api_error"}
                
            result_text = response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "No response")

            # Extract JSON from response
            cleaned_text, my_json = self.extract_json_from_response(result_text)
            logger.info(f"JSON extraction result - found: {bool(my_json)}")
            
            # Add validation status to response
            if my_json:
                validation_status = "validated_basic"
                logger.info(f"JSON data successfully validated ({validation_status}): {len(my_json) if isinstance(my_json, list) else 1} features")
            else:
                validation_status = "no_json"
                logger.info("No valid JSON data found in response after validation")
            
            return {
                "success": True,
                "result_text": result_text,  # Keep original text with JSON for UI formatting
                "json_data": my_json,
                "image_data": image_data,
                "provider": provider,
                "validation_status": validation_status
            }
            
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}", "error_type": "exception", "image_data": image_data}

    def _prepare_gemini_request(self, image_data, prompt_text, chat_history=None, model=None, system_prompt=None, api_key=None):
        """Prepare Gemini-specific request headers, URL, and payload"""
        logger.info(f"Preparing Gemini request - model: {model}, has_image: {bool(image_data)}")
        headers = {"Content-Type": "application/json"}

        # Build contents array with new sequence: image(s), then chat history, then new user message (with system prompt prepended)
        contents = []

        # 1. Add image(s) if available (as a single user message with multiple parts)
        if image_data:
            # Support both single image (string) and multiple images (list)
            images_list = image_data if isinstance(image_data, list) else [image_data]

            # Create a single user message with all images as parts
            image_parts = []
            for img_data in images_list:
                image_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": img_data
                    }
                })

            # Add single message with all image parts
            contents.append({
                "role": "user",
                "parts": image_parts
            })

        # 2. Add chat history (convert roles for Gemini format)
        if chat_history:
            for msg in chat_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    contents.append({"role": "user", "parts": [{"text": content}]})
                elif role == 'assistant':
                    contents.append({"role": "model", "parts": [{"text": content}]})
                # Skip system messages in history as they're handled separately

        # 3. New user message comes last (with system prompt prepended if available)
        user_message_text = f"{system_prompt}\n{prompt_text}" if system_prompt else prompt_text
        contents.append({"role": "user", "parts": [{"text": user_message_text}]})
        
        payload = {
            "contents": contents,
            "generationConfig": {
#                "temperature": 0.5,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 4096,
#                "thinkingConfig": {
#                    "thinkingBudget": 0
#                }
            },
            "tools": [
                {
                    "urlContext": {}
                }
            ]
        }
        
        # Construct the full URL with model name and endpoint
        base_url = self.gemini_api_url
        logger.info(f"before base_url {base_url}")
        if model and ':generateContent' in model:
            # Extract the model name without the endpoint suffix to avoid duplication
            model_name = model.split(':generateContent')[0]
            url = f"{base_url}{model_name}:generateContent?key={api_key.strip()}"
        else:
            model_name = model if model else "gemini-1.5-flash"
            url = f"{base_url}{model_name}:generateContent?key={api_key.strip()}"

        logger.info(f"Gemini request prepared - {len(contents)} messages")
        logger.info(f"url {url}, base_url {base_url}, model_name {model_name}")
        self._log_request_messages(contents, "gemini")

        return headers, url, payload

    def _prepare_gpt_request(self, image_data, prompt_text, chat_history=None, model=None, system_prompt=None, api_key=None):
        """Prepare GPT-specific request headers, URL, and payload"""
        logger.info(f"Preparing GPT request - model: {model}, has_image: {bool(image_data)}")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # Build messages array with new sequence: system prompt first, then image, then chat history, then new user message
        messages = []

        # 1. System prompt always comes first if available
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 2. Add image(s) if available (as separate user message(s))
        if image_data:
            # Support both single image (string) and multiple images (list)
            images_list = image_data if isinstance(image_data, list) else [image_data]

            for img_data in images_list:
                # Base64 encode the image if it's not already encoded
                if isinstance(img_data, bytes) or not img_data.startswith("data:"):
                    encoded_image = base64.b64encode(img_data).decode('utf-8') if isinstance(img_data, bytes) else img_data
                    image_url = f"data:image/png;base64,{encoded_image}"
                else:
                    image_url = img_data

                messages.append({
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": image_url}}]
                })

        # 3. Add chat history
        if chat_history:
            for msg in chat_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                # Only add text content for history messages (no images)
                if role in ['user', 'assistant', 'system']:
                    messages.append({"role": role, "content": content})

        # 4. New user message comes last
        messages.append({"role": "user", "content": prompt_text})

        # Determine the model to use
        selected_model = self.GPT_MODEL_MAPPING.get(model, "gpt-5-mini") if model else "gpt-5-mini"

        payload = {
            "model": selected_model,
            "messages": messages,
        }

        logger.info(f"GPT request prepared - {len(messages)} messages, model: {selected_model}")
        self._log_request_messages(messages, "gpt")

        return headers, self.gpt_api_url, payload

    def _parse_gemini_response(self, response_json):
        """Parse Gemini API response (already in correct format)"""
        return response_json

    def _parse_gpt_response(self, response_json):
        """Parse GPT API response and normalize to Gemini format"""
        # Extract the text from GPT response and normalize to Gemini format
        if 'choices' in response_json and len(response_json['choices']) > 0:
            result_text = response_json['choices'][0]['message']['content']
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": result_text}]
                    }
                }]
            }
        return response_json

    def extract_json_from_response(self, response_text):
        """Extract first valid JSON string from AI response text and return cleaned text and validated JSON data"""
        import json
        import re

        if not response_text or not isinstance(response_text, str):
            return response_text, None

        logger.info("Extracting JSON from response")

        # Use json.loads to find valid JSON by testing different string boundaries
        # Start from each opening brace/bracket and try to find the complete JSON
        for i, char in enumerate(response_text):
            if char in '{[':
                # Try to find the complete JSON starting from this position
                for end_pos in range(i + 1, len(response_text) + 1):
                    try:
                        json_candidate = response_text[i:end_pos]
                        parsed_json = json.loads(json_candidate)

                        # Use basic validation
                        if self._basic_json_validation(parsed_json):
                            # Remove the JSON from the response text and clean up whitespace
                            cleaned_text = (response_text[:i] + response_text[end_pos:].strip()).replace('\n\n\n', '\n\n').strip()
                            logger.info("Successfully extracted and validated JSON")
                            return cleaned_text, parsed_json
                    except json.JSONDecodeError as e:
                        # Try to repair common JSON issues before giving up on this position
                        if end_pos == len(response_text):
                            json_candidate = response_text[i:end_pos]
                            repaired_json = self._attempt_json_repair(json_candidate)
                            if repaired_json:
                                try:
                                    parsed_json = json.loads(repaired_json)
                                    if self._basic_json_validation(parsed_json):
                                        cleaned_text = (response_text[:i] + response_text[end_pos:].strip()).replace('\n\n\n', '\n\n').strip()
                                        logger.info("Successfully extracted and validated JSON after repair")
                                        return cleaned_text, parsed_json
                                except json.JSONDecodeError:
                                    pass
                        continue

        logger.info("No valid JSON data found in response")
        return response_text, None

    def _attempt_json_repair(self, json_str):
        """Attempt to repair common JSON syntax errors

        Args:
            json_str: Malformed JSON string

        Returns:
            str: Repaired JSON string or None if repair failed
        """
        import re

        if not json_str or not isinstance(json_str, str):
            return None

        logger.info(f"Attempting to repair JSON: {json_str[:200]}...")

        try:
            # Pattern 1: Fix missing values after colons (e.g., "key":, -> "key": null,)
            # This handles cases like {"box_2d":, "label": ...}
            repaired = re.sub(r':\s*,', ': null,', json_str)

            # Pattern 2: Fix missing values before closing braces (e.g., "key":} -> "key": null})
            repaired = re.sub(r':\s*}', ': null}', repaired)

            # Pattern 3: Fix missing values before closing brackets (e.g., "key":] -> "key": null])
            repaired = re.sub(r':\s*\]', ': null]', repaired)

            # Pattern 4: Fix trailing commas in objects
            repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)

            # Pattern 5: Fix missing quotes around keys (basic attempt)
            # Match word characters followed by colon, ensure they're quoted
            repaired = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', repaired)

            # Pattern 6: Handle incomplete arrays at the end
            # If string ends with incomplete structure, try to close it
            if repaired.count('[') > repaired.count(']'):
                repaired += ']' * (repaired.count('[') - repaired.count(']'))
            if repaired.count('{') > repaired.count('}'):
                repaired += '}' * (repaired.count('{') - repaired.count('}'))

            if repaired != json_str:
                logger.info(f"JSON repair attempted. Original: {json_str[:100]}... -> Repaired: {repaired[:100]}...")
                return repaired

        except Exception as e:
            logger.warning(f"JSON repair failed: {str(e)}")

        return None
    
    def _has_field_case_insensitive(self, obj, field_variants):
        """Check if object has any of the field variants (case-insensitive)"""
        if not isinstance(obj, dict):
            return False
        obj_keys_lower = {k.lower(): k for k in obj.keys()}
        return any(variant.lower() in obj_keys_lower for variant in field_variants)

    def _get_field_value_case_insensitive(self, obj, field_variants):
        """Get value from dict using case-insensitive field lookup

        Args:
            obj: Dictionary to search
            field_variants: List of field names to try (in order of priority)

        Returns:
            Value if found, None otherwise
        """
        if not isinstance(obj, dict):
            return None
        obj_keys_lower = {k.lower(): k for k in obj.keys()}
        for field_name in field_variants:
            field_lower = field_name.lower()
            if field_lower in obj_keys_lower:
                return obj[obj_keys_lower[field_lower]]
        return None

    def _validate_feature_object(self, item):
        """Validate a single feature object has required fields with valid values"""
        # Check for label/object_type
        label_value = self._get_field_value_case_insensitive(item, ['label', 'object_type', 'object type', 'objectType'])
        has_valid_label = label_value is not None and label_value != ''

        # Check for bbox with valid data (list/array with at least 4 elements)
        bbox_value = self._get_field_value_case_insensitive(item, ['box_2d', 'box2d', 'bounding_box', 'bounding box', 'bbox'])
        has_valid_bbox = (bbox_value is not None and
                         isinstance(bbox_value, (list, tuple)) and
                         len(bbox_value) >= 4 and
                         all(v is not None for v in bbox_value[:4]))

        # Check for point with valid data (list/array with at least 2 elements)
        point_value = self._get_field_value_case_insensitive(item, ['point', 'points', 'coordinates'])
        has_valid_point = (point_value is not None and
                          isinstance(point_value, (list, tuple)) and
                          len(point_value) >= 2 and
                          all(v is not None for v in point_value[:2]))

        has_valid_geometry = has_valid_bbox or has_valid_point

        # Log validation failure reasons for debugging
        if not has_valid_label:
            logger.debug(f"Feature validation failed: missing or empty label (value: {label_value})")
        if not has_valid_geometry:
            logger.debug(f"Feature validation failed: invalid geometry (bbox: {bbox_value}, point: {point_value})")

        # Only require object_type and geometry - confidence and reason are optional
        return has_valid_label and has_valid_geometry

    def _basic_json_validation(self, json_data):
        """Basic JSON validation fallback when Pydantic is not available"""
        try:

            if isinstance(json_data, list):
                # Check if it's a list of objects with expected fields
                if len(json_data) == 0:
                    return False
                return all(isinstance(item, dict) and self._validate_feature_object(item) for item in json_data)
            elif isinstance(json_data, dict):
                # Check if it's a wrapper object containing features
                if self._has_field_case_insensitive(json_data, ['features', 'objects', 'detections']):
                    for key in json_data.keys():
                        if key.lower() in ['features', 'objects', 'detections']:
                            nested_items = json_data[key]
                            return isinstance(nested_items, list) and self._basic_json_validation(nested_items)
                else:
                    # It's a single object, validate it
                    return self._validate_feature_object(json_data)
            return False
        except Exception as e:
            logger.warning(f"Basic validation error: {e}")
            return False
