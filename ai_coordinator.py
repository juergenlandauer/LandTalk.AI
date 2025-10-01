# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI
                                 A QGIS Plugin
 AI Processing Coordinator for LandTalk Plugin
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

AI Processing Coordinator Module for LandTalk Plugin

This module coordinates AI workflow, worker management, result processing,
and debug visualization.
"""

import json
import tempfile
import base64
import os
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMessageBox
from .genai import GenAIHandler
from .ai_worker import AIWorker
from .logging import logger


class AIProcessingCoordinator(QObject):
    """Coordinates AI processing workflow and result handling"""
    
    # Signals
    processing_started = pyqtSignal()
    processing_finished = pyqtSignal(object)  # Emitted with results
    processing_error = pyqtSignal(str)  # Emitted with error message
    processing_progress = pyqtSignal(str)  # Emitted with progress updates
    
    def __init__(self, config_manager, layer_manager, visualization_manager, iface):
        """Initialize the AI processing coordinator
        
        Args:
            config_manager: PluginConfigManager instance
            layer_manager: LayerManager instance  
            visualization_manager: MapVisualizationManager instance
            iface: QGIS interface object
        """
        super().__init__()
        self.config_manager = config_manager
        self.layer_manager = layer_manager
        self.visualization_manager = visualization_manager
        self.iface = iface
        
        # AI components
        self.genai_handler = None
        self.ai_worker = None
        
        # Initialize GenAI handler
        self._ensure_genai_handler()
    
    def _ensure_genai_handler(self):
        """Ensure GenAI handler is initialized"""
        if not self.genai_handler:
            self.genai_handler = GenAIHandler()
    
    def analyze_with_ai(self, model_data, prompt=None):
        """Start AI analysis with the specified model"""
        try:
            logger.info(f"Starting AI analysis with model: {model_data}")
            
            # Check if we have captured image data
            if not self.visualization_manager.has_captured_data():
                logger.error("No captured image data available for AI analysis")
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Warning", 
                    "Please select an area on the map first."
                )
                return False
            
            # Validate model data
            if not isinstance(model_data, dict) or 'provider' not in model_data or 'model' not in model_data:
                logger.error(f"Invalid model data: {model_data}")
                self.processing_error.emit("Invalid model configuration")
                return False
            
            provider = model_data['provider']
            model = model_data['model']
            
            # Check API keys
            if not self._validate_api_keys(provider):
                return False
            
            # Use provided prompt or system prompt
            if not prompt:
                prompt = self.config_manager.get_system_prompt()
            
            # Get captured image data
            image_data = self.visualization_manager.get_captured_image_data()
            if not image_data:
                logger.error("No image data available")
                self.processing_error.emit("No image data available")
                return False
            
            # Start AI worker
            self._start_ai_worker(provider, model, prompt, image_data)
            return True
            
        except Exception as e:
            logger.error(f"Error starting AI analysis: {str(e)}")
            self.processing_error.emit(f"Error starting AI analysis: {str(e)}")
            return False
    
    def _validate_api_keys(self, provider):
        """Validate that the required API key is available"""
        try:
            if provider == 'gemini':
                if not self.config_manager.get_gemini_api_key():
                    if not self.config_manager.get_gemini_key():
                        logger.warning("No Gemini API key provided")
                        return False
            elif provider == 'gpt':
                if not self.config_manager.get_gpt_api_key():
                    if not self.config_manager.get_gpt_key():
                        logger.warning("No GPT API key provided")
                        return False
            else:
                logger.error(f"Unknown AI provider: {provider}")
                self.processing_error.emit(f"Unknown AI provider: {provider}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating API keys: {str(e)}")
            return False
    
    def _start_ai_worker(self, provider, model, prompt, image_data):
        """Start the AI worker thread"""
        try:
            # Clean up any existing worker
            self.cleanup_ai_worker()
            
            # Create and configure AI worker
            self.ai_worker = AIWorker()
            self.ai_worker.set_provider(provider)
            self.ai_worker.set_model(model)
            self.ai_worker.set_prompt(prompt)
            self.ai_worker.set_image_data(image_data)
            
            # Set API configuration
            if provider == 'gemini':
                self.ai_worker.set_api_key(self.config_manager.get_gemini_api_key())
                self.ai_worker.set_api_url(self.config_manager.gemini_api_url)
            elif provider == 'gpt':
                self.ai_worker.set_api_key(self.config_manager.get_gpt_api_key())
                self.ai_worker.set_api_url(self.config_manager.gpt_api_url)
            
            self.ai_worker.set_timeout(self.config_manager.api_timeout)
            
            # Connect signals
            self.ai_worker.finished.connect(self.on_ai_worker_finished)
            self.ai_worker.error.connect(self.on_ai_worker_error)
            self.ai_worker.progress.connect(self.on_ai_worker_progress)
            
            # Start the worker
            self.ai_worker.start()
            
            # Emit processing started signal
            self.processing_started.emit()
            
            logger.info(f"AI worker started for {provider} with model {model}")
            
        except Exception as e:
            logger.error(f"Error starting AI worker: {str(e)}")
            self.processing_error.emit(f"Error starting AI worker: {str(e)}")
    
    def on_ai_worker_finished(self, result):
        """Handle AI worker completion"""
        try:
            logger.info("AI worker finished successfully")
            
            if not result:
                logger.warning("AI worker returned empty result")
                self.processing_error.emit("AI analysis returned no results")
                return
            
            # Process the results
            self._process_ai_results(result)
            
            # Emit completion signal
            self.processing_finished.emit(result)
            
        except Exception as e:
            logger.error(f"Error handling AI worker completion: {str(e)}")
            self.processing_error.emit(f"Error processing AI results: {str(e)}")
        finally:
            self.cleanup_ai_worker()
    
    def on_ai_worker_error(self, error_message):
        """Handle AI worker error"""
        try:
            logger.error(f"AI worker error: {error_message}")
            self.processing_error.emit(error_message)
            
        except Exception as e:
            logger.error(f"Error handling AI worker error: {str(e)}")
        finally:
            self.cleanup_ai_worker()
    
    def on_ai_worker_progress(self, progress_message):
        """Handle AI worker progress updates"""
        try:
            logger.info(f"AI worker progress: {progress_message}")
            self.processing_progress.emit(progress_message)
            
        except Exception as e:
            logger.error(f"Error handling AI worker progress: {str(e)}")
    
    def _process_ai_results(self, result):
        """Process AI results and create layers"""
        try:
            logger.info("Processing AI results")
            
            # Extract AI provider from worker
            ai_provider = self.ai_worker.provider if self.ai_worker else 'unknown'
            
            # Process JSON and create layers
            self.process_json_and_create_layers(result, ai_provider)
            
            # Debug visualization if enabled
            self.debug_render_ai_results_on_image(result.get('features', []), ai_provider)
            
        except Exception as e:
            logger.error(f"Error processing AI results: {str(e)}")
            raise
    
    def process_json_and_create_layers(self, my_json, ai_provider):
        """
        Process JSON response from AI and create QGIS layers.
        
        Args:
            my_json: JSON response from AI
            ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        """
        try:
            logger.info(f"Processing JSON and creating layers for provider: {ai_provider}")
            logger.info(f"JSON data type: {type(my_json)}")
            
            if isinstance(my_json, str):
                try:
                    my_json = json.loads(my_json)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON string: {str(e)}")
                    return
            
            if not isinstance(my_json, dict):
                logger.error(f"Expected dictionary, got {type(my_json)}")
                return
            
            # Extract features from the JSON response
            features_data = my_json.get('features', [])
            
            if not features_data:
                logger.warning("No features found in AI response")
                # Check for alternative structure
                if 'objects' in my_json:
                    features_data = my_json['objects']
                elif 'results' in my_json:
                    features_data = my_json['results']
                elif 'detections' in my_json:
                    features_data = my_json['detections']
            
            if not features_data:
                logger.warning("No feature data found in any expected field")
                return
            
            logger.info(f"Found {len(features_data)} features to process")
            
            # Filter features by confidence threshold
            confidence_threshold = self.config_manager.get_confidence_threshold()
            filtered_features = []
            
            for feature in features_data:
                if isinstance(feature, dict):
                    confidence = feature.get('confidence', feature.get('Confidence', 100.0))
                    try:
                        confidence = float(confidence)
                        if confidence >= confidence_threshold:
                            filtered_features.append(feature)
                        else:
                            logger.info(f"Filtered out feature with confidence {confidence} (threshold: {confidence_threshold})")
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid confidence value: {confidence}, including feature anyway")
                        filtered_features.append(feature)
                else:
                    logger.warning(f"Feature is not a dictionary: {feature}")
            
            logger.info(f"After confidence filtering: {len(filtered_features)} features")
            
            if not filtered_features:
                logger.info("No features passed confidence threshold")
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Analysis Complete",
                    f"No features found with confidence >= {confidence_threshold}%. "
                    f"Try lowering the confidence threshold in settings."
                )
                return
            
            # Get captured area information
            captured_extent = self.visualization_manager.get_captured_extent()
            captured_width, captured_height = self.visualization_manager.get_captured_dimensions()
            captured_top_left, captured_bottom_right = self.visualization_manager.get_captured_corners()
            
            if not captured_extent:
                logger.error("No captured extent available for coordinate conversion")
                return
            
            # Create layers using the layer manager
            created_layers = self.layer_manager.create_single_layer_with_features(
                filtered_features, 
                ai_provider,
                captured_extent,
                captured_top_left,
                captured_bottom_right,
                captured_width,
                captured_height
            )
            
            if created_layers:
                logger.info(f"Successfully created {len(created_layers)} layers")
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Analysis Complete",
                    f"Analysis complete! Created {len(created_layers)} feature layers."
                )
            else:
                logger.warning("No layers were created")
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Analysis Complete",
                    "Analysis complete, but no layers were created. Check the logs for details."
                )
            
        except Exception as e:
            logger.error(f"Error in process_json_and_create_layers: {str(e)}")
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"Error processing AI results: {str(e)}"
            )
    
    def debug_render_ai_results_on_image(self, ai_results, ai_provider):
        """
        Debug function to render AI results as yellow rectangles on the captured image.
        
        Args:
            ai_results: List of AI detection results with bounding box coordinates
            ai_provider: String indicating the AI provider ('gemini' or 'gpt')
        """
        try:
            logger.info("Starting debug_render_ai_results_on_image")
            logger.info(f"AI provider: {ai_provider}")
            logger.info(f"Number of AI results: {len(ai_results) if ai_results else 0}")
            
            if not ai_results:
                logger.info("No AI results to render, returning early")
                return
            
            # Get captured image data
            image_data = self.visualization_manager.get_captured_image_data()
            if not image_data:
                logger.warning("No captured image data available for debug rendering")
                return
            
            # Get the temp directory
            temp_dir = tempfile.gettempdir()
            
            # Create a temporary file for the captured image
            temp_image_path = os.path.join(temp_dir, "debug_captured_image.png")
            
            # Decode and save the base64 image data
            with open(temp_image_path, "wb") as f:
                f.write(base64.b64decode(image_data))
            
            # Call the debug render function from MapRenderer
            map_renderer = self.visualization_manager.get_map_renderer()
            debug_path = map_renderer.debug_render_ai_results(ai_results, temp_image_path, temp_dir)
            
            if debug_path:
                logger.info(f"Debug image created successfully: {debug_path}")
            else:
                logger.warning("Failed to create debug image")
            
            # Clean up temporary file
            try:
                os.remove(temp_image_path)
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Error in debug_render_ai_results_on_image: {str(e)}")
        finally:
            logger.info("Exiting debug_render_ai_results_on_image")
    
    def cleanup_ai_worker(self):
        """Clean up the AI worker"""
        try:
            if self.ai_worker:
                logger.info("Cleaning up AI worker")
                
                # Disconnect signals to prevent further callbacks
                try:
                    self.ai_worker.finished.disconnect()
                    self.ai_worker.error.disconnect()
                    self.ai_worker.progress.disconnect()
                except Exception:
                    pass  # Signals might not be connected
                
                # Terminate the worker if it's still running
                if self.ai_worker.isRunning():
                    self.ai_worker.terminate()
                    if not self.ai_worker.wait(3000):  # Wait up to 3 seconds
                        logger.warning("AI worker did not terminate gracefully")
                
                self.ai_worker = None
                logger.info("AI worker cleanup completed")
                
        except Exception as e:
            logger.error(f"Error cleaning up AI worker: {str(e)}")
    
    def is_processing(self):
        """Check if AI processing is currently active"""
        return self.ai_worker is not None and self.ai_worker.isRunning()
    
    def cancel_processing(self):
        """Cancel any ongoing AI processing"""
        if self.is_processing():
            logger.info("Cancelling AI processing")
            self.cleanup_ai_worker()
            self.processing_error.emit("Processing cancelled by user")
    
    def get_genai_handler(self):
        """Get the GenAI handler instance"""
        self._ensure_genai_handler()
        return self.genai_handler
