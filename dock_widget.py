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

LandTalk Dock Widget Module

This module contains the LandTalkDockWidget class for the interactive chat interface.
"""

import os
import tempfile
import shutil
from datetime import datetime

from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QPushButton, QLabel, QLineEdit, QComboBox, QMenuBar, QMenu, 
    QAction, QSizePolicy, QFileDialog, QMessageBox, QApplication,
    QDialog, QScrollArea
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QPixmap, QPainter, QKeySequence, QIntValidator
try:
    from qgis.PyQt.QtWidgets import QShortcut
except ImportError:
    from qgis.PyQt.QtGui import QShortcut

from .logging import logger
from .tutorial_dialog import TutorialDialog


# Detect macOS for DPI scaling
import platform
IS_MACOS = platform.system() == 'Darwin'

# Font size multiplier for macOS high-DPI displays
FONT_SCALE = 1.4 if IS_MACOS else 1.0

def scale_font(base_size):
    """Scale font size based on platform"""
    return f"{int(base_size * FONT_SCALE)}pt"

# Style constants for consistent UI theming
class UIStyles:
    """Centralized UI styles for consistent theming"""
    
    # Button styles
    BUTTON_PRIMARY = f"""
        QPushButton {{
            background-color: #4285F4;
            color: white;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: {scale_font(9)};
        }}
        QPushButton:hover {{
            background-color: #3367D6;
        }}
        QPushButton:pressed {{
            background-color: #2E5AB8;
        }}
        QPushButton:disabled {{
            background-color: #cccccc;
            color: #666666;
        }}
    """
    
    BUTTON_SECONDARY = f"""
        QPushButton {{
            background-color: #dee2e6;
            color: #666;
            border: 2px solid #dee2e6;
            border-radius: 4px;
            padding: 4px 8px;
            font-weight: bold;
            font-size: {scale_font(10)};
        }}
        QPushButton:hover {{
            background-color: #d1d5db;
            border-color: #d1d5db;
        }}
        QPushButton:pressed {{
            background-color: #c4c9d0;
            border-color: #c4c9d0;
        }}
    """
    
    BUTTON_SMALL = f"""
        QPushButton {{
            background-color: #6c757d;
            color: white;
            border-radius: 4px;
            padding: 4px 8px;
            font-weight: bold;
            font-size: {scale_font(8)};
            margin: 2px;
        }}
        QPushButton:hover {{
            background-color: #5a6268;
        }}
        QPushButton:pressed {{
            background-color: #545b62;
        }}
    """
    
    # Input field styles
    COMBO_BOX = f"""
        QComboBox {{
            border: 2px solid #dee2e6;
            border-radius: 4px;
            padding: 4px 4px;
            font-size: {scale_font(8)};
            min-width: 60px;
            max-width: 120px;
            margin-left: 0;
            height: 25px;
        }}
        QComboBox:focus {{
            border-color: #4285F4;
        }}
        QComboBox QAbstractItemView {{
            min-width: 180px;
        }}
    """
    
    LINE_EDIT = f"""
        QLineEdit {{
            border: 2px solid #dee2e6;
            border-radius: 4px;
            padding: 4px 4px;
            font-size: {scale_font(8)};
            margin-left: 0;
            text-align: right;
        }}
        QLineEdit:focus {{
            border-color: #4285F4;
        }}
    """
    
    TEXT_EDIT = f"""
        QTextEdit {{
            border: 2px solid #dee2e6;
            border-radius: 4px;
            padding: 8px;
            font-size: {scale_font(9)};
            background-color: white;
        }}
        QTextEdit:focus {{
            border-color: #4285F4;
        }}
    """
    
    # Label styles
    LABEL_SMALL = f"font-size: {scale_font(8)}; font-weight: bold; color: #666;"
    LABEL_VALUE = f"font-size: {scale_font(8)}; color: #333;"
    LABEL_INPUT = f"color: #666; font-size: {scale_font(9)};"
    
    # Panel styles
    INFO_PANEL = """
        QWidget {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 8px;
        }
    """
    
    THUMBNAIL_LABEL = """
        QLabel {
            border: 2px solid #dee2e6;
            border-radius: 4px;
            background-color: white;
            padding: 4px;
        }
    """


class ImagePopupDialog(QDialog):
    """Popup dialog to display full-size image"""
    
    def __init__(self, parent=None):
        super(ImagePopupDialog, self).__init__(parent)
        self.setWindowTitle("Full Size Image")
        self.setModal(True)
        
        # Set minimum size and allow resizing
        self.setMinimumSize(400, 300)
        self.resize(800, 600)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Create scroll area for the image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Create label to hold the image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        
        # Set the image label as the scroll area's widget
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
        
        # Add close button
        close_button = QPushButton("Close")
        close_button.setMaximumWidth(100)
        close_button.clicked.connect(self.close)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
        """)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
    def show_image_from_file(self, image_path):
        """Show the image from file path"""
        if not image_path or not os.path.exists(image_path):
            logger.warning(f"Image file not found: {image_path}")
            return
            
        try:
            # Create QPixmap from file
            pixmap = QPixmap(image_path)
            
            if pixmap.isNull():
                logger.warning(f"Failed to load image from file: {image_path}")
                return
            
            # Set the pixmap to the label
            self.image_label.setPixmap(pixmap)
            
            # Resize dialog to fit image if it's smaller than current size
            image_size = pixmap.size()
            dialog_size = self.size()
            
            # Add some padding for the scrollbars and margins
            padding = 60
            optimal_width = min(image_size.width() + padding, 1200)  # Max width of 1200
            optimal_height = min(image_size.height() + padding, 800)  # Max height of 800
            
            # Only resize if the optimal size is smaller than current size
            if optimal_width < dialog_size.width() or optimal_height < dialog_size.height():
                self.resize(max(optimal_width, 400), max(optimal_height, 300))
            
            logger.info(f"Showing full-size image in popup: {image_size.width()}x{image_size.height()}")
            
        except Exception as e:
            logger.error(f"Error displaying image in popup: {str(e)}")


class LandTalkDockWidget(QDockWidget):
    """Dock widget for interactive chat conversation with LandTalk AI"""
    
    def __init__(self, parent=None):
        super(LandTalkDockWidget, self).__init__(parent)
        self.setWindowTitle("LandTalk.AI Analysis")
        
        # Store references for dynamic sizing
        self.menu_bar = None
        self.chat_display = None
        self.input_section_widget = None
        # Configure dock widget features (robust across PyQt5 and PyQt6)
        def _resolve_feature(owner, candidate_names):
            for name in candidate_names:
                if hasattr(owner, name):
                    return getattr(owner, name)
            # Fallback: fuzzy match by substring
            for attr in dir(owner):
                for name in candidate_names:
                    if name.lower() in attr.lower():
                        return getattr(owner, attr)
            return None

        feature_owners = [QDockWidget]
        feature_enum = getattr(QDockWidget, 'DockWidgetFeature', None)
        if feature_enum is not None:
            feature_owners.append(feature_enum)

        movable_feature = None
        floatable_feature = None
        closable_feature = None
        for owner in feature_owners:
            if movable_feature is None:
                movable_feature = _resolve_feature(owner, ['DockWidgetMovable', 'Movable'])
            if floatable_feature is None:
                floatable_feature = _resolve_feature(owner, ['DockWidgetFloatable', 'Floatable'])
            if closable_feature is None:
                closable_feature = _resolve_feature(owner, ['DockWidgetClosable', 'Closable'])

        # Combine all available features using the original feature objects
        features_list = []
        if movable_feature is not None:
            features_list.append(movable_feature)
        if floatable_feature is not None:
            features_list.append(floatable_feature)
        if closable_feature is not None:
            features_list.append(closable_feature)
        
        if features_list:
            # Combine features using bitwise OR
            combined_features = features_list[0]
            for feature in features_list[1:]:
                combined_features = combined_features | feature
            self.setFeatures(combined_features)
        # else: leave default features
        
        # Create the main widget and layout
        self.main_widget = QWidget()
        self.setWidget(self.main_widget)
        
        layout = QVBoxLayout(self.main_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        
        self.parent_plugin = None  # Will be set by the plugin
        self.chat_history = []  # Store chat conversation history
        self.last_selected_resolution_index = 2  # Default to 1.0 m/px (index 2)
        
        # Create a menu bar
        self.menu_bar = QMenuBar(self.main_widget)
        
        # Create options menu
        self.settings_menu = QMenu("Options", self.menu_bar)
        self.settings_menu.setToolTip("Options")
        
        # Create menu actions
        self.logging_action = QAction("Save Log File", self.main_widget)
        self.gemini_key_action = QAction("Set Gemini API Key", self.main_widget)
        self.gpt_key_action = QAction("Set GPT API Key", self.main_widget)
        
        # Connect actions to functions
        self.logging_action.triggered.connect(self.save_log_file)
        self.gemini_key_action.triggered.connect(lambda: self.parent_plugin.get_gemini_key() if self.parent_plugin else None)
        self.gpt_key_action.triggered.connect(lambda: self.parent_plugin.get_gpt_key() if self.parent_plugin else None)
        
        self.settings_menu.addAction(self.logging_action)
        self.settings_menu.addSeparator()
        self.settings_menu.addAction(self.gemini_key_action)
        self.settings_menu.addAction(self.gpt_key_action)
        
        # Create a prefs button with text
        self.prefs_button = QPushButton("Options")
        self.prefs_button.setMinimumWidth(80)
        self.prefs_button.setMaximumHeight(25)
        self.prefs_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.prefs_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: {scale_font(8)};
                margin-right: 6px;
                margin-left: 0;
            }}
            QPushButton:hover {{
                background-color: #5a6268;
            }}
            QPushButton:pressed {{
                background-color: #545b62;
            }}
        """)
        self.prefs_button.setToolTip("Options")
        self.prefs_button.setMenu(self.settings_menu)
        
        # Note: Options button will be added to the bottom button layout instead
        
        # Add AI model selection label and dropdown 
        self.ai_model_label = QLabel("AI Model:")
        self.ai_model_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-size: {scale_font(9)};
                margin-left: 4px;
                margin-right: 2px;
                padding: 2px 0px;
            }}
        """)
        
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.addItem("gemini-2.0-flash", "gemini-2.0-flash")
        self.ai_model_combo.addItem("gemini-2.5-flash-lite", "gemini-2.5-flash-lite")
        self.ai_model_combo.addItem("gemini-2.5-pro", "gemini-2.5-pro")
        self.ai_model_combo.addItem("gemini-2.5-flash (recommended)", "gemini-2.5-flash")
        self.ai_model_combo.addItem("gpt-5-mini (recommended)", "gpt5-mini")
        self.ai_model_combo.addItem("gpt-5-nano", "gpt-5-nano")
        self.ai_model_combo.addItem("gpt-5", "gpt5")
        self.ai_model_combo.addItem("gpt-4o-mini", "gpt-4o-mini")
        self.ai_model_combo.setCurrentIndex(3)  # Default to gemini-2.5-flash
        self.ai_model_combo.setStyleSheet(f"""
            QComboBox {{
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 4px 4px;
                font-size: {scale_font(9)};
                min-width: 140px;
                max-width: 220px;
            }}
            QComboBox:focus {{
                border-color: #4285F4;
            }}
            QComboBox QAbstractItemView {{
                min-width: 220px;
                font-size: {scale_font(9)};
            }}
        """)
        self.ai_model_combo.setToolTip("Select the AI model to use for analysis")

        
        # Add probability input field
        self.prob_label = QLabel("Conf. (%):")
        self.prob_label.setStyleSheet(f"""
            QLabel {{
                color: #666;
                font-size: {scale_font(9)};
                margin-left: 4px;
                margin-right: 2px;
                padding: 2px 0px;
            }}
        """)
        self.prob_label.setToolTip("Filter for features with confidence greater than this value (0-100)")
        
        self.prob_input = QLineEdit()
        self.prob_input.setText("0")
        self.prob_input.setMaximumWidth(50)
        self.prob_input.setToolTip("Filter for features with confidence greater than this value (0-100)")
        
        # Set up integer validator for 0-99 range
        prob_validator = QIntValidator(0, 99)
        self.prob_input.setValidator(prob_validator)
        
        self.prob_input.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 4px 4px;
                font-size: {scale_font(9)};
                margin-left: 0;
                text-align: right;
            }}
            QLineEdit:focus {{
                border-color: #4285F4;
            }}
        """)
        
        # Add rules button
        self.rules_button = QPushButton("Rules")
        self.rules_button.setMinimumWidth(80)
        self.rules_button.setMaximumHeight(25)
        self.rules_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.rules_button.setToolTip("Edit chat rules")
        self.rules_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: {scale_font(8)};
                margin-right: 6px;
                margin-left: 0;
            }}
            QPushButton:hover {{
                background-color: #5a6268;
            }}
            QPushButton:pressed {{
                background-color: #545b62;
            }}
        """)
        self.rules_button.clicked.connect(lambda: self.parent_plugin.edit_system_prompt() if self.parent_plugin else None)
        
        # Add tutorial button
        self.tutorial_button = QPushButton("Tutorial")
        self.tutorial_button.setMinimumWidth(80)
        self.tutorial_button.setMaximumHeight(25)
        self.tutorial_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.tutorial_button.setToolTip("Show tutorial")
        self.tutorial_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #6c757d;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: {scale_font(8)};
                margin-right: 6px;
                margin-left: 0;
            }}
            QPushButton:hover {{
                background-color: #5a6268;
            }}
            QPushButton:pressed {{
                background-color: #545b62;
            }}
        """)
        self.tutorial_button.clicked.connect(self.show_tutorial)
        
        
        # Add menu bar to layout (without corner widgets for macOS compatibility)
        layout.setMenuBar(self.menu_bar)
        
        # Create a dedicated controls row for AI model and confidence settings
        # This works better on macOS than menu bar corner widgets
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(8, 4, 8, 4)
        controls_layout.setSpacing(8)
        
        # Add AI model selection
        controls_layout.addWidget(self.ai_model_label)
        controls_layout.addWidget(self.ai_model_combo)
        
        # Add spacer
        controls_layout.addStretch()
        
        # Add confidence threshold controls
        controls_layout.addWidget(self.prob_label)
        controls_layout.addWidget(self.prob_input)
        
        # Set size policy for controls widget
        controls_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Add controls widget to main layout
        layout.addWidget(controls_widget)
        
        # Add area selection section between menu and chat
        self.area_selection_widget = QWidget()
        area_selection_layout = QVBoxLayout(self.area_selection_widget)
        area_selection_layout.setContentsMargins(8, 8, 8, 8)
        
        # Select Area button
        self.select_area_button = QPushButton("Select area")
        self.select_area_button.setMinimumHeight(28)
        self.select_area_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #4285F4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: {scale_font(11)};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #5294FF;
            }}
            QPushButton:pressed {{
                background-color: #3A76D8;
            }}
            QPushButton:disabled {{
                background-color: #6c757d;
                color: #dee2e6;
            }}
        """)
        self.select_area_button.clicked.connect(self.on_select_area_clicked)
        area_selection_layout.addWidget(self.select_area_button)
        
        # Thumbnail display area (initially hidden)
        self.thumbnail_widget = QWidget()
        self.thumbnail_widget.setVisible(False)
        thumbnail_layout = QVBoxLayout(self.thumbnail_widget)
        thumbnail_layout.setContentsMargins(0, 8, 0, 0)
        
        # Create horizontal layout for image and info panel
        thumbnail_horizontal_layout = QHBoxLayout()
        thumbnail_horizontal_layout.setSpacing(8)
        
        # Thumbnail image container
        self.thumbnail_image_label = QLabel()
        self.thumbnail_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_image_label.setStyleSheet("""
            QLabel {
                border: 2px solid #dee2e6;
                border-radius: 4px;
                background-color: #f8f9fa;
                padding: 4px;
                min-height: 64px;
                max-height: 96px;
                cursor: pointer;
            }
            QLabel:hover {
                border-color: #4285F4;
                background-color: #e3f2fd;
            }
        """)
        self.thumbnail_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Make thumbnail clickable
        self.thumbnail_image_label.mousePressEvent = self.on_thumbnail_clicked
        self.thumbnail_image_label.setToolTip("Click to view full-size image")
        
        # Create information panel for resolution and dimensions
        self.thumbnail_info_panel = QWidget()
        self.thumbnail_info_panel.setStyleSheet("""
            QWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: #f8f9fa;
                padding: 2px;
            }
        """)
        self.thumbnail_info_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.thumbnail_info_panel.setFixedWidth(120)
        
        info_layout = QVBoxLayout(self.thumbnail_info_panel)
        info_layout.setContentsMargins(4, 4, 4, 4)
        info_layout.setSpacing(2)
        
        # Ground resolution dropdown
        self.resolution_label = QLabel("Resolution:")
        self.resolution_label.setStyleSheet(f"font-size: {scale_font(9)}; font-weight: bold; color: #666;")
        
        # Create resolution dropdown
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("0.25 m/px", 0.25)
        self.resolution_combo.addItem("0.5 m/px", 0.5)
        self.resolution_combo.addItem("1.0 m/px", 1.0)
        self.resolution_combo.addItem("5.0 m/px", 5.0)
        self.resolution_combo.addItem("10.0 m/px", 10.0)
        self.resolution_combo.addItem("100.0 m/px", 100.0)
        self.resolution_combo.setCurrentIndex(2)  # Default to 1.0 m/px
        self.resolution_combo.setStyleSheet(f"""
            QComboBox {{
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {scale_font(9)};
                background-color: white;
                color: #333;
                min-width: 80px;
                max-width: 120px;
            }}
            QComboBox:focus {{
                border-color: #4285F4;
            }}
            QComboBox:hover {{
                border-color: #4285F4;
            }}
            QComboBox QAbstractItemView {{
                font-size: {scale_font(9)};
                min-width: 100px;
                background-color: white;
                border: 2px solid #dee2e6;
                border-radius: 4px;
                selection-background-color: #4285F4;
                selection-color: white;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                background-color: white;
                color: #333;
                min-height: 20px;
                border: none;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #f8f9fa;
                color: #333;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: #4285F4;
                color: white;
            }}
            QComboBox QAbstractItemView::item:selected:hover {{
                background-color: #4285F4;
                color: white;
            }}
        """)
        self.resolution_combo.setToolTip("Select ground resolution for dimension calculations")
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        
        # Width dimension label
        self.width_label = QLabel("Width:")
        self.width_label.setStyleSheet(f"font-size: {scale_font(9)}; font-weight: bold; color: #666;")
        self.width_value = QLabel("0 m")
        self.width_value.setStyleSheet(f"font-size: {scale_font(9)}; color: #333;")
        
        # Height dimension label
        self.height_label = QLabel("Height:")
        self.height_label.setStyleSheet(f"font-size: {scale_font(9)}; font-weight: bold; color: #666;")
        self.height_value = QLabel("0 m")
        self.height_value.setStyleSheet(f"font-size: {scale_font(9)}; color: #333;")
        
        # Add labels to info layout
        info_layout.addWidget(self.resolution_label)
        info_layout.addWidget(self.resolution_combo)
        info_layout.addWidget(self.width_label)
        info_layout.addWidget(self.width_value)
        info_layout.addWidget(self.height_label)
        info_layout.addWidget(self.height_value)
        info_layout.addStretch()
        
        # Add image and info panel to horizontal layout
        thumbnail_horizontal_layout.addWidget(self.thumbnail_image_label)
        thumbnail_horizontal_layout.addWidget(self.thumbnail_info_panel)
        
        thumbnail_layout.addLayout(thumbnail_horizontal_layout)
        
        area_selection_layout.addWidget(self.thumbnail_widget)
        
        # Set fixed height policy for area selection section
        self.area_selection_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.area_selection_widget.setMinimumWidth(200)
        layout.addWidget(self.area_selection_widget)
        
        # Chat history display (takes most of the space)
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(200)  # Minimum height for readability
        # Set size policy to expand in both directions to fill available space
        self.chat_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Remove any maximum height constraints to allow full expansion
        self.chat_display.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX
        
        # Enable horizontal scrollbar when needed
        self.chat_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if hasattr(Qt, 'ScrollBarPolicy') else 1)
        self.chat_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if hasattr(Qt, 'ScrollBarPolicy') else 1)
        
        # Enable word wrapping for normal readability, but horizontal scrollbar will appear
        # when content is genuinely too wide (like wide tables or code blocks)
        self.chat_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if hasattr(QTextEdit, 'LineWrapMode') else 1)
        
        self.chat_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: {scale_font(11)};
            }}
        """)
        layout.addWidget(self.chat_display)
        
        # Add initial welcome message
        self.add_system_message("Welcome! Click 'Select area' above to choose a map area.")
        
        # Input section at the bottom
        input_section = QVBoxLayout()
        
        # Create a widget to wrap the input section for size calculation
        self.input_section_widget = QWidget()
        self.input_section_widget.setLayout(input_section)
        # Set fixed size policy for input section to prevent resizing
        self.input_section_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # User input area
        input_label = QLabel("Your message (optional):")
        input_label.setStyleSheet(f"color: #666; font-size: {scale_font(10)};")
        # Ensure label has fixed size
        input_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        input_section.addWidget(input_label)
        
        # Create horizontal layout for text input and analyze button
        input_and_button_layout = QHBoxLayout()
        input_and_button_layout.setSpacing(8)
        
        self.prompt_text = QTextEdit()
        self.prompt_text.setMaximumHeight(50)  # Reduced for 2 lines
        self.prompt_text.setMinimumHeight(50)  # Reduced for 2 lines
        self.prompt_text.setToolTip("Type your message here and click 'Analyze' to send.")
        # Set expanding size policy for input text area
        self.prompt_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.prompt_text.setStyleSheet(f"""
            QTextEdit {{
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 6px;
                font-size: {scale_font(11)};
            }}
            QTextEdit:focus {{
                border-color: #4285F4;
            }}
        """)
        
        # Create and style the send button
        self.send_button = QPushButton("Analyze")
        self.send_button.setMinimumWidth(60)  # Reduced width
        self.send_button.setMaximumWidth(60)  # Set maximum width to match minimum
        self.send_button.setMaximumHeight(50)  # Match the text input height
        self.send_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #4285F4;
                color: white;
                border-radius: 4px;
                padding: 4px 4px;
                font-weight: bold;
                font-size: {scale_font(9)};
            }}
            QPushButton:hover {{
                background-color: #5294FF;
            }}
            QPushButton:pressed {{
                background-color: #3A76D8;
            }}
        """)
        self.send_button.clicked.connect(self.send_message_to_selected_ai)
        
        # Add text input and button to horizontal layout
        input_and_button_layout.addWidget(self.prompt_text)
        input_and_button_layout.addStretch()  # Add stretch to push button to the right
        input_and_button_layout.addWidget(self.send_button)
        input_section.addLayout(input_and_button_layout)
        
        # Add keyboard shortcut support for sending messages
        
        # Escape key to interrupt AI response
        escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        escape_shortcut.activated.connect(self.interrupt_ai_request)
        
        # Other buttons layout
        button_layout = QHBoxLayout()
        
        # Connect model selection change to auto-clear functionality
        self.ai_model_combo.currentTextChanged.connect(self.on_model_changed)
        
        button_layout.addWidget(self.tutorial_button)
        button_layout.addWidget(self.rules_button)
        button_layout.addWidget(self.prefs_button)
        button_layout.addStretch()
        input_section.addLayout(button_layout)
        
        layout.addWidget(self.input_section_widget)
    
    
    def on_select_area_clicked(self):
        """Handle the select area button click"""
        if self.parent_plugin:
            # Start the rectangle selection tool
            self.parent_plugin.start_rectangle_selection()
    
    def calculate_ground_dimensions(self):
        """Calculate real-world dimensions in meters from captured extent and ground resolution"""
        if not self.parent_plugin:
            logger.warning("No parent plugin available for dimension calculation")
            return None, None, None
            
        # Get the ground resolution from parent plugin
        ground_resolution = getattr(self.parent_plugin, 'ground_resolution_m_per_px', 1.0)
        
        # Get captured extent information from parent plugin
        extent_width = getattr(self.parent_plugin, 'captured_extent_width', None)
        extent_height = getattr(self.parent_plugin, 'captured_extent_height', None)
        
        logger.debug(f"Calculating dimensions - extent_width: {extent_width}, extent_height: {extent_height}, ground_resolution: {ground_resolution}")
        
        if extent_width is None or extent_height is None:
            logger.warning("No captured extent dimensions available for calculation")
            return None, None, ground_resolution
        
        # Calculate dimensions based on extent and ground resolution
        # The extent is in map units, but we need to convert to meters based on the map's CRS
        try:
            from qgis.core import QgsDistanceArea, QgsProject, QgsPointXY
            
            # Get the captured coordinates
            top_left_map = getattr(self.parent_plugin, 'captured_top_left_map', None)
            bottom_right_map = getattr(self.parent_plugin, 'captured_bottom_right_map', None)
            
            if top_left_map and bottom_right_map:
                # Use QgsDistanceArea to calculate real distances
                distance_calc = QgsDistanceArea()
                if hasattr(self.parent_plugin, 'map_canvas'):
                    distance_calc.setSourceCrs(
                        self.parent_plugin.map_canvas.mapSettings().destinationCrs(), 
                        QgsProject.instance().transformContext()
                    )
                    try:
                        distance_calc.setEllipsoid(QgsProject.instance().ellipsoid())
                    except Exception:
                        pass
                
                # Calculate width (horizontal distance)
                width_meters = distance_calc.measureLine(
                    QgsPointXY(top_left_map.x(), top_left_map.y()),
                    QgsPointXY(bottom_right_map.x(), top_left_map.y())
                )
                
                # Calculate height (vertical distance)
                height_meters = distance_calc.measureLine(
                    QgsPointXY(top_left_map.x(), top_left_map.y()),
                    QgsPointXY(top_left_map.x(), bottom_right_map.y())
                )
                
                logger.info(f"Calculated dimensions: {width_meters:.1f}m x {height_meters:.1f}m (resolution: {ground_resolution}m/px)")
                return width_meters, height_meters, ground_resolution
            else:
                logger.warning("No captured coordinates available for dimension calculation")
                return None, None, ground_resolution
                
        except Exception as e:
            logger.error(f"Error calculating ground dimensions: {str(e)}")
            return None, None, ground_resolution

    def update_thumbnail_display(self, pixmap):
        """Update the thumbnail display with a new pixmap"""
        if pixmap and not pixmap.isNull():
            # Calculate display dimensions while preserving aspect ratio
            # Use the actual pixmap aspect ratio to determine optimal display size
            pixmap_aspect_ratio = pixmap.width() / pixmap.height() if pixmap.height() > 0 else 1.0
            
            # Maximum display dimensions (slightly smaller than original fixed size)
            max_display_width = 120
            max_display_height = 80
            
            # Scale to fit within max dimensions while preserving aspect ratio
            if pixmap_aspect_ratio >= (max_display_width / max_display_height):
                # Pixmap is wider, constrain by width
                display_width = max_display_width
                display_height = int(max_display_width / pixmap_aspect_ratio)
            else:
                # Pixmap is taller, constrain by height  
                display_height = max_display_height
                display_width = int(max_display_height * pixmap_aspect_ratio)
            
            # Scale the pixmap to calculated dimensions
            scaled_pixmap = pixmap.scaled(
                display_width, display_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Create a framed version
            frame_width = 2
            framed_pixmap = QPixmap(
                scaled_pixmap.width() + 2 * frame_width,
                scaled_pixmap.height() + 2 * frame_width
            )
            framed_pixmap.fill(Qt.GlobalColor.black)
            
            painter = QPainter(framed_pixmap)
            painter.drawPixmap(frame_width, frame_width, scaled_pixmap)
            painter.end()
            
            # Set the pixmap and show the thumbnail widget
            self.thumbnail_image_label.setPixmap(framed_pixmap)
            
            self.thumbnail_widget.setVisible(True)
        else:
            # Hide the thumbnail widget if no valid pixmap
            self.thumbnail_widget.setVisible(False)
    
    def update_thumbnail_info(self):
        """Update the information panel with current ground resolution and dimensions"""
        try:
            # Calculate ground dimensions
            width_meters, height_meters, ground_resolution = self.calculate_ground_dimensions()
            
            # Update resolution dropdown to match current resolution
            if ground_resolution and hasattr(self, 'resolution_combo'):
                # Find the closest matching resolution in the dropdown
                resolutions = [0.25, 0.5, 1.0, 5.0, 10.0, 100.0]
                closest_index = 0
                min_diff = abs(ground_resolution - resolutions[0])
                
                for i, res in enumerate(resolutions):
                    diff = abs(ground_resolution - res)
                    if diff < min_diff:
                        min_diff = diff
                        closest_index = i
                
                # Only update if the current selection doesn't match
                if self.resolution_combo.currentIndex() != closest_index:
                    self.resolution_combo.setCurrentIndex(closest_index)
            
            # Update width display
            if width_meters is not None:
                if width_meters >= 1000:
                    width_text = f"{width_meters/1000:.1f} km"
                elif width_meters >= 10:
                    width_text = f"{width_meters:.0f} m"
                else:
                    width_text = f"{width_meters:.1f} m"
                self.width_value.setText(width_text)
            else:
                self.width_value.setText("Unknown")
            
            # Update height display
            if height_meters is not None:
                if height_meters >= 1000:
                    height_text = f"{height_meters/1000:.1f} km"
                elif height_meters >= 10:
                    height_text = f"{height_meters:.0f} m"
                else:
                    height_text = f"{height_meters:.1f} m"
                self.height_value.setText(height_text)
            else:
                self.height_value.setText("Unknown")
                
            logger.debug(f"Updated thumbnail info - Resolution: {ground_resolution:.2f} m/px, Width: {width_text if width_meters else 'Unknown'}, Height: {height_text if height_meters else 'Unknown'}")
            
        except Exception as e:
            logger.error(f"Error updating thumbnail info: {str(e)}")
            # Set default values on error but preserve resolution selection
            if hasattr(self, 'resolution_combo'):
                self.resolution_combo.setCurrentIndex(self.last_selected_resolution_index)
            self.width_value.setText("Error")
            self.height_value.setText("Error")
        
    def clear_thumbnail_display(self):
        """Clear the thumbnail display and hide it"""
        self.thumbnail_image_label.clear()
        # Reset information panel to default values but preserve resolution selection
        if hasattr(self, 'resolution_combo'):
            # Keep the last selected resolution instead of resetting to default
            self.resolution_combo.setCurrentIndex(self.last_selected_resolution_index)
        self.width_value.setText("0 m")
        self.height_value.setText("0 m")
        self.thumbnail_widget.setVisible(False)
    
    def on_thumbnail_clicked(self, event):
        """Handle thumbnail click to show full-size image popup"""
        try:
            # Get the path to gemini_map_image.png
            image_path = os.path.join(tempfile.gettempdir(), "gemini_map_image.png")
            
            if os.path.exists(image_path):
                # Create and show the popup dialog
                popup = ImagePopupDialog(self)
                popup.show_image_from_file(image_path)
                popup.exec()
            else:
                logger.warning(f"Image file not found: {image_path}")
                QMessageBox.information(
                    self,
                    "No Image Available",
                    "No image file is available. Please select a new area first."
                )
        except Exception as e:
            logger.error(f"Error showing image popup: {str(e)}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to display full-size image: {str(e)}"
            )
        
    def send_message_to_selected_ai(self):
        """Send message to the currently selected AI model"""
        if not self.parent_plugin:
            return
        
        # Get prompt text from UI and validate
        prompt_text = self.prompt_text.toPlainText().strip()
        
        # Debug: log the text being processed
        logger.info(f"send_message_to_selected_ai: prompt_text = '{prompt_text}' (length: {len(prompt_text)})")
        
        # Check if the text is empty or contains only whitespace/newlines
        if not prompt_text or prompt_text.isspace():
            logger.info(f"send_message_to_selected_ai: Text is empty, setting to default 'analyze this image'")
            prompt_text = "analyze this image"
            # Update the input field to show the default text
            self.prompt_text.setPlainText(prompt_text)
                
        # Get the selected AI model from the dropdown
        selected_model = self.ai_model_combo.currentData()
        
        # Route to the unified AI analysis function
        self.parent_plugin.analyze_with_ai_ui(selected_model)
    
    def interrupt_ai_request(self):
        """Interrupt the current AI request when Escape is pressed"""
        if not self.parent_plugin:
            return
        
        logger.info("Escape key pressed - interrupting AI request")
        
        # Interrupt the current request in the genai handler
        if hasattr(self.parent_plugin, 'genai_handler'):
            # Check if the interrupt method exists (for backward compatibility)
            if hasattr(self.parent_plugin.genai_handler, 'interrupt_request'):
                self.parent_plugin.genai_handler.interrupt_request()
            else:
                logger.warning("GenAI handler does not support interruption - plugin may need to be restarted")
        
        # Clean up the AI worker if it's running
        if hasattr(self.parent_plugin, 'ai_worker') and self.parent_plugin.ai_worker:
            if self.parent_plugin.ai_worker.isRunning():
                logger.info("Terminating AI worker thread")
                self.parent_plugin.ai_worker.terminate()
                self.parent_plugin.ai_worker.wait()
                self.parent_plugin.ai_worker = None
        
        # Add a system message to the chat
        self.add_system_message("Request interrupted by user (Escape key pressed)")
        
        # Re-enable the UI
        self.setEnabled(True)
        QApplication.restoreOverrideCursor()
        
        # Re-enable the send button
        if hasattr(self, 'send_button'):
            self.send_button.setEnabled(True)
    
    def _add_chat_message(self, message, message_type, sender_name):
        """Add a message to the chat display with specified styling"""
        current_text = self.chat_display.toHtml()
        
        # Define styling based on message type
        styles = {
            'system': {
                'margin': '4px 0',
                'padding': '4px',
                'bg_color': '#e3f2fd',
                'border_color': '#2196f3',
                'text_color': '#1976d2',
                'border_width': '4px'
            },
            'user': {
                'margin': '2px 0',
                'padding': '2px',
                'bg_color': '#f3e5f5',
                'border_color': '#9c27b0',
                'text_color': '#7b1fa2',
                'border_width': '2px'
            }
        }
        
        style = styles.get(message_type, styles['user'])
        
        formatted_message = f"""
        <div style="margin: {style['margin']}; padding: {style['padding']}; background-color: {style['bg_color']}; border-left: {style['border_width']} solid {style['border_color']}; border-radius: 4px;">
            <strong style="color: {style['text_color']};">{sender_name}:</strong> {message}
        </div>
        """
        self.chat_display.setHtml(current_text + formatted_message)
        # Move cursor to end and scroll to bottom
        self.chat_display.ensureCursorVisible()
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def add_system_message(self, message):
        """Add a system message to the chat display"""
        self._add_chat_message(message, 'system', 'System')
    
    def add_user_message(self, message):
        """Add a user message to the chat display"""
        self._add_chat_message(message, 'user', 'You')
    
    def show_tutorial(self):
        """Show the tutorial dialog"""
        try:
            tutorial_dialog = TutorialDialog(self)
            result = tutorial_dialog.exec()
            
            # Check if user wants to show tutorial again
            if not tutorial_dialog.should_show_again():
                # Update parent plugin settings to not show tutorial again
                if self.parent_plugin:
                    self.parent_plugin.show_tutorial = False
                    self.parent_plugin.save_settings()
                    logger.info("Tutorial disabled - will not show again")
            
        except Exception as e:
            logger.error(f"Error showing tutorial: {str(e)}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to show tutorial: {str(e)}"
            )
    
    
    def json_to_bullet_points(self, json_data, bg_color="#f8f9fa"):
        """Convert JSON data to HTML format reflecting layer names"""
        if isinstance(json_data, list):
            # Handle array of objects (common for multiple detections)
            if not json_data:
                return f"<div style='color: #000000; background-color: {bg_color}; padding: 8px; border-radius: 4px;'>No items found</div>"
            
            html = "<div>"
            for i, item in enumerate(json_data):
                if isinstance(item, dict):
                    # Extract the relevant fields using the same logic as process_json_and_create_layers
                    detection_num = i + 1
                    object_type = None
                    probability = None
                    reason = None
                    
                    # Try different common field names for object type
                    for type_field in ['object_type', 'Object Type']:
                        if type_field in item:
                            object_type = str(item[type_field])
                            break
                    
                    if not object_type:
                        object_type = 'Unknown'
                    
                    # Try different common field names for probability/confidence
                    for prob_field in ['probability', 'confidence', 'confidence_score', 'Confidence Score', 'prob', 'score']:
                        if prob_field in item:
                            try:
                                prob_value = item[prob_field]
                                if isinstance(prob_value, (int, float)):
                                    probability = float(prob_value)
                                elif isinstance(prob_value, str):
                                    # Handle percentage strings like "85%" or "0.85"
                                    prob_str = prob_value.replace('%', '').strip()
                                    probability = float(prob_str)
                                    # If value is between 0 and 1, convert to percentage
                                    if probability <= 1.0:
                                        probability *= 100
                                break
                            except (ValueError, TypeError):
                                continue
                    
                    # Try different common field names for reason
                    for reason_field in ['reason', 'Reason', 'explanation', 'Explanation', 'description', 'Description']:
                        if reason_field in item:
                            reason = str(item[reason_field])
                            break
                    
                    # Format: (detection number) Object Type (percentage)
                    percentage = f"{probability:.0f}%" if isinstance(probability, (int, float)) else "0%"
                    html += f"<div style='margin-bottom: 8px; color: #000000; background-color: {bg_color}; padding: 8px; border-radius: 4px;'><strong>({detection_num}) {object_type} ({percentage})</strong>"
                    
                    # Add reason on new line if present
                    if reason:
                        html += f"<br>{reason}"
                    
                    html += "</div>"
                else:
                    html += f"<div style='color: #000000; background-color: {bg_color}; padding: 8px; border-radius: 4px;'>{self.format_value(item)}</div>"
            html += "</div>"
            return html
            
        elif isinstance(json_data, dict):
            # Handle single object - format as single detection
            detection_num = 1
            object_type = None
            probability = None
            reason = None
            
            # Try different common field names for object type
            for type_field in ['object_type', 'Object Type']:
                if type_field in json_data:
                    object_type = str(json_data[type_field])
                    break
            
            if not object_type:
                object_type = 'Unknown'
            
            # Try different common field names for probability/confidence
            for prob_field in ['probability', 'confidence', 'confidence_score', 'Confidence Score', 'prob', 'score']:
                if prob_field in json_data:
                    try:
                        prob_value = json_data[prob_field]
                        if isinstance(prob_value, (int, float)):
                            probability = float(prob_value)
                        elif isinstance(prob_value, str):
                            # Handle percentage strings like "85%" or "0.85"
                            prob_str = prob_value.replace('%', '').strip()
                            probability = float(prob_str)
                            # If value is between 0 and 1, convert to percentage
                            if probability <= 1.0:
                                probability *= 100
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Try different common field names for reason
            for reason_field in ['reason', 'Reason', 'explanation', 'Explanation', 'description', 'Description']:
                if reason_field in json_data:
                    reason = str(json_data[reason_field])
                    break
            
            # Format: (detection number) Object Type (percentage)
            percentage = f"{probability:.0f}%" if isinstance(probability, (int, float)) else "0%"
            html = f"<div style='color: #000000; background-color: {bg_color}; padding: 8px; border-radius: 4px;'><strong>({detection_num}) {object_type} ({percentage})</strong>"
            
            # Add reason on new line if present
            if reason:
                html += f"<br>{reason}"
            
            html += "</div>"
            return html
        else:
            return str(json_data)
    
    def format_value(self, value):
        """Format individual values for display"""
        if isinstance(value, list):
            if all(isinstance(x, (int, float)) for x in value):
                # Format coordinate arrays nicely
                return f"[{', '.join(map(str, value))}]"
            else:
                return f"[{', '.join(map(str, value))}]"
        elif isinstance(value, float):
            return f"{value:.2f}"
        else:
            return str(value)
    

    def add_ai_message(self, message, ai_provider, json_data=None):
        """Add an AI response message to the chat display"""
        current_text = self.chat_display.toHtml()
        
        # Choose color based on AI provider (handle None case)
        if ai_provider and ai_provider.lower() == 'gemini':
            bg_color = "#e8f5e8"
            border_color = "#4caf50"
            text_color = "#388e3c"
            provider_name = "Gemini"
        else:  # GPT or unknown/None
            bg_color = "#ffebee"
            border_color = "#f44336"
            text_color = "#d32f2f"
            provider_name = "GPT" if ai_provider else "Unknown"
        
        # If JSON data is provided, show only the structured data
        if json_data:
            if isinstance(json_data, (dict, list)):
                json_formatted = self.json_to_bullet_points(json_data, bg_color)
            else:
                json_formatted = str(json_data)
            formatted_message = json_formatted
        else:
            # Format message and handle line breaks for regular text
            formatted_message = message.replace('\n', '<br>')
        
        ai_message = f"""
        <div style="margin: 0; padding: 1em; background-color: {bg_color}; border-left: 4px solid {border_color}; border-radius: 4px;">
            <strong style="color: {text_color};">{provider_name}:</strong> {formatted_message}
        </div>
        """
        self.chat_display.setHtml(current_text + ai_message)
        # Move cursor to end and scroll to bottom
        self.chat_display.ensureCursorVisible()
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    
    def on_model_changed(self):
        """Handle AI model selection change - auto-clear chat if setting is enabled"""
        if hasattr(self, 'parent_plugin') and self.parent_plugin:
            # Save the selected model to settings
            selected_model = self.ai_model_combo.currentData()
            if selected_model and hasattr(self.parent_plugin, 'on_model_selection_changed'):
                self.parent_plugin.on_model_selection_changed(selected_model)
            
            # Ensure settings are loaded
            self.parent_plugin.ensure_settings_loaded()
            
            # Check if auto-clear is enabled
            if getattr(self.parent_plugin, 'auto_clear_on_model_change', True):
                # Only clear if there's existing chat history to avoid clearing on initialization
                if len(self.chat_history) > 0:
                    logger.info("AI model changed, auto-clearing chat history, UI contents, and rectangular selection")
                    # Clear the chat history and UI contents
                    self.chat_history = []
                    self.chat_display.clear()
                    # Clear the prompt text input field
                    self.prompt_text.clear()
                    # Clear the thumbnail display
                    self.clear_thumbnail_display()
                    # Ensure a fresh map image will be captured for the next chat
                    if hasattr(self, 'parent_plugin') and self.parent_plugin:
                        self.parent_plugin.captured_image_data = None
                    self.add_system_message("Click 'Select area' above to choose a new map area and start a new conversation. You can add type a message (optional) and click 'Analyze' to analyze this image.")
                    # Also clear the rectangular selection when model changes
                    self.parent_plugin.cleanup_selection()
    
    def save_log_file(self):
        """Open file dialog to save the current log file to a custom location"""
        try:
            # Get the current log file path from the logger
            from .logging import logger
            current_log_path = logger.get_log_file_path()   
            
            if not current_log_path or not os.path.exists(current_log_path):
                QMessageBox.warning(
                    self, 
                    "Log File Not Found", 
                    "No log file found to save. The log file will be created when the plugin starts logging."
                )
                return
            
            # Open file dialog to choose save location
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"gemini_plugin_log_{timestamp}.txt"
            
            # Use getSaveFileName for better compatibility
            selected_file, _ = QFileDialog.getSaveFileName(
                self,
                "Save Log File",
                default_filename,
                "Text Files (*.txt);;All Files (*)"
            )
            
            if selected_file:
                # Copy the log file to the selected location
                try:
                    shutil.copy2(current_log_path, selected_file)
                    QMessageBox.information(
                        self,
                        "Log File Saved",
                        f"Log file has been successfully saved to:\n{selected_file}"
                    )
                    logger.info(f"Log file saved to: {selected_file}")
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Save Error", 
                        f"Failed to save log file:\n{str(e)}"
                    )
                    logger.error(f"Failed to save log file: {str(e)}")
                    
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error", 
                f"An error occurred while saving the log file:\n{str(e)}"
            )
            logger.error(f"Error in save_log_file: {str(e)}")
    
    def get_chat_context(self):
        """Get the current chat history for API context"""
        return self.chat_history.copy()
    
    def add_to_chat_history(self, role, content, ai_provider=None):
        """Add a message to the chat history for API context"""
        message = {
            'role': role,  # 'user' or 'assistant' or 'system'
            'content': content
        }
        if ai_provider:
            message['ai_provider'] = ai_provider
        self.chat_history.append(message)
        
        # Keep history manageable (last 20 messages)
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]
    
    def on_resolution_changed(self, index):
        """Handle resolution dropdown change"""
        if not self.parent_plugin:
            return
            
        # Get the resolution value from the dropdown
        resolution_value = self.resolution_combo.currentData()
        if resolution_value is None:
            return
        
        # Save the selected resolution index for persistence
        self.last_selected_resolution_index = index
            
        # Update the parent plugin's ground resolution
        self.parent_plugin.ground_resolution_m_per_px = resolution_value
        
        # Update the map renderer's ground resolution as well
        if hasattr(self.parent_plugin, 'map_renderer'):
            self.parent_plugin.map_renderer.ground_resolution_m_per_px = resolution_value
        
        logger.info(f"Ground resolution changed to {resolution_value:.2f} m/pixel via dropdown")
        
        # Re-capture the image with the new resolution if there's a selected area
        if (hasattr(self.parent_plugin, 'selected_rectangle') and 
            self.parent_plugin.selected_rectangle and 
            self.thumbnail_widget.isVisible()):
            
            logger.info("Re-capturing image with new resolution")
            
            # Capture new high-resolution image with updated resolution first
            captured_image = self.parent_plugin.capture_map_image()
            if captured_image:
                logger.info("High-resolution image re-captured successfully with new resolution")
                
                # Now capture new thumbnail from the AI image for consistency
                thumbnail_pixmap = self.parent_plugin.capture_map_thumbnail()
                if thumbnail_pixmap:
                    self.update_thumbnail_display(thumbnail_pixmap)
                
                # Update the thumbnail info panel with the newly captured extent data
                self.update_thumbnail_info()
            else:
                logger.warning("Failed to re-capture high-resolution image with new resolution")
        else:
            # Just update the thumbnail info panel if no area is selected
            if self.thumbnail_widget.isVisible():
                self.update_thumbnail_info()
    
    def resizeEvent(self, event):
        """Handle resize event to adjust chat display height dynamically"""
        super(LandTalkDockWidget, self).resizeEvent(event)
        self.adjust_chat_display_height()
    
    def adjust_chat_display_height(self):
        """Adjust chat display height to ensure it uses maximum available space"""
        if not (self.chat_display and self.input_section_widget and self.menu_bar):
            return
            
        try:
            # Force layout update to get accurate size hints
            self.input_section_widget.updateGeometry()
            QApplication.processEvents()
            
            # Get actual heights of fixed elements
            menu_bar_height = self.menu_bar.sizeHint().height() if self.menu_bar.isVisible() else 0
            input_section_height = self.input_section_widget.sizeHint().height()
            
            logger.debug(f"Layout update - Menu bar: {menu_bar_height}px, Input section: {input_section_height}px")
            
            # The chat display will automatically expand to fill remaining space
            # due to its Expanding size policy, no manual height setting needed
            
        except Exception as e:
            logger.warning(f"Error adjusting chat display height: {str(e)}")
    
    def showEvent(self, event):
        """Handle show event to adjust initial sizing"""
        super(LandTalkDockWidget, self).showEvent(event)
        # Use QTimer to delay the size adjustment until the widget is fully shown
        QTimer.singleShot(100, self.adjust_chat_display_height)
    
    def closeEvent(self, event):
        """Handle close event to clean up resources"""
        if self.parent_plugin:
            self.parent_plugin.cleanup_selection()
        super(LandTalkDockWidget, self).closeEvent(event)
