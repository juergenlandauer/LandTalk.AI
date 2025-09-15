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

AI Worker Module for LandTalk Plugin

This module contains classes for handling asynchronous AI API calls and API key management.
"""

from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton
)
from .logging import logger


class AIWorker(QThread):
    """Worker thread for making AI API calls asynchronously"""
    
    # Signals for communication with main thread
    finished = pyqtSignal(dict)  # Emits the result when AI call completes
    error = pyqtSignal(str)      # Emits error messages
    progress = pyqtSignal(str)   # Emits progress updates
    
    def __init__(self, genai_handler, prompt_text, chat_context, model, api_key, image_data, system_prompt):
        super().__init__()
        self.genai_handler = genai_handler
        self.prompt_text = prompt_text
        self.chat_context = chat_context
        self.model = model
        self.api_key = api_key
        self.image_data = image_data
        self.system_prompt = system_prompt
        
    def run(self):
        """Execute the AI API call in the background thread"""
        try:
            self.progress.emit("Sending request to AI...")
            
            # Make the AI API call
            result = self.genai_handler.analyze_with_ai(
                self.prompt_text, 
                self.chat_context, 
                self.model, 
                self.api_key, 
                self.image_data, 
                self.system_prompt
            )
            
            if result["success"]:
                self.progress.emit("AI response received, processing...")
            else:
                self.progress.emit("AI request failed")
                
            # Emit the result
            self.finished.emit(result)
            
        except Exception as e:
            logger.error(f"Error in AI worker thread: {str(e)}")
            self.error.emit(f"Unexpected error: {str(e)}")


class ApiKeyDialog(QDialog):
    """Custom dialog for API key input with embedded setup instructions"""
    
    def __init__(self, parent, title, api_type, current_key=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        layout = QVBoxLayout()
        
        # Create instructions based on API type
        if api_type.lower() == "gemini":
            instructions = self._get_gemini_instructions()
        else:  # OpenAI/GPT
            instructions = self._get_openai_instructions()
        
        # Create instructions label
        instructions_label = QLabel(instructions)
        instructions_label.setWordWrap(True)
        instructions_label.setOpenExternalLinks(True)  # This makes links clickable
        instructions_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                margin: 2px 0;
            }
        """)
        layout.addWidget(instructions_label)
        
        # Create input field
        input_label = QLabel("Enter your API Key:")
        input_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        layout.addWidget(input_label)
        
        self.input_field = QLineEdit()
        self.input_field.setText(current_key)
        self.input_field.setEchoMode(QLineEdit.EchoMode.Normal)  # Show the key normally
        self.input_field.setStyleSheet("""
            QLineEdit {
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 6px;
                font-size: 10pt;
            }
            QLineEdit:focus {
                border-color: #4285F4;
            }
        """)
        layout.addWidget(self.input_field)
        
        # Create buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #4285F4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #3367d6;
            }
            QPushButton:pressed {
                background-color: #2c5aa0;
            }
        """)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
        """)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to input field
        self.input_field.setFocus()
        
    def _get_gemini_instructions(self):
        """Get Gemini API key setup instructions"""
        return """
        <h3 style="color: #333; margin-top: 0;">Google Gemini API Key Setup</h3>
        <p>To access Gemini, you need to provide your Google Gemini API key. Follow these steps:</p>
        
        <div style="background-color: #e8f0fe; padding: 10px; border-radius: 5px; border-left: 4px solid #4285f4; margin: 5px 0;">
            <strong>Setup Steps:</strong>
            <ol>
                <li>Register with Google (also works with your Gmail account)</li>
                <li>Login here and get your API key: <a href="https://aistudio.google.com/apikey" style="color: #4285f4;">https://aistudio.google.com/apikey</a></li>
                <li>Click <strong>Copy</strong>. This will place your private key in the clipboard.</li>
                <li>Paste the key in the field below.</li>
            </ol>
        </div>
        
        
        <p><strong>Additional Resources:</strong> <a href="https://github.com/google-gemini/gemini-api-cookbook/blob/main/quickstarts/Authentication.ipynb" style="color: #4285f4;">Authentication Guide</a></p>
        """
    
    def _get_openai_instructions(self):
        """Get OpenAI API key setup instructions"""
        return """
        <h3 style="color: #333; margin-top: 0;">OpenAI API Key Setup</h3>
        <p>To access GPT-4, you need to provide your OpenAI API key. Follow these steps:</p>
        
        <div style="background-color: #e8f0fe; padding: 10px; border-radius: 5px; border-left: 4px solid #007acc; margin: 5px 0;">
            <strong>Setup Steps:</strong>
            <ol>
                <li>Register with <a href="https://auth.openai.com/create-account" style="color: #007acc;">OpenAI</a></li>
                <li>Open your OpenAI Settings page. Click <strong>User API keys</strong> then <strong>Create new secret key</strong> to generate new token.</li>
                <li>Click <strong>Copy</strong>. This will place your private key in the clipboard.</li>
                <li>Paste the key in the field below.</li>
            </ol>
        </div>
        
        """
    
    def get_text(self):
        """Get the text from the input field"""
        return self.input_field.text()
