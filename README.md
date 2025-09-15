# QGIS LLM Image Analysis Plugin

 A QGIS plugin that allows users to analyze map areas using Google's Gemini multimodal AI. This plugin has been upgraded to PyQt6 for compatibility with QGIS 3.40+.

 ## Features

 - Select a rectangular area of your map
 - Capture the selected area as an image
 - Send the image along with a text prompt to Google Gemini API
 - View the AI analysis results

 ## Requirements

- QGIS 3.40 or later (PyQt6)
- Google Gemini API key
- OpenAI GPT API key (optional, for GPT analysis)
- Python packages (install in QGIS Python environment):
  - `requests>=2.25.0` (for API calls)

## Installation

1. Download the plugin folder
2. Install required Python packages in your QGIS Python environment:
   ```bash
   # Using pip (adjust path to your QGIS Python installation)
   pip install requests>=2.25.0
   
   # Or install from requirements.txt
   pip install -r requirements.txt
   ```
3. Copy the `LandTalk` folder to your QGIS plugins directory:
   - Windows: `C:\Users\{username}\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins`
4. Open QGIS and enable the plugin from Plugins > Manage and Install Plugins

 ## Usage

 1. Click the Gemini Image Analysis icon in the QGIS toolbar
 2. Enter your Google Gemini API key when prompted (only required once per session)
 3. Draw a rectangle on the map to select the area you want to analyze
 4. Enter a text prompt in the dialog that appears
 5. Click "Analyze with Gemini" to send the request
 6. View the analysis results in the lower part of the dialog

 ## Obtaining a Google Gemini API Key

 1. Visit the [Google AI Studio](https://makersuite.google.com/)
 2. Sign in with your Google account
 3. Go to the API keys section and create a new API key
 4. Copy the API key and use it in the plugin

 ## License

 This plugin is released under the GPL v2 license.

 ## Support

 For issues or feature requests, please contact the developer.
