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
import base64
from datetime import datetime

from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QLineEdit, QComboBox, QMenuBar, QMenu,
    QAction, QSizePolicy, QFileDialog, QMessageBox, QApplication,
    QDialog, QScrollArea, QActionGroup
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QPixmap, QPainter, QKeySequence, QIntValidator
try:
    from qgis.PyQt.QtWidgets import QShortcut
except ImportError:
    from qgis.PyQt.QtGui import QShortcut

from .logging import logger
from .tutorial_dialog import TutorialDialog
from .platform_utils import IS_MACOS, scale_font, resolve_dock_widget_features
from .ui_styles import UIStyles
from .dimension_utils import calculate_ground_dimensions, format_dimension
from .constants import PluginConstants


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
        layout.setContentsMargins(2, 2, 2, 2)

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
        close_button.setStyleSheet(UIStyles.dialog_close_button())

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


class ExampleImagesDialog(QDialog):
    """Dialog to manage example images with thumbnails and delete functionality"""

    def __init__(self, parent=None):
        super(ExampleImagesDialog, self).__init__(parent)
        self.setWindowTitle("Example Images")
        self.setModal(True)
        self.setMinimumSize(500, 400)
        self.resize(600, 500)

        # Reference to parent dock widget to access uploaded_images
        self.parent_widget = parent

        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Add title label
        title_label = QLabel("Example Images")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        main_layout.addWidget(title_label)

        # Add description
        desc_label = QLabel("Add example images to help the AI understand what you're looking for. These images will be sent along with the map image.")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        main_layout.addWidget(desc_label)

        # Create scroll area for thumbnails
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(250)

        # Create widget to hold thumbnail grid
        self.thumbnails_widget = QWidget()
        self.thumbnails_layout = QVBoxLayout(self.thumbnails_widget)
        self.thumbnails_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.thumbnails_widget)
        main_layout.addWidget(self.scroll_area)

        # Create button layout
        button_layout = QHBoxLayout()

        # Add Images button
        self.add_button = QPushButton("Add Images...")
        self.add_button.setMinimumWidth(120)
        self.add_button.setStyleSheet(UIStyles.button_analyze())
        self.add_button.clicked.connect(self.on_add_images)

        # Delete All button
        self.delete_all_button = QPushButton("Delete All")
        self.delete_all_button.setMinimumWidth(100)
        self.delete_all_button.setStyleSheet(UIStyles.button_options())
        self.delete_all_button.clicked.connect(self.on_delete_all)

        # Close button
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(100)
        close_button.setStyleSheet(UIStyles.dialog_close_button())
        close_button.clicked.connect(self.accept)

        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.delete_all_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

        # Initial display of thumbnails
        self.refresh_thumbnails()

    def refresh_thumbnails(self):
        """Refresh the thumbnail display"""
        # Clear existing thumbnails
        for i in reversed(range(self.thumbnails_layout.count())):
            widget = self.thumbnails_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Check if we have any images
        if not self.parent_widget or not hasattr(self.parent_widget, 'uploaded_images') or not self.parent_widget.uploaded_images:
            # Show "no images" message
            no_images_label = QLabel("No example images added yet.\nClick 'Add Images...' to select images.")
            no_images_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_images_label.setStyleSheet("color: #999; font-size: 11pt; padding: 40px;")
            self.thumbnails_layout.addWidget(no_images_label)
            self.delete_all_button.setEnabled(False)
            return

        self.delete_all_button.setEnabled(True)

        # Display each uploaded image as a thumbnail with delete button
        for idx, (file_path, base64_data) in enumerate(self.parent_widget.uploaded_images):
            # Create container for each thumbnail
            thumbnail_container = QWidget()
            thumbnail_layout = QHBoxLayout(thumbnail_container)
            thumbnail_layout.setContentsMargins(5, 5, 5, 5)
            thumbnail_layout.setSpacing(10)

            # Create thumbnail image label
            thumbnail_label = QLabel()
            thumbnail_label.setFixedSize(100, 100)
            thumbnail_label.setStyleSheet("border: 2px solid #2196f3; border-radius: 4px; background-color: #f0f0f0;")
            thumbnail_label.setScaledContents(False)
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Load and scale the image
            try:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    thumbnail_label.setPixmap(scaled_pixmap)
            except Exception as e:
                logger.warning(f"Failed to load thumbnail for {file_path}: {str(e)}")

            # Create filename label
            filename = os.path.basename(file_path)
            filename_label = QLabel(filename)
            filename_label.setWordWrap(True)
            filename_label.setStyleSheet("font-size: 10pt;")

            # Create delete button
            delete_button = QPushButton("Delete")
            delete_button.setFixedWidth(80)
            delete_button.setStyleSheet(UIStyles.button_options())
            delete_button.setProperty("image_index", idx)
            delete_button.clicked.connect(lambda checked, index=idx: self.on_delete_image(index))

            # Add widgets to layout
            thumbnail_layout.addWidget(thumbnail_label)
            thumbnail_layout.addWidget(filename_label, 1)
            thumbnail_layout.addWidget(delete_button)

            # Add separator line
            separator = QWidget()
            separator.setFixedHeight(1)
            separator.setStyleSheet("background-color: #ccc;")

            self.thumbnails_layout.addWidget(thumbnail_container)
            self.thumbnails_layout.addWidget(separator)

    def on_add_images(self):
        """Handle add images button click"""
        try:
            file_dialog = QFileDialog(self)
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
            file_dialog.setNameFilter("Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif)")
            file_dialog.setWindowTitle("Select Example Images")

            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files and self.parent_widget:
                    # Load the images using parent widget's method
                    for file_path in selected_files:
                        # Read and encode the image
                        with open(file_path, 'rb') as image_file:
                            image_data = image_file.read()
                            base64_data = base64.b64encode(image_data).decode('utf-8')

                        # Store the image data
                        self.parent_widget.uploaded_images.append((file_path, base64_data))

                    logger.info(f"Added {len(selected_files)} example image(s)")
                    # Refresh the display
                    self.refresh_thumbnails()
        except Exception as e:
            logger.error(f"Error adding images: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to add images: {str(e)}")

    def on_delete_image(self, index):
        """Handle delete button click for a specific image"""
        try:
            if self.parent_widget and hasattr(self.parent_widget, 'uploaded_images'):
                if 0 <= index < len(self.parent_widget.uploaded_images):
                    # Remove the image at the specified index
                    deleted_file = self.parent_widget.uploaded_images[index][0]
                    del self.parent_widget.uploaded_images[index]
                    logger.info(f"Deleted example image: {os.path.basename(deleted_file)}")
                    # Refresh the display
                    self.refresh_thumbnails()
        except Exception as e:
            logger.error(f"Error deleting image: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to delete image: {str(e)}")

    def on_delete_all(self):
        """Handle delete all button click"""
        try:
            if self.parent_widget and hasattr(self.parent_widget, 'uploaded_images'):
                count = len(self.parent_widget.uploaded_images)
                if count > 0:
                    # Confirm deletion
                    reply = QMessageBox.question(
                        self,
                        "Delete All Images?",
                        f"Are you sure you want to delete all {count} example image(s)?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        self.parent_widget.uploaded_images = []
                        logger.info(f"Deleted all {count} example image(s)")
                        # Refresh the display
                        self.refresh_thumbnails()
        except Exception as e:
            logger.error(f"Error deleting all images: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to delete all images: {str(e)}")


class WikidataQNumberDialog(QDialog):
    """Dialog to input a Wikidata Q number"""

    def __init__(self, parent=None):
        super(WikidataQNumberDialog, self).__init__(parent)
        self.setWindowTitle("Enter Wikidata Q Number")
        self.setModal(True)
        self.setMinimumSize(350, 150)
        self.resize(400, 150)

        self.q_number = None

        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Add title label
        title_label = QLabel("Wikidata Q Number")
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        main_layout.addWidget(title_label)

        # Add description
        desc_label = QLabel("Enter a Wikidata Q number (e.g., Q100530634):")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)

        # Input field for Q number
        self.q_input = QLineEdit()
        self.q_input.setPlaceholderText("Q100530634")
        self.q_input.setStyleSheet("padding: 5px; font-size: 11pt;")
        main_layout.addWidget(self.q_input)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumWidth(80)
        cancel_button.setStyleSheet(UIStyles.dialog_close_button())
        cancel_button.clicked.connect(self.reject)

        # OK button
        ok_button = QPushButton("OK")
        ok_button.setMinimumWidth(80)
        ok_button.setStyleSheet(UIStyles.button_analyze())
        ok_button.clicked.connect(self.on_ok_clicked)
        ok_button.setDefault(True)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        main_layout.addLayout(button_layout)

    def on_ok_clicked(self):
        """Handle OK button click"""
        q_text = self.q_input.text().strip()
        logger.debug(f"Q number input received: '{q_text}'")

        # Validate Q number format
        if not q_text:
            logger.warning("User attempted to submit empty Q number")
            QMessageBox.warning(self, "Invalid Input", "Please enter a Q number.")
            return

        # Add Q prefix if not present
        if not q_text.upper().startswith('Q'):
            q_text = 'Q' + q_text
            logger.debug(f"Added Q prefix, new value: '{q_text}'")

        # Check if it's a valid Q number format
        if not q_text[1:].isdigit():
            logger.warning(f"Invalid Q number format: '{q_text}'")
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid Q number (e.g., Q100530634).")
            return

        self.q_number = q_text
        logger.info(f"Valid Q number accepted: {q_text}")
        self.accept()

    def get_q_number(self):
        """Return the entered Q number"""
        return self.q_number


class WikidataSparqlDialog(QDialog):
    """Dialog to edit and send SPARQL query to Wikidata"""

    def __init__(self, q_number, parent=None):
        super(WikidataSparqlDialog, self).__init__(parent)
        self.setWindowTitle("Edit SPARQL Query")
        self.setModal(True)
        self.setMinimumSize(600, 400)
        self.resize(700, 500)

        self.q_number = q_number
        self.sparql_result = None

        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Add title label
        title_label = QLabel(f"SPARQL Query for {q_number}")
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        main_layout.addWidget(title_label)

        # Add description
        desc_label = QLabel("Edit the SPARQL query below and click 'Send' to execute it:")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)

        # Text editor for SPARQL query
        self.sparql_editor = QTextEdit()
        self.sparql_editor.setStyleSheet("font-family: 'Courier New', monospace; font-size: 10pt; padding: 5px;")

        # Set default SPARQL query with the Q number
        default_query = f"""#defaultView:Map
SELECT ?item ?itemLabel ?geo WHERE {{
  ?item wdt:P361 wd:{q_number};
    wdt:P31 wd:Q72617071;
    wdt:P625 ?geo.
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
}}"""
        self.sparql_editor.setPlainText(default_query)
        main_layout.addWidget(self.sparql_editor)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumWidth(80)
        cancel_button.setStyleSheet(UIStyles.dialog_close_button())
        cancel_button.clicked.connect(self.reject)

        # Send button
        send_button = QPushButton("Send")
        send_button.setMinimumWidth(80)
        send_button.setStyleSheet(UIStyles.button_analyze())
        send_button.clicked.connect(self.on_send_clicked)
        send_button.setDefault(True)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(send_button)
        main_layout.addLayout(button_layout)

    def on_send_clicked(self):
        """Handle Send button click - execute SPARQL query"""
        sparql_query = self.sparql_editor.toPlainText().strip()

        if not sparql_query:
            QMessageBox.warning(self, "Invalid Query", "Please enter a SPARQL query.")
            logger.warning("User attempted to send empty SPARQL query")
            return

        try:
            # Import requests library for HTTP requests
            import requests
            import json

            # Wikidata SPARQL endpoint
            endpoint_url = "https://query.wikidata.org/sparql"

            logger.info(f"Executing SPARQL query for Q number: {self.q_number}")
            logger.debug(f"SPARQL query:\n{sparql_query}")

            # Show progress message
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

            # Execute SPARQL query
            headers = {
                'Accept': 'application/sparql-results+json',
                'User-Agent': 'LandTalkAI/1.0'
            }

            response = requests.get(
                endpoint_url,
                params={'query': sparql_query, 'format': 'json'},
                headers=headers,
                timeout=30
            )

            QApplication.restoreOverrideCursor()

            if response.status_code == 200:
                result_data = response.json()
                self.sparql_result = result_data
                num_results = len(result_data.get('results', {}).get('bindings', []))
                logger.info(f"SPARQL query executed successfully. Results: {num_results} items")
                logger.debug(f"SPARQL result data: {json.dumps(result_data, indent=2)}")
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Query Failed",
                    f"SPARQL query failed with status code {response.status_code}:\n{response.text[:200]}"
                )
                logger.error(f"SPARQL query failed: {response.status_code} - {response.text}")

        except ImportError:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                "Missing Library",
                "The 'requests' library is required to execute SPARQL queries.\nPlease install it using: pip install requests"
            )
            logger.error("requests library not available for SPARQL queries")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to execute SPARQL query:\n{str(e)}"
            )
            logger.error(f"Error executing SPARQL query: {str(e)}")

    def get_sparql_result(self):
        """Return the SPARQL query result"""
        return self.sparql_result


class LandTalkDockWidget(QDockWidget):
    """Dock widget for interactive chat conversation with LandTalk AI"""

    def __init__(self, parent=None):
        super(LandTalkDockWidget, self).__init__(parent)
        self.setWindowTitle("LandTalk.AI Analysis")

        # Initialize instance variables
        self._init_instance_variables()

        # Configure dock widget features (PyQt5/PyQt6 compatibility)
        self._configure_dock_features()

        # Create the main widget and layout
        self.main_widget = QWidget()
        self.setWidget(self.main_widget)

        layout = QVBoxLayout(self.main_widget)
        layout.setContentsMargins(2, 2, 2, 2)

        # Setup all UI components
        self._setup_menu_bar()
        self._setup_controls(layout)
        self._setup_area_selection(layout)
        self._setup_chat_display(layout)
        self._setup_input_section(layout)
        self._setup_shortcuts()

    def _init_instance_variables(self):
        """Initialize all instance variables"""
        self.parent_plugin = None  # Will be set by the plugin
        self.chat_history = []  # Store chat conversation history
        self.last_selected_resolution_index = 2  # Default to 1.0 m/px (index 2)

        # Store references for dynamic sizing
        self.menu_bar = None
        self.chat_display = None
        self.input_section_widget = None

        # Store uploaded images
        self.uploaded_images = []  # List of tuples (file_path, base64_data)

    def _configure_dock_features(self):
        """Configure dock widget features with PyQt5/PyQt6 compatibility"""
        features = resolve_dock_widget_features()
        if features:
            self.setFeatures(features)

    def _setup_menu_bar(self):
        """Setup menu bar with options menu"""
        # Create a menu bar - but hide it on macOS to prevent conflicts with QGIS main menu
        self.menu_bar = QMenuBar(self.main_widget)

        # Hide menu bar on macOS to prevent interference with QGIS main menu bar
        if IS_MACOS:
            self.menu_bar.setVisible(False)
            logger.info("Menu bar hidden on macOS to prevent QGIS menu bar conflicts")

        # Create options menu
        self.settings_menu = QMenu("Options", self.menu_bar)
        self.settings_menu.setToolTip("Options")

        # Create menu actions
        self.logging_action = QAction("Save Log File", self.main_widget)
        self.gemini_key_action = QAction("Set Gemini API Key", self.main_widget)
        self.gpt_key_action = QAction("Set GPT API Key", self.main_widget)

        # Connect actions to functions
        self.logging_action.triggered.connect(self.save_log_file)
        self.gemini_key_action.triggered.connect(lambda: self.parent_plugin.config_manager.get_gemini_key() if self.parent_plugin else None)
        self.gpt_key_action.triggered.connect(lambda: self.parent_plugin.config_manager.get_gpt_key() if self.parent_plugin else None)

        # Create layer persistence submenu
        self.layer_persistence_menu = QMenu("Layer Persistence", self.settings_menu)

        # Create action group for radio button behavior
        self.persistence_action_group = QActionGroup(self.main_widget)
        self.persistence_action_group.setExclusive(True)

        # Create persistence mode actions
        self.auto_save_action = QAction("Auto-save each analysis", self.main_widget)
        self.auto_save_action.setCheckable(True)
        self.auto_save_action.setData("auto_save")
        self.auto_save_action.triggered.connect(self.on_persistence_mode_changed)
        self.persistence_action_group.addAction(self.auto_save_action)

        self.temporary_action = QAction("Temporary (manual save)", self.main_widget)
        self.temporary_action.setCheckable(True)
        self.temporary_action.setData("temporary")
        self.temporary_action.triggered.connect(self.on_persistence_mode_changed)
        self.persistence_action_group.addAction(self.temporary_action)

        # Add persistence actions to submenu
        self.layer_persistence_menu.addAction(self.auto_save_action)
        self.layer_persistence_menu.addAction(self.temporary_action)

        # Add manual save action
        self.save_layers_action = QAction("Save All Layers Now", self.main_widget)
        self.save_layers_action.triggered.connect(self.on_save_layers_clicked)

        # Build the settings menu
        self.settings_menu.addAction(self.logging_action)
        self.settings_menu.addSeparator()
        self.settings_menu.addMenu(self.layer_persistence_menu)
        self.settings_menu.addAction(self.save_layers_action)
        self.settings_menu.addSeparator()
        self.settings_menu.addAction(self.gemini_key_action)
        self.settings_menu.addAction(self.gpt_key_action)

        # Create prefs button
        self.prefs_button = QPushButton("Options")
        self.prefs_button.setMinimumWidth(80)
        self.prefs_button.setMaximumHeight(25)
        self.prefs_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.prefs_button.setStyleSheet(UIStyles.button_options())
        self.prefs_button.setToolTip("Options")
        self.prefs_button.setMenu(self.settings_menu)

        # Create rules button
        self.rules_button = QPushButton("Rules")
        self.rules_button.setMinimumWidth(80)
        self.rules_button.setMaximumHeight(25)
        self.rules_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.rules_button.setToolTip("Edit chat rules")
        self.rules_button.setStyleSheet(UIStyles.button_options())
        self.rules_button.clicked.connect(lambda: self.parent_plugin.edit_system_prompt() if self.parent_plugin else None)

        # Create tutorial button
        self.tutorial_button = QPushButton("Tutorial")
        self.tutorial_button.setMinimumWidth(80)
        self.tutorial_button.setMaximumHeight(25)
        self.tutorial_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.tutorial_button.setToolTip("Show tutorial")
        self.tutorial_button.setStyleSheet(UIStyles.button_options())
        self.tutorial_button.clicked.connect(self.show_tutorial)

    def _setup_controls(self, layout):
        """Setup control panel with AI model and confidence settings"""
        # Add menu bar to layout only on non-macOS systems
        if not IS_MACOS:
            layout.setMenuBar(self.menu_bar)
        else:
            logger.info("Skipping menu bar layout on macOS to prevent QGIS menu bar conflicts")

        # Create AI model selection
        self.ai_model_label = QLabel("AI Model:")
        self.ai_model_label.setStyleSheet(UIStyles.label_input_control())

        self.ai_model_combo = QComboBox()
        self.ai_model_combo.addItem("gemini-2.5-pro", "gemini-2.5-pro")
        self.ai_model_combo.addItem("gemini-2.5-flash", "gemini-2.5-flash")
        self.ai_model_combo.addItem("gemini-robotics-er-1.5-preview (recommended)", "gemini-robotics-er-1.5-preview")
        self.ai_model_combo.addItem("gemini-3-flash-preview (recommended)", "gemini-3-flash-preview")
        self.ai_model_combo.addItem("gemini-3-pro-preview", "gemini-3-pro-preview")
        self.ai_model_combo.addItem("gpt-5.2", "gpt-5.2")
        self.ai_model_combo.addItem("gpt-5.1-mini", "gpt-5.1-mini")
        self.ai_model_combo.addItem("gpt-5.1-nano", "gpt-5.1-nano")

        # Select gemini-robotics by default
        idx = self.ai_model_combo.findData("gemini-3-flash-preview")
        if idx != -1:
            self.ai_model_combo.setCurrentIndex(idx)
        else:
            self.ai_model_combo.setCurrentIndex(0)

        self.ai_model_combo.setStyleSheet(UIStyles.combo_box_ai_model())
        self.ai_model_combo.setToolTip("Select the AI model to use for analysis")
        self.ai_model_combo.currentTextChanged.connect(self.on_model_changed)

        # Create probability input
        self.prob_label = QLabel("Conf. (%):")
        self.prob_label.setStyleSheet(UIStyles.label_input_control())
        self.prob_label.setToolTip("Filter for features with confidence greater than this value (0-100)")

        self.prob_input = QLineEdit()
        self.prob_input.setText("0")
        self.prob_input.setMaximumWidth(50)
        self.prob_input.setToolTip("Filter for features with confidence greater than this value (0-100)")
        self.prob_input.setValidator(QIntValidator(0, 99))
        self.prob_input.setStyleSheet(UIStyles.line_edit_probability())

        # Create controls widget
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(2, 2, 2, 2)
        controls_layout.setSpacing(8)

        controls_layout.addWidget(self.ai_model_label)
        controls_layout.addWidget(self.ai_model_combo)
        controls_layout.addStretch()
        controls_layout.addWidget(self.prob_label)
        controls_layout.addWidget(self.prob_input)

        controls_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(controls_widget)

    def _setup_area_selection(self, layout):
        """Setup area selection section with thumbnail display"""
        self.area_selection_widget = QWidget()
        area_selection_layout = QVBoxLayout(self.area_selection_widget)
        area_selection_layout.setContentsMargins(8, 2, 8, 2)

        # Select Area button
        self.select_area_button = QPushButton("Select area")
        self.select_area_button.setMinimumHeight(28)
        self.select_area_button.setStyleSheet(UIStyles.button_select_area())
        self.select_area_button.clicked.connect(self.on_select_area_clicked)
        area_selection_layout.addWidget(self.select_area_button)

        # Setup thumbnail widget
        self._setup_thumbnail_widget()
        area_selection_layout.addWidget(self.thumbnail_widget)

        # Set size policies
        self.area_selection_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.area_selection_widget.setMinimumWidth(200)
        layout.addWidget(self.area_selection_widget)

    def _setup_thumbnail_widget(self):
        """Setup thumbnail display widget with image and info panel"""
        self.thumbnail_widget = QWidget()
        self.thumbnail_widget.setVisible(False)
        thumbnail_layout = QVBoxLayout(self.thumbnail_widget)
        thumbnail_layout.setContentsMargins(2, 2, 2, 2)

        # Create horizontal layout for image and info panel
        thumbnail_horizontal_layout = QHBoxLayout()
        thumbnail_horizontal_layout.setSpacing(8)

        # Thumbnail image container
        self.thumbnail_image_label = QLabel()
        self.thumbnail_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_image_label.setStyleSheet(UIStyles.thumbnail_image_clickable())
        self.thumbnail_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.thumbnail_image_label.mousePressEvent = self.on_thumbnail_clicked
        self.thumbnail_image_label.setToolTip("Click to view full-size image")

        # Create information panel
        self._setup_thumbnail_info_panel()

        # Add image and info panel to horizontal layout
        thumbnail_horizontal_layout.addWidget(self.thumbnail_image_label)
        thumbnail_horizontal_layout.addWidget(self.thumbnail_info_panel)

        thumbnail_layout.addLayout(thumbnail_horizontal_layout)

    def _setup_thumbnail_info_panel(self):
        """Setup thumbnail information panel with resolution and dimensions"""
        self.thumbnail_info_panel = QWidget()
        self.thumbnail_info_panel.setStyleSheet(UIStyles.thumbnail_info_panel())
        self.thumbnail_info_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.thumbnail_info_panel.setFixedWidth(120)

        info_layout = QVBoxLayout(self.thumbnail_info_panel)
        info_layout.setContentsMargins(2, 2, 2, 2)
        info_layout.setSpacing(2)

        # Ground resolution dropdown
        self.resolution_label = QLabel("Resolution:")
        self.resolution_label.setStyleSheet(UIStyles.label_value_resolution())

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("0.25 m/px", 0.25)
        self.resolution_combo.addItem("0.5 m/px", 0.5)
        self.resolution_combo.addItem("1.0 m/px", 1.0)
        self.resolution_combo.addItem("2.0 m/px", 2.0)
        self.resolution_combo.addItem("5.0 m/px", 5.0)
        self.resolution_combo.addItem("10.0 m/px", 10.0)
        self.resolution_combo.addItem("20.0 m/px", 20.0)
        self.resolution_combo.addItem("100.0 m/px", 100.0)
        self.resolution_combo.setCurrentIndex(2)  # Default to 1.0 m/px
        self.resolution_combo.setStyleSheet(UIStyles.combo_box_resolution())
        self.resolution_combo.setToolTip("Select ground resolution for dimension calculations")
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)

        # Width dimension label
        self.width_label = QLabel("Width:")
        self.width_label.setStyleSheet(UIStyles.label_value_resolution())
        self.width_value = QLabel("0 m")
        self.width_value.setStyleSheet(UIStyles.label_value())

        # Height dimension label
        self.height_label = QLabel("Height:")
        self.height_label.setStyleSheet(UIStyles.label_value_resolution())
        self.height_value = QLabel("0 m")
        self.height_value.setStyleSheet(UIStyles.label_value())

        # Add all widgets to info layout
        info_layout.addWidget(self.resolution_label)
        info_layout.addWidget(self.resolution_combo)
        info_layout.addWidget(self.width_label)
        info_layout.addWidget(self.width_value)
        info_layout.addWidget(self.height_label)
        info_layout.addWidget(self.height_value)
        info_layout.addStretch()

    def _setup_chat_display(self, layout):
        """Setup chat display area"""
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(200)
        self.chat_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chat_display.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX

        # Enable scrollbars when needed
        self.chat_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if hasattr(Qt, 'ScrollBarPolicy') else 1)
        self.chat_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if hasattr(Qt, 'ScrollBarPolicy') else 1)

        # Enable word wrapping
        self.chat_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if hasattr(QTextEdit, 'LineWrapMode') else 1)

        self.chat_display.setStyleSheet(UIStyles.text_edit_chat_display())
        layout.addWidget(self.chat_display)

        # Add initial welcome message
        self.add_system_message("Welcome! Click 'Select area' above to choose a map area.")

    def _setup_input_section(self, layout):
        """Setup input section with text area and buttons"""
        input_section = QVBoxLayout()

        # Create widget to wrap input section
        self.input_section_widget = QWidget()
        self.input_section_widget.setLayout(input_section)
        self.input_section_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # User input label with add image button
        label_layout = QHBoxLayout()
        label_layout.setSpacing(4)

        input_label = QLabel("Your message (optional):")
        input_label.setStyleSheet(UIStyles.label_user_input())
        input_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Examples button, currently disabled
        self.add_image_button = QPushButton("Add examples")
        self.add_image_button.setMaximumWidth(90)
        self.add_image_button.setMaximumHeight(20)
        self.add_image_button.setToolTip("Manage example images")
        self.add_image_button.setStyleSheet(UIStyles.button_analyze())  # Reuse analyze button style
        self.add_image_button.clicked.connect(self.on_examples_button_clicked)

        # Wikidata button
        self.wikidata_button = QPushButton("Wikidata")
        self.wikidata_button.setMaximumWidth(90)
        self.wikidata_button.setMaximumHeight(20)
        self.wikidata_button.setToolTip("Query Wikidata and add results to AI context")
        self.wikidata_button.setStyleSheet(UIStyles.button_analyze())  # Reuse analyze button style
        self.wikidata_button.clicked.connect(self.on_wikidata_button_clicked)

        label_layout.addWidget(input_label)

        # Conditionally add buttons based on feature flags
        if PluginConstants.ENABLE_ADD_EXAMPLES_BUTTON:
            label_layout.addWidget(self.add_image_button)
        if PluginConstants.ENABLE_WIKIDATA_BUTTON:
            label_layout.addWidget(self.wikidata_button)

        label_layout.addStretch()

        input_section.addLayout(label_layout)

        # Text input and analyze button
        input_and_button_layout = QHBoxLayout()
        input_and_button_layout.setSpacing(8)

        self.prompt_text = QTextEdit()
        self.prompt_text.setMaximumHeight(50)
        self.prompt_text.setMinimumHeight(50)
        self.prompt_text.setToolTip("Type your message here and click 'Analyze' to send.")
        self.prompt_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.prompt_text.setStyleSheet(UIStyles.text_edit_prompt())

        self.send_button = QPushButton("Analyze")
        self.send_button.setMinimumWidth(60)
        self.send_button.setMaximumWidth(60)
        self.send_button.setMaximumHeight(50)
        self.send_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.send_button.setStyleSheet(UIStyles.button_analyze())
        self.send_button.clicked.connect(self.send_message_to_selected_ai)

        input_and_button_layout.addWidget(self.prompt_text)
        input_and_button_layout.addWidget(self.send_button)
        input_section.addLayout(input_and_button_layout)

        # Bottom buttons layout
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.tutorial_button)
        button_layout.addWidget(self.rules_button)
        button_layout.addWidget(self.prefs_button)
        button_layout.addStretch()
        input_section.addLayout(button_layout)

        layout.addWidget(self.input_section_widget)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Escape key to interrupt AI response
        escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        escape_shortcut.activated.connect(self.interrupt_ai_request)
    
    
    def on_select_area_clicked(self):
        """Handle the select area button click"""
        if self.parent_plugin:
            # Start the rectangle selection tool
            self.parent_plugin.start_rectangle_selection()
    
    def calculate_ground_dimensions(self):
        """Calculate real-world dimensions in meters from captured extent and ground resolution"""
        return calculate_ground_dimensions(self.parent_plugin)

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
                resolutions = [0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 100.0]
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

            # Update width and height displays using utility function
            width_text = format_dimension(width_meters)
            height_text = format_dimension(height_meters)
            self.width_value.setText(width_text)
            self.height_value.setText(height_text)

            logger.debug(f"Updated thumbnail info - Resolution: {ground_resolution:.2f} m/px, Width: {width_text}, Height: {height_text}")

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
                    self.parent_plugin.config_manager.set_show_tutorial(False)
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
                    
                    # Try different common field names for object type (prioritize 'label' as new format)
                    for type_field in ['label', 'Label', 'object_type', 'Object Type']:
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
            
            # Try different common field names for object type (prioritize 'label' as new format)
            for type_field in ['label', 'Label', 'object_type', 'Object Type']:
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
        if not (self.chat_display and self.input_section_widget):
            return
            
        try:
            # Force layout update to get accurate size hints
            self.input_section_widget.updateGeometry()
            QApplication.processEvents()
            
            # Get actual heights of fixed elements
            # On macOS, menu bar is hidden so its height should be 0
            if IS_MACOS or not self.menu_bar.isVisible():
                menu_bar_height = 0
            else:
                menu_bar_height = self.menu_bar.sizeHint().height()
            
            input_section_height = self.input_section_widget.sizeHint().height()
            
            logger.debug(f"Layout update - Menu bar: {menu_bar_height}px, Input section: {input_section_height}px (macOS: {IS_MACOS})")
            
            # The chat display will automatically expand to fill remaining space
            # due to its Expanding size policy, no manual height setting needed
            
        except Exception as e:
            logger.warning(f"Error adjusting chat display height: {str(e)}")
    
    def showEvent(self, event):
        """Handle show event to adjust initial sizing"""
        super(LandTalkDockWidget, self).showEvent(event)
        # Use QTimer to delay the size adjustment until the widget is fully shown
        QTimer.singleShot(100, self.adjust_chat_display_height)
    
    def on_examples_button_clicked(self):
        """Handle examples button click to open the example images dialog"""
        try:
            # Create and show the example images dialog
            dialog = ExampleImagesDialog(self)
            dialog.exec()
            logger.info("Example images dialog closed")
        except Exception as e:
            logger.error(f"Error opening example images dialog: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to open example images dialog: {str(e)}")

    def on_wikidata_button_clicked(self):
        """Handle Wikidata button click to query Wikidata and add results to AI context"""
        logger.info("Wikidata button clicked - starting Wikidata query workflow")

        try:
            # Step 1: Show Q number input dialog
            logger.debug("Opening Q number input dialog")
            q_dialog = WikidataQNumberDialog(self)
            if q_dialog.exec() == QDialog.DialogCode.Accepted:
                q_number = q_dialog.get_q_number()
                if not q_number:
                    logger.warning("Q number dialog accepted but no Q number returned")
                    return

                logger.info(f"User entered Q number: {q_number}")

                # Step 2: Show SPARQL editor dialog with the Q number
                logger.debug(f"Opening SPARQL editor dialog for Q number: {q_number}")
                sparql_dialog = WikidataSparqlDialog(q_number, self)
                if sparql_dialog.exec() == QDialog.DialogCode.Accepted:
                    sparql_result = sparql_dialog.get_sparql_result()
                    if sparql_result:
                        # Step 3: Process and format the results
                        logger.info(f"SPARQL dialog accepted with results for Q number: {q_number}")
                        self.process_wikidata_results(sparql_result, q_number)
                        logger.info("Wikidata workflow completed successfully - results processed and added to context")
                    else:
                        logger.warning("SPARQL dialog accepted but no results returned")
                else:
                    logger.info("User cancelled SPARQL editor dialog")
            else:
                logger.info("User cancelled Q number input dialog")

        except Exception as e:
            logger.error(f"Error in Wikidata query workflow: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to process Wikidata query: {str(e)}")

    def process_wikidata_results(self, sparql_result, q_number):
        """Process SPARQL results and add them to the AI query context"""
        try:
            logger.info(f"Processing Wikidata results for Q number: {q_number}")

            # Extract bindings from SPARQL result
            bindings = sparql_result.get('results', {}).get('bindings', [])
            logger.debug(f"Extracted {len(bindings)} bindings from SPARQL result")

            if not bindings:
                logger.warning(f"No results found for Q number: {q_number}")
                QMessageBox.information(
                    self,
                    "No Results",
                    f"The SPARQL query for {q_number} returned no results."
                )
                return

            # Format results as a readable text for AI context
            formatted_results = f"\n\n--- Wikidata Query Results for {q_number} ---\n"
            formatted_results += f"Found {len(bindings)} items:\n\n"

            for idx, binding in enumerate(bindings, 1):
                # Extract common fields (item, itemLabel, geo)
                item = binding.get('item', {}).get('value', 'N/A')
                item_label = binding.get('itemLabel', {}).get('value', 'N/A')
                geo = binding.get('geo', {}).get('value', 'N/A')

                logger.debug(f"Item {idx}: {item_label} | {item} | {geo}")

                formatted_results += f"{idx}. {item_label}\n"
                formatted_results += f"   - Item: {item}\n"
                formatted_results += f"   - Coordinates: {geo}\n\n"

            logger.info(f"Formatted results (length: {len(formatted_results)} chars):\n{formatted_results}")

            # Append the formatted results to the current prompt text
            current_text = self.prompt_text.toPlainText()
            if current_text:
                logger.debug(f"Appending to existing prompt text (current length: {len(current_text)} chars)")
                new_text = current_text + "\n" + formatted_results
            else:
                logger.debug("Setting formatted results as new prompt text")
                new_text = formatted_results

            self.prompt_text.setPlainText(new_text)

            # Show success message
            QMessageBox.information(
                self,
                "Wikidata Results Added",
                f"Successfully added {len(bindings)} Wikidata results to your message.\n\n"
                f"The results will be sent to the AI along with your next query."
            )

        except Exception as e:
            logger.error(f"Error processing Wikidata results for {q_number}: {str(e)}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to process Wikidata results:\n{str(e)}"
            )

    def clear_uploaded_images(self):
        """Clear all uploaded images"""
        self.uploaded_images = []
        logger.info("Cleared uploaded images")

    def on_persistence_mode_changed(self):
        """Handle layer persistence mode change"""
        if not self.parent_plugin:
            return

        # Get the selected mode from the action that triggered this
        action = self.sender()
        if action and hasattr(action, 'data'):
            mode = action.data()
            if mode:
                logger.info(f"Layer persistence mode changed to: {mode}")
                self.parent_plugin.config_manager.set_layer_persistence_mode(mode)

                # Show info message
                mode_names = {
                    'auto_save': 'Auto-save each analysis',
                    'temporary': 'Temporary (manual save)'
                }

                descriptions = {
                    'auto_save': 'Layers will be automatically saved to GeoPackage files after each analysis.',
                    'temporary': 'Layers will be saved when you click "Save All Layers Now" or when the project is saved.'
                }

                QMessageBox.information(
                    self,
                    "Layer Persistence Mode",
                    f"Layer persistence mode set to: {mode_names.get(mode, mode)}\n\n"
                    f"{descriptions.get(mode, '')}"
                )

    def on_save_layers_clicked(self):
        """Handle manual save layers button click"""
        if not self.parent_plugin:
            return

        try:
            # Export all layers from the LandTalk.ai group
            layer_manager = self.parent_plugin.layer_manager

            # Get the LandTalk.ai group
            from qgis.core import QgsProject
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup("LandTalk.ai")

            if not landtalk_group:
                QMessageBox.warning(
                    self,
                    "No Layers",
                    "No LandTalk layers found to save."
                )
                return

            # Save to GeoPackage
            output_path = layer_manager.export_landtalk_group_to_geopackage()

            if output_path:
                # Convert memory layers to file-based layers
                success = layer_manager.convert_memory_layers_to_file_based(landtalk_group, output_path)

                if success:
                    QMessageBox.information(
                        self,
                        "Layers Saved",
                        f"All LandTalk layers have been saved to:\n{output_path}\n\nMemory layers have been converted to persistent file-based layers."
                    )
                    logger.info(f"Manually saved layers to: {output_path} and converted to file-based layers")
                else:
                    QMessageBox.warning(
                        self,
                        "Partial Success",
                        f"Layers were saved to:\n{output_path}\n\nHowever, some layers could not be converted to file-based layers."
                    )
                    logger.warning(f"Layers saved but conversion to file-based layers had issues")
            else:
                QMessageBox.warning(
                    self,
                    "Save Failed",
                    "Failed to save layers. Make sure the project is saved and there are layers to export."
                )

        except Exception as e:
            logger.error(f"Error saving layers: {str(e)}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while saving layers:\n{str(e)}"
            )

    def update_persistence_mode_ui(self):
        """Update the UI to reflect the current persistence mode"""
        if not self.parent_plugin:
            return

        try:
            # Get current mode
            mode = self.parent_plugin.config_manager.get_layer_persistence_mode()
            logger.info(f"Updating UI for persistence mode: {mode}")

            # Update the checked state of the actions
            if mode == 'auto_save':
                self.auto_save_action.setChecked(True)
            else:
                # Default to temporary if mode is unknown or was prompt_on_close
                self.temporary_action.setChecked(True)

        except Exception as e:
            logger.error(f"Error updating persistence mode UI: {str(e)}")

    def closeEvent(self, event):
        """Handle close event to clean up resources"""
        if self.parent_plugin:
            # Clean up selection
            self.parent_plugin.cleanup_selection()

        super(LandTalkDockWidget, self).closeEvent(event)
