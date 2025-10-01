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
import json
import threading
from .logging import logger
from .simple_network_handler import SimpleNetworkHandler, NetworkError, TimeoutError

class GenAIHandler:
    """Handler for GenAI API interactions (Gemini and GPT)"""
    
    def __init__(self, gemini_api_url, gpt_api_url, api_timeout):
        """Initialize with reference to the main plugin instance and API configuration"""
        self.gemini_api_url = gemini_api_url
        self.gpt_api_url = gpt_api_url
        self.api_timeout = api_timeout
        self.interrupt_flag = threading.Event()
        self.current_request = None
        self.network_handler = SimpleNetworkHandler(timeout=api_timeout)
    
    def _initialize_interrupt_support(self):
        """Initialize interrupt support attributes (for backward compatibility)"""
        logger.info("Initializing interrupt support for GenAI handler")
        self.interrupt_flag = threading.Event()
        self.current_request = None
    
    def interrupt_request(self):
        """Interrupt the current AI request"""
        # Ensure interrupt attributes exist (for backward compatibility)
        if not hasattr(self, 'interrupt_flag'):
            self._initialize_interrupt_support()
        
        logger.info("Request interruption requested by user")
        self.interrupt_flag.set()
        # Note: QgsBlockingNetworkRequest doesn't support cancellation during execution
        # The interruption will be checked after the request completes
        logger.info("Interrupt flag set - request will be cancelled when checked")
    
    def reset_interrupt(self):
        """Reset the interrupt flag for new requests"""
        # Ensure interrupt attributes exist (for backward compatibility)
        if not hasattr(self, 'interrupt_flag'):
            self._initialize_interrupt_support()
        
        self.interrupt_flag.clear()
    
    def analyze_with_ai(self, prompt_text, chat_context, model, api_key, image_data=None, system_prompt=None):
        """Unified method to send message to AI API (Gemini or GPT) and return results"""
        # Reset interrupt flag for new request
        self.reset_interrupt()
        
        # Determine provider from model name
        if model.startswith("gemini"): provider = "gemini"
        elif model.startswith("gpt"):  provider = "gpt"
        else: return {"success": False, "error": f"Unknown model type: {model}", "error_type": "invalid_model"}
        
        logger.info(f"analyze_with_ai called with prompt: {prompt_text}, model: {model}, provider: {provider}")
        
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
            logger.info(f"Image data length: {len(image_data) if image_data else 'None'}")
            logger.info(f"Prompt text: {prompt_text}")
            logger.info(f"Chat history length: {len(chat_context) if chat_context else 'None'}")
            
            # Use the provided chat context
            chat_history = chat_context
            
            # Prepare provider-specific request data
            if provider == "gemini":
                headers, url, payload = self._prepare_gemini_request(image_data, prompt_text, chat_history, model, system_prompt, api_key)
            elif provider == "gpt":
                headers, url, payload = self._prepare_gpt_request(image_data, prompt_text, chat_history, model, system_prompt, api_key)

            # Make the API call with configurable timeout and interruption support
            logger.info(f"Making API call to {provider.upper()}")
            
            # Check for interruption before making the request
            # Ensure interrupt attributes exist (for backward compatibility)
            if not hasattr(self, 'interrupt_flag'):
                self._initialize_interrupt_support()
            
            if self.interrupt_flag.is_set():
                logger.info("Request interrupted before API call")
                return {"success": False, "error": "Request interrupted by user", "error_type": "interrupted"}
            
            # Use QGIS network handler for proxy support
            try:
                network_response = self.network_handler.post_json(url, headers, payload)
                
                # Check for interruption after the request
                if self.interrupt_flag.is_set():
                    logger.info("Request interrupted after API call")
                    return {"success": False, "error": "Request interrupted by user", "error_type": "interrupted"}
                
                if not network_response['success']:
                    raise NetworkError(network_response.get('error', 'Unknown network error'))
                
                response_json = network_response['data']
                logger.info(f"API response: {response_json}")
            except NetworkError as e:
                logger.error(f"Network error occurred while calling {provider.upper()} API: {str(e)}")
                return {"success": False, "error": f"Network error occurred while calling {provider.upper()} API: {str(e)}", "error_type": "network_error"}
            except TimeoutError as e:
                # Check if this was actually an interruption
                if self.interrupt_flag.is_set():
                    logger.info("Request interrupted by user (timeout)")
                    return {"success": False, "error": "Request interrupted by user", "error_type": "interrupted"}
                logger.warning(f"API request to {provider.upper()} timed out after {self.api_timeout} seconds")
                return {"success": False, "error": f"Request to {provider.upper()} API timed out after {self.api_timeout} seconds. Please try again.", "error_type": "timeout"}
            
            # Parse provider-specific response
            if provider == "gemini":
                parsed_response = self._parse_gemini_response(response_json)
                logger.info(f"Gemini parsed response: {parsed_response}")
            elif provider == "gpt":
                parsed_response = self._parse_gpt_response(response_json)
                logger.info(f"GPT parsed response: {parsed_response}")
            
            response = parsed_response
                

            if 'error' in response:
                error_message = response.get('error', {}).get('message', "Unknown error")
                return {"success": False, "error": f"Error: {error_message}", "error_type": "api_error"}
                
            result_text = response.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "No response")
            
            # Extract JSON from response
            logger.info(f"About to extract JSON from {provider.upper()} result_text: {result_text}")
            cleaned_text, my_json = self.extract_json_from_response(result_text)
            logger.info(f"{provider.upper()} JSON extraction result - cleaned_text: {cleaned_text}, my_json: {my_json}")
            
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
        logger.info(f"Preparing Gemini request with image_data: {bool(image_data)}, prompt: {prompt_text}, model: {model}")
        headers = {
            "Content-Type": "application/json",
        }
        
        # Build contents array with new sequence: system prompt first, then image, then chat history, then new user message
        contents = []

        # 1. System prompt always comes first if available
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": system_prompt}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "I understand. I'll follow these instructions for all interactions."}]
            })
            logger.info(f"Added system prompt to Gemini request: {system_prompt[:100]}...")

        # 2. Add image if available (as separate user message)
        if image_data:
            contents.append({
                "role": "user",
                "parts": [{
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_data
                    }
                }]
            })
            logger.info(f"Added image to Gemini request, image data length: {len(image_data)} characters")
        else:
            logger.warning("No image data provided for Gemini request - this may indicate missing rectangular selection")

        # 3. Add chat history (convert roles for Gemini format)
        if chat_history:
            for msg in chat_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')

                if role == 'user':
                    contents.append({
                        "role": "user",
                        "parts": [{"text": content}]
                    })
                elif role == 'assistant':
                    contents.append({
                        "role": "model",
                        "parts": [{"text": content}]
                    })
                # Skip system messages in history as they're handled separately
            logger.info(f"Added {len(chat_history)} chat history messages to Gemini request")

        # 4. New user message comes last
        contents.append({
            "role": "user",
            "parts": [{"text": prompt_text}]
        })
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 4096,
#                "thinkingBudget": 0, # does not work
            }
        }
        
        base_url = self.gemini_api_url
        
        # Add API key as a query parameter
        url = f"{base_url}?key={api_key}"
        
        logger.info(f"Gemini request URL: {url}")
        logger.info(f"Gemini request payload prepared with {len(contents)} contents")
        
        # Log all message contents for debugging
        logger.info("=== Gemini Request Messages ===")
        for i, content in enumerate(contents):
            role = content.get('role', 'unknown')
            parts = content.get('parts', [])
            logger.info(f"  Message {i+1} [{role}]:")
            for j, part in enumerate(parts):
                if 'text' in part:
                    text = part['text']
                    # Truncate very long messages for readability
                    if len(text) > 500:
                        text = text[:497] + "..."
                    logger.info(f"    Part {j+1} [text]: {text}")
                elif 'inline_data' in part:
                    logger.info(f"    Part {j+1} [image]: [IMAGE_DATA_EXCLUDED_FROM_LOG]")
                else:
                    logger.info(f"    Part {j+1}: {str(part)[:100]}...")
        logger.info("=== End Gemini Request Messages ===")
        
        return headers, url, payload

    def _prepare_gpt_request(self, image_data, prompt_text, chat_history=None, model=None, system_prompt=None, api_key=None):
        """Prepare GPT-specific request headers, URL, and payload"""
        logger.info(f"Preparing GPT request with image_data: {bool(image_data)}, prompt: {prompt_text}, model: {model}")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Build messages array with new sequence: system prompt first, then image, then chat history, then new user message
        messages = []

        # 1. System prompt always comes first if available
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
            logger.info(f"Added system prompt to GPT request: {system_prompt[:100]}...")

        # 2. Add image if available (as separate user message)
        if image_data:
            # Base64 encode the image if it's not already encoded
            if isinstance(image_data, bytes) or not image_data.startswith("data:"):
                if isinstance(image_data, bytes):
                    encoded_image = base64.b64encode(image_data).decode('utf-8')
                else:
                    encoded_image = image_data
                image_url = f"data:image/png;base64,{encoded_image}"
            else:
                image_url = image_data

            messages.append({
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": image_url}}]
            })
            logger.info(f"Added image to GPT request, image data length: {len(image_data)} characters")
        else:
            logger.warning("No image data provided for GPT request - this may indicate missing rectangular selection")

        # 3. Add chat history
        if chat_history:
            for msg in chat_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')

                # Only add text content for history messages (no images)
                if role in ['user', 'assistant', 'system']:
                    messages.append({
                        "role": role,
                        "content": content
                    })
            logger.info(f"Added {len(chat_history)} chat history messages to GPT request")

        # 4. New user message comes last
        messages.append({
            "role": "user",
            "content": prompt_text
        })
        
        # Determine the model to use
        if model:
            # Map model names to OpenAI model identifiers
            model_mapping = {
                "gpt5-mini": "gpt-5-mini",
                "gpt-4o-mini": "gpt-4o-mini"
            }
            selected_model = model_mapping.get(model, "gpt-5-mini")
        else:
            selected_model = "gpt-5-mini"
        
        payload = {
            "model": selected_model,
            "messages": messages,
            #"max_completion_tokens": 4096
        }
        
        logger.info(f"GPT request payload prepared with {len(messages)} messages, model: {selected_model}")
        
        # Log all message contents for debugging
        logger.info("=== GPT Request Messages ===")
        for i, message in enumerate(messages):
            role = message.get('role', 'unknown')
            content = message.get('content', '')
            logger.info(f"  Message {i+1} [{role}]:")
            
            if isinstance(content, list):
                # Handle GPT-style content with mixed text and image objects
                for j, part in enumerate(content):
                    if isinstance(part, dict) and part.get('type') == 'text':
                        text = part.get('text', '')
                        # Truncate very long messages for readability
                        if len(text) > 500:
                            text = text[:497] + "..."
                        logger.info(f"    Part {j+1} [text]: {text}")
                    elif isinstance(part, dict) and part.get('type') == 'image_url':
                        logger.info(f"    Part {j+1} [image]: [IMAGE_DATA_EXCLUDED_FROM_LOG]")
                    else:
                        logger.info(f"    Part {j+1}: {str(part)[:100]}...")
            elif isinstance(content, str):
                # Handle simple string content
                text = content
                # Truncate very long messages for readability
                if len(text) > 500:
                    text = text[:497] + "..."
                logger.info(f"    Content: {text}")
            else:
                logger.info(f"    Content: {str(content)[:100]}...")
        logger.info("=== End GPT Request Messages ===")
        
        return headers, self.gpt_api_url, payload

    def _parse_gemini_response(self, response_json):
        """Parse Gemini API response"""
        return response_json

    def _parse_gpt_response(self, response_json):
        """Parse GPT API response and normalize to Gemini format"""
        logger.info(f"Parsing GPT response: {response_json}")
        
        # Extract the text from GPT response
        if 'choices' in response_json and len(response_json['choices']) > 0:
            result_text = response_json['choices'][0]['message']['content']
            logger.info(f"Extracted GPT result text: {result_text}")
            
            normalized_response = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": result_text}
                            ]
                        }
                    }
                ]
            }
            logger.info(f"Normalized GPT response: {normalized_response}")
            return normalized_response
        else:
            logger.info(f"No choices found in GPT response, returning original: {response_json}")
            return response_json

    def extract_json_from_response(self, response_text):
        """Extract first valid JSON string from AI response text and return cleaned text and validated JSON data"""
        import json
        
        if not response_text or not isinstance(response_text, str):
            return response_text, None
        
        logger.info(f"Extracting JSON from response: {response_text}")
        
        # Use json.loads to find valid JSON by testing different string boundaries
        # Start from each opening brace/bracket and try to find the complete JSON
        for i, char in enumerate(response_text):
            if char in '{[':
                # Try to find the complete JSON starting from this position
                for end_pos in range(i + 1, len(response_text) + 1):
                    candidate = response_text[i:end_pos]
                    try:
                        parsed_json = json.loads(candidate)
                        logger.info(f"Found valid JSON starting at position {i}: {json.dumps(parsed_json, indent=2)}")
                        
                        # Use basic validation
                        if self._basic_json_validation(parsed_json):
                            logger.info("Basic JSON validation successful")
                            
                            # Remove the JSON from the response text
                            cleaned_text = response_text[:i] + response_text[end_pos:].strip()
                            
                            # Clean up extra whitespace
                            cleaned_text = cleaned_text.replace('\n\n\n', '\n\n').strip()
                            
                            logger.info("Successfully extracted JSON (basic validation)")
                            return cleaned_text, parsed_json
                        else:
                            logger.warning("Basic JSON validation failed")
                            # Continue trying other JSON candidates
                            continue
                        
                    except json.JSONDecodeError:
                        # Continue trying longer strings
                        continue
        
        logger.info("No valid JSON data found in response")
        return response_text, None
    
    def _basic_json_validation(self, json_data):
        """Basic JSON validation fallback when Pydantic is not available"""
        try:
            if isinstance(json_data, list):
                # Check if it's a list of objects with expected fields
                for item in json_data:
                    if not isinstance(item, dict):
                        return False
                    # Check for at least one of the expected field patterns
                    has_object_type = any(field in item for field in ['object_type', 'Object Type', 'objectType'])
                    has_confidence = any(field in item for field in ['confidence_score', 'Confidence Score', 'confidence', 'prob'])
                    has_bbox = any(field in item for field in ['bounding_box', 'Bounding Box', 'bbox'])
                    has_reason = any(field in item for field in ['reason', 'Reason', 'explanation'])
                    
                    if not (has_object_type and has_confidence and has_bbox and has_reason):
                        return False
                return True
            elif isinstance(json_data, dict):
                # Check if it's a single object or wrapper
                if any(field in json_data for field in ['features', 'objects', 'detections']):
                    # It's a wrapper, validate the nested items
                    nested_items = json_data.get('features') or json_data.get('objects') or json_data.get('detections')
                    if isinstance(nested_items, list):
                        return self._basic_json_validation(nested_items)
                else:
                    # It's a single object, check for expected fields
                    has_object_type = any(field in json_data for field in ['object_type', 'Object Type', 'objectType'])
                    has_confidence = any(field in json_data for field in ['confidence_score', 'Confidence Score', 'confidence', 'prob'])
                    has_bbox = any(field in json_data for field in ['bounding_box', 'Bounding Box', 'bbox'])
                    has_reason = any(field in json_data for field in ['reason', 'Reason', 'explanation'])
                    
                    return has_object_type and has_confidence and has_bbox and has_reason
            return False
        except Exception as e:
            logger.warning(f"Basic validation error: {e}")
            return False
