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
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QFont, QPixmap, QIcon, QDesktopServices, QTextDocument
from .logging import logger
from .i18n.tutorial_texts import *


class ClickableTextEdit(QTextEdit):
    """Custom QTextEdit that handles link clicks"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
    
    def mousePressEvent(self, event):
        """Handle mouse press events to detect link clicks"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Get the cursor at the click position
            cursor = self.cursorForPosition(event.pos())
            
            # Check if the cursor is over a link
            if cursor.charFormat().isAnchor():
                anchor = cursor.charFormat().anchorHref()
                if anchor:
                    QDesktopServices.openUrl(QUrl(anchor))
                    return
        
        super().mousePressEvent(event)


class TutorialDialog(QDialog):
    """Tutorial dialog for first-time users with three sections"""
    
    def __init__(self, parent=None):
        super(TutorialDialog, self).__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.setModal(True)
        self.setMinimumSize(800, 640)
        self.resize(960, 720)
        
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
        
        # Create horizontal layout for icon and text
        icon_text_layout = QHBoxLayout()
        icon_text_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add icon to the left
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(__file__), 'icons', 'LT.AI.png')
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            # Scale the icon to a reasonable size (64x64)
            scaled_pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(scaled_pixmap)
        else:
            # Fallback if icon not found
            icon_label.setText("LT.AI")
            icon_label.setStyleSheet("font-size: 24pt; font-weight: bold; color: #4285F4;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        icon_label.setFixedSize(80, 80)  # Reserve space for icon
        icon_text_layout.addWidget(icon_label)
        
        # Create vertical layout for text content
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(10, 0, 0, 0)
        
        # Title
        title_label = QLabel(WELCOME_TITLE)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4285F4; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        text_layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel(WELCOME_SUBTITLE)
        subtitle_label.setStyleSheet("color: #666; font-size: 12pt; margin-bottom: 15px;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        text_layout.addWidget(subtitle_label)
        
        # Description
        desc_label = QLabel(WELCOME_DESCRIPTION)
        desc_label.setStyleSheet("color: #333; font-size: 10pt; margin-bottom: 10px;")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        text_layout.addWidget(desc_label)
        
        # Add text layout to horizontal layout
        icon_text_layout.addLayout(text_layout)
        icon_text_layout.addStretch()  # Push content to the left
        
        # Add the horizontal layout to the main header layout
        header_layout.addLayout(icon_text_layout)
        
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
        
        # Single combined text content
        combined_content = GETTING_STARTED_CONTENT
        
        self.add_text_content(content_layout, combined_content)
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(tab_widget, TAB_GETTING_STARTED)
    
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
        
        # Single combined text content
        combined_content = TIPS_TRICKS_CONTENT
        
        self.add_text_content(content_layout, combined_content)
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(tab_widget, TAB_TIPS_TRICKS)
    
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
        
        # Single combined text content
        combined_content = FAQ_CONTENT
        
        self.add_text_content(content_layout, combined_content)
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(tab_widget, TAB_FAQ)
    
    
    def add_text_content(self, layout, text):
        """Add formatted text content with clickable links"""
        text_widget = ClickableTextEdit()
        text_widget.setHtml(text)
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
            QTextEdit a {
                color: #4285F4;
                text-decoration: underline;
            }
            QTextEdit a:hover {
                color: #3367D6;
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
    
    
    def create_bottom_buttons(self, layout):
        """Create the bottom button section"""
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 20, 0, 0)
        
        # Don't show again checkbox
        self.dont_show_checkbox = QCheckBox(DONT_SHOW_AGAIN_TEXT)
        self.dont_show_checkbox.setStyleSheet("color: #666; font-size: 10pt;")
        button_layout.addWidget(self.dont_show_checkbox)
        
        button_layout.addStretch()
        
        # Close button
        close_button = QPushButton(CLOSE_BUTTON_TEXT)
        close_button.setMinimumWidth(100)
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addWidget(button_widget)
    
    def should_show_again(self):
        """Check if user wants to see tutorial again"""
        return not self.dont_show_checkbox.isChecked()
