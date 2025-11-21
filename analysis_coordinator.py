# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - Analysis Coordinator
                                 A QGIS Plugin
 Coordinate the AI analysis workflow
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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
from qgis.core import QgsProject, Qgis
from .logging import logger
from .constants import PluginConstants
from .ai_worker import AIWorker


class AnalysisCoordinator:
    """Coordinate the AI analysis workflow"""

    def __init__(self, plugin):
        """
        Initialize the coordinator.

        Args:
            plugin: Reference to the main LandTalkPlugin instance
        """
        self.plugin = plugin
        self.config_manager = plugin.config_manager
        self.iface = plugin.iface
        self.ai_worker = None

    def start_analysis(self, model):
        """
        Main entry point for starting AI analysis.

        Args:
            model: AI model name (e.g., 'gemini-1.5-pro', 'gpt-4')

        Returns:
            bool: True if analysis started successfully, False otherwise
        """
        # Determine AI provider based on model name
        ai_provider = self._determine_provider(model)
        if not ai_provider:
            logger.error(f"Unknown model type: {model}")
            QMessageBox.warning(self.plugin.dock_widget, "Error", f"Unknown model type: {model}")
            return False

        logger.info(f"Starting analysis with model: {model} (provider: {ai_provider})")

        # Deselect all existing LandTalk.ai layers to ensure only the most recent one is selected
        self.plugin.layer_manager.update_ai_analysis_visibility(current_group_name=None)

        # Get prompt text from UI
        prompt_text = self._get_prompt_text()
        logger.info(f"Prompt text: {prompt_text}")

        # Validate prerequisites
        is_valid, error_message = self._validate_prerequisites()
        if not is_valid:
            QMessageBox.warning(self.plugin.dock_widget, "Error", error_message)
            return False

        # Prepare images for analysis
        all_images, prompt_modifier = self._prepare_images()
        if all_images is None:
            QMessageBox.warning(self.plugin.dock_widget, "Error", prompt_modifier)  # Error message is in second return value
            return False

        # Modify prompt if needed
        if prompt_modifier:
            prompt_text = f"{prompt_modifier}{prompt_text}"

        # Add user message to chat display
        self.plugin.dock_widget.add_user_message(prompt_text)

        # Clear the input field only (keep uploaded images until QGIS closes)
        self.plugin.dock_widget.prompt_text.clear()

        # Set current AI provider for conversation continuity
        self.plugin.dock_widget.current_ai_provider = ai_provider

        # Get chat context for the AI call
        chat_context = self.plugin.dock_widget.get_chat_context()

        # Add the user message to chat history
        self.plugin.dock_widget.add_to_chat_history('user', prompt_text)

        # Get the appropriate API key
        api_key = self._get_api_key(ai_provider)
        if not api_key:
            return False

        # Log image data info
        if isinstance(all_images, list):
            logger.info(f"Successfully prepared {len(all_images)} image(s) for AI")
        else:
            logger.info(f"Successfully captured image data, length: {len(all_images)} characters")

        # Start the AI worker thread
        self._start_worker(prompt_text, chat_context, model, api_key, all_images)
        return True

    def handle_result(self, result):
        """
        Handle the completion of an AI worker thread.

        Args:
            result: Dictionary with analysis results
        """
        try:
            dock_widget = self.plugin.dock_widget
            ai_provider = dock_widget.current_ai_provider if hasattr(dock_widget, 'current_ai_provider') else "unknown"

            if result["success"]:
                # Process JSON first if found
                json_data = None
                if result["json_data"]:
                    provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
                    logger.info(f"Processing {provider_name} JSON data: {result['json_data']}")
                    self.plugin.process_json_and_create_layers(result["json_data"], ai_provider)
                    json_data = result["json_data"]

                # Add AI response to chat and history with JSON data
                dock_widget.add_ai_message(result["result_text"], ai_provider, json_data)
                dock_widget.add_to_chat_history('assistant', result["result_text"], ai_provider)
            else:
                # Handle different error types
                if result["error_type"] == "interrupted":
                    # Don't show error message for interruption, it's already handled by the interrupt method
                    logger.info("Request was interrupted by user")
                elif result["error_type"] in ["input_required", "api_key_required"]:
                    QMessageBox.warning(dock_widget, "Error", result["error"])
                else:
                    dock_widget.add_ai_message(result["error"], ai_provider)

                    # Even on error, try to create a layer with the bounding box if we captured an image
                    if result.get("image_data"):
                        try:
                            self._create_error_extent_layer(ai_provider)
                        except Exception:
                            pass  # Don't let bounding box creation errors mask the original error

        except Exception as e:
            dock_widget.add_ai_message(f"Unexpected error: {str(e)}", ai_provider)
        finally:
            # Clean up the worker and restore UI
            self.cleanup_worker()

    def handle_error(self, error_message):
        """
        Handle errors from the AI worker thread.

        Args:
            error_message: Error message string
        """
        dock_widget = self.plugin.dock_widget
        ai_provider = dock_widget.current_ai_provider if hasattr(dock_widget, 'current_ai_provider') else "unknown"
        dock_widget.add_ai_message(f"Error: {error_message}", ai_provider)
        self.cleanup_worker()

    def handle_progress(self, progress_message):
        """
        Handle progress updates from the AI worker thread.

        Args:
            progress_message: Progress message string
        """
        # Update the status or show progress in the UI
        if hasattr(self.plugin.dock_widget, 'update_status'):
            self.plugin.dock_widget.update_status(progress_message)
        logger.info(f"AI Progress: {progress_message}")

    def cleanup_worker(self):
        """Clean up the AI worker thread and restore UI state"""
        if self.ai_worker:
            self.ai_worker.quit()
            self.ai_worker.wait()
            self.ai_worker = None

        # Update plugin's reference
        self.plugin.ai_worker = None

        # Restore cursor and re-enable dock widget
        QApplication.restoreOverrideCursor()
        self.plugin.dock_widget.setEnabled(True)

        # Re-enable the send button specifically
        if hasattr(self.plugin.dock_widget, 'send_button'):
            self.plugin.dock_widget.send_button.setEnabled(True)

    def _determine_provider(self, model):
        """
        Determine AI provider from model name.

        Args:
            model: Model name string

        Returns:
            str: 'gemini', 'gpt', or None if unknown
        """
        if model.startswith("gemini"):
            return "gemini"
        elif model.startswith("gpt"):
            return "gpt"
        return None

    def _get_prompt_text(self):
        """
        Get prompt text from UI with default fallback.

        Returns:
            str: Prompt text
        """
        prompt_text = self.plugin.dock_widget.prompt_text.toPlainText().strip()

        # Use default prompt if user didn't enter anything
        if not prompt_text:
            prompt_text = PluginConstants.DEFAULT_ANALYSIS_PROMPT
            logger.info(f"No prompt provided, using default: {prompt_text}")

        return prompt_text

    def _validate_prerequisites(self):
        """
        Validate that all prerequisites for analysis are met.

        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if the project has been saved
        project = QgsProject.instance()
        if not project.fileName():
            return False, "Please save your project first before analyzing. The plugin needs to create analysis files next to your project file."

        # Always ensure we have a selected rectangle
        if not self.plugin.selected_rectangle:
            return False, "Please select a map area first by drawing a rectangle on the map."

        # Check if there's already an AI request in progress
        if self.ai_worker and self.ai_worker.isRunning():
            return False, "Please wait for the current AI request to complete."

        return True, None

    def _prepare_images(self):
        """
        Prepare images (map + uploaded) for AI analysis.

        Returns:
            tuple: (all_images, prompt_modifier) or (None, error_message) on error
        """
        # Use the image that was captured when the rectangle was selected
        if self.plugin.capture_state.has_capture():
            logger.info("Using image captured during rectangle selection.")
            image_data = self.plugin.capture_state.image_data
        else:
            logger.error("No captured image data available. Rectangle selection may have failed.")
            return None, "No map image available. Please select a map area again."

        # Collect uploaded images and combine with map image
        uploaded_images_data = []
        if hasattr(self.plugin.dock_widget, 'uploaded_images') and self.plugin.dock_widget.uploaded_images:
            uploaded_images_data = [img_data for _, img_data in self.plugin.dock_widget.uploaded_images]
            logger.info(f"Found {len(uploaded_images_data)} uploaded image(s)")

        # Combine uploaded images with map image
        prompt_modifier = ""
        if uploaded_images_data:
            all_images = uploaded_images_data + [image_data]
            logger.info(f"Sending {len(all_images)} images to AI ({len(uploaded_images_data)} uploaded + 1 map)")
            prompt_modifier = "Take these example images into consideration. "
        else:
            all_images = image_data
            logger.info("Sending only map image to AI")

        return all_images, prompt_modifier

    def _get_api_key(self, ai_provider):
        """
        Get the API key for the specified AI provider.

        Args:
            ai_provider: 'gemini' or 'gpt'

        Returns:
            str: API key or None if not available
        """
        if ai_provider == "gemini":
            if not self.config_manager.gemini_api_key:
                if self.config_manager.get_gemini_key():
                    pass  # Key was set in config_manager
                if not self.config_manager.gemini_api_key:
                    QMessageBox.warning(self.plugin.dock_widget, "Error", "Please set your Google Gemini API key first.")
                    return None
            return self.config_manager.gemini_api_key
        else:  # gpt
            if not self.config_manager.gpt_api_key:
                if self.config_manager.get_gpt_key():
                    pass  # Key was set in config_manager
                if not self.config_manager.gpt_api_key:
                    QMessageBox.warning(self.plugin.dock_widget, "Error", "Please set your OpenAI GPT API key first.")
                    return None
            return self.config_manager.gpt_api_key

    def _start_worker(self, prompt_text, chat_context, model, api_key, all_images):
        """
        Start the AI worker thread with the given parameters.

        Args:
            prompt_text: User prompt
            chat_context: Chat history context
            model: AI model name
            api_key: API key for the provider
            all_images: Image data to analyze
        """
        # Set wait cursor and disable send button
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor if hasattr(Qt, 'CursorShape') else 4))

        if hasattr(self.plugin.dock_widget, 'send_button'):
            self.plugin.dock_widget.send_button.setEnabled(False)

        # Create and start the AI worker thread
        self.ai_worker = AIWorker(
            self.plugin.get_genai_handler(),
            prompt_text,
            chat_context,
            model,
            api_key,
            all_images,
            self.config_manager.system_prompt
        )

        # Store reference in plugin for compatibility
        self.plugin.ai_worker = self.ai_worker

        # Connect worker signals to handler methods
        self.ai_worker.finished.connect(self.handle_result)
        self.ai_worker.error.connect(self.handle_error)
        self.ai_worker.progress.connect(self.handle_progress)

        # Start the worker thread
        self.ai_worker.start()

    def _create_error_extent_layer(self, ai_provider):
        """
        Create a layer with only the bounding box feature for errors.

        Args:
            ai_provider: AI provider name
        """
        provider_name = ai_provider.upper() if ai_provider else "UNKNOWN"
        bbox_features_data = [{
            'label': f"Query extent analyzed by {provider_name}",
            'object_type': 'query_extent',
            'probability': None,
            'result_number': 0,
            'box_2d': [0, 0, 1000, 1000],  # Full extent in 0-1000 range
            'reason': ''
        }]
        # Unpack capture state for layer creation (only need extent, width, height)
        extent, _, _, width, height, _ = self.plugin.capture_state.get_all()
        self.plugin.layer_manager.create_single_layer_with_features(
            bbox_features_data, ai_provider,
            extent, width, height
        )
