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

LandTalk Tutorial Dialog Module

This module contains the tutorial dialog for first-time users.
"""

import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QLabel, QTabWidget, QWidget, QScrollArea, QCheckBox
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QPixmap, QIcon
from .logging import logger


class TutorialDialog(QDialog):
    """Tutorial dialog for first-time users with three sections"""
    
    def __init__(self, parent=None):
        super(TutorialDialog, self).__init__(parent)
        self.setWindowTitle("Welcome to LandTalk.AI")
        self.setModal(True)
        self.setMinimumSize(1000, 800)
        self.resize(1200, 900)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Welcome header
        self.create_welcome_header(layout)
        
        # Create tab widget for tutorials
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tutorial sections
        self.create_getting_started_tab()
        self.create_tips_tricks_tab()
        self.create_faq_tab()
        
        # Add bottom buttons
        self.create_bottom_buttons(layout)
        
        # Style the dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e9ecef;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #4285F4;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #d1d5db;
            }
            QPushButton {
                background-color: #4285F4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #3367D6;
            }
            QPushButton:pressed {
                background-color: #2E5AB8;
            }
            QPushButton#secondary {
                background-color: #6c757d;
            }
            QPushButton#secondary:hover {
                background-color: #5a6268;
            }
        """)
    
    def create_welcome_header(self, layout):
        """Create the welcome header section"""
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 20)
        
        # Title
        title_label = QLabel("Welcome to LandTalk.AI!")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4285F4; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel("Your Landscape Talks With You using AI")
        subtitle_label.setStyleSheet("color: #666; font-size: 12pt; margin-bottom: 15px;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle_label)
        
        # Description
        desc_label = QLabel(
            "This tutorial will help you get started with LandTalk.AI. "
            "Learn how to analyze map areas using AI and discover tips for better results."
        )
        desc_label.setStyleSheet("color: #333; font-size: 10pt; margin-bottom: 10px;")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(desc_label)
        
        layout.addWidget(header_widget)
    
    def create_getting_started_tab(self):
        """Create the Getting Started tutorial tab"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # Step 1: API Keys
        self.add_section_header(content_layout, "Step 1: Set Up Your API Keys", "1")
        self.add_text_content(content_layout, 
            "Before you can use LandTalk.AI, you need to register with Google Gemini and/or OpenAI and get an API key:<br><br>"
            "• <b>Google Gemini:</b> Visit <a href='https://makersuite.google.com/app/apikey'>Google AI Studio</a> to get your free API key<br>"
            "• <b>OpenAI GPT:</b> Visit <a href='https://platform.openai.com/api-keys'>OpenAI Platform</a> to get your API key<br><br>"
            "Once you have your key, click the <b>Options</b> button in the LandTalk.AI panel and select the appropriate key option to enter it.<br>"
            "Recommendation: try both AI providers to see which one works best for your use case."
        )
        
        # Step 2: Basic Workflow
        self.add_section_header(content_layout, "Step 2: Basic Workflow", "2")
        self.add_text_content(content_layout,
            "The basic workflow for using LandTalk.AI is simple:<br><br>"
            "1. <b>Select an area:</b> Click 'Select area' and draw a rectangle on your map<br>"
            "2. <b>Add a message (optional):</b> Explain in more detail what you want to analyze in the text box<br>"
            "3. <b>Choose AI model (optional):</b> Select from Gemini or GPT models in the dropdown<br>"
            "4. <b>Analyze:</b> Click 'Analyze' to send your request to the AI<br>"
            "5. <b>View results:</b> The AI will create map layers in a new group called 'LandTalk.ai' showing detected features"
        )
        
        # Step 3: Understanding Results
        self.add_section_header(content_layout, "Step 3: Understanding Results", "3")
        self.add_text_content(content_layout, 
            "When the AI analyzes your map area, it will:<br><br>"
            "• <b>Create map layers:</b> Each detected feature becomes a separate layer in the 'LandTalk.ai' group<br>"
            "• <b>Show confidence scores:</b> Each feature includes a confidence percentage (0-100)<br>"
            "• <b>Provide explanations:</b> The AI explains why it identified each feature<br>"
            "• <b>Display labels:</b> Feature names and confidence scores are shown on the map<br><br>"
            "You can adjust the confidence threshold to filter out low-confidence detections."
        )
        
        # Step 4: Tips for Better Results
        self.add_section_header(content_layout, "Step 4: Tips for Better Results", "4")
        self.add_text_content(content_layout,
            "To get the best results from LandTalk.AI:<br><br>"
            "• <b>Choose clear areas:</b> Select areas with distinct, visible features<br>"
            "• <b>Use appropriate resolution:</b> Higher resolution works better for detailed analysis<br>"
            "• <b>Be specific in prompts:</b> Ask for specific types of features or analysis<br>"
            "• <b>Try different models:</b> Gemini and GPT may give different results<br>"
            "• <b>Adjust confidence threshold:</b> Lower values show more features, higher values show only confident detections<br>"
            "• <b>Use the 'Rules' button:</b> Customize the AI's behavior to focus on specific features or analysis"
        )
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(tab_widget, "Getting Started")
    
    def create_tips_tricks_tab(self):
        """Create the Tips and Tricks tutorial tab"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # Editable Rules
        self.add_section_header(content_layout, "Customizing AI Behavior with Rules", "💡")
        self.add_text_content(content_layout,
            "One of LandTalk.AI's most powerful features is the ability to customize how the AI analyzes your maps:<br><br>"
            "• <b>Access Rules:</b> Click the 'Rules' button in the LandTalk.AI panel<br>"
            "• <b>Edit Instructions:</b> Modify the system prompt to change how the AI behaves<br>"
            "• <b>Specialize Analysis:</b> Add instructions for specific types of analysis (e.g., 'Focus on agricultural features')<br>"
            "• <b>Change Output Format:</b> Modify how the AI structures its responses<br>"
            "• <b>Add Context:</b> Include information about your specific use case or region<br><br>"
            "<b>Example customizations:</b><br>"
            "• 'Always identify building types and construction materials'<br>"
            "• 'Focus on environmental features like water bodies and vegetation'<br>"
            "• 'Provide detailed explanations for each detected feature'<br>"
            "• 'Use specific terminology for urban planning analysis'"
        )
        
        # Advanced Features
        self.add_section_header(content_layout, "Advanced Features", "⚙️")
        self.add_text_content(content_layout,
            "LandTalk.AI includes several advanced features to enhance your analysis:<br><br>"
            "• <b>Confidence Filtering:</b> Adjust the confidence threshold to show only high-confidence detections<br>"
            "• <b>Model Selection:</b> Choose between different AI models for different analysis types<br>"
            "• <b>Resolution Control:</b> Set the ground resolution for accurate measurements<br>"
            "• <b>Layer Management:</b> All results are organized in the 'LandTalk.ai' layer group<br>"
            "• <b>Conversation History:</b> Continue conversations about the same area for deeper analysis"
        )
        
        # Best Practices
        self.add_section_header(content_layout, "Best Practices", "⭐")
        self.add_text_content(content_layout,
            "Follow these best practices for optimal results:<br><br>"
            "• <b>Start Simple:</b> Begin with basic analysis before trying complex customizations<br>"
            "• <b>Iterate and Refine:</b> Use conversation history to refine your analysis<br>"
            "• <b>Test Different Areas:</b> Try the same analysis on different map areas to understand AI capabilities<br>"
            "• <b>Save Your Rules:</b> Keep a backup of your custom rules for future use<br>"
            "• <b>Combine Models:</b> Try both Gemini and GPT for different perspectives on the same area"
        )
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(tab_widget, "Tips & Tricks")
    
    def create_faq_tab(self):
        """Create the FAQ tutorial tab"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # FAQ Content
        faq_items = [
            {
                "question": "What types of features can LandTalk.AI detect?",
                "answer": "LandTalk.AI can detect a wide variety of landscape features including buildings, roads, water bodies, vegetation, agricultural areas, infrastructure, and more. The specific features depend on the AI model used and your custom rules."
            },
            {
                "question": "How accurate are the AI detections?",
                "answer": "Accuracy varies depending on image quality, feature clarity, and AI model. Each detection includes a confidence score. You can adjust the confidence threshold to show only high-confidence detections."
            },
            {
                "question": "Can I use both Gemini and GPT models?",
                "answer": "Yes! You can switch between different AI models using the dropdown menu. Each model may provide different insights and detection capabilities."
            },
            {
                "question": "How do I get better results?",
                "answer": "For better results: select clear, well-defined areas; use appropriate resolution settings; be specific in your prompts; try different AI models; and customize the rules for your specific use case."
            },
            {
                "question": "What if the AI doesn't detect what I'm looking for?",
                "answer": "Try adjusting your prompt to be more specific, lower the confidence threshold, try a different AI model, or customize the rules to focus on the features you're interested in."
            },
            {
                "question": "Can I save my analysis results?",
                "answer": "Yes! All analysis results are saved as GeoPackage files in the 'LandTalk.AI analysis' directory next to your QGIS project file. The layers are also added to your QGIS project."
            },
            {
                "question": "How do I customize the AI behavior?",
                "answer": "Click the 'Rules' button to edit the system prompt. This allows you to customize how the AI analyzes your maps, what features to focus on, and how to structure the output."
            },
            {
                "question": "What if I get an API key error?",
                "answer": "Make sure you've entered a valid API key in the Options menu. Check that your API key has the necessary permissions and that you have sufficient credits/quota remaining."
            },
            {
                "question": "Can I analyze the same area multiple times?",
                "answer": "Yes! You can continue conversations about the same area by adding new messages. The AI will remember the previous context and build upon it."
            },
            {
                "question": "How do I remove old analysis results?",
                "answer": "You can delete individual layers from the 'LandTalk.ai' group in QGIS, or delete the entire group to remove all analysis results. The files in the analysis directory can also be deleted manually."
            }
        ]
        
        for i, faq in enumerate(faq_items, 1):
            self.add_faq_item(content_layout, f"Q{i}: {faq['question']}", faq['answer'])
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(tab_widget, "FAQ")
    
    def add_section_header(self, layout, title, icon):
        """Add a section header with icon"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 20, 0, 15)
        
        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18pt; color: #4285F4; margin-right: 12px;")
        icon_label.setFixedWidth(35)
        header_layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #333; margin-bottom: 5px;")
        title_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        layout.addWidget(header_widget)
    
    def add_text_content(self, layout, text):
        """Add formatted text content"""
        text_widget = QTextEdit()
        text_widget.setHtml(text)
        text_widget.setReadOnly(True)
        text_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_widget.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 15px;
                font-size: 11pt;
                line-height: 1.5;
            }
        """)
        
        # Calculate the required height based on content
        # First, we need to ensure the widget is properly sized to get accurate measurements
        text_widget.setMinimumHeight(0)
        text_widget.setMaximumHeight(16777215)  # Reset max height temporarily
        
        # Force a layout update to get proper document size
        text_widget.document().setTextWidth(text_widget.viewport().width())
        
        # Get the document height
        doc_height = text_widget.document().size().height()
        
        # Add padding for borders and margins (15px top + 15px bottom + some extra)
        content_height = int(doc_height) + 50  # Increased padding for better spacing
        min_height = 100  # Reduced minimum height
        max_height = 800  # Increased maximum height for longer content
        
        # Set the height within reasonable bounds
        final_height = max(min_height, min(content_height, max_height))
        text_widget.setFixedHeight(final_height)
        
        layout.addWidget(text_widget)
    
    def add_faq_item(self, layout, question, answer):
        """Add an FAQ item"""
        faq_widget = QWidget()
        faq_layout = QVBoxLayout(faq_widget)
        faq_layout.setContentsMargins(0, 15, 0, 15)
        
        # Question
        question_label = QLabel(question)
        question_label.setStyleSheet("font-weight: bold; color: #4285F4; font-size: 12pt; margin-bottom: 8px;")
        question_label.setWordWrap(True)
        faq_layout.addWidget(question_label)
        
        # Answer
        answer_label = QLabel(answer)
        answer_label.setStyleSheet("color: #333; font-size: 11pt; margin-left: 20px; line-height: 1.4;")
        answer_label.setWordWrap(True)
        
        # Calculate height based on content
        answer_label.setText(answer)  # Ensure text is set for size calculation
        answer_label.adjustSize()
        answer_height = answer_label.sizeHint().height()
        
        # Set reasonable height based on content
        min_answer_height = 40
        max_answer_height = 200
        final_answer_height = max(min_answer_height, min(answer_height + 20, max_answer_height))
        answer_label.setMinimumHeight(final_answer_height)
        
        faq_layout.addWidget(answer_label)
        layout.addWidget(faq_widget)
    
    def create_bottom_buttons(self, layout):
        """Create the bottom button section"""
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 20, 0, 0)
        
        # Don't show again checkbox
        self.dont_show_checkbox = QCheckBox("Don't show this tutorial again")
        self.dont_show_checkbox.setStyleSheet("color: #666; font-size: 10pt;")
        button_layout.addWidget(self.dont_show_checkbox)
        
        button_layout.addStretch()
        
        # Close button
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(100)
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_widget)
    
    def should_show_again(self):
        """Check if user wants to see tutorial again"""
        return not self.dont_show_checkbox.isChecked()
