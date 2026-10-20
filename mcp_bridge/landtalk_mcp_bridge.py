#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.2.0,<2"]
# ///
# -*- coding: utf-8 -*-
"""
LandTalk.AI MCP bridge.

Standalone process - NOT imported by QGIS, and does not need QGIS's own
Python environment. Launched over stdio by an MCP host (Claude Desktop,
Claude Code, ...), e.g. via `uv run landtalk_mcp_bridge.py`.

It forwards every tool call over a local TCP socket to the LandTalk MCP
server running inside QGIS (see landtalk_mcp_server.py, started from the
"LandTalk MCP Server" dock widget in the plugin's menu), and relays the
JSON response back as the tool's result.

Configure the MCP host to launch this script with these environment
variables set:
  LANDTALK_MCP_HOST   default "127.0.0.1"
  LANDTALK_MCP_PORT   default 9877
  LANDTALK_MCP_TOKEN  required - copy from the LandTalk MCP Server dock widget in QGIS
"""

import json
import os
import socket
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

try:
    from mcp.server.fastmcp import Image
except ImportError:  # pragma: no cover - depends on installed mcp[cli] version
    Image = None

mcp = FastMCP("LandTalk.AI")

HOST = os.environ.get("LANDTALK_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("LANDTALK_MCP_PORT", "9877"))
TOKEN = os.environ.get("LANDTALK_MCP_TOKEN", "")

CONNECT_TIMEOUT_S = 10
# analyze_image_with_ai proxies an outbound HTTP call to an AI provider inside QGIS,
# which can legitimately take a while - give it more room than a plain capture/query.
RESPONSE_TIMEOUT_S = 120


class LandTalkConnectionError(RuntimeError):
    """Raised when the bridge can't reach, or gets an error from, the in-QGIS MCP server."""


def send_command(command: str, params: Optional[dict] = None) -> dict:
    """Send one newline-delimited JSON request to the in-QGIS LandTalk MCP server
    and return its parsed 'result'. Raises LandTalkConnectionError on any failure."""
    if not TOKEN:
        raise LandTalkConnectionError(
            "LANDTALK_MCP_TOKEN is not set. Open the 'LandTalk MCP Server' dock widget in "
            "QGIS, start the server, and copy its token into this bridge's environment/config."
        )

    request = {"type": command, "params": params or {}, "token": TOKEN}
    payload = (json.dumps(request) + "\n").encode("utf-8")

    try:
        with socket.create_connection((HOST, PORT), timeout=CONNECT_TIMEOUT_S) as sock:
            sock.sendall(payload)
            sock.settimeout(RESPONSE_TIMEOUT_S)
            buffer = b""
            while b"\n" not in buffer:
                chunk = sock.recv(65536)
                if not chunk:
                    raise LandTalkConnectionError("QGIS closed the connection before sending a response")
                buffer += chunk
            line, _ = buffer.split(b"\n", 1)
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        raise LandTalkConnectionError(
            f"Could not reach the LandTalk MCP server at {HOST}:{PORT} - "
            f"is it started in QGIS? ({e})"
        ) from e

    response = json.loads(line.decode("utf-8"))
    if not response.get("success"):
        raise LandTalkConnectionError(response.get("error", "Unknown error from LandTalk MCP server"))
    return response.get("result", {})


# ----------------------------------------------------------------------
# connectivity / info
# ----------------------------------------------------------------------

@mcp.tool()
def ping() -> dict:
    """Check whether the LandTalk MCP server running inside QGIS is reachable."""
    return send_command("ping")


@mcp.tool()
def get_qgis_info() -> dict:
    """Get the running QGIS and LandTalk plugin versions."""
    return send_command("get_qgis_info")


@mcp.tool()
def get_project_info() -> dict:
    """Get info about the currently open QGIS project: file name, title, layer count, CRS."""
    return send_command("get_project_info")


# ----------------------------------------------------------------------
# specifying an area of interest
# ----------------------------------------------------------------------

@mcp.tool()
def get_current_extent() -> dict:
    """Get the map extent (xmin, ymin, xmax, ymax, crs) currently visible in the QGIS canvas."""
    return send_command("get_current_extent")


@mcp.tool()
def get_selected_extent() -> dict:
    """
    Get the extent of the map area a human last selected in QGIS with the rectangle-select
    tool ("Select area"). Falls back to the current canvas view if nothing was manually
    selected. Use this to pick up exactly what a person pointed at, instead of guessing
    coordinates yourself.
    """
    return send_command("get_selected_extent")


@mcp.tool()
def get_layer_extent(layer_name: str) -> dict:
    """Get the bounding extent of an existing QGIS layer by name."""
    return send_command("get_layer_extent", {"layer_name": layer_name})


# ----------------------------------------------------------------------
# map capture
# ----------------------------------------------------------------------

@mcp.tool()
def capture_map_area(xmin: float, ymin: float, xmax: float, ymax: float,
                      ground_resolution_m_per_px: Optional[float] = None):
    """
    Render the given map extent (in the project's CRS) to a PNG, at a controlled ground
    resolution in meters/pixel (omit to use the plugin's configured default), for visual
    inspection or object-detection reasoning.

    This also becomes LandTalk's "last capture": create_layers_from_json (with
    use_last_capture=true, the default) and analyze_image_with_ai both operate on it.

    The output size is capped (~8 million pixels total); a request that would exceed it
    fails with a message suggesting a coarser ground_resolution_m_per_px or a smaller area.
    """
    result = send_command("capture_map_area", {
        "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
        "ground_resolution_m_per_px": ground_resolution_m_per_px,
    })
    metadata = {k: v for k, v in result.items() if k not in ("image_base64", "mime_type")}
    if Image is not None:
        import base64
        return [Image(data=base64.b64decode(result["image_base64"]), format="png"), metadata]
    # Fallback for older mcp[cli] versions without the Image content helper.
    return result


# ----------------------------------------------------------------------
# generic layer inspection
# ----------------------------------------------------------------------

@mcp.tool()
def get_layers() -> dict:
    """List all layers currently loaded in the QGIS project."""
    return send_command("get_layers")


@mcp.tool()
def get_layer_features(layer_name: str, limit: int = 50) -> dict:
    """Get up to `limit` features (attributes + WKT geometry) from a QGIS layer by name."""
    return send_command("get_layer_features", {"layer_name": layer_name, "limit": limit})


@mcp.tool()
def zoom_to_layer(layer_name: str) -> dict:
    """Zoom the QGIS map canvas to the extent of a layer by name."""
    return send_command("zoom_to_layer", {"layer_name": layer_name})


# ----------------------------------------------------------------------
# optional delegated AI reasoning (distinct from this MCP client's own model)
# ----------------------------------------------------------------------

@mcp.tool()
def analyze_image_with_ai(model: Optional[str] = None, prompt: Optional[str] = None,
                           provider: Optional[str] = None) -> dict:
    """
    Delegate object-detection reasoning over the last captured image (see capture_map_area)
    to a specific AI provider/model - e.g. "gemini-3.5-flash", "gpt-5.5", "claude-sonnet-4-6" -
    using LandTalk's own tuned system prompt and stored API key, instead of reasoning over the
    image yourself. Use this when the detection step should run on a specific model, separate
    from whichever model is driving this conversation (provider is inferred from the model
    name prefix if omitted).

    If model is omitted, uses whatever model is currently selected in the LandTalk dock
    widget in QGIS (or the last one selected there, if the widget isn't open).

    Returns json_data: a list of detections, each shaped like
      {"box_2d": [ymin, xmin, ymax, xmax] (integers, 0-1000, normalized to the captured image),
       "label": str, "probability": <0-100>, "reason": str}
    (or {"point": [y, x]} instead of box_2d for point features). Feed json_data straight into
    create_layers_from_json.
    """
    params: dict[str, Any] = {}
    if model:
        params["model"] = model
    if prompt:
        params["prompt"] = prompt
    if provider:
        params["provider"] = provider
    return send_command("analyze_image_with_ai", params)


# ----------------------------------------------------------------------
# detections -> QGIS layers
# ----------------------------------------------------------------------

@mcp.tool()
def create_layers_from_json(detections: list, provider: str = "mcp-client",
                             model_name: Optional[str] = None,
                             confidence_threshold: Optional[float] = None,
                             use_last_capture: bool = True,
                             xmin: Optional[float] = None, ymin: Optional[float] = None,
                             xmax: Optional[float] = None, ymax: Optional[float] = None) -> dict:
    """
    Turn a list of detections into QGIS vector layers, grouped under the "LandTalk.ai" layer
    tree group. Detections below confidence_threshold (percent; default is LandTalk's own
    configured threshold) are dropped. Each detection must match the schema documented in
    analyze_image_with_ai's docstring - this works whether that JSON came from
    analyze_image_with_ai or from your own reasoning over a capture_map_area image.

    By default (use_last_capture=true) coordinates are converted using the extent from the
    most recent capture_map_area call. Pass use_last_capture=false with xmin/ymin/xmax/ymax
    to use an explicit extent instead.
    """
    params: dict[str, Any] = {
        "detections": detections,
        "provider": provider,
        "model_name": model_name,
        "confidence_threshold": confidence_threshold,
        "use_last_capture": use_last_capture,
    }
    if not use_last_capture:
        if None in (xmin, ymin, xmax, ymax):
            raise ValueError("xmin, ymin, xmax, ymax are required when use_last_capture=False")
        params["extent"] = {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
    return send_command("create_layers_from_json", params)


@mcp.tool()
def list_analysis_layers() -> dict:
    """List the layer groups/layers LandTalk has created under the "LandTalk.ai" group."""
    return send_command("list_analysis_layers")


if __name__ == "__main__":
    mcp.run()
