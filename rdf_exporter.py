# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LandTalk.AI - RDF Exporter
                                 A QGIS Plugin
 Export analysis results to RDF/Turtle format
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
 ***************************************************************************/

RDF/Turtle Exporter for LandTalk Plugin

This module exports AI analysis results to RDF/Turtle format following
semantic web standards including PROV-O, DCAT, CIDOC CRM, and GeoSPARQL.

This implementation generates TTL format without requiring rdflib.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from qgis.core import QgsProject, QgsLayerTreeGroup

from .logging import logger

# rdflib is not required - we generate TTL manually
RDFLIB_AVAILABLE = True  # Always available since we don't use rdflib


@dataclass(frozen=True)
class RunMeta:
    """Metadata for an analysis run"""
    base_uri: str
    run_local_id: str
    dataset_title: str
    dataset_description: str
    dataset_created: str  # ISO datetime string
    activity_started: str  # ISO datetime string
    activity_ended: str  # ISO datetime string
    ai_provider: str
    model_version: str
    license_iri: Optional[str] = None
    creator_iri: Optional[str] = None


@dataclass(frozen=True)
class FeatureRow:
    """A single feature/detection from AI analysis"""
    fid: Union[int, str]
    label: str
    reason: str
    confidence: Union[int, float]
    geometry_wkt: str
    geometry_crs: Optional[str] = None


def _require_nonempty(value: Any, name: str) -> None:
    """Validate that a value is not empty"""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Missing/empty required parameter: {name}")


def _escape_turtle_string(s: str) -> str:
    """Escape special characters for Turtle string literals"""
    if s is None:
        return ""
    # Escape backslashes first, then quotes and newlines
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s


def _safe_local_id(s: str) -> str:
    """Sanitize local ID for use in URIs"""
    # Remove or replace characters that are not valid in URIs
    s = s.strip()
    # Replace spaces and special chars with underscores
    s = re.sub(r'[^\w\-.]', '_', s)
    return s


class TurtleWriter:
    """Simple Turtle/TTL format writer without rdflib dependency"""

    def __init__(self):
        self.prefixes: Dict[str, str] = {}
        self.triples: List[str] = []

    def bind(self, prefix: str, namespace: str) -> None:
        """Add a namespace prefix binding"""
        self.prefixes[prefix] = namespace

    def add_triple(self, subject: str, predicate: str, obj: str) -> None:
        """Add a triple (subject, predicate, object)"""
        self.triples.append(f"{subject} {predicate} {obj} .")

    def uri(self, namespace_prefix: str, local_name: str) -> str:
        """Create a prefixed URI reference"""
        return f"{namespace_prefix}:{local_name}"

    def full_uri(self, uri: str) -> str:
        """Create a full URI reference"""
        return f"<{uri}>"

    def literal(self, value: str, lang: Optional[str] = None, datatype: Optional[str] = None) -> str:
        """Create a literal value"""
        escaped = _escape_turtle_string(str(value))
        if lang:
            return f'"{escaped}"@{lang}'
        elif datatype:
            return f'"{escaped}"^^{datatype}'
        else:
            return f'"{escaped}"'

    def serialize(self) -> str:
        """Serialize the graph to Turtle format"""
        lines = []

        # Add prefix declarations
        for prefix, namespace in sorted(self.prefixes.items()):
            lines.append(f"@prefix {prefix}: <{namespace}> .")

        lines.append("")  # Empty line after prefixes

        # Add triples
        lines.extend(self.triples)

        return "\n".join(lines)


def export_qgis_ai_ttl(
    run_meta: Union[RunMeta, Dict[str, Any]],
    features: Sequence[Union[FeatureRow, Dict[str, Any]]],
    out_path: Union[str, Path],
) -> Path:
    """
    Create RDF graph and serialize to Turtle.

    Parameters
    ----------
    run_meta:
        RunMeta dataclass OR dict with run metadata
    features:
        List/sequence of FeatureRow OR dicts with feature data
    out_path:
        Path to write TTL file

    Returns
    -------
    Path to written TTL file
    """
    # Coerce/validate run_meta
    if isinstance(run_meta, dict):
        rm = RunMeta(**run_meta)
    else:
        rm = run_meta

    # Required run-level fields
    _require_nonempty(rm.base_uri, "run_meta.base_uri")
    _require_nonempty(rm.run_local_id, "run_meta.run_local_id")
    _require_nonempty(rm.dataset_title, "run_meta.dataset_title")
    _require_nonempty(rm.dataset_description, "run_meta.dataset_description")
    _require_nonempty(rm.dataset_created, "run_meta.dataset_created")
    _require_nonempty(rm.activity_started, "run_meta.activity_started")
    _require_nonempty(rm.activity_ended, "run_meta.activity_ended")
    _require_nonempty(rm.ai_provider, "run_meta.ai_provider")
    _require_nonempty(rm.model_version, "run_meta.model_version")

    run_id = _safe_local_id(rm.run_local_id)

    # Coerce/validate features
    feature_rows: List[FeatureRow] = []
    for i, f in enumerate(features):
        if isinstance(f, dict):
            fr = FeatureRow(**f)
        else:
            fr = f

        _require_nonempty(fr.fid, f"features[{i}].fid")
        _require_nonempty(fr.label, f"features[{i}].label")
        _require_nonempty(fr.reason, f"features[{i}].reason")
        _require_nonempty(fr.confidence, f"features[{i}].confidence")
        _require_nonempty(fr.geometry_wkt, f"features[{i}].geometry_wkt")
        feature_rows.append(fr)

    # Create Turtle writer
    g = TurtleWriter()

    # Define namespaces
    base_uri = rm.base_uri.rstrip("/") + "/"
    g.bind("ex", base_uri)
    g.bind("geo", "http://www.opengis.net/ont/geosparql#")
    g.bind("sf", "http://www.opengis.net/ont/sf#")
    g.bind("prov", "http://www.w3.org/ns/prov#")
    g.bind("dcat", "http://www.w3.org/ns/dcat#")
    g.bind("dct", "http://purl.org/dc/terms/")
    g.bind("datacite", "http://purl.org/spar/datacite/")
    g.bind("crm", "http://www.cidoc-crm.org/cidoc-crm/")
    g.bind("dig", "http://www.cidoc-crm.org/extensions/crmdig/")
    g.bind("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
    g.bind("xsd", "http://www.w3.org/2001/XMLSchema#")

    # Run-level nodes (underscore naming)
    dataset = g.uri("ex", f"dataset_{run_id}")
    identifier = g.uri("ex", f"identifier_{run_id}")
    activity = g.uri("ex", f"activity_{run_id}")
    agent = g.uri("ex", f"agent_{run_id}")

    # DCAT + CIDOC class layer for dataset
    g.add_triple(dataset, "rdf:type", "dcat:Dataset")
    g.add_triple(dataset, "rdf:type", "crm:E73_Information_Object")
    g.add_triple(dataset, "dct:title", g.literal(rm.dataset_title, lang="en"))
    g.add_triple(dataset, "dct:description", g.literal(rm.dataset_description, lang="en"))
    g.add_triple(dataset, "dct:created", g.literal(rm.dataset_created, datatype="xsd:dateTime"))

    if rm.license_iri:
        g.add_triple(dataset, "dct:license", g.full_uri(rm.license_iri))
    if rm.creator_iri:
        g.add_triple(dataset, "dct:creator", g.full_uri(rm.creator_iri))

    # DataCite identifier (+ optional CIDOC identifier typing)
    g.add_triple(dataset, "datacite:hasIdentifier", identifier)
    g.add_triple(identifier, "rdf:type", "datacite:Identifier")
    g.add_triple(identifier, "rdf:type", "crm:E42_Identifier")
    g.add_triple(identifier, "datacite:hasIdentifierValue", g.literal(run_id))

    # PROV activity + CRMdig execution typing
    g.add_triple(activity, "rdf:type", "prov:Activity")
    g.add_triple(activity, "rdf:type", "dig:D10_Software_Execution")
    g.add_triple(activity, "prov:startedAtTime", g.literal(rm.activity_started, datatype="xsd:dateTime"))
    g.add_triple(activity, "prov:endedAtTime", g.literal(rm.activity_ended, datatype="xsd:dateTime"))
    g.add_triple(activity, "prov:used", dataset)

    # Correct PROV relation
    g.add_triple(activity, "prov:wasAssociatedWith", agent)

    g.add_triple(agent, "rdf:type", "prov:SoftwareAgent")
    g.add_triple(agent, "dct:title", g.literal("LandTalk.AI QGIS Plugin", lang="en"))

    # Model/provider as explicit fields
    g.add_triple(activity, "ex:aiProvider", g.literal(rm.ai_provider))
    g.add_triple(activity, "ex:modelUsed", g.literal(rm.model_version))

    # Human-readable note
    g.add_triple(
        activity,
        "dct:description",
        g.literal(f"AI provider: {rm.ai_provider}; model version: {rm.model_version}", lang="en")
    )

    # Feature-level nodes
    for fr in feature_rows:
        fid_str = str(fr.fid)

        feature = g.uri("ex", f"feature_{run_id}_{fid_str}")
        geometry = g.uri("ex", f"geometry_{run_id}_{fid_str}")
        assignment = g.uri("ex", f"assignment_{run_id}_{fid_str}")

        # Feature: GeoSPARQL + CIDOC class layer
        g.add_triple(feature, "rdf:type", "geo:Feature")
        g.add_triple(feature, "rdf:type", "crm:E24_Physical_Human_Made_Thing")
        g.add_triple(feature, "dct:identifier", g.literal(fid_str))
        g.add_triple(feature, "dct:title", g.literal(fr.label, lang="en"))
        g.add_triple(feature, "geo:hasGeometry", geometry)
        g.add_triple(feature, "prov:wasGeneratedBy", activity)

        # Geometry: GeoSPARQL
        g.add_triple(geometry, "rdf:type", "geo:Geometry")
        g.add_triple(geometry, "rdf:type", "sf:Polygon")
        g.add_triple(geometry, "geo:asWKT", g.literal(fr.geometry_wkt, datatype="geo:wktLiteral"))

        if fr.geometry_crs:
            g.add_triple(geometry, "dct:description", g.literal(f"CRS: {fr.geometry_crs}", lang="en"))

        # Attribute assignment: CIDOC class layer + link to feature + PROV provenance
        g.add_triple(assignment, "rdf:type", "crm:E13_Attribute_Assignment")
        g.add_triple(assignment, "crm:P141_assigned", feature)
        g.add_triple(assignment, "crm:P3_has_note", g.literal(fr.reason, lang="en"))
        g.add_triple(assignment, "crm:P3_has_note", g.literal(f"Confidence: {fr.confidence}"))
        g.add_triple(assignment, "prov:wasGeneratedBy", activity)

        # Structured confidence
        g.add_triple(feature, "ex:confidenceScore", g.literal(str(fr.confidence)))

    # Write TTL
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ttl_content = g.serialize()
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(ttl_content)

    return out_path


class RDFExporter:
    """RDF Exporter for LandTalk.AI plugin"""

    GROUP_NAME = "LandTalk.ai"
    BASE_URI = "https://w3id.org/landtalk-ai/"

    def __init__(self, plugin):
        """Initialize the RDF exporter

        Args:
            plugin: LandTalkPlugin instance
        """
        self.plugin = plugin

    def get_project_directory(self) -> Optional[str]:
        """Get the project directory for saving RDF files"""
        project = QgsProject.instance()
        project_path = project.fileName()

        if not project_path:
            logger.warning("Project is not saved, cannot determine project directory")
            return None

        return os.path.dirname(project_path)

    def collect_features_from_group(self, group: QgsLayerTreeGroup) -> List[Dict[str, Any]]:
        """Collect all features from layers in a group

        Args:
            group: QgsLayerTreeGroup to collect features from

        Returns:
            List of feature dictionaries
        """
        features = []
        fid_counter = 1

        try:
            for layer_tree_layer in group.findLayers():
                layer = layer_tree_layer.layer()
                if not layer or not layer.isValid():
                    continue

                # Get CRS for this layer
                crs = layer.crs().authid() if layer.crs() else None

                # Iterate through features in the layer
                for qgs_feature in layer.getFeatures():
                    try:
                        # Get geometry as WKT
                        geom = qgs_feature.geometry()
                        if geom.isNull():
                            continue

                        geometry_wkt = geom.asWkt()

                        # Get attributes
                        attrs = qgs_feature.attributes()
                        field_names = [f.name() for f in layer.fields()]
                        attr_dict = dict(zip(field_names, attrs))

                        # Extract relevant fields
                        label = attr_dict.get('label', layer.name())
                        reason = attr_dict.get('reason', 'No reason provided')
                        confidence = attr_dict.get('confidence', 50.0)

                        # Handle confidence conversion
                        try:
                            confidence = float(confidence)
                        except (ValueError, TypeError):
                            confidence = 50.0

                        feature_data = {
                            'fid': fid_counter,
                            'label': str(label) if label else f'Feature_{fid_counter}',
                            'reason': str(reason) if reason else 'No reason provided',
                            'confidence': confidence,
                            'geometry_wkt': geometry_wkt,
                            'geometry_crs': crs
                        }
                        features.append(feature_data)
                        fid_counter += 1

                    except Exception as e:
                        logger.error(f"Error processing feature: {str(e)}")
                        continue

            # Recursively collect from subgroups
            for child in group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    features.extend(self.collect_features_from_group(child))

        except Exception as e:
            logger.error(f"Error collecting features from group: {str(e)}")

        return features

    def get_analysis_metadata(self, group: QgsLayerTreeGroup) -> Dict[str, Any]:
        """Extract metadata from the analysis group

        Args:
            group: QgsLayerTreeGroup to extract metadata from

        Returns:
            Dictionary with metadata
        """
        ai_provider = "unknown"
        model_name = "unknown"
        response_timestamp = None

        try:
            # Look for metadata in layer attributes
            for layer_tree_layer in group.findLayers():
                layer = layer_tree_layer.layer()
                if not layer or not layer.isValid():
                    continue

                # Get first feature to extract metadata
                for qgs_feature in layer.getFeatures():
                    attrs = qgs_feature.attributes()
                    field_names = [f.name() for f in layer.fields()]
                    attr_dict = dict(zip(field_names, attrs))

                    if 'ai_provider' in attr_dict and attr_dict['ai_provider']:
                        ai_provider = str(attr_dict['ai_provider'])
                    if 'model_name' in attr_dict and attr_dict['model_name']:
                        model_name = str(attr_dict['model_name'])
                    if 'response_timestamp' in attr_dict and attr_dict['response_timestamp']:
                        response_timestamp = str(attr_dict['response_timestamp'])

                    # Only need first feature for metadata
                    break

                if ai_provider != "unknown":
                    break

        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")

        return {
            'ai_provider': ai_provider,
            'model_name': model_name,
            'response_timestamp': response_timestamp
        }

    def export_to_ttl(self) -> Optional[str]:
        """Export all LandTalk.ai analysis results to TTL format

        Returns:
            Path to the created TTL file, or None on error
        """
        try:
            # Get project directory
            project_dir = self.get_project_directory()
            if not project_dir:
                logger.error("Project must be saved before exporting RDF")
                return None

            # Create LandTalk_Analysis directory if needed
            analysis_dir = os.path.join(project_dir, "LandTalk_Analysis")
            if not os.path.exists(analysis_dir):
                os.makedirs(analysis_dir)
                logger.info(f"Created analysis directory: {analysis_dir}")

            # Find LandTalk.ai group
            project = QgsProject.instance()
            root = project.layerTreeRoot()
            landtalk_group = root.findGroup(self.GROUP_NAME)

            if not landtalk_group:
                logger.warning(f"No {self.GROUP_NAME} group found")
                return None

            # Collect all features
            features = self.collect_features_from_group(landtalk_group)

            if not features:
                logger.warning("No features found to export")
                return None

            logger.info(f"Found {len(features)} features to export")

            # Get metadata
            metadata = self.get_analysis_metadata(landtalk_group)

            # Generate run ID and timestamps
            now = datetime.now()
            run_local_id = f"run-{now.strftime('%Y-%m-%dT%H%M%SZ')}"
            created_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Use response timestamp if available, otherwise use current time
            if metadata['response_timestamp']:
                # Parse and format the timestamp
                try:
                    ts = datetime.strptime(metadata['response_timestamp'], "%Y-%m-%d %H:%M:%S")
                    activity_ended = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                    activity_started = (ts.replace(second=max(0, ts.second - 2))).strftime("%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    activity_started = created_time
                    activity_ended = created_time
            else:
                activity_started = created_time
                activity_ended = created_time

            # Build run metadata
            run_meta = {
                "base_uri": self.BASE_URI,
                "run_local_id": run_local_id,
                "dataset_title": "LandTalk.AI Analysis Results",
                "dataset_description": "Bounding box geometries and attribute assignments produced by LandTalk.AI QGIS plugin for landscape/archaeological feature detection.",
                "dataset_created": created_time,
                "activity_started": activity_started,
                "activity_ended": activity_ended,
                "ai_provider": metadata['ai_provider'],
                "model_version": metadata['model_name'],
            }

            # Generate output filename
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            filename = f"LandTalk_RDF_Export_{timestamp}.ttl"
            out_path = os.path.join(analysis_dir, filename)

            # Export to TTL
            result_path = export_qgis_ai_ttl(
                run_meta=run_meta,
                features=features,
                out_path=out_path
            )

            logger.info(f"Successfully exported RDF to: {result_path}")
            return str(result_path)

        except Exception as e:
            logger.error(f"Error exporting to TTL: {str(e)}")
            return None
