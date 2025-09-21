# -*- coding: utf-8 -*-
"""
Tutorial Dialog Text Resources

This module contains all the text content for the tutorial dialog,
separated from the UI code for better maintainability and potential localization.
"""

# Window and Header Texts
WINDOW_TITLE = "Welcome to LandTalk.AI"
WELCOME_TITLE = "Welcome to LandTalk.AI!"
WELCOME_SUBTITLE = "Your Landscape Talks With You - using AI"
WELCOME_DESCRIPTION = (
    "This tutorial will help you get started with LandTalk.AI. "
    "Learn how to analyze map areas using AI and discover tips for better results."
)

# Tab Names
TAB_GETTING_STARTED = "Getting Started"
TAB_TIPS_TRICKS = "Tips and Tricks"
TAB_FAQ = "FAQ"

# Getting Started Tab Content
GETTING_STARTED_CONTENT = """
<h2>Step 1: Set Up Your API Keys</h2>
<p>Before you can use LandTalk.AI, you need to register with Google Gemini and/or OpenAI and then get an API key:</p>
<ul>
    <li><b>Google Gemini:</b> Visit <a href='https://makersuite.google.com/app/apikey'>Google AI Studio</a> to get your free API key</li>
    <li><b>OpenAI GPT:</b> Visit <a href='https://platform.openai.com/api-keys'>OpenAI Platform</a> to get your API key</li>
</ul>
<p>Once you have your key, click the <b>Options</b> button in the LandTalk.AI panel and select the appropriate key option to enter it.<br>
Recommendation: try both AI providers to see which one works best for your use case.</p>

<h2>Step 2: Basic Workflow</h2>
<p>The basic workflow for using LandTalk.AI is simple:</p>
<ol>
    <li><b>Select an area:</b> Click 'Select area' and draw a rectangle on your map</li>
    <li><b>Add a message (optional):</b> Explain in more detail what you want to analyze in the text box</li>
    <li><b>Choose AI model (optional):</b> Select from Gemini or GPT models in the dropdown</li>
    <li><b>Analyze:</b> Click 'Analyze' to send your request to the AI</li>
    <li><b>View results:</b> The AI will create map layers in a new group called 'LandTalk.ai' showing detected features</li>
</ol>

<h2>Step 3: Understanding Results</h2>
<p>When the AI analyzes your map area, it will:</p>
<ul>
    <li><b>Create map layers:</b> Each detected feature becomes a separate layer in the 'LandTalk.ai' group</li>
    <li><b>Show confidence scores:</b> Each feature includes a confidence percentage (0-100)</li>
    <li><b>Provide explanations:</b> The AI explains why it identified each feature</li>
    <li><b>Display labels:</b> Feature names and confidence scores are shown on the map</li>
    <li><b>Results layers:</b> all new map layers are stored as GeoPackages (gpkg) in a directory LandTalk.ai where your project file is located. Feel free to delete unused layers</li>
</ul>
"""

# Tips & Tricks Tab Content
TIPS_TRICKS_CONTENT = """
<h2>⭐ Tips for Better Results</h2>
<p>To get the best results from LandTalk.AI:</p>
<ul>
    <li><b>Adjust confidence threshold:</b> filter out low-confidence detections if needed. 80% makes a good starting point but try different values</li>
    <li><b>Adjust resolution:</b> Higher resolution works better for detailed analysis</li>
    <li><b>Add messages (prompts):</b> Asking more specifically for features you are interested in will guide the AI (e.g., 'Focus on medieval features')</li>
    <li><b>Try different models:</b> Gemini and GPT may give different results, so often it is worth trying several models</li>
    <li><b>Have a longer chat:</b> discuss the AI response across several chat steps to refine the results</li>
</ul>

<h2>💡 Customizing AI Behavior with Rules</h2>
<p>One of LandTalk.AI's most powerful features is the ability to customize how the AI analyzes your maps:</p>
<ul>
    <li><b>Access Rules:</b> Click the 'Rules' button in the LandTalk.AI panel</li>
    <li><b>Edit Instructions:</b> Modify the roles there (called "system prompt" to change how the AI behaves across all your requests</li>
    <li><b>Specialize Analysis:</b> Add instructions for specific types of analysis. If you do not work in Archaeology, change the text so that it matches your interests</li>
    <li><b>Add Context:</b> Include information about your specific use case or region</li>
</ul>
<p><b>Example customizations:</b></p>
<ul>
    <li>'Always identify building types and construction materials'</li>
    <li>'Focus on environmental features like water bodies and vegetation'</li>
    <li>'Provide detailed explanations for each detected feature'</li>
    <li>'Use specific terminology for urban planning analysis'</li>
</ul>

"""

# FAQ Tab Content
FAQ_CONTENT = """
<h3>Q1: What types of features can LandTalk.AI detect?</h3>
<p>LandTalk.AI can detect a wide variety of landscape features including buildings, roads, water bodies, vegetation, agricultural areas, infrastructure, and more. The specific features depend on the AI model used and your custom rules.</p>

<h3>Q2: How accurate are the AI detections?</h3>
<p>Accuracy varies depending on image quality, feature clarity, and AI model. Each detection includes a confidence score. You can adjust the confidence threshold to show only high-confidence detections.</p>

<h3>Q3: Can I use both Gemini and GPT models?</h3>
<p>Yes! You can switch between different AI models using the dropdown menu. Each model may provide different insights and detection capabilities.</p>

<h3>Q4: How do I get better results?</h3>
<p>For better results: select clear, well-defined areas; use appropriate resolution settings; be specific in your prompts; try different AI models; and customize the rules for your specific use case.</p>

<h3>Q5: What if the AI doesn't detect what I'm looking for?</h3>
<p>Try adjusting your prompt to be more specific, lower the confidence threshold, try a different AI model, or customize the rules to focus on the features you're interested in.</p>

<h3>Q6: Can I save my analysis results?</h3>
<p>Yes! All analysis results are saved as GeoPackage files in the 'LandTalk.AI analysis' directory next to your QGIS project file. The layers are also added to your QGIS project.</p>

<h3>Q7: How do I customize the AI behavior?</h3>
<p>Click the 'Rules' button to edit the system prompt. This allows you to customize how the AI analyzes your maps, what features to focus on, and how to structure the output.</p>

<h3>Q8: What if I get an API key error?</h3>
<p>Make sure you've entered a valid API key in the Options menu. Check that your API key has the necessary permissions and that you have sufficient credits/quota remaining.</p>

<h3>Q9: Can I analyze the same area multiple times?</h3>
<p>Yes! You can continue conversations about the same area by adding new messages. The AI will remember the previous context and build upon it.</p>

<h3>Q10: How do I remove old analysis results?</h3>
<p>You can delete individual layers from the 'LandTalk.ai' group in QGIS, or delete the entire group to remove all analysis results. The files in the analysis directory can also be deleted manually.</p>
"""

# Button and UI Texts
DONT_SHOW_AGAIN_TEXT = "Don't show this tutorial again"
CLOSE_BUTTON_TEXT = "Close"
