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
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from .logging import logger
from .domain_wizard_dialog import DomainWizardDialog
from .ai_worker import ApiKeyDialog
from .constants import PluginConstants


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

        # Wikidata response truncation limit (loaded from constants)
        self.wikidata_response_max_chars = PluginConstants.WIKIDATA_RESPONSE_MAX_CHARS

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
        """Load API keys from QSettings (with one-time migration from legacy keys.txt)"""
        settings = QSettings()

        # One-time migration from legacy keys.txt
        legacy_keys_file = os.path.join(self.plugin_dir, 'keys.txt')
        if os.path.exists(legacy_keys_file):
            try:
                with open(legacy_keys_file, 'r') as f:
                    keys_data = json.load(f)
                settings.setValue("LandTalkAI/gemini_api_key", keys_data.get('gemini', ''))
                settings.setValue("LandTalkAI/gpt_api_key", keys_data.get('gpt', ''))
                os.remove(legacy_keys_file)
                logger.info("API keys migrated from keys.txt to QSettings and legacy file removed")
            except Exception as e:
                logger.warning(f"Error migrating API keys from keys.txt: {str(e)}")

        self.gemini_api_key = settings.value("LandTalkAI/gemini_api_key", "", type=str)
        self.gpt_api_key = settings.value("LandTalkAI/gpt_api_key", "", type=str)
        logger.info("API keys loaded from QSettings")
    
    def save_keys(self):
        """Save API keys to QSettings"""
        try:
            settings = QSettings()
            settings.setValue("LandTalkAI/gemini_api_key", self.gemini_api_key)
            settings.setValue("LandTalkAI/gpt_api_key", self.gpt_api_key)
            logger.info("API keys saved to QSettings")
        except Exception as e:
            logger.error(f"Error saving API keys: {str(e)}")
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Warning",
                f"Could not save API keys: {str(e)}"
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
                    self.wikidata_response_max_chars = settings_data.get('wikidata_response_max_chars', PluginConstants.WIKIDATA_RESPONSE_MAX_CHARS)
                logger.info(f"Plugin settings loaded from file. Confidence threshold: {self.confidence_threshold}, Last model: {self.last_selected_model}, Layer persistence: {self.layer_persistence_mode}")
            except Exception as e:
                logger.warning(f"Error loading plugin settings: {str(e)}")
                self.confidence_threshold = self.default_confidence_threshold
                self.last_selected_model = ''  # No hard-coded default; UI determines default
                self.layer_persistence_mode = 'auto_save'
                self.wikidata_response_max_chars = PluginConstants.WIKIDATA_RESPONSE_MAX_CHARS
        else:
            logger.info("No settings file found, using default values")
            self.confidence_threshold = self.default_confidence_threshold
            self.last_selected_model = ''  # No hard-coded default; UI determines default
            self.layer_persistence_mode = 'auto_save'
            self.wikidata_response_max_chars = PluginConstants.WIKIDATA_RESPONSE_MAX_CHARS
    
    def save_settings(self):
        """Save plugin settings to settings.txt file"""
        try:
            settings_data = {
                'confidence_threshold': self.confidence_threshold,
                'custom_analysis_directory': self.custom_analysis_directory,
                'auto_clear_on_model_change': self.auto_clear_on_model_change,
                'last_selected_model': self.last_selected_model,
                'show_tutorial': self.show_tutorial,
                'layer_persistence_mode': self.layer_persistence_mode,
                'wikidata_response_max_chars': self.wikidata_response_max_chars
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
            self.gemini_api_key
        )

        if dialog.exec_() == QDialog.Accepted:
            self.gemini_api_key = dialog.get_text()
            self.save_keys()
            return True
        return False
    
    def get_gpt_key(self):
        """Get GPT API key from the user"""
        dialog = ApiKeyDialog(
            self.iface.mainWindow(),
            "GPT API Key",
            "openai",
            self.gpt_api_key
        )

        if dialog.exec_() == QDialog.Accepted:
            self.gpt_api_key = dialog.get_text()
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
        """Open Domain Wizard dialog to configure the AI system prompt."""
        dialog = DomainWizardDialog(
            parent=self.iface.mainWindow(),
            current_prompt=self.system_prompt,
            plugin_dir=self.plugin_dir,
        )
        if dialog.exec_() == QDialog.Accepted:
            new_prompt = dialog.get_prompt()
            if new_prompt:
                self.save_system_prompt(new_prompt)
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Success",
                    "Domain configuration saved."
                )
            else:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Warning",
                    "System prompt cannot be empty."
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

    def get_wikidata_response_max_chars(self):
        """Get the Wikidata response maximum character limit"""
        return self.wikidata_response_max_chars

    def set_wikidata_response_max_chars(self, max_chars):
        """Set the Wikidata response maximum character limit

        Args:
            max_chars: Maximum number of characters to include in response (default: 5000)
        """
        if isinstance(max_chars, int) and max_chars > 0:
            self.wikidata_response_max_chars = max_chars
            self.save_settings()
            logger.info(f"Wikidata response max chars set to: {max_chars}")
        else:
            logger.warning(f"Invalid wikidata_response_max_chars value: {max_chars}")
