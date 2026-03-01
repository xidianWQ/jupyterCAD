"""
Geometric Feature Extraction Service for JupyterCAD

This module provides functionality to extract low-level geometric features from
JCAD objects using OpenCASCADE (pythonocc-core) for SolveSpace constraint solver.

SolveSpace only supports primitive geometric features:
- Feature::Point: A single point in 3D space (position)
- Feature::Edge: A line segment between two points (start, end)
- Feature::Plane: A planar face with normal and center (normal, center)
- Feature::Circle: A complete circle with center, radius, and normal
- Feature::Arc: A partial circle (arc) with center, radius, normal, start/end points and angles
- Feature::Face: A bounded planar surface with normal, center, and bounds

Features are extracted in two modes:
1. Parameter-based: Fast extraction for basic shapes (Box, Cylinder, Sphere, Cone, Torus)
2. BRep-based: Precise extraction for boolean operations using OpenCASCADE analysis

Only visible=True objects are extracted (intermediate boolean results are skipped).

Example: For a Box, we extract low-level features:
- 8 Feature::Point instances (the 8 corners)
- 12 Feature::Edge instances (the 12 edges)
- 6 Feature::Plane instances (the 6 faces)
- 6 Feature::Face instances (the 6 faces with bounds)

Example: For a Cylinder, we extract low-level features:
- 2 Feature::Point instances (top and bottom centers)
- 1 Feature::Circle instance (top circle)
- 1 Feature::Circle instance (bottom circle)
- 3 Feature::Plane instances (top, bottom, and tangent planes)
"""

from __future__ import annotations

import sys
import json
import hashlib
import logging
from typing import Any, ClassVar, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__file__)
if logger.hasHandlers():
    logger.handlers.clear()

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Try to import scipy, but make it optional
try:
    from scipy.spatial.transform import Rotation
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy not available, using pure numpy for rotation calculations")


def _rotation_from_axis_angle(axis: np.ndarray, angle_degrees: float) -> Any:
    """
    Create a rotation from axis and angle.

    Uses scipy if available, otherwise falls back to pure numpy.

    Args:
        axis: Normalized rotation axis [x, y, z]
        angle_degrees: Rotation angle in degrees

    Returns:
        Rotation object (scipy Rotation or dict with matrix)
    """
    angle_rad = np.radians(angle_degrees)
    rotvec = axis * angle_rad

    if HAS_SCIPY:
        return Rotation.from_rotvec(rotvec)
    else:
        # Pure numpy fallback - return Rodrigues' rotation matrix
        # Using Rodrigues' rotation formula
        K = np.array([
            [0, -axis[2], axis[1]],
            [axis[2], 0, -axis[0]],
            [-axis[1], axis[0], 0]
        ])
        I = np.eye(3)
        R = I + np.sin(angle_rad) * K + (1 - np.cos(angle_rad)) * np.dot(K, K)
        return {'matrix': R}


def _apply_rotation(rotation: Any, vector: np.ndarray) -> np.ndarray:
    """
    Apply rotation to a vector.

    Args:
        rotation: Rotation object from _rotation_from_axis_angle
        vector: Vector to rotate [x, y, z]

    Returns:
        Rotated vector
    """
    if HAS_SCIPY:
        return rotation.apply(vector)
    else:
        # Pure numpy fallback - use rotation matrix
        R = rotation['matrix']
        return np.dot(R, vector)


class ExtractionMethod(Enum):
    """Method used for feature extraction"""
    PARAMETER = "parameter"  # Fast parameter-based extraction
    BREP = "brep"  # Precise BRep analysis
    CACHED = "cached"  # Using previously cached features
    ERROR = "error"  # Extraction failed


class ExtractionLevel(Enum):
    """
    Feature extraction level for SolveSpace constraint solver.

    SolveSpace WASM only supports low-level geometric features:
    - Point (SLVS_E_POINT_IN_3D)
    - Plane (via Normal/SLVS_E_NORMAL_IN_3D)
    - Circle (SLVS_E_CIRCLE)
    - Arc (SLVS_E_ARC_OF_CIRCLE)
    - Edge/Line (SLVS_E_LINE_SEGMENT)

    High-level features (Cylinder, Sphere, Cone, Torus) are NOT supported by SolveSpace.
    """
    FULL = "full"  # All low-level features (Point, Plane, Circle, Arc, Edge, Face)
    STANDARD = "standard"  # Standard assembly features (Circle, Arc, Plane, Point)
    MINIMAL = "minimal"  # Minimal assembly features (Circle, Plane only)


# Feature type sets for each extraction level (module-level constant)
_FEATURE_TYPE_SETS: Dict[ExtractionLevel, Set[str]] = {
    ExtractionLevel.FULL: {
        "Feature::Point", "Feature::Plane", "Feature::Circle",
        "Feature::Arc", "Feature::Edge", "Feature::Face"
    },
    ExtractionLevel.STANDARD: {
        "Feature::Circle", "Feature::Arc", "Feature::Plane", "Feature::Point"
    },
    ExtractionLevel.MINIMAL: {
        "Feature::Circle", "Feature::Plane"
    }
}


@dataclass
class ExtractionOptions:
    """
    Options for controlling feature extraction behavior.

    Note: Only low-level features are extracted because SolveSpace constraint solver
    only supports primitive geometric features. High-level features (Cylinder, Sphere,
    Cone, Torus) are filtered out as they are not supported by SolveSpace.

    Args:
        extraction_level: Feature extraction level (full/standard/minimal)
        skip_intermediate_objects: Skip extraction for intermediate boolean results (visible=False objects)

    Feature types by level:
        - FULL: Point, Plane, Circle, Arc, Edge, Face
        - STANDARD: Circle, Arc, Plane, Point
        - MINIMAL: Circle, Plane
    """
    extraction_level: ExtractionLevel = ExtractionLevel.STANDARD
    skip_intermediate_objects: bool = True

    @classmethod
    def full(cls) -> "ExtractionOptions":
        """Create options for full feature extraction (all low-level features)"""
        return cls(extraction_level=ExtractionLevel.FULL)

    @classmethod
    def standard(cls) -> "ExtractionOptions":
        """Create options for standard assembly feature extraction"""
        return cls(extraction_level=ExtractionLevel.STANDARD)

    @classmethod
    def minimal(cls) -> "ExtractionOptions":
        """Create options for minimal assembly feature extraction"""
        return cls(extraction_level=ExtractionLevel.MINIMAL)

    def allowed_feature_types(self) -> Set[str]:
        """Get the set of allowed feature types for this extraction level"""
        return _FEATURE_TYPE_SETS[self.extraction_level]


@dataclass
class FeatureExtractionResult:
    """Result of feature extraction for a single object"""
    object_name: str
    features: List[Dict[str, Any]]
    extraction_method: ExtractionMethod
    hash: str
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "object_name": self.object_name,
            "features": self.features,
            "extraction_method": self.extraction_method.value,
            "hash": self.hash,
            "errors": self.errors
        }


class FeatureExtractionService:
    """
    Service for extracting geometric features from JCAD objects.

    This service supports two extraction strategies:
    1. Parameter-based: Fast extraction for basic shapes using JCAD parameters
    2. BRep-based: Precise extraction for boolean operations using OpenCASCADE
    """

    # Basic shapes that can be extracted via parameters
    BASIC_SHAPES = {
        "Part::Box",
        "Part::Cylinder",
        "Part::Sphere",
        "Part::Cone",
        "Part::Torus"
    }

    # Boolean operations that require BRep analysis
    BOOLEAN_OPERATIONS = {
        "Part::Cut",
        "Part::MultiFuse",
        "Part::MultiCommon"
    }

    def __init__(self, cad_document, options: Optional[ExtractionOptions] = None):
        """
        Initialize the feature extraction service.

        Args:
            cad_document: CadDocument instance to access objects
            options: ExtractionOptions controlling feature extraction behavior
        """
        self.cad_document = cad_document
        self._shape_cache = {}  # Cache for reconstructed shapes
        self.options = options if options is not None else ExtractionOptions.standard()

        # Track which objects are final results vs intermediate boolean operations
        self._final_objects = self._identify_final_objects()

    def extract_all_features(
        self,
        objects: Optional[List[str]] = None,
        force_recompute: bool = False
    ) -> Dict[str, FeatureExtractionResult]:
        """
        Extract features for all or specified objects.

        Args:
            objects: List of object names to process (None = all)
            force_recompute: Force BRep analysis even if cached features exist

        Returns:
            Dictionary mapping object names to FeatureExtractionResult
        """
        results = {}

        if objects is None:
            objects = self.cad_document.objects

        # Pre-populate shape cache with basic shapes (for boolean operations)
        self._build_shape_cache(objects)

        for obj_name in objects:
            try:
                result = self.extract_object_features(obj_name, force_recompute)
                results[obj_name] = result
            except Exception as e:
                logger.error(f"Failed to extract features for {obj_name}: {e}")
                results[obj_name] = FeatureExtractionResult(
                    object_name=obj_name,
                    features=[],
                    extraction_method=ExtractionMethod.ERROR,
                    hash="",
                    errors=[str(e)]
                )

        return results

    def _build_shape_cache(self, object_names: List[str]) -> None:
        """
        Pre-populate the shape cache with basic shapes for boolean operations.

        This ensures that when we encounter Cut/Fuse operations, their base
        and tool shapes are already available in the cache.

        Process objects in order, as boolean operations depend on their
        operands being created first.
        """
        for obj_name in object_names:
            # Skip if already cached
            if obj_name in self._shape_cache:
                continue

            obj = self.cad_document.get_object(obj_name)
            if not obj:
                continue

            shape_type = obj.shape.value if hasattr(obj.shape, 'value') else str(obj.shape)

            # Cache all shapes (basic shapes get cached first, then boolean ops can use them)
            try:
                occ_shape = self.cad_document._reconstruct_occ_shape(obj, self._shape_cache)
                if occ_shape:
                    self._shape_cache[obj_name] = occ_shape
            except Exception as e:
                logger.debug(f"Could not cache shape for {obj_name}: {e}")

    def _identify_final_objects(self) -> set:
        """
        Identify which objects are final results (not intermediate boolean operations).

        Simplified logic: An object is "final" if it's visible.
        For models where all intermediate operations are hidden (visible=False),
        only the final result will have features extracted.

        Returns:
            Set of object names that are final results
        """
        final_objects = set()
        objects = self.cad_document.objects

        for obj_name in objects:
            obj = self.cad_document.get_object(obj_name)
            if not obj:
                continue

            # Check if visible
            is_visible = getattr(obj, 'visible', True)
            if is_visible:
                final_objects.add(obj_name)

        # Always include the last object as final (in case all are hidden)
        if objects and not final_objects:
            final_objects.add(objects[-1])

        return final_objects

    def _is_intermediate_object(self, obj_name: str) -> bool:
        """
        Check if an object is an intermediate boolean operation result.

        Args:
            obj_name: Name of the object to check

        Returns:
            True if the object is an intermediate result
        """
        if not self.options.skip_intermediate_objects:
            return False

        return obj_name not in self._final_objects

    def extract_object_features(
        self,
        obj_name: str,
        force_recompute: bool = False
    ) -> FeatureExtractionResult:
        """
        Extract features for a single object.

        Strategy:
        1. Check if object already has cached geometryFeatures
        2. If basic shape (Box, Cylinder, etc.) → use parameter extraction
        3. If boolean operation (Cut, Fuse) → use BRep analysis

        Args:
            obj_name: Name of the object to extract features from
            force_recompute: Force BRep analysis even if cached features exist

        Returns:
            FeatureExtractionResult containing extracted features
        """
        obj = self.cad_document.get_object(obj_name)
        if not obj:
            raise ValueError(f"Object {obj_name} not found")

        # Skip intermediate boolean operations
        if self._is_intermediate_object(obj_name):
            logger.debug(f"Skipping intermediate object {obj_name}")
            return FeatureExtractionResult(
                object_name=obj_name,
                features=[],
                extraction_method=ExtractionMethod.PARAMETER,
                hash="",
                errors=[]
            )

        # Check for existing cached features
        if not force_recompute and hasattr(obj, 'geometryFeatures') and obj.geometryFeatures:
            # Verify freshness
            current_hash = self._compute_object_hash(obj)
            cached_hash = obj.geometryFeatures[0].get('hash', '') if obj.geometryFeatures else ''

            if current_hash == cached_hash:
                return FeatureExtractionResult(
                    object_name=obj_name,
                    features=obj.geometryFeatures,
                    extraction_method=ExtractionMethod.CACHED,
                    hash=current_hash,
                    errors=[]
                )

        # Determine extraction strategy
        shape_type = obj.shape.value if hasattr(obj.shape, 'value') else str(obj.shape)

        if shape_type in self.BASIC_SHAPES:
            features = self._extract_from_parameters(obj)
            method = ExtractionMethod.PARAMETER
        elif shape_type in self.BOOLEAN_OPERATIONS:
            features = self._extract_from_brep(obj)
            method = ExtractionMethod.BREP
        else:
            logger.warning(f"Unknown shape type {shape_type}, attempting BRep analysis")
            features = self._extract_from_brep(obj)
            method = ExtractionMethod.BREP

        # Add hash to features for freshness tracking
        content_hash = self._compute_object_hash(obj)
        for feature in features:
            feature['hash'] = content_hash

        # Filter features based on extraction options
        features = self._filter_features(features)

        return FeatureExtractionResult(
            object_name=obj_name,
            features=features,
            extraction_method=method,
            hash=content_hash,
            errors=[]
        )

    def _filter_features(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter features based on extraction level.

        Only includes low-level geometric features supported by SolveSpace:
        - FULL: Point, Edge, Plane, Circle, Arc, Face
        - STANDARD: Circle, Arc, Plane, Point
        - MINIMAL: Circle, Plane

        High-level features (Cylinder, Sphere, Cone, Torus) are always filtered out
        as they are not supported by SolveSpace WASM.

        Args:
            features: List of extracted features

        Returns:
            Filtered list based on extraction level
        """
        allowed_types = self.options.allowed_feature_types()

        filtered = []
        for feature in features:
            feature_type = feature.get("type", "")

            # Only include allowed feature types for this extraction level
            if feature_type in allowed_types:
                filtered.append(feature)

        return filtered

    def _extract_from_parameters(self, obj) -> List[Dict[str, Any]]:
        """
        Extract features from JCAD parameters (fast, precise for basic shapes).

        Extracts both low-level and high-level geometric features:
        - Low-level: Feature::Point, Feature::Edge, Feature::Plane
        - High-level: Feature::Cylinder, Feature::Sphere, Feature::Cone, Feature::Torus, Feature::Face

        Supported shapes: Box, Cylinder, Sphere, Cone, Torus

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries (both low-level and high-level)
        """
        shape_type = obj.shape.value if hasattr(obj.shape, 'value') else str(obj.shape)
        params = obj.parameters

        features = []

        if shape_type == "Part::Box":
            features.extend(self._extract_box_features(obj))
        elif shape_type == "Part::Cylinder":
            features.extend(self._extract_cylinder_features(obj))
        elif shape_type == "Part::Sphere":
            features.extend(self._extract_sphere_features(obj))
        elif shape_type == "Part::Cone":
            features.extend(self._extract_cone_features(obj))
        elif shape_type == "Part::Torus":
            features.extend(self._extract_torus_features(obj))
        else:
            logger.warning(f"No parameter extractor for shape type: {shape_type}")

        return features

    def _extract_cylinder_feature(self, obj) -> Dict[str, Any]:
        """
        Extract cylinder feature from JCAD parameters.

        JCAD Cylinder defaults to Y-axis orientation.
        The Placement.Axis and Placement.Angle define the rotation.
        """
        params = obj.parameters
        placement = params.Placement

        # Get position
        position = list(placement.Position)  # [x, y, z]

        # Compute actual axis by applying rotation
        axis = list(placement.Axis)  # [x, y, z] - rotation axis
        angle = placement.Angle  # degrees

        # Normalize the rotation axis
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        # Create rotation from axis-angle
        rotation = _rotation_from_axis_angle(axis_norm, angle)

        # JCAD default cylinder is along Y-axis
        default_axis = np.array([0, 1, 0])
        actual_axis = _apply_rotation(rotation, default_axis)

        return {
            "type": "Feature::Cylinder",
            "name": f"{obj.name}_cylinder",
            "position": position,
            "axis": actual_axis.tolist(),
            "radius": float(params.Radius),
            "height": float(params.Height),
            "metadata": {
                "originalShape": "Part::Cylinder",
                "angle": float(params.Angle),
                "featureLevel": "high"
            }
        }

    def _extract_sphere_feature(self, obj) -> Dict[str, Any]:
        """Extract sphere feature from JCAD parameters."""
        params = obj.parameters
        placement = params.Placement

        return {
            "type": "Feature::Sphere",
            "name": f"{obj.name}_sphere",
            "center": list(placement.Position),
            "radius": float(params.Radius),
            "metadata": {
                "originalShape": "Part::Sphere",
                "angles": {
                    "angle1": float(params.Angle1),
                    "angle2": float(params.Angle2),
                    "angle3": float(params.Angle3)
                },
                "featureLevel": "high"
            }
        }

    def _extract_cone_feature(self, obj) -> Dict[str, Any]:
        """
        Extract cone feature from JCAD parameters.

        JCAD Cone defaults to Y-axis orientation.
        """
        params = obj.parameters
        placement = params.Placement

        # Compute actual axis (similar to cylinder)
        axis = list(placement.Axis)
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        rotation = _rotation_from_axis_angle(axis_norm, placement.Angle)

        # JCAD default cone is along Y-axis
        default_axis = np.array([0, 1, 0])
        actual_axis = _apply_rotation(rotation, default_axis)

        return {
            "type": "Feature::Cone",
            "name": f"{obj.name}_cone",
            "position": list(placement.Position),
            "axis": actual_axis.tolist(),
            "radius1": float(params.Radius1),  # Bottom radius
            "radius2": float(params.Radius2),  # Top radius
            "height": float(params.Height),
            "metadata": {
                "originalShape": "Part::Cone",
                "angle": float(params.Angle),
                "featureLevel": "high"
            }
        }

    def _extract_torus_feature(self, obj) -> Dict[str, Any]:
        """
        Extract torus feature from JCAD parameters.

        CRITICAL MAPPING:
        - Assembly 'radius' = JCAD 'Radius1' (main radius, center to tube center)
        - Assembly 'tube' = JCAD 'Radius2' (tube radius)

        JCAD Torus defaults to Z-axis orientation.
        """
        params = obj.parameters
        placement = params.Placement

        # Compute actual axis
        axis = list(placement.Axis)
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        rotation = _rotation_from_axis_angle(axis_norm, placement.Angle)

        # JCAD default torus is along Z-axis
        default_axis = np.array([0, 0, 1])
        actual_axis = _apply_rotation(rotation, default_axis)

        return {
            "type": "Feature::Torus",
            "name": f"{obj.name}_torus",
            "position": list(placement.Position),
            "axis": actual_axis.tolist(),
            "radius": float(params.Radius1),  # Main radius (NOT Radius2!)
            "tube": float(params.Radius2),    # Tube radius
            "metadata": {
                "originalShape": "Part::Torus",
                "angles": {
                    "angle1": float(params.Angle1),
                    "angle2": float(params.Angle2),
                    "angle3": float(params.Angle3)
                },
                "featureLevel": "high"
            }
        }

    def _extract_box_features(self, obj) -> List[Dict[str, Any]]:
        """
        Extract both low-level and high-level geometric features from a Box.

        Low-level features (for SolveSpace):
        - 8 Feature::Point instances (the 8 corners)
        - 12 Feature::Edge instances (the 12 edges)
        - 6 Feature::Plane instances (the 6 faces)

        High-level features (for advanced assembly):
        - 6 Feature::Face instances (the 6 faces with bounds)

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries
        """
        params = obj.parameters
        placement = params.Placement

        length = float(params.Length)
        width = float(params.Width)
        height = float(params.Height)

        # Get position and rotation
        position = list(placement.Position)  # [x, y, z]

        # Compute rotation matrix
        axis = list(placement.Axis)
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        rotation = _rotation_from_axis_angle(axis_norm, placement.Angle)

        # Define 8 corners in local coordinates
        # Box center is at origin, corners are at +/- half dimensions
        local_corners = [
            (-length/2, -width/2, -height/2),  # 0: bottom-left-back
            (length/2, -width/2, -height/2),   # 1: bottom-right-back
            (length/2, width/2, -height/2),    # 2: bottom-right-front
            (-length/2, width/2, -height/2),   # 3: bottom-left-front
            (-length/2, -width/2, height/2),   # 4: top-left-back
            (length/2, -width/2, height/2),    # 5: top-right-back
            (length/2, width/2, height/2),     # 6: top-right-front
            (-length/2, width/2, height/2),    # 7: top-left-front
        ]

        # Transform corners to world coordinates
        world_corners = []
        for i, corner in enumerate(local_corners):
            local_point = np.array(corner)
            world_point = _apply_rotation(rotation, local_point) + np.array(position)
            world_corners.append(world_point.tolist())

        features = []

        # ========== LOW-LEVEL FEATURES ==========

        # Extract 8 Feature::Point instances (the corners)
        corner_names = [
            "bottom_left_back", "bottom_right_back", "bottom_right_front", "bottom_left_front",
            "top_left_back", "top_right_back", "top_right_front", "top_left_front"
        ]
        for i, (corner, name) in enumerate(zip(world_corners, corner_names)):
            features.append({
                "type": "Feature::Point",
                "name": f"{obj.name}_corner_{name}",
                "position": corner,
                "metadata": {
                    "originalShape": "Part::Box",
                    "cornerIndex": i,
                    "cornerName": name,
                    "featureLevel": "low"
                }
            })

        # Define 12 edges by corner indices
        edge_definitions = [
            # Bottom face edges
            (0, 1, "bottom_back"),
            (1, 2, "bottom_right"),
            (2, 3, "bottom_front"),
            (3, 0, "bottom_left"),
            # Top face edges
            (4, 5, "top_back"),
            (5, 6, "top_right"),
            (6, 7, "top_front"),
            (7, 4, "top_left"),
            # Vertical edges
            (0, 4, "left_back"),
            (1, 5, "right_back"),
            (2, 6, "right_front"),
            (3, 7, "left_front"),
        ]

        # Extract 12 Feature::Edge instances
        for start_idx, end_idx, edge_name in edge_definitions:
            features.append({
                "type": "Feature::Edge",
                "name": f"{obj.name}_edge_{edge_name}",
                "start": world_corners[start_idx],
                "end": world_corners[end_idx],
                "metadata": {
                    "originalShape": "Part::Box",
                    "edgeName": edge_name,
                    "startCorner": corner_names[start_idx],
                    "endCorner": corner_names[end_idx],
                    "featureLevel": "low"
                }
            })

        # Define 6 faces (planes) by corner indices
        face_definitions = [
            # (name, corner indices)
            ("bottom", [0, 1, 2, 3]),
            ("top", [7, 6, 5, 4]),
            ("front", [3, 2, 6, 7]),
            ("back", [1, 0, 4, 5]),
            ("right", [2, 1, 5, 6]),
            ("left", [0, 3, 7, 4]),
        ]

        # Local normals for each face
        local_normals = {
            "bottom": [0, 0, -1],
            "top": [0, 0, 1],
            "front": [0, 1, 0],
            "back": [0, -1, 0],
            "right": [1, 0, 0],
            "left": [-1, 0, 0],
        }

        # ========== LOW-LEVEL: Feature::Plane and Feature::Face instances ==========

        for face_name, corner_indices in face_definitions:
            # Transform normal to world coordinates
            local_normal = np.array(local_normals[face_name])
            world_normal = _apply_rotation(rotation, local_normal)

            # Compute face center as average of corner positions
            corners = [world_corners[i] for i in corner_indices]
            center = np.mean(corners, axis=0).tolist()

            # Compute bounds based on face orientation
            if face_name in ("top", "bottom"):
                bounds = {"length": length, "width": width}
            elif face_name in ("front", "back"):
                bounds = {"length": length, "height": height}
            else:  # left, right
                bounds = {"width": width, "height": height}

            # Low-level: Feature::Plane
            features.append({
                "type": "Feature::Plane",
                "name": f"{obj.name}_plane_{face_name}",
                "normal": world_normal.tolist(),
                "center": center,
                "metadata": {
                    "originalShape": "Part::Box",
                    "faceName": face_name,
                    "corners": corner_indices,
                    "bounds": bounds,
                    "featureLevel": "low"
                }
            })

            # Low-level: Feature::Face (with bounds)
            features.append({
                "type": "Feature::Face",
                "name": f"{obj.name}_face_{face_name}",
                "normal": world_normal.tolist(),
                "center": center,
                "bounds": bounds,
                "metadata": {
                    "originalShape": "Part::Box",
                    "faceName": face_name,
                    "corners": corner_indices,
                    "featureLevel": "low"
                }
            })

        return features

    def _extract_cylinder_features(self, obj) -> List[Dict[str, Any]]:
        """
        Extract both low-level and high-level geometric features from a Cylinder.

        Low-level features (for SolveSpace):
        - 2 Feature::Point instances (center of top and bottom circles)
        - 2 Feature::Edge instances (axis line, and a representative edge on the surface)
        - 3 Feature::Plane instances (top, bottom, and a tangent plane)

        High-level features (for advanced assembly):
        - 1 Feature::Cylinder instance (complete cylinder definition)

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries
        """
        params = obj.parameters
        placement = params.Placement

        radius = float(params.Radius)
        height = float(params.Height)
        angle = float(params.Angle)  # For partial cylinders

        position = list(placement.Position)

        # Compute actual axis direction
        axis = list(placement.Axis)
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        rotation = _rotation_from_axis_angle(axis_norm, placement.Angle)
        default_axis = np.array([0, 1, 0])  # JCAD default is Y-axis
        actual_axis = _apply_rotation(rotation, default_axis)

        features = []

        # ========== LOW-LEVEL FEATURES ==========

        # Center points of top and bottom circles
        bottom_center = np.array(position)
        top_center = bottom_center + actual_axis * height

        # Feature::Point - Top and bottom centers
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_bottom_center",
            "position": bottom_center.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "pointType": "bottom_center", "featureLevel": "low"}
        })
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_top_center",
            "position": top_center.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "pointType": "top_center", "featureLevel": "low"}
        })

        # Feature::Edge - The axis line
        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_axis",
            "start": bottom_center.tolist(),
            "end": top_center.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "edgeType": "axis", "featureLevel": "low"}
        })

        # Feature::Edge - A representative edge on the cylinder surface
        perp_vec1 = np.cross(actual_axis, np.array([1, 0, 0]))
        if np.linalg.norm(perp_vec1) < 0.1:
            perp_vec1 = np.cross(actual_axis, np.array([0, 0, 1]))
        perp_vec1 = perp_vec1 / (np.linalg.norm(perp_vec1) + 1e-10)

        bottom_rim_point = bottom_center + perp_vec1 * radius
        top_rim_point = top_center + perp_vec1 * radius

        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_surface_edge",
            "start": bottom_rim_point.tolist(),
            "end": top_rim_point.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "edgeType": "surface_generator", "featureLevel": "low"}
        })

        # Feature::Circle - Bottom circle
        features.append({
            "type": "Feature::Circle",
            "name": f"{obj.name}_bottom_circle",
            "center": bottom_center.tolist(),
            "radius": radius,
            "normal": (-actual_axis).tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "circleType": "bottom", "featureLevel": "low"}
        })

        # Feature::Circle - Top circle
        features.append({
            "type": "Feature::Circle",
            "name": f"{obj.name}_top_circle",
            "center": top_center.tolist(),
            "radius": radius,
            "normal": actual_axis.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "circleType": "top", "featureLevel": "low"}
        })

        # Feature::Plane - Top plane
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_top_plane",
            "normal": actual_axis.tolist(),
            "center": top_center.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "planeType": "top", "featureLevel": "low"}
        })

        # Feature::Plane - Bottom plane
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_bottom_plane",
            "normal": (-actual_axis).tolist(),
            "center": bottom_center.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "planeType": "bottom", "featureLevel": "low"}
        })

        # Feature::Plane - A tangent plane (side)
        tangent_center = bottom_center + perp_vec1 * radius + actual_axis * height / 2
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_tangent_plane",
            "normal": perp_vec1.tolist(),
            "center": tangent_center.tolist(),
            "metadata": {"originalShape": "Part::Cylinder", "planeType": "tangent", "featureLevel": "low"}
        })

        # ========== HIGH-LEVEL FEATURES ==========

        # Feature::Cylinder - Complete cylinder definition
        features.append({
            "type": "Feature::Cylinder",
            "name": f"{obj.name}_cylinder",
            "position": position,
            "axis": actual_axis.tolist(),
            "radius": radius,
            "height": height,
            "metadata": {
                "originalShape": "Part::Cylinder",
                "angle": angle,
                "featureLevel": "high"
            }
        })

        return features

    def _extract_sphere_features(self, obj) -> List[Dict[str, Any]]:
        """
        Extract both low-level and high-level geometric features from a Sphere.

        Low-level features (for SolveSpace):
        - 2 Feature::Point instances (center and a point on surface)
        - 1 Feature::Edge instance (a great circle arc)
        - 3 Feature::Plane instances (orthogonal planes through center)

        High-level features (for advanced assembly):
        - 1 Feature::Sphere instance (complete sphere definition)

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries
        """
        params = obj.parameters
        placement = params.Placement

        radius = float(params.Radius)
        center = list(placement.Position)

        features = []

        # ========== LOW-LEVEL FEATURES ==========

        # Feature::Point - Sphere center
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_center",
            "position": center,
            "metadata": {"originalShape": "Part::Sphere", "pointType": "center", "featureLevel": "low"}
        })

        # Feature::Point - A point on the surface
        import numpy as np
        surface_point = np.array(center) + np.array([radius, 0, 0])
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_surface_point",
            "position": surface_point.tolist(),
            "metadata": {"originalShape": "Part::Sphere", "pointType": "surface", "featureLevel": "low"}
        })

        # Feature::Edge - An arc on a great circle (quarter circle)
        import math
        arc_mid = np.array(center) + np.array([radius * math.cos(math.pi/4), radius * math.sin(math.pi/4), 0])
        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_equatorial_arc",
            "start": surface_point.tolist(),
            "end": arc_mid.tolist(),
            "metadata": {"originalShape": "Part::Sphere", "edgeType": "great_circle_arc", "featureLevel": "low"}
        })

        # Feature::Plane - XY plane through center
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_equatorial_plane",
            "normal": [0, 0, 1],
            "center": center,
            "metadata": {"originalShape": "Part::Sphere", "planeType": "equatorial", "featureLevel": "low"}
        })

        # Feature::Plane - XZ plane through center
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_meridional_plane_1",
            "normal": [0, 1, 0],
            "center": center,
            "metadata": {"originalShape": "Part::Sphere", "planeType": "meridional", "featureLevel": "low"}
        })

        # Feature::Plane - YZ plane through center
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_meridional_plane_2",
            "normal": [1, 0, 0],
            "center": center,
            "metadata": {"originalShape": "Part::Sphere", "planeType": "meridional", "featureLevel": "low"}
        })

        # ========== HIGH-LEVEL FEATURES ==========

        # Feature::Sphere - Complete sphere definition
        features.append({
            "type": "Feature::Sphere",
            "name": f"{obj.name}_sphere",
            "center": center,
            "radius": radius,
            "metadata": {
                "originalShape": "Part::Sphere",
                "angles": {
                    "angle1": float(params.Angle1),
                    "angle2": float(params.Angle2),
                    "angle3": float(params.Angle3)
                },
                "featureLevel": "high"
            }
        })

        return features

    def _extract_cone_features(self, obj) -> List[Dict[str, Any]]:
        """
        Extract both low-level and high-level geometric features from a Cone.

        Low-level features (for SolveSpace):
        - 3 Feature::Point instances (apex, bottom center, and a point on rim)
        - 2 Feature::Edge instances (axis line and a generator line)
        - 2 Feature::Plane instances (bottom plane and a plane containing the axis)

        High-level features (for advanced assembly):
        - 1 Feature::Cone instance (complete cone definition)

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries
        """
        params = obj.parameters
        placement = params.Placement

        radius1 = float(params.Radius1)  # Bottom radius
        radius2 = float(params.Radius2)  # Top radius (apex if 0)
        height = float(params.Height)
        angle = float(params.Angle)

        position = list(placement.Position)

        # Compute actual axis direction
        axis = list(placement.Axis)
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        rotation = _rotation_from_axis_angle(axis_norm, placement.Angle)
        default_axis = np.array([0, 1, 0])  # JCAD default is Y-axis
        actual_axis = _apply_rotation(rotation, default_axis)

        features = []

        # Compute apex location (where radius becomes 0)
        if abs(radius1 - radius2) > 1e-10:
            apex_distance = height * radius1 / (radius1 - radius2)
        else:
            apex_distance = 0

        bottom_center = np.array(position)
        apex_point = bottom_center + actual_axis * apex_distance

        # ========== LOW-LEVEL FEATURES ==========

        # Feature::Point - Apex
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_apex",
            "position": apex_point.tolist(),
            "metadata": {"originalShape": "Part::Cone", "pointType": "apex", "featureLevel": "low"}
        })

        # Feature::Point - Bottom center
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_bottom_center",
            "position": bottom_center.tolist(),
            "metadata": {"originalShape": "Part::Cone", "pointType": "bottom_center", "featureLevel": "low"}
        })

        # Feature::Point - A point on the bottom rim
        perp_vec1 = np.cross(actual_axis, np.array([1, 0, 0]))
        if np.linalg.norm(perp_vec1) < 0.1:
            perp_vec1 = np.cross(actual_axis, np.array([0, 0, 1]))
        perp_vec1 = perp_vec1 / (np.linalg.norm(perp_vec1) + 1e-10)

        rim_point = bottom_center + perp_vec1 * radius1
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_rim_point",
            "position": rim_point.tolist(),
            "metadata": {"originalShape": "Part::Cone", "pointType": "rim", "featureLevel": "low"}
        })

        # Feature::Edge - The axis line
        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_axis",
            "start": bottom_center.tolist(),
            "end": apex_point.tolist(),
            "metadata": {"originalShape": "Part::Cone", "edgeType": "axis", "featureLevel": "low"}
        })

        # Feature::Edge - A generator line (from apex to rim)
        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_generator",
            "start": apex_point.tolist(),
            "end": rim_point.tolist(),
            "metadata": {"originalShape": "Part::Cone", "edgeType": "generator", "featureLevel": "low"}
        })

        # Feature::Plane - Bottom plane
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_bottom_plane",
            "normal": (-actual_axis).tolist(),
            "center": bottom_center.tolist(),
            "metadata": {"originalShape": "Part::Cone", "planeType": "bottom", "featureLevel": "low"}
        })

        # Feature::Plane - A plane containing the axis and a generator
        plane_center = (bottom_center + apex_point) / 2
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_axial_plane",
            "normal": np.cross(actual_axis, perp_vec1).tolist(),
            "center": plane_center.tolist(),
            "metadata": {"originalShape": "Part::Cone", "planeType": "axial", "featureLevel": "low"}
        })

        # ========== HIGH-LEVEL FEATURES ==========

        # Feature::Cone - Complete cone definition
        features.append({
            "type": "Feature::Cone",
            "name": f"{obj.name}_cone",
            "position": position,
            "axis": actual_axis.tolist(),
            "radius1": radius1,
            "radius2": radius2,
            "height": height,
            "metadata": {
                "originalShape": "Part::Cone",
                "angle": angle,
                "featureLevel": "high"
            }
        })

        return features

    def _extract_torus_features(self, obj) -> List[Dict[str, Any]]:
        """
        Extract both low-level and high-level geometric features from a Torus.

        Low-level features (for SolveSpace):
        - 4 Feature::Point instances (center, inner point, outer point, top point)
        - 2 Feature::Edge instances (major circle arc and minor circle arc)
        - 3 Feature::Plane instances (main plane, cross section planes)

        High-level features (for advanced assembly):
        - 1 Feature::Torus instance (complete torus definition)

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries
        """
        params = obj.parameters
        placement = params.Placement

        # CRITICAL MAPPING:
        # Assembly 'radius' = JCAD 'Radius1' (main radius, center to tube center)
        # Assembly 'tube' = JCAD 'Radius2' (tube radius)
        radius = float(params.Radius1)  # Main radius
        tube = float(params.Radius2)    # Tube radius

        position = list(placement.Position)

        # Compute actual axis direction
        axis = list(placement.Axis)
        axis_array = np.array(axis)
        axis_norm = axis_array / (np.linalg.norm(axis_array) + 1e-10)

        rotation = _rotation_from_axis_angle(axis_norm, placement.Angle)
        default_axis = np.array([0, 0, 1])  # JCAD default torus is Z-axis
        actual_axis = _apply_rotation(rotation, default_axis)

        # Find a perpendicular vector for radial direction
        perp_vec1 = np.cross(actual_axis, np.array([1, 0, 0]))
        if np.linalg.norm(perp_vec1) < 0.1:
            perp_vec1 = np.cross(actual_axis, np.array([0, 1, 0]))
        perp_vec1 = perp_vec1 / (np.linalg.norm(perp_vec1) + 1e-10)

        center = np.array(position)

        features = []

        # ========== LOW-LEVEL FEATURES ==========

        # Feature::Point - Torus center
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_center",
            "position": center.tolist(),
            "metadata": {"originalShape": "Part::Torus", "pointType": "center", "featureLevel": "low"}
        })

        # Feature::Point - Point on the outer rim of the tube
        outer_point = center + perp_vec1 * (radius + tube)
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_outer_point",
            "position": outer_point.tolist(),
            "metadata": {"originalShape": "Part::Torus", "pointType": "outer_rim", "featureLevel": "low"}
        })

        # Feature::Point - Point on the inner rim of the tube
        inner_point = center + perp_vec1 * (radius - tube)
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_inner_point",
            "position": inner_point.tolist(),
            "metadata": {"originalShape": "Part::Torus", "pointType": "inner_rim", "featureLevel": "low"}
        })

        # Feature::Point - Point on the top of the tube
        top_point = center + actual_axis * tube + perp_vec1 * radius
        features.append({
            "type": "Feature::Point",
            "name": f"{obj.name}_top_point",
            "position": top_point.tolist(),
            "metadata": {"originalShape": "Part::Torus", "pointType": "top", "featureLevel": "low"}
        })

        # Feature::Edge - Arc on the major circle
        import math
        mid_angle_point = center + perp_vec1 * radius * math.cos(math.pi/4) + actual_axis * radius * math.sin(math.pi/4)
        major_start = center + perp_vec1 * radius
        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_major_circle_arc",
            "start": major_start.tolist(),
            "end": mid_angle_point.tolist(),
            "metadata": {"originalShape": "Part::Torus", "edgeType": "major_circle", "featureLevel": "low"}
        })

        # Feature::Edge - Arc on the minor circle (cross-section)
        minor_start = center + perp_vec1 * radius
        minor_end = center + perp_vec1 * radius + actual_axis * tube
        features.append({
            "type": "Feature::Edge",
            "name": f"{obj.name}_minor_circle_arc",
            "start": minor_start.tolist(),
            "end": minor_end.tolist(),
            "metadata": {"originalShape": "Part::Torus", "edgeType": "minor_circle", "featureLevel": "low"}
        })

        # Feature::Plane - Main plane of the torus
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_main_plane",
            "normal": actual_axis.tolist(),
            "center": center.tolist(),
            "metadata": {"originalShape": "Part::Torus", "planeType": "main", "featureLevel": "low"}
        })

        # Feature::Plane - Cross section plane 1
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_cross_section_1",
            "normal": perp_vec1.tolist(),
            "center": center.tolist(),
            "metadata": {"originalShape": "Part::Torus", "planeType": "cross_section", "featureLevel": "low"}
        })

        # Feature::Plane - Cross section plane 2 (orthogonal to plane 1)
        perp_vec2 = np.cross(actual_axis, perp_vec1)
        features.append({
            "type": "Feature::Plane",
            "name": f"{obj.name}_cross_section_2",
            "normal": perp_vec2.tolist(),
            "center": center.tolist(),
            "metadata": {"originalShape": "Part::Torus", "planeType": "cross_section", "featureLevel": "low"}
        })

        # ========== HIGH-LEVEL FEATURES ==========

        # Feature::Torus - Complete torus definition
        features.append({
            "type": "Feature::Torus",
            "name": f"{obj.name}_torus",
            "position": position,
            "axis": actual_axis.tolist(),
            "radius": radius,  # Main radius (Radius1)
            "tube": tube,      # Tube radius (Radius2)
            "metadata": {
                "originalShape": "Part::Torus",
                "angles": {
                    "angle1": float(params.Angle1),
                    "angle2": float(params.Angle2),
                    "angle3": float(params.Angle3)
                },
                "featureLevel": "high"
            }
        })

        return features

    def _extract_from_brep(self, obj) -> List[Dict[str, Any]]:
        """
        Extract features from OpenCASCADE BRep geometry.

        This method is used for boolean operations (Cut, Fuse, Common) where
        the resulting geometry cannot be determined from parameters alone.

        Process:
        1. Reconstruct TopoDS_Shape from JCAD object
        2. Analyze faces to identify geometric primitives
        3. Extract cylinders, spheres, cones, torus, planes from faces

        Args:
            obj: PythonJcadObject instance

        Returns:
            List of feature dictionaries
        """
        try:
            from OCC.Core.TopAbs import TopAbs_FACE
            from OCC.Core.TopExp import TopExp_Explorer
            from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
            from OCC.Core.GeomAbs import (
                GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere,
                GeomAbs_Cone, GeomAbs_Torus
            )
        except ImportError:
            logger.error("OpenCASCADE (pythonocc-core) is required for BRep analysis")
            return []

        # Get shape type (for metadata) - define BEFORE occ_shape check
        shape_type = obj.shape.value if hasattr(obj.shape, 'value') else str(obj.shape)

        # Reconstruct OCC shape
        occ_shape = self.cad_document._reconstruct_occ_shape(obj, self._shape_cache)

        if not occ_shape:
            # For boolean operations, this is expected if base/tool shapes aren't available
            if shape_type in self.BOOLEAN_OPERATIONS:
                logger.debug(f"Could not reconstruct boolean operation {obj.name} - base/tool shapes may not be in cache")
            else:
                logger.warning(f"Could not reconstruct shape for {obj.name}")
            return []

        features = []
        vertex_count = 0
        edge_count = 0
        face_count = 0

        # ========== LOW-LEVEL FEATURES: Vertices (Points) ==========
        # NOTE: Vertex geometry extraction is skipped because BRep_Tool.Pnt() is not available.
        # However, we build a vertex index map for topological connectivity (which edges connect to which vertices).
        # This allows Edge features to reference their connected vertices even without vertex coordinates.

        # Build vertex map: vertex_hash -> vertex_index
        # This helps track which edges connect to which vertices
        vertex_map: Dict[int, int] = {}
        vertex_index = 0

        try:
            from OCC.Core.TopAbs import TopAbs_VERTEX

            vertex_explorer = TopExp_Explorer(occ_shape, TopAbs_VERTEX)

            while vertex_explorer.More():
                vertex = vertex_explorer.Current()
                # Use hash code to identify unique vertices
                vertex_hash = vertex.HashCode(2147483647)
                if vertex_hash not in vertex_map:
                    vertex_map[vertex_hash] = vertex_index
                    vertex_index += 1
                vertex_explorer.Next()

            logger.debug(f"[Vertex topology] Found {vertex_index} unique vertices for {obj.name}")
        except Exception as e:
            logger.error(f"[Vertex topology] Failed to map vertices for {obj.name}: {e}")

        vertex_count = vertex_index  # Total unique vertices found

        # ========== LOW-LEVEL FEATURES: Edges ==========
        # Track curve type statistics
        curve_type_counts = {}

        logger.debug(f"Starting BRep feature extraction for {obj.name} with Circle/Arc support")

        try:
            from OCC.Core.TopAbs import TopAbs_EDGE
            from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
            from OCC.Core.GeomAbs import (
                GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse,
                GeomAbs_Hyperbola, GeomAbs_Parabola, GeomAbs_BezierCurve,
                GeomAbs_BSplineCurve, GeomAbs_OtherCurve
            )

            edge_explorer = TopExp_Explorer(occ_shape, TopAbs_EDGE)

            while edge_explorer.More():
                edge = edge_explorer.Current()
                try:
                    curve = BRepAdaptor_Curve(edge)
                    curve_type = curve.GetType()

                    # Count curve types for debugging
                    curve_type_name = {
                        GeomAbs_Line: "Line",
                        GeomAbs_Circle: "Circle",
                        GeomAbs_Ellipse: "Ellipse",
                        GeomAbs_Hyperbola: "Hyperbola",
                        GeomAbs_Parabola: "Parabola",
                        GeomAbs_BezierCurve: "BezierCurve",
                        GeomAbs_BSplineCurve: "BSplineCurve",
                        GeomAbs_OtherCurve: "OtherCurve"
                    }.get(curve_type, f"Unknown({curve_type})")
                    curve_type_counts[curve_type_name] = curve_type_counts.get(curve_type_name, 0) + 1

                    edge_name = f"{obj.name}_edge_{edge_count}"

                    if curve_type == GeomAbs_Line:
                        # Line edge - get start and end points
                        try:
                            from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
                            from OCC.Core.gp import gp_Pnt
                            from OCC.Core.TopAbs import TopAbs_FORWARD, TopAbs_REVERSED, TopAbs_VERTEX

                            first_param = curve.FirstParameter()
                            last_param = curve.LastParameter()

                            pnt_first = curve.Value(first_param)
                            pnt_last = curve.Value(last_param)

                            # Get connected vertices using vertex explorer on this edge
                            # We explore vertices within the edge to find its endpoints
                            first_vertex_idx = -1
                            last_vertex_idx = -1
                            try:
                                edge_vertex_explorer = TopExp_Explorer(edge, TopAbs_VERTEX)
                                vertices_found = []

                                while edge_vertex_explorer.More():
                                    edge_vertex = edge_vertex_explorer.Current()
                                    edge_vertex_hash = edge_vertex.HashCode(2147483647)
                                    vertices_found.append(vertex_map.get(edge_vertex_hash, -1))
                                    edge_vertex_explorer.Next()

                                # Edge typically has 2 vertices (start and end)
                                if len(vertices_found) >= 2:
                                    first_vertex_idx, last_vertex_idx = vertices_found[0], vertices_found[1]
                                elif len(vertices_found) == 1:
                                    first_vertex_idx = vertices_found[0]
                            except Exception as e:
                                logger.error(f"[Edge #{edge_count}] Could not get vertex connectivity: {e}")
                                first_vertex_idx = -1
                                last_vertex_idx = -1

                            # Check edge orientation - REVERSED edges need start/end swapped
                            # to match the topological direction
                            edge_direction = edge.Orientation()
                            if edge_direction == TopAbs_REVERSED:
                                # Swap start and end for reversed edges
                                pnt_first, pnt_last = pnt_last, pnt_first
                                first_vertex_idx, last_vertex_idx = last_vertex_idx, first_vertex_idx

                            features.append({
                                "type": "Feature::Edge",
                                "name": edge_name,
                                "start": [pnt_first.X(), pnt_first.Y(), pnt_first.Z()],
                                "end": [pnt_last.X(), pnt_last.Y(), pnt_last.Z()],
                                "direction": "FORWARD" if edge_direction == TopAbs_FORWARD else "REVERSED",
                                "metadata": {
                                    "originalShape": shape_type,
                                    "edgeType": "line",
                                    "startVertex": first_vertex_idx,
                                    "endVertex": last_vertex_idx,
                                    "edgeIndex": edge_count,
                                    "featureLevel": "low"
                                }
                            })
                        except Exception as e:
                            logger.error(f"Error extracting line edge: {e}")
                            import traceback
                            traceback.print_exc()

                    elif curve_type == GeomAbs_Circle:
                        # Circular edge - extract Circle or Arc feature
                        logger.debug(f"[DEBUG-CIRCLE] Processing Circle curve #{edge_count}")
                        try:
                            circle = curve.Circle()
                            radius = circle.Radius()
                            center = circle.Location()
                            position = [center.X(), center.Y(), center.Z()]

                            # Get circle normal
                            try:
                                from OCC.Core.gp import gp_Dir
                                normal_dir = circle.Axis().Direction()
                                normal = [normal_dir.X(), normal_dir.Y(), normal_dir.Z()]
                            except Exception:
                                # Default to Z-axis if normal cannot be determined
                                normal = [0, 0, 1]

                            # Get two points on the circle (for edge representation and arc endpoints)
                            first_param = curve.FirstParameter()
                            last_param = curve.LastParameter()

                            pnt_first = curve.Value(first_param)
                            pnt_last = curve.Value(last_param)

                            # Check if it's a full circle or arc
                            is_full_circle = abs(last_param - first_param - 2 * 3.14159) < 0.01

                            if is_full_circle:
                                # Extract as Feature::Circle for complete circles
                                features.append({
                                    "type": "Feature::Circle",
                                    "name": f"{obj.name}_circle_{edge_count}",
                                    "center": position,
                                    "radius": float(radius),
                                    "normal": normal,
                                    "metadata": {
                                        "originalShape": shape_type,
                                        "edgeIndex": edge_count,
                                        "featureLevel": "low"
                                    }
                                })
                            else:
                                # Extract as Feature::Arc for partial circles
                                features.append({
                                    "type": "Feature::Arc",
                                    "name": f"{obj.name}_arc_{edge_count}",
                                    "center": position,
                                    "radius": float(radius),
                                    "normal": normal,
                                    "startAngle": float(first_param),
                                    "endAngle": float(last_param),
                                    "start": [pnt_first.X(), pnt_first.Y(), pnt_first.Z()],
                                    "end": [pnt_last.X(), pnt_last.Y(), pnt_last.Z()],
                                    "metadata": {
                                        "originalShape": shape_type,
                                        "edgeIndex": edge_count,
                                        "featureLevel": "low"
                                    }
                                })

                            # Also add a Point at the circle/arc center for constraint solving
                            features.append({
                                "type": "Feature::Point",
                                "name": f"{obj.name}_circle_center_{edge_count}",
                                "position": position,
                                "metadata": {
                                    "originalShape": shape_type,
                                    "pointType": "circle_center" if is_full_circle else "arc_center",
                                    "featureLevel": "low"
                                }
                            })
                        except Exception as e:
                            logger.error(f"Error extracting circle/arc feature: {e}")
                            import traceback
                            traceback.print_exc()

                    elif curve_type == GeomAbs_Ellipse:
                        # Elliptical edge - treat as general curve
                        try:
                            first_param = curve.FirstParameter()
                            last_param = curve.LastParameter()

                            pnt_first = curve.Value(first_param)
                            pnt_last = curve.Value(last_param)

                            features.append({
                                "type": "Feature::Edge",
                                "name": edge_name,
                                "start": [pnt_first.X(), pnt_first.Y(), pnt_first.Z()],
                                "end": [pnt_last.X(), pnt_last.Y(), pnt_last.Z()],
                                "metadata": {
                                    "originalShape": shape_type,
                                    "edgeType": "ellipse",
                                    "edgeIndex": edge_count,
                                    "featureLevel": "low"
                                }
                            })
                        except Exception as e:
                            logger.debug(f"Error extracting ellipse edge: {e}")
                    else:
                        # Other curve types - extract as generic edge with endpoints
                        try:
                            first_param = curve.FirstParameter()
                            last_param = curve.LastParameter()

                            pnt_first = curve.Value(first_param)
                            pnt_last = curve.Value(last_param)

                            features.append({
                                "type": "Feature::Edge",
                                "name": edge_name,
                                "start": [pnt_first.X(), pnt_first.Y(), pnt_first.Z()],
                                "end": [pnt_last.X(), pnt_last.Y(), pnt_last.Z()],
                                "metadata": {
                                    "originalShape": shape_type,
                                    "edgeType": "curve",
                                    "edgeIndex": edge_count,
                                    "featureLevel": "low"
                                }
                            })
                        except Exception as e:
                            logger.debug(f"Error extracting generic edge: {e}")

                    edge_count += 1
                except Exception as e:
                    logger.debug(f"Error processing edge: {e}")
                edge_explorer.Next()

            # Log curve type statistics
            logger.debug(f"Curve type distribution for {obj.name}: {curve_type_counts}")

        except Exception as e:
            logger.error(f"Error exploring edges: {e}")
            import traceback
            traceback.print_exc()

        # ========== LOW-LEVEL & HIGH-LEVEL FEATURES: Faces ==========
        # Analyze faces to extract both Planes (low-level) and specific features (high-level)
        face_explorer = TopExp_Explorer(occ_shape, TopAbs_FACE)

        while face_explorer.More():
            face = face_explorer.Current()

            # Get surface type
            try:
                surface = BRepAdaptor_Surface(face, True)
                surf_type = surface.GetType()

                if surf_type == GeomAbs_Cylinder:
                    # High-level: Cylinder
                    cyl_feature = self._extract_cylinder_from_brep(face, surface, obj.name)
                    if cyl_feature:
                        features.append(cyl_feature)

                elif surf_type == GeomAbs_Sphere:
                    # High-level: Sphere
                    sphere_feature = self._extract_sphere_from_brep(face, surface, obj.name)
                    if sphere_feature:
                        features.append(sphere_feature)

                elif surf_type == GeomAbs_Cone:
                    # High-level: Cone
                    cone_feature = self._extract_cone_from_brep(face, surface, obj.name)
                    if cone_feature:
                        features.append(cone_feature)

                elif surf_type == GeomAbs_Torus:
                    # High-level: Torus
                    torus_feature = self._extract_torus_from_brep(face, surface, obj.name)
                    if torus_feature:
                        features.append(torus_feature)

                elif surf_type == GeomAbs_Plane:
                    # Low-level: Plane (for SolveSpace constraints)
                    plane_feature = self._extract_plane_from_brep(face, surface, obj.name, face_count)
                    if plane_feature:
                        features.append(plane_feature)

                    # Low-level: Face (with bounds for advanced operations)
                    face_feature = self._extract_face_from_brep(face, surface, obj.name, face_count)
                    if face_feature:
                        features.append(face_feature)

                face_count += 1

            except Exception as e:
                logger.debug(f"Error analyzing face: {e}")

            face_explorer.Next()

        # Count feature types for debugging
        feature_counts = {}
        for f in features:
            ftype = f.get("type", "unknown")
            feature_counts[ftype] = feature_counts.get(ftype, 0) + 1

        logger.debug(f"Extracted {vertex_count} vertices, {edge_count} edges, {face_count} faces for {obj.name} using BRep analysis")
        logger.info(f"Extracted {feature_counts}")
        return features

    def _extract_cylinder_from_brep(
        self,
        face,
        surface: "BRepAdaptor_Surface",
        obj_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract cylinder feature from BRep face."""
        try:
            from OCC.Core.BRepBndLib import brepbndlib_Add
            from OCC.Core.Bnd import Bnd_Box
        except ImportError:
            return None

        # Get cylinder parameters
        cylinder = surface.Cylinder()

        # Position (axis location)
        pos = cylinder.Location()
        position = [pos.X(), pos.Y(), pos.Z()]

        # Axis direction
        axis_dir = cylinder.Axis().Direction()
        axis = [axis_dir.X(), axis_dir.Y(), axis_dir.Z()]

        # Radius
        radius = cylinder.Radius()

        # For height, analyze face boundaries using bounding box
        try:
            bbox = Bnd_Box()
            brepbndlib_Add(face, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            height = max(abs(xmax - xmin), abs(ymax - ymin), abs(zmax - zmin))
        except Exception:
            height = 1.0  # Default fallback

        return {
            "type": "Feature::Cylinder",
            "name": f"{obj_name}_brep_cylinder",
            "position": position,
            "axis": axis,
            "radius": float(radius),
            "height": float(height),
            "metadata": {
                "extractionMethod": "brep",
                "featureLevel": "high"
            }
        }

    def _extract_sphere_from_brep(
        self,
        face,
        surface: "BRepAdaptor_Surface",
        obj_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract sphere feature from BRep face."""
        sphere = surface.Sphere()

        pos = sphere.Location()
        center = [pos.X(), pos.Y(), pos.Z()]
        radius = sphere.Radius()

        return {
            "type": "Feature::Sphere",
            "name": f"{obj_name}_brep_sphere",
            "center": center,
            "radius": float(radius),
            "metadata": {
                "extractionMethod": "brep",
                "featureLevel": "high"
            }
        }

    def _extract_cone_from_brep(
        self,
        face,
        surface: "BRepAdaptor_Surface",
        obj_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract cone feature from BRep face."""
        cone = surface.Cone()

        pos = cone.Location()
        position = [pos.X(), pos.Y(), pos.Z()]

        axis_dir = cone.Axis().Direction()
        axis = [axis_dir.X(), axis_dir.Y(), axis_dir.Z()]

        radius1 = cone.RefRadius()  # Bottom radius
        radius2 = cone.Radius()     # Top radius (at apex, typically 0)

        # Estimate height from semi-angle
        import math
        semi_angle = cone.SemiAngle()
        if abs(semi_angle) > 1e-10:
            height = abs(radius1 / math.tan(semi_angle))
        else:
            height = 1.0  # Default fallback

        return {
            "type": "Feature::Cone",
            "name": f"{obj_name}_brep_cone",
            "position": position,
            "axis": axis,
            "radius1": float(radius1),
            "radius2": float(radius2),
            "height": float(height),
            "metadata": {
                "extractionMethod": "brep",
                "featureLevel": "high"
            }
        }

    def _extract_torus_from_brep(
        self,
        face,
        surface: "BRepAdaptor_Surface",
        obj_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract torus feature from BRep face.

        CRITICAL: OpenCASCADE uses different parameter names than JCAD
        - OCC.Location() = torus center
        - OCC.Axis().Direction() = torus axis
        - OCC.MajorRadius() = Assembly 'radius' = JCAD 'Radius1'
        - OCC.MinorRadius() = Assembly 'tube' = JCAD 'Radius2'
        """
        torus = surface.Torus()

        pos = torus.Location()
        position = [pos.X(), pos.Y(), pos.Z()]

        axis_dir = torus.Axis().Direction()
        axis = [axis_dir.X(), axis_dir.Y(), axis_dir.Z()]

        # CRITICAL MAPPING
        radius = torus.MajorRadius()  # Main radius (center to tube center)
        tube = torus.MinorRadius()    # Tube radius

        return {
            "type": "Feature::Torus",
            "name": f"{obj_name}_brep_torus",
            "position": position,
            "axis": axis,
            "radius": float(radius),  # MajorRadius
            "tube": float(tube),      # MinorRadius
            "metadata": {
                "extractionMethod": "brep",
                "featureLevel": "high"
            }
        }

    def _extract_plane_from_brep(
        self,
        face,
        surface: "BRepAdaptor_Surface",
        obj_name: str,
        face_index: int
    ) -> Optional[Dict[str, Any]]:
        """Extract planar face feature (low-level) from BRep face."""
        try:
            from OCC.Core.BRepBndLib import brepbndlib_Add
            from OCC.Core.Bnd import Bnd_Box
        except ImportError:
            return None

        plane = surface.Plane()

        # Get plane location and normal
        pos = plane.Location()
        center = [pos.X(), pos.Y(), pos.Z()]

        normal_dir = plane.Axis().Direction()
        normal = [normal_dir.X(), normal_dir.Y(), normal_dir.Z()]

        # Get bounds from bounding box
        try:
            bbox = Bnd_Box()
            brepbndlib_Add(face, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            bounds = {
                "length": abs(xmax - xmin),
                "width": abs(ymax - ymin),
                "height": abs(zmax - zmin)
            }
        except Exception:
            bounds = {}

        return {
            "type": "Feature::Plane",
            "name": f"{obj_name}_plane_{face_index}",
            "normal": normal,
            "center": center,
            "metadata": {
                "originalShape": "Part::Cut",
                "faceIndex": face_index,
                "bounds": bounds,
                "featureLevel": "low"
            }
        }

    def _extract_face_from_brep(
        self,
        face,
        surface: "BRepAdaptor_Surface",
        obj_name: str,
        face_index: int
    ) -> Optional[Dict[str, Any]]:
        """Extract face feature (low-level) with bounds from BRep face."""
        try:
            from OCC.Core.BRepBndLib import brepbndlib_Add
            from OCC.Core.Bnd import Bnd_Box
        except ImportError:
            return None

        plane = surface.Plane()

        # Get plane location and normal
        pos = plane.Location()
        center = [pos.X(), pos.Y(), pos.Z()]

        normal_dir = plane.Axis().Direction()
        normal = [normal_dir.X(), normal_dir.Y(), normal_dir.Z()]

        # Get bounds from bounding box
        try:
            bbox = Bnd_Box()
            brepbndlib_Add(face, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            bounds = {
                "length": abs(xmax - xmin),
                "width": abs(ymax - ymin),
                "height": abs(zmax - zmin)
            }
        except Exception:
            bounds = {}

        return {
            "type": "Feature::Face",
            "name": f"{obj_name}_face_{face_index}",
            "normal": normal,
            "center": center,
            "bounds": bounds,
            "metadata": {
                "extractionMethod": "brep",
                "faceIndex": face_index,
                "featureLevel": "low"
            }
        }

    def _compute_object_hash(self, obj) -> str:
        """
        Compute hash of object for freshness detection.

        The hash is based on the object's shape type and parameters.
        If the parameters change, the hash will change.

        Args:
            obj: PythonJcadObject instance

        Returns:
            SHA256 hash string
        """
        # Get parameters as dict
        if hasattr(obj.parameters, 'model_dump'):
            params_dict = obj.parameters.model_dump()
        elif hasattr(obj.parameters, 'dict'):
            params_dict = obj.parameters.dict()
        else:
            params_dict = obj.parameters

        data = {
            "shape": str(obj.shape),
            "parameters": params_dict
        }

        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
