# -*- coding: utf-8 -*-
"""
Domain Wizard Dialog for LandTalk.AI

Provides a user-friendly guided interface for configuring the AI system prompt
without requiring users to understand the underlying XML structure.
"""

import re
import os

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QTabWidget, QScrollArea, QMessageBox, QSizePolicy, QFrame,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont

from .ui_styles import UIStyles
from .logging import logger


# ---------------------------------------------------------------------------
# Locked prompt fragments — never exposed to users, always injected on save
# ---------------------------------------------------------------------------

_LOCKED_FORMAT = (
    '- Format: [{"box_2d": [ymin, xmin, ymax, xmax] normalized to 0-1000. '
    'The values in box_2d must only be integers,   '
    '"label": <label for the object. Always try to assign an object class. use the most likely one>, \n'
    '  "probability": <probability of this detection in percent>, \n'
    '  "reason": <textually explain why you think this object is found>}]'
)

_LOCKED_BRIDGE = "Based on the context provided above, execute the task."

TONE_OPTIONS = ["Academic", "Technical", "Professional", "Plain English"]

# ---------------------------------------------------------------------------
# Domain preset definitions
# ---------------------------------------------------------------------------

DOMAIN_PRESETS = [
    {
        "id": "archaeology",
        "label": "Archaeology",
        "role": "world-class archaeologist. You answer with precision and avoid fluff.",
        "context": (
            "you are working with remote sensing data like lidar, satellite, aerial "
            "or maps to find archaeological features i.e. ancient man-made structures."
        ),
        "task": (
            'find all archaeological features in this image. '
            'If no archaeological features are confidently detected, '
            'return the text "Sorry, nothing found."'
        ),
        "tone": "Academic",
    },
    {
        "id": "disaster_assessment",
        "label": "Disaster Assessment",
        "role": "disaster response analyst specializing in rapid damage assessment from remote sensing.",
        "context": (
            "you are analyzing pre- or post-event satellite and aerial imagery to assess "
            "damage caused by natural or man-made disasters such as floods, earthquakes, "
            "wildfires, or landslides."
        ),
        "task": (
            'identify and locate all visible signs of damage, destruction, or hazard in '
            'this image, including collapsed structures, flooded areas, burn scars, debris '
            'flows, and blocked roads. If no damage is detected, return "Sorry, nothing found."'
        ),
        "tone": "Professional",
    },
    {
        "id": "environmental_monitoring",
        "label": "Environmental Monitoring",
        "role": "environmental scientist specializing in remote sensing and ecosystem analysis.",
        "context": (
            "you are analyzing satellite or aerial imagery for environmental change detection, "
            "including pollution, habitat loss, wetland degradation, coastal erosion, "
            "and water quality indicators."
        ),
        "task": (
            'identify all environmental features and anomalies in this image that indicate '
            'ecosystem stress, degradation, or change, such as algal blooms, burn scars, '
            'deforestation, or oil spills. If nothing is detected, return "Sorry, nothing found."'
        ),
        "tone": "Academic",
    },
    {
        "id": "forestry_vegetation",
        "label": "Forestry & Vegetation",
        "role": "forestry expert and vegetation ecologist with remote sensing expertise.",
        "context": (
            "you are working with aerial, LiDAR, or multispectral imagery to assess "
            "forest structure, tree species composition, canopy density, forest health, "
            "and vegetation phenology."
        ),
        "task": (
            'detect and characterize all vegetation and forestry features in this image, '
            'including canopy gaps, tree die-off patches, windthrow areas, logging roads, '
            'and regeneration zones. If nothing relevant is found, return "Sorry, nothing found."'
        ),
        "tone": "Technical",
    },
    {
        "id": "land_use_agriculture",
        "label": "Land Use & Agriculture",
        "role": "agricultural remote sensing specialist and land-use analyst.",
        "context": (
            "you are interpreting aerial or satellite imagery to classify land use and "
            "land cover, distinguish crop types, identify field boundaries, irrigation "
            "systems, and signs of soil degradation."
        ),
        "task": (
            'map and classify all agricultural and land-use features visible in this image, '
            'including field parcels, crop types, irrigation canals, bare soil, and land cover categories. '
            'If nothing relevant is detected, return "Sorry, nothing found."'
        ),
        "tone": "Technical",
    },
    {
        "id": "mineral_prospection",
        "label": "Mineral / Resource Prospection",
        "role": "expert geologist specializing in mineral exploration and remote sensing.",
        "context": (
            "you are working with multispectral, hyperspectral, or high-resolution satellite "
            "imagery to identify geological structures, lithological units, alteration zones, "
            "or surface expressions of mineral deposits."
        ),
        "task": (
            'detect and delineate all geological and mineralogical features of interest in '
            'this image, including fault lines, lineaments, color anomalies, and exposed rock units. '
            'If no relevant features are detected, return "Sorry, nothing found."'
        ),
        "tone": "Technical",
    },
    {
        "id": "urban_planning",
        "label": "Urban Planning",
        "role": "senior urban planner and land-use analyst.",
        "context": (
            "you are analyzing aerial or satellite imagery to identify urban structures, "
            "zoning patterns, infrastructure, green spaces, and informal settlements."
        ),
        "task": (
            'identify and locate all urban planning features visible in this image, '
            'such as road networks, building footprints, parks, industrial zones, and '
            'residential areas. If nothing relevant is detected, return "Sorry, nothing found."'
        ),
        "tone": "Professional",
    },
    {
        "id": "custom",
        "label": "Custom (fill in yourself)",
        "role": "",
        "context": "",
        "task": "",
        "tone": "Professional",
    },
]

# ---------------------------------------------------------------------------
# Pure functions for prompt assembly and parsing
# ---------------------------------------------------------------------------

def assemble_system_prompt(role: str, context: str, task: str, tone: str) -> str:
    """Build the full XML system prompt from editable fields.

    The bounding-box format block and bridge are always injected from
    locked module-level constants and cannot be overridden by callers.
    """
    return (
        f"<system_instruction>\n    You are a {role.strip()}\n</system_instruction>\n"
        f"<context>\n  {context.strip()}\n</context>\n"
        f"<task>\n{task.strip()}\n</task>\n"
        f"<constraints>\n"
        f"{_LOCKED_FORMAT}\n"
        f"- Tone: {tone}\n"
        f"</constraints>\n"
        f"<bridge>\n    {_LOCKED_BRIDGE}\n</bridge>"
    )


_TAG_RE = {
    "role":    re.compile(r"<system_instruction>\s*You are a\s*(.*?)\s*</system_instruction>", re.DOTALL),
    "context": re.compile(r"<context>\s*(.*?)\s*</context>", re.DOTALL),
    "task":    re.compile(r"<task>\s*(.*?)\s*</task>", re.DOTALL),
    "tone":    re.compile(r"-\s*Tone:\s*(\w[\w ]*)", re.MULTILINE),
}


def parse_system_prompt(prompt_text: str) -> dict:
    """Extract editable fields from an existing XML system prompt.

    Falls back gracefully if tags are missing (e.g. legacy free-form prompts).
    Returns a dict with keys: role, context, task, tone.
    """
    result = {"role": "", "context": "", "task": "", "tone": "Professional"}
    any_match = False
    for key, pattern in _TAG_RE.items():
        m = pattern.search(prompt_text)
        if m:
            result[key] = m.group(1).strip()
            any_match = True
    # Legacy fallback: no XML tags found — treat entire text as task
    if not any_match and prompt_text.strip():
        result["task"] = prompt_text.strip()
    return result


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class DomainWizardDialog(QDialog):
    """User-friendly wizard for configuring the AI domain system prompt.

    Replaces the raw XML text editor with a guided form for non-technical
    users. An Advanced tab provides raw access for power users.

    The <constraints> bounding-box format and <bridge> are always locked
    and re-injected automatically — users cannot break them.
    """

    def __init__(self, parent=None, current_prompt: str = "", plugin_dir: str = ""):
        super().__init__(parent)
        self.plugin_dir = plugin_dir
        self._syncing = False  # guard against re-entrant signal loops
        self._final_prompt = ""
        self._build_ui()
        # Populate form from existing prompt (or leave blank for custom)
        if current_prompt.strip():
            self._populate_from_prompt(current_prompt)
        else:
            # Default to first preset (Archaeology)
            self._on_preset_changed(0)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle("Configure AI Domain")
        self.setMinimumSize(700, 580)
        self.resize(720, 620)

        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        outer.setContentsMargins(12, 12, 12, 12)

        # Header
        header = QLabel("Configure AI Domain")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
        sub = QLabel("Choose a domain preset or fill in the fields below to tailor the AI analysis.")
        sub.setStyleSheet("color: #666; font-size: 11px;")
        sub.setWordWrap(True)
        outer.addWidget(header)
        outer.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")
        outer.addWidget(sep)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_guided_tab(), "Guided")
        self._tabs.addTab(self._build_advanced_tab(), "Advanced")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self._tabs, stretch=1)

        # Buttons
        outer.addLayout(self._build_button_row())

    def _build_guided_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        # Domain preset
        row = QHBoxLayout()
        row.addWidget(QLabel("Domain Preset:"))
        self._preset_combo = QComboBox()
        for p in DOMAIN_PRESETS:
            self._preset_combo.addItem(p["label"])
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        row.addWidget(self._preset_combo, stretch=1)
        layout.addLayout(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")
        layout.addWidget(sep)

        # Expert Role
        layout.addWidget(self._make_field_label(
            "Expert Role",
            "The AI will be introduced as: \"You are a [role]\""
        ))
        self._role_edit = QLineEdit()
        self._role_edit.setPlaceholderText("e.g. world-class archaeologist")
        self._role_edit.textChanged.connect(self._on_guided_field_changed)
        layout.addWidget(self._role_edit)

        # Context / What to look for
        layout.addWidget(self._make_field_label(
            "What to look for",
            "Describe the type of data and features the AI should detect."
        ))
        self._context_edit = QTextEdit()
        self._context_edit.setPlaceholderText(
            "Describe the remote sensing data and the features to look for..."
        )
        self._context_edit.setFixedHeight(72)
        self._context_edit.textChanged.connect(self._on_guided_field_changed)
        layout.addWidget(self._context_edit)

        # Task description
        layout.addWidget(self._make_field_label(
            "Task Description",
            "What should the AI do with each image? What to return if nothing is found?"
        ))
        self._task_edit = QTextEdit()
        self._task_edit.setPlaceholderText(
            "Describe the detection task and the fallback message..."
        )
        self._task_edit.setFixedHeight(72)
        self._task_edit.textChanged.connect(self._on_guided_field_changed)
        layout.addWidget(self._task_edit)

        # Tone
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Response Tone:"))
        self._tone_combo = QComboBox()
        for t in TONE_OPTIONS:
            self._tone_combo.addItem(t)
        self._tone_combo.currentIndexChanged.connect(self._on_guided_field_changed)
        row2.addWidget(self._tone_combo)
        row2.addStretch()
        layout.addLayout(row2)

        # Live preview
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #dee2e6;")
        layout.addWidget(sep2)

        preview_label = QLabel("Live Preview  (gray sections are locked and auto-managed)")
        preview_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(preview_label)

        self._preview_edit = QTextEdit()
        self._preview_edit.setReadOnly(True)
        mono = QFont("Courier New")
        mono.setPointSize(8)
        self._preview_edit.setFont(mono)
        self._preview_edit.setFixedHeight(130)
        self._preview_edit.setStyleSheet("background: #f8f9fa; border: 1px solid #dee2e6;")
        layout.addWidget(self._preview_edit)

        return container

    def _build_advanced_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Warning banner
        warning = QLabel(
            "Power users only.  The bounding-box format block inside "
            "<constraints> is always protected — it will be restored "
            "automatically when you save."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background: #fff3cd; color: #856404; border: 1px solid #ffc107; "
            "border-radius: 4px; padding: 6px; font-size: 11px;"
        )
        layout.addWidget(warning)

        self._advanced_edit = QTextEdit()
        mono = QFont("Courier New")
        mono.setPointSize(9)
        self._advanced_edit.setFont(mono)
        self._advanced_edit.textChanged.connect(self._on_advanced_text_changed)
        layout.addWidget(self._advanced_edit, stretch=1)

        return container

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        reset_btn = QPushButton("Reset to Default")
        reset_btn.setStyleSheet(UIStyles.button_secondary())
        reset_btn.clicked.connect(self._on_reset_to_default)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(UIStyles.button_secondary())
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(UIStyles.button_primary())
        save_btn.clicked.connect(self._on_save)

        row.addWidget(reset_btn)
        row.addStretch()
        row.addWidget(cancel_btn)
        row.addSpacing(8)
        row.addWidget(save_btn)
        return row

    @staticmethod
    def _make_field_label(title: str, hint: str) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet("color: #888; font-size: 10px;")
        l.addWidget(title_lbl)
        l.addWidget(hint_lbl)
        return w

    # ------------------------------------------------------------------
    # Signal Handlers
    # ------------------------------------------------------------------

    def _on_preset_changed(self, index: int):
        if self._syncing:
            return
        self._syncing = True
        try:
            preset = DOMAIN_PRESETS[index]
            self._role_edit.setText(preset["role"])
            self._context_edit.setPlainText(preset["context"])
            self._task_edit.setPlainText(preset["task"])
            tone_idx = self._tone_combo.findText(preset["tone"])
            if tone_idx >= 0:
                self._tone_combo.setCurrentIndex(tone_idx)
            self._update_preview()
            self._sync_to_advanced()
        finally:
            self._syncing = False

    def _on_guided_field_changed(self):
        if self._syncing:
            return
        self._syncing = True
        try:
            self._update_preview()
            self._sync_to_advanced()
        finally:
            self._syncing = False

    def _on_advanced_text_changed(self):
        if self._syncing:
            return
        self._syncing = True
        try:
            raw = self._advanced_edit.toPlainText()
            parsed = parse_system_prompt(raw)
            self._role_edit.setText(parsed["role"])
            self._context_edit.setPlainText(parsed["context"])
            self._task_edit.setPlainText(parsed["task"])
            tone_idx = self._tone_combo.findText(parsed["tone"])
            if tone_idx >= 0:
                self._tone_combo.setCurrentIndex(tone_idx)
            self._update_preview()
        finally:
            self._syncing = False

    def _on_tab_changed(self, index: int):
        if self._syncing:
            return
        self._syncing = True
        try:
            if index == 1:  # switching TO Advanced
                self._sync_to_advanced()
            else:           # switching FROM Advanced
                raw = self._advanced_edit.toPlainText()
                parsed = parse_system_prompt(raw)
                self._role_edit.setText(parsed["role"])
                self._context_edit.setPlainText(parsed["context"])
                self._task_edit.setPlainText(parsed["task"])
                tone_idx = self._tone_combo.findText(parsed["tone"])
                if tone_idx >= 0:
                    self._tone_combo.setCurrentIndex(tone_idx)
                self._update_preview()
        finally:
            self._syncing = False

    # ------------------------------------------------------------------
    # Core Logic
    # ------------------------------------------------------------------

    def _sync_to_advanced(self):
        """Push assembled prompt into the Advanced tab editor (no signal loop)."""
        prompt = assemble_system_prompt(
            self._role_edit.text(),
            self._context_edit.toPlainText(),
            self._task_edit.toPlainText(),
            self._tone_combo.currentText(),
        )
        self._advanced_edit.blockSignals(True)
        self._advanced_edit.setPlainText(prompt)
        self._advanced_edit.blockSignals(False)

    def _update_preview(self):
        """Regenerate the live preview HTML in the Guided tab."""
        role = self._role_edit.text()
        context = self._context_edit.toPlainText()
        task = self._task_edit.toPlainText()
        tone = self._tone_combo.currentText()
        html = self._render_preview_html(role, context, task, tone)
        self._preview_edit.setHtml(html)

    def _render_preview_html(self, role: str, context: str, task: str, tone: str) -> str:
        """Build HTML for the preview, graying out locked sections."""
        def esc(t):
            return (t.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;").replace("\n", "<br>"))

        gray = "color:#aaaaaa; background:#f0f0f0;"
        normal = "color:#2c3e50;"

        locked_format_html = esc(_LOCKED_FORMAT).replace("  ", "&nbsp;&nbsp;")
        locked_bridge_html = esc(_LOCKED_BRIDGE)

        return (
            f'<pre style="font-family:Courier New; font-size:8pt; margin:0;">'
            f'<span style="{normal}">&lt;system_instruction&gt;<br>'
            f'    You are a {esc(role)}<br>'
            f'&lt;/system_instruction&gt;<br>'
            f'&lt;context&gt;<br>'
            f'  {esc(context)}<br>'
            f'&lt;/context&gt;<br>'
            f'&lt;task&gt;<br>'
            f'{esc(task)}<br>'
            f'&lt;/task&gt;<br>'
            f'&lt;constraints&gt;<br>'
            f'</span>'
            f'<span style="{gray}">{locked_format_html}<br></span>'
            f'<span style="{normal}">- Tone: {esc(tone)}<br>'
            f'&lt;/constraints&gt;<br>'
            f'</span>'
            f'<span style="{gray}">&lt;bridge&gt;<br>'
            f'    {locked_bridge_html}<br>'
            f'&lt;/bridge&gt;</span>'
            f'</pre>'
        )

    def _populate_from_prompt(self, prompt_text: str):
        """Parse an existing prompt and fill all form fields."""
        parsed = parse_system_prompt(prompt_text)
        self._syncing = True
        try:
            self._role_edit.setText(parsed["role"])
            self._context_edit.setPlainText(parsed["context"])
            self._task_edit.setPlainText(parsed["task"])
            tone_idx = self._tone_combo.findText(parsed["tone"])
            if tone_idx >= 0:
                self._tone_combo.setCurrentIndex(tone_idx)
            # Select matching preset in dropdown (or Custom)
            preset_idx = self._detect_matching_preset(
                parsed["role"], parsed["context"], parsed["task"]
            )
            self._preset_combo.setCurrentIndex(preset_idx)
            self._update_preview()
            self._sync_to_advanced()
        finally:
            self._syncing = False

    def _detect_matching_preset(self, role: str, context: str, task: str) -> int:
        """Return index of the best matching preset, or Custom index."""
        custom_idx = len(DOMAIN_PRESETS) - 1  # Custom is always last
        for i, p in enumerate(DOMAIN_PRESETS):
            if p["id"] == "custom":
                continue
            if (p["role"].strip() == role.strip() and
                    p["context"].strip() == context.strip() and
                    p["task"].strip() == task.strip()):
                return i
        return custom_idx

    def _get_current_prompt(self) -> str:
        """Assemble the final prompt, always re-injecting locked sections."""
        if self._tabs.currentIndex() == 1:
            # Advanced tab: parse what's there, then reassemble to restore locks
            raw = self._advanced_edit.toPlainText()
            parsed = parse_system_prompt(raw)
            return assemble_system_prompt(
                parsed["role"], parsed["context"], parsed["task"], parsed["tone"]
            )
        return assemble_system_prompt(
            self._role_edit.text(),
            self._context_edit.toPlainText(),
            self._task_edit.toPlainText(),
            self._tone_combo.currentText(),
        )

    # ------------------------------------------------------------------
    # Button Actions
    # ------------------------------------------------------------------

    def _on_save(self):
        role = self._role_edit.text().strip()
        task = self._task_edit.toPlainText().strip()
        missing = []
        if not role:
            missing.append("Expert Role")
        if not task:
            missing.append("Task Description")
        if missing:
            QMessageBox.warning(
                self,
                "Missing Fields",
                f"Please fill in the following required fields:\n\n• " + "\n• ".join(missing)
            )
            return
        self._final_prompt = self._get_current_prompt()
        self.accept()

    def _on_reset_to_default(self):
        default_file = os.path.join(self.plugin_dir, "defaultSystemprompt.txt")
        if not os.path.exists(default_file):
            QMessageBox.warning(self, "Not Found", "Default system prompt file not found.")
            return
        resp = QMessageBox.question(
            self,
            "Reset to Default",
            "This will replace your current settings with the original Archaeology defaults.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        try:
            with open(default_file, "r", encoding="utf-8") as f:
                default_text = f.read()
            self._populate_from_prompt(default_text)
        except Exception as e:
            logger.error(f"Error reading default prompt: {e}")
            QMessageBox.warning(self, "Error", f"Could not read default prompt: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_prompt(self) -> str:
        """Return the assembled prompt. Call after exec_() == QDialog.Accepted."""
        return self._final_prompt
