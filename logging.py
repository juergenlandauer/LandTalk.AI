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

Logging module for QGIS Gemini Plugin

This module provides a centralized logging system that integrates with QGIS
standard logging functions and also writes to a file with timestamps.
"""

import os
import datetime
from typing import Optional
from qgis.core import QgsMessageLog, Qgis


class Logging:
    """
    Centralized logging class for the QGIS Gemini Plugin.
    
    This class encapsulates all logging functionality, providing methods to log
    messages at different levels using QGIS standard logging functions while
    also maintaining a persistent log file with timestamps.
    """
    
    def __init__(self, plugin_name: str = "GeminiPlugin", log_file: str = "logging.txt"):
        """
        Initialize the logging system.
        
        Args:
            plugin_name (str): Name of the plugin for QGIS logging
            log_file (str): Path to the log file (relative to plugin directory)
        """
        self.plugin_name = plugin_name
        self.log_file = log_file
        self.log_file_path = None
        self._log_file_initialized = False
        # Defer file creation until first log message to avoid startup delays
    
    def _ensure_log_file_exists(self):
        """Ensure the log file exists and is writable. Deletes existing log file upon initialization."""
        try:
            # Get the plugin directory
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            self.log_file_path = os.path.join(plugin_dir, self.log_file)
            
            # Delete existing log file if it exists
            if os.path.exists(self.log_file_path):
                os.remove(self.log_file_path)
            
            # Create a new log file
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                f.write(f"# {self.plugin_name} Log File\n")
                f.write(f"# Created: {datetime.datetime.now().isoformat()}\n\n")
        except Exception as e:
            # If we can't create the log file, we'll just log to QGIS
            QgsMessageLog.logMessage(
                f"Failed to create log file: {str(e)}", 
                self.plugin_name, 
                Qgis.Warning
            )
            self.log_file_path = None
    
    def _write_to_file(self, level: str, message: str):
        """
        Write a log entry to the file with timestamp.
        
        Args:
            level (str): Log level
            message (str): Log message
        """
        # Initialize log file on first write to avoid startup delays
        if not self._log_file_initialized:
            self._ensure_log_file_exists()
            self._log_file_initialized = True
            
        if self.log_file_path is None:
            return
            
        try:
            timestamp = datetime.datetime.now().isoformat()
            log_entry = f"[{timestamp}] [{level}] {message}\n"
            
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            # If we can't write to file, log the error to QGIS
            QgsMessageLog.logMessage(
                f"Failed to write to log file: {str(e)}", 
                self.plugin_name, 
                Qgis.Warning
            )
    
    def debug(self, message: str, tag: Optional[str] = None):
        """
        Log a debug message.
        
        Args:
            message (str): The message to log
            tag (str, optional): Additional tag for the message
        """
        full_message = f"[DEBUG] {message}"
        if tag:
            full_message = f"[{tag}] {full_message}"
        
        QgsMessageLog.logMessage(full_message, self.plugin_name, Qgis.Info)
        self._write_to_file("DEBUG", full_message)
    
    def info(self, message: str, tag: Optional[str] = None):
        """
        Log an info message.
        
        Args:
            message (str): The message to log
            tag (str, optional): Additional tag for the message
        """
        full_message = f"[INFO] {message}"
        if tag:
            full_message = f"[{tag}] {full_message}"
        
        QgsMessageLog.logMessage(full_message, self.plugin_name, Qgis.Info)
        self._write_to_file("INFO", full_message)
    
    def warning(self, message: str, tag: Optional[str] = None):
        """
        Log a warning message.
        
        Args:
            message (str): The message to log
            tag (str, optional): Additional tag for the message
        """
        full_message = f"[WARNING] {message}"
        if tag:
            full_message = f"[{tag}] {full_message}"
        
        QgsMessageLog.logMessage(full_message, self.plugin_name, Qgis.Warning)
        self._write_to_file("WARNING", full_message)
    
    def error(self, message: str, tag: Optional[str] = None):
        """
        Log an error message.
        
        Args:
            message (str): The message to log
            tag (str, optional): Additional tag for the message
        """
        full_message = f"[ERROR] {message}"
        if tag:
            full_message = f"[{tag}] {full_message}"
        
        QgsMessageLog.logMessage(full_message, self.plugin_name, Qgis.Critical)
        self._write_to_file("ERROR", full_message)
    
    def critical(self, message: str, tag: Optional[str] = None):
        """
        Log a critical message.
        
        Args:
            message (str): The message to log
            tag (str, optional): Additional tag for the message
        """
        full_message = f"[CRITICAL] {message}"
        if tag:
            full_message = f"[{tag}] {full_message}"
        
        QgsMessageLog.logMessage(full_message, self.plugin_name, Qgis.Critical)
        self._write_to_file("CRITICAL", full_message)
    
    def log(self, level: str, message: str, tag: Optional[str] = None):
        """
        Generic log method that accepts a level parameter.
        
        Args:
            level (str): Log level ('debug', 'info', 'warning', 'error', 'critical')
            message (str): The message to log
            tag (str, optional): Additional tag for the message
        """
        level = level.lower()
        if level == 'debug':
            self.debug(message, tag)
        elif level == 'info':
            self.info(message, tag)
        elif level == 'warning':
            self.warning(message, tag)
        elif level == 'error':
            self.error(message, tag)
        elif level == 'critical':
            self.critical(message, tag)
        else:
            self.info(f"[UNKNOWN_LEVEL:{level}] {message}", tag)
    
    
    def get_log_file_path(self) -> Optional[str]:
        """
        Get the path to the log file.
        
        Returns:
            str or None: Path to the log file, or None if file logging is disabled
        """
        return self.log_file_path
    


# Create a default logger instance for the plugin
logger = Logging()


