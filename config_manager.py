# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI
                                 A QGIS Plugin
 Configuration and Settings Manager for LandTalk Plugin
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

Configuration and Settings Manager Module for LandTalk Plugin

This module handles all plugin configuration, including API keys, settings,
and system prompts.
"""

import os
import json
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox
from .logging import logger
from .ai_worker import ApiKeyDialog


class PluginConfigManager:
    """Manages plugin configuration, settings, and API keys"""
    
    def __init__(self, plugin_dir, iface):
        """Initialize the configuration manager
        
        Args:
            plugin_dir: Path to the plugin directory
            iface: QGIS interface object
        """
        self.plugin_dir = plugin_dir
        self.iface = iface
        
        # File paths
        self.keys_file = os.path.join(plugin_dir, 'keys.txt')
        self.settings_file = os.path.join(plugin_dir, 'settings.txt')
        self.system_prompt_file = os.path.join(plugin_dir, 'systemprompt.txt')
        
        # API configuration
        self.gemini_api_key = ""
        # Use a base Gemini API models URL; the specific model will be appended at runtime
        self.gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/models/"
        self.gpt_api_key = ""
        self.gpt_api_url = "https://api.openai.com/v1/chat/completions"
        self.api_timeout = 60
        
        # Settings
        self.default_confidence_threshold = 50.0
        self.confidence_threshold = self.default_confidence_threshold
        self.custom_analysis_directory = None
        self.auto_clear_on_model_change = True
        # Leave empty so the UI combo's currentData() becomes authoritative
        self.last_selected_model = ''
        self.show_tutorial = True
        self.ground_resolution_m_per_px = 1.0  # Fixed ground resolution in meters per pixel

        # Layer persistence mode: 'auto_save', 'temporary', or 'prompt_on_close'
        self.layer_persistence_mode = 'auto_save'  # Default to auto-save for beginners
        
        # System prompt (builtin fallback)
        self.system_prompt = "You are an expert in landscape analysis and geography."
        # New: keep separate default and user override files.
        # `defaultSystemprompt.txt` contains the read-only default prompt.
        # `systemprompt.txt` contains the user's edited prompt (override).
        self.default_system_prompt_file = os.path.join(plugin_dir, 'defaultSystemprompt.txt')
        self.system_prompt_file = os.path.join(plugin_dir, 'systemprompt.txt')
        
        # If a `systemprompt.txt` exists but no `defaultSystemprompt.txt`, migrate
        # the existing file to become the default (one-time migration).
        try:
            if os.path.exists(self.system_prompt_file) and not os.path.exists(self.default_system_prompt_file):
                os.replace(self.system_prompt_file, self.default_system_prompt_file)
                logger.info("Migrated existing systemprompt.txt -> defaultSystemprompt.txt")
        except Exception as e:
            logger.warning(f"Error migrating system prompt files: {e}")

        # Load all configuration on initialization
        self.load_all_config()
    
    def load_all_config(self):
        """Load all configuration files"""
        self.load_keys()
        self.load_settings()
        self.load_system_prompt()
    
    def load_keys(self):
        """Load API keys from keys.txt file if it exists"""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    keys_data = json.load(f)
                    self.gemini_api_key = keys_data.get('gemini', '')
                    self.gpt_api_key = keys_data.get('gpt', '')
                logger.info("API keys loaded from file")
            except Exception as e:
                logger.warning(f"Error loading API keys: {str(e)}")
        else:
            logger.info("No keys file found")
    
    def save_keys(self):
        """Save API keys to keys.txt file"""
        try:
            keys_data = {
                'gemini': self.gemini_api_key,
                'gpt': self.gpt_api_key
            }
            with open(self.keys_file, 'w') as f:
                json.dump(keys_data, f, indent=2)
            logger.info("API keys saved to file")
        except Exception as e:
            logger.error(f"Error saving API keys: {str(e)}")
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Warning",
                f"Could not save API keys to file: {str(e)}"
            )
    
    def load_settings(self):
        """Load plugin settings from settings.txt file if it exists"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    settings_data = json.load(f)
                    self.confidence_threshold = settings_data.get('confidence_threshold', self.default_confidence_threshold)
                    self.custom_analysis_directory = settings_data.get('custom_analysis_directory', None)
                    self.auto_clear_on_model_change = settings_data.get('auto_clear_on_model_change', True)
                    self.last_selected_model = settings_data.get('last_selected_model', '')
                    self.show_tutorial = settings_data.get('show_tutorial', True)
                    self.layer_persistence_mode = settings_data.get('layer_persistence_mode', 'auto_save')
                logger.info(f"Plugin settings loaded from file. Confidence threshold: {self.confidence_threshold}, Last model: {self.last_selected_model}, Layer persistence: {self.layer_persistence_mode}")
            except Exception as e:
                logger.warning(f"Error loading plugin settings: {str(e)}")
                self.confidence_threshold = self.default_confidence_threshold
                self.last_selected_model = ''  # No hard-coded default; UI determines default
                self.layer_persistence_mode = 'auto_save'
        else:
            logger.info("No settings file found, using default values")
            self.confidence_threshold = self.default_confidence_threshold
            self.last_selected_model = ''  # No hard-coded default; UI determines default
            self.layer_persistence_mode = 'auto_save'
    
    def save_settings(self):
        """Save plugin settings to settings.txt file"""
        try:
            settings_data = {
                'confidence_threshold': self.confidence_threshold,
                'custom_analysis_directory': self.custom_analysis_directory,
                'auto_clear_on_model_change': self.auto_clear_on_model_change,
                'last_selected_model': self.last_selected_model,
                'show_tutorial': self.show_tutorial,
                'layer_persistence_mode': self.layer_persistence_mode
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings_data, f, indent=2)
            logger.info("Plugin settings saved to file")
        except Exception as e:
            logger.error(f"Error saving plugin settings: {str(e)}")
    
    def get_gemini_key(self):
        """Get Gemini API key from the user"""
        dialog = ApiKeyDialog(
            self.iface.mainWindow(), 
            "Gemini API Key", 
            "gemini",
            "Please enter your Google Gemini API key:\n\n"
            "1. Go to https://aistudio.google.com/app/apikey\n"
            "2. Create a new API key\n"
            "3. Copy and paste it below",
            self.gemini_api_key
        )
        
        if dialog.exec_() == QDialog.Accepted:
            self.gemini_api_key = dialog.get_api_key()
            self.save_keys()
            return True
        return False
    
    def get_gpt_key(self):
        """Get GPT API key from the user"""
        dialog = ApiKeyDialog(
            self.iface.mainWindow(), 
            "GPT API Key", 
            "openai",
            "Please enter your OpenAI API key:\n\n"
            "1. Go to https://platform.openai.com/api-keys\n"
            "2. Create a new API key\n"
            "3. Copy and paste it below",
            self.gpt_api_key
        )
        
        if dialog.exec_() == QDialog.Accepted:
            self.gpt_api_key = dialog.get_api_key()
            self.save_keys()
            return True
        return False
    
    def get_confidence_threshold(self):
        """
        Get the confidence threshold value from stored settings.
        
        :return: Float confidence threshold value (0-100)
        """
        try:
            if hasattr(self, 'confidence_threshold') and self.confidence_threshold is not None:
                return float(self.confidence_threshold)
            else:
                return self.default_confidence_threshold
        except (ValueError, TypeError):
            logger.warning(f"Invalid confidence threshold value: {getattr(self, 'confidence_threshold', 'None')}")
            return self.default_confidence_threshold
    
    def load_system_prompt(self):
        """Load chat rules from systemprompt.txt file if it exists"""
        # Read default (read-only) prompt first, if available
        default_prompt = None
        if os.path.exists(self.default_system_prompt_file):
            try:
                with open(self.default_system_prompt_file, 'r') as f:
                    default_prompt = f.read().strip()
                logger.info("Default system prompt loaded from defaultSystemprompt.txt")
            except Exception as e:
                logger.warning(f"Error loading default system prompt: {e}")

        # If there's a user override, load it; otherwise use the default or builtin
        if os.path.exists(self.system_prompt_file):
            try:
                with open(self.system_prompt_file, 'r') as f:
                    self.system_prompt = f.read().strip()
                logger.info("User system prompt loaded from systemprompt.txt")
            except Exception as e:
                logger.warning(f"Error loading user system prompt: {e}")
                if default_prompt is not None:
                    self.system_prompt = default_prompt
        else:
            if default_prompt is not None:
                self.system_prompt = default_prompt
            else:
                logger.info("No system prompt files found, using built-in default")
    
    def save_system_prompt(self, prompt_text):
        """Save chat rules to systemprompt.txt file"""
        try:
            with open(self.system_prompt_file, 'w') as f:
                f.write(prompt_text)
            self.system_prompt = prompt_text
            logger.info("System prompt saved to file")
        except Exception as e:
            logger.error(f"Error saving system prompt: {str(e)}")
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Warning",
                f"Could not save system prompt to file: {str(e)}"
            )
    
    def edit_system_prompt(self):
        """Open dialog to edit chat rules"""
        # Create a dialog for editing the chat rules
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("Edit Chat Rules")
        dialog.resize(600, 400)
        
        layout = QVBoxLayout()
        
        # Add label
        label = QLabel("Edit the system prompt that will be sent to the AI:")
        layout.addWidget(label)
        
        # Add text edit
        text_edit = QTextEdit()
        text_edit.setPlainText(self.system_prompt)
        layout.addWidget(text_edit)
        
        # Add buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        reset_button = QPushButton("Reset")
        cancel_button = QPushButton("Cancel")
        button_layout.addWidget(save_button)
        button_layout.addWidget(reset_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Connect buttons
        save_button.clicked.connect(dialog.accept)
        # Reset: replace the user's `systemprompt.txt` with the default prompt
        def on_reset():
            # Confirm with the user
            resp = QMessageBox.question(
                self.iface.mainWindow(),
                "Reset System Prompt",
                "Reset will replace your custom system prompt with the original default. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return

            # Load default prompt
            if not os.path.exists(self.default_system_prompt_file):
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Warning",
                    "Default system prompt file not found. Cannot reset."
                )
                return

            try:
                with open(self.default_system_prompt_file, 'r') as df:
                    default_text = df.read()
                # Overwrite or create the user override file
                with open(self.system_prompt_file, 'w') as uf:
                    uf.write(default_text)
                # Update the editor
                text_edit.setPlainText(default_text)
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Reset",
                    "System prompt has been reset to the default."
                )
            except Exception as e:
                logger.error(f"Error resetting system prompt: {e}")
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Error",
                    f"Could not reset system prompt: {e}"
                )

        reset_button.clicked.connect(on_reset)
        cancel_button.clicked.connect(dialog.reject)
        
        # Show dialog and handle result
        if dialog.exec_() == QDialog.Accepted:
            new_prompt = text_edit.toPlainText().strip()
            if new_prompt:
                self.save_system_prompt(new_prompt)
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Success",
                    "Chat rules have been updated."
                )
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Warning",
                    "Chat rules cannot be empty."
                )
    
    # Getters for configuration values
    def get_gemini_api_key(self):
        """Get the Gemini API key"""
        return self.gemini_api_key
    
    def get_gpt_api_key(self):
        """Get the GPT API key"""
        return self.gpt_api_key
    
    def get_system_prompt(self):
        """Get the system prompt"""
        return self.system_prompt
    
    def get_last_selected_model(self):
        """Get the last selected model"""
        return self.last_selected_model
    
    def set_last_selected_model(self, model):
        """Set the last selected model"""
        self.last_selected_model = model
        self.save_settings()
    
    def get_auto_clear_on_model_change(self):
        """Get the auto clear on model change setting"""
        return self.auto_clear_on_model_change
    
    def set_auto_clear_on_model_change(self, value):
        """Set the auto clear on model change setting"""
        self.auto_clear_on_model_change = value
        self.save_settings()
    
    def get_show_tutorial(self):
        """Get the show tutorial setting"""
        return self.show_tutorial
    
    def set_show_tutorial(self, value):
        """Set the show tutorial setting"""
        self.show_tutorial = value
        self.save_settings()
    
    def get_custom_analysis_directory(self):
        """Get the custom analysis directory"""
        return self.custom_analysis_directory
    
    def set_custom_analysis_directory(self, directory):
        """Set the custom analysis directory"""
        self.custom_analysis_directory = directory
        self.save_settings()
    
    def set_confidence_threshold(self, threshold):
        """Set the confidence threshold"""
        self.confidence_threshold = threshold
        self.save_settings()

    def get_layer_persistence_mode(self):
        """Get the layer persistence mode"""
        return self.layer_persistence_mode

    def set_layer_persistence_mode(self, mode):
        """Set the layer persistence mode

        Args:
            mode: One of 'auto_save', 'temporary', or 'prompt_on_close'
        """
        if mode in ['auto_save', 'temporary', 'prompt_on_close']:
            self.layer_persistence_mode = mode
            self.save_settings()
            logger.info(f"Layer persistence mode set to: {mode}")
        else:
            logger.warning(f"Invalid layer persistence mode: {mode}")
