# -*- coding: utf-8 -*-
"""
UI styling utilities for LandTalk.AI plugin

This module provides centralized UI styling for consistent theming.
"""

from .platform_utils import scale_font


class UIStyles:
    """Centralized UI styles for consistent theming"""

    # Button styles
    @staticmethod
    def button_primary():
        """Primary action button style (blue)"""
        return f"""
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

    @staticmethod
    def button_secondary():
        """Secondary action button style (gray)"""
        return f"""
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

    @staticmethod
    def button_small():
        """Small utility button style (dark gray)"""
        return f"""
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

    @staticmethod
    def button_options():
        """Options/settings button style"""
        return f"""
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
        """

    @staticmethod
    def button_select_area():
        """Select area button style (large blue)"""
        return f"""
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
        """

    @staticmethod
    def button_analyze():
        """Analyze button style"""
        return f"""
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
        """

    # Input field styles
    @staticmethod
    def combo_box():
        """Standard combo box style"""
        return f"""
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

    @staticmethod
    def combo_box_ai_model():
        """AI model combo box style"""
        return f"""
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
        """

    @staticmethod
    def combo_box_resolution():
        """Resolution combo box style"""
        return f"""
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
        """

    @staticmethod
    def line_edit():
        """Standard line edit style"""
        return f"""
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

    @staticmethod
    def line_edit_probability():
        """Probability input line edit style"""
        return f"""
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
        """

    @staticmethod
    def text_edit():
        """Standard text edit style"""
        return f"""
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

    @staticmethod
    def text_edit_prompt():
        """Prompt text edit style"""
        return f"""
            QTextEdit {{
                border: 2px solid #dee2e6;
                border-radius: 4px;
                padding: 6px;
                font-size: {scale_font(11)};
            }}
            QTextEdit:focus {{
                border-color: #4285F4;
            }}
        """

    @staticmethod
    def text_edit_chat_display():
        """Chat display text edit style"""
        return f"""
            QTextEdit {{
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: {scale_font(11)};
            }}
        """

    # Label styles
    @staticmethod
    def label_small():
        """Small bold label style"""
        return f"font-size: {scale_font(8)}; font-weight: bold; color: #666;"

    @staticmethod
    def label_value():
        """Value display label style"""
        return f"font-size: {scale_font(8)}; color: #333;"

    @staticmethod
    def label_value_resolution():
        """Resolution value label style"""
        return f"font-size: {scale_font(9)}; font-weight: bold; color: #666;"

    @staticmethod
    def label_input():
        """Input field label style"""
        return f"color: #666; font-size: {scale_font(9)};"

    @staticmethod
    def label_input_control():
        """Control label with margins"""
        return f"""
            QLabel {{
                color: #666;
                font-size: {scale_font(9)};
                margin-left: 4px;
                margin-right: 2px;
                padding: 2px 0px;
            }}
        """

    @staticmethod
    def label_user_input():
        """User input area label"""
        return f"color: #666; font-size: {scale_font(10)};"

    # Panel styles
    @staticmethod
    def info_panel():
        """Information panel style"""
        return """
            QWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """

    @staticmethod
    def thumbnail_info_panel():
        """Thumbnail information panel style"""
        return """
            QWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: #f8f9fa;
                padding: 2px;
            }
        """

    @staticmethod
    def thumbnail_label():
        """Thumbnail image label style"""
        return """
            QLabel {
                border: 2px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                padding: 4px;
            }
        """

    @staticmethod
    def thumbnail_image_clickable():
        """Clickable thumbnail image style"""
        return """
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
        """

    @staticmethod
    def dialog_close_button():
        """Close button style for dialogs"""
        return """
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
        """
