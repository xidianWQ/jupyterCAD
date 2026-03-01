"""
Unit tests for geometric feature extraction service.

Tests cover:
1. Parameter-based extraction for all 5 basic shapes
2. Feature count verification for low-level and high-level features
3. Critical parameter mappings (especially Torus radius/tube)
4. Hash consistency and freshness detection
5. Error handling and edge cases
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from enum import Enum
import numpy as np


# Mock the JupyterCAD core types
class ShapeType(Enum):
    """Mock shape type enum"""
    Box = "Part::Box"
    Cylinder = "Part::Cylinder"
    Sphere = "Part::Sphere"
    Cone = "Part::Cone"
    Torus = "Part::Torus"
    Cut = "Part::Cut"
    MultiFuse = "Part::MultiFuse"


@dataclass
class MockPlacement:
    """Mock JCAD Placement"""
    Position: list
    Axis: list
    Angle: float


@dataclass
class MockParameters:
    """Mock JCAD parameters"""
    Placement: MockPlacement
    Length: float = 10.0
    Width: float = 5.0
    Height: float = 2.0
    Radius: float = 1.0
    Radius1: float = 5.0
    Radius2: float = 1.0
    Angle: float = 360.0
    Angle1: float = 0.0
    Angle2: float = 180.0
    Angle3: float = 360.0


@dataclass
class MockJCadObject:
    """Mock JCAD object"""
    name: str
    shape: ShapeType
    parameters: MockParameters
    geometryFeatures: list = None


class MockCadDocument:
    """Mock CadDocument for testing"""

    def __init__(self):
        self.objects = {}

    def add_object(self, obj: MockJCadObject):
        self.objects[obj.name] = obj

    def get_object(self, name: str):
        return self.objects.get(name)


@pytest.fixture
def mock_document():
    """Create a mock CadDocument with test objects"""
    doc = MockCadDocument()

    # Box at origin
    doc.add_object(MockJCadObject(
        name="test_box",
        shape=ShapeType.Box,
        parameters=MockParameters(
            Placement=MockPlacement(Position=[0, 0, 0], Axis=[0, 0, 1], Angle=0),
            Length=10.0,
            Width=8.0,
            Height=5.0
        )
    ))

    # Cylinder at origin
    doc.add_object(MockJCadObject(
        name="test_cylinder",
        shape=ShapeType.Cylinder,
        parameters=MockParameters(
            Placement=MockPlacement(Position=[0, 0, 0], Axis=[0, 0, 1], Angle=0),
            Radius=2.0,
            Height=10.0
        )
    ))

    # Sphere at origin
    doc.add_object(MockJCadObject(
        name="test_sphere",
        shape=ShapeType.Sphere,
        parameters=MockParameters(
            Placement=MockPlacement(Position=[0, 0, 0], Axis=[0, 0, 1], Angle=0),
            Radius=5.0
        )
    ))

    # Cone at origin
    doc.add_object(MockJCadObject(
        name="test_cone",
        shape=ShapeType.Cone,
        parameters=MockParameters(
            Placement=MockPlacement(Position=[0, 0, 0], Axis=[0, 0, 1], Angle=0),
            Radius1=3.0,
            Radius2=0.0,
            Height=8.0
        )
    ))

    # Torus at origin - CRITICAL TEST
    doc.add_object(MockJCadObject(
        name="test_torus",
        shape=ShapeType.Torus,
        parameters=MockParameters(
            Placement=MockPlacement(Position=[0, 0, 0], Axis=[0, 0, 1], Angle=0),
            Radius1=5.0,  # Main radius
            Radius2=1.0   # Tube radius
        )
    ))

    return doc


@pytest.fixture
def extractor(mock_document):
    """Create FeatureExtractionService instance"""
    # Import here to avoid import errors if module doesn't exist
    import sys
    from pathlib import Path

    # Add the notebook module to path
    notebook_path = Path(__file__).parent.parent / "jupytercad_lab" / "notebook"
    sys.path.insert(0, str(notebook_path))

    from feature_extraction import FeatureExtractionService
    return FeatureExtractionService(mock_document)


class TestBoxExtraction:
    """Tests for Box feature extraction"""

    def test_box_low_level_feature_count(self, extractor, mock_document):
        """Box should have 8 Points, 12 Edges, 6 Planes = 26 low-level features"""
        obj = mock_document.get_object("test_box")
        features = extractor._extract_box_features(obj)

        low_level_features = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'low']

        # Count by type
        points = [f for f in low_level_features if f['type'] == 'Feature::Point']
        edges = [f for f in low_level_features if f['type'] == 'Feature::Edge']
        planes = [f for f in low_level_features if f['type'] == 'Feature::Plane']

        assert len(points) == 8, f"Expected 8 corner points, got {len(points)}"
        assert len(edges) == 12, f"Expected 12 edges, got {len(edges)}"
        assert len(planes) == 6, f"Expected 6 planes, got {len(planes)}"

    def test_box_high_level_feature_count(self, extractor, mock_document):
        """Box should have 6 Face features (high-level)"""
        obj = mock_document.get_object("test_box")
        features = extractor._extract_box_features(obj)

        high_level_features = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'high']
        faces = [f for f in high_level_features if f['type'] == 'Feature::Face']

        assert len(faces) == 6, f"Expected 6 face features, got {len(faces)}"

    def test_box_corner_positions(self, extractor, mock_document):
        """Verify corner positions are correctly computed"""
        obj = mock_document.get_object("test_box")
        features = extractor._extract_box_features(obj)

        points = [f for f in features if f['type'] == 'Feature::Point']

        # Check that corners are at expected positions (half dimensions from center)
        L, W, H = 10.0, 8.0, 5.0
        expected_corners = [
            (-L/2, -W/2, -H/2),
            (L/2, -W/2, -H/2),
            (L/2, W/2, -H/2),
            (-L/2, W/2, -H/2),
            (-L/2, -W/2, H/2),
            (L/2, -W/2, H/2),
            (L/2, W/2, H/2),
            (-L/2, W/2, H/2),
        ]

        for point in points:
            pos = tuple(point['position'])
            assert pos in expected_corners, f"Corner {pos} not in expected positions"

    def test_box_edge_endpoints(self, extractor, mock_document):
        """Verify edges connect correct corners"""
        obj = mock_document.get_object("test_box")
        features = extractor._extract_box_features(obj)

        edges = [f for f in features if f['type'] == 'Feature::Edge']
        points = {f['name']: f['position'] for f in features if f['type'] == 'Feature::Point'}

        for edge in edges:
            start = edge['start']
            end = edge['end']
            assert start in points.values(), f"Edge start {start} not a corner"
            assert end in points.values(), f"Edge end {end} not a corner"
            assert start != end, "Edge has same start and end point"


class TestCylinderExtraction:
    """Tests for Cylinder feature extraction"""

    def test_cylinder_feature_count(self, extractor, mock_document):
        """Cylinder should have low-level + 1 high-level Cylinder feature"""
        obj = mock_document.get_object("test_cylinder")
        features = extractor._extract_cylinder_features(obj)

        low_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'low']
        high_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'high']

        # Low-level: 2 Points, 2 Edges, 3 Planes = 7
        assert len(low_level) == 7, f"Expected 7 low-level features, got {len(low_level)}"

        # High-level: 1 Cylinder
        cylinders = [f for f in high_level if f['type'] == 'Feature::Cylinder']
        assert len(cylinders) == 1, f"Expected 1 cylinder feature, got {len(cylinders)}"

    def test_cylinder_radius_and_height(self, extractor, mock_document):
        """Verify radius and height are correctly extracted"""
        obj = mock_document.get_object("test_cylinder")
        features = extractor._extract_cylinder_features(obj)

        cylinder = next(f for f in features if f['type'] == 'Feature::Cylinder')
        assert cylinder['radius'] == 2.0, f"Expected radius 2.0, got {cylinder['radius']}"
        assert cylinder['height'] == 10.0, f"Expected height 10.0, got {cylinder['height']}"

    def test_cylinder_axis(self, extractor, mock_document):
        """Verify axis direction is computed correctly"""
        obj = mock_document.get_object("test_cylinder")
        features = extractor._extract_cylinder_features(obj)

        cylinder = next(f for f in features if f['type'] == 'Feature::Cylinder')
        axis = np.array(cylinder['axis'])

        # Default cylinder is along Y-axis, no rotation
        expected_axis = np.array([0, 1, 0])
        assert np.allclose(axis, expected_axis), f"Expected axis {expected_axis}, got {axis}"


class TestSphereExtraction:
    """Tests for Sphere feature extraction"""

    def test_sphere_feature_count(self, extractor, mock_document):
        """Sphere should have low-level + 1 high-level Sphere feature"""
        obj = mock_document.get_object("test_sphere")
        features = extractor._extract_sphere_features(obj)

        low_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'low']
        high_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'high']

        # Low-level: 2 Points, 1 Edge, 3 Planes = 6
        assert len(low_level) == 6, f"Expected 6 low-level features, got {len(low_level)}"

        # High-level: 1 Sphere
        spheres = [f for f in high_level if f['type'] == 'Feature::Sphere']
        assert len(spheres) == 1, f"Expected 1 sphere feature, got {len(spheres)}"

    def test_sphere_center_and_radius(self, extractor, mock_document):
        """Verify center and radius are correctly extracted"""
        obj = mock_document.get_object("test_sphere")
        features = extractor._extract_sphere_features(obj)

        sphere = next(f for f in features if f['type'] == 'Feature::Sphere')
        assert sphere['center'] == [0, 0, 0], f"Expected center [0, 0, 0], got {sphere['center']}"
        assert sphere['radius'] == 5.0, f"Expected radius 5.0, got {sphere['radius']}"


class TestConeExtraction:
    """Tests for Cone feature extraction"""

    def test_cone_feature_count(self, extractor, mock_document):
        """Cone should have low-level + 1 high-level Cone feature"""
        obj = mock_document.get_object("test_cone")
        features = extractor._extract_cone_features(obj)

        low_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'low']
        high_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'high']

        # Low-level: 3 Points, 2 Edges, 2 Planes = 7
        assert len(low_level) == 7, f"Expected 7 low-level features, got {len(low_level)}"

        # High-level: 1 Cone
        cones = [f for f in high_level if f['type'] == 'Feature::Cone']
        assert len(cones) == 1, f"Expected 1 cone feature, got {len(cones)}"

    def test_cone_apex_calculation(self, extractor, mock_document):
        """Verify apex is correctly computed for a cone with radius2=0"""
        obj = mock_document.get_object("test_cone")
        features = extractor._extract_cone_features(obj)

        apex_point = next((f for f in features if f['name'] == 'test_cone_apex'), None)
        assert apex_point is not None, "Apex point not found"

        # For cone with radius1=3, radius2=0, height=8
        # apex is at height * radius1 / (radius1 - radius2) = 8 * 3 / 3 = 8
        # along the axis from bottom center
        expected_apex = np.array([0, 8, 0])  # Y-axis is default
        actual_apex = np.array(apex_point['position'])
        assert np.allclose(actual_apex, expected_apex), f"Expected apex {expected_apex}, got {actual_apex}"


class TestTorusExtraction:
    """Tests for Torus feature extraction - CRITICAL FOR CORRECTNESS"""

    def test_torus_critical_mapping(self, extractor, mock_document):
        """
        CRITICAL TEST: Verify radius/tube mapping
        Assembly 'radius' = JCAD 'Radius1' (main radius, center to tube center)
        Assembly 'tube' = JCAD 'Radius2' (tube radius)
        """
        obj = mock_document.get_object("test_torus")
        features = extractor._extract_torus_features(obj)

        torus = next((f for f in features if f['type'] == 'Feature::Torus'), None)
        assert torus is not None, "Torus feature not found"

        # CRITICAL MAPPING VERIFICATION
        assert torus['radius'] == 5.0, (
            f"CRITICAL: Expected radius=5.0 (Radius1), got {torus['radius']}. "
            f"This should map to JCAD Radius1!"
        )
        assert torus['tube'] == 1.0, (
            f"CRITICAL: Expected tube=1.0 (Radius2), got {torus['tube']}. "
            f"This should map to JCAD Radius2!"
        )

    def test_torus_feature_count(self, extractor, mock_document):
        """Torus should have low-level + 1 high-level Torus feature"""
        obj = mock_document.get_object("test_torus")
        features = extractor._extract_torus_features(obj)

        low_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'low']
        high_level = [f for f in features if f.get('metadata', {}).get('featureLevel') == 'high']

        # Low-level: 4 Points, 2 Edges, 3 Planes = 9
        assert len(low_level) == 9, f"Expected 9 low-level features, got {len(low_level)}"

        # High-level: 1 Torus
        tori = [f for f in high_level if f['type'] == 'Feature::Torus']
        assert len(tori) == 1, f"Expected 1 torus feature, got {len(tori)}"

    def test_torus_axis(self, extractor, mock_document):
        """Verify axis direction (default Z-axis for Torus)"""
        obj = mock_document.get_object("test_torus")
        features = extractor._extract_torus_features(obj)

        torus = next(f for f in features if f['type'] == 'Feature::Torus')
        axis = np.array(torus['axis'])

        # JCAD default torus is along Z-axis
        expected_axis = np.array([0, 0, 1])
        assert np.allclose(axis, expected_axis), f"Expected axis {expected_axis}, got {axis}"


class TestHashConsistency:
    """Tests for hash computation and freshness detection"""

    def test_hash_consistency(self, extractor, mock_document):
        """Hash should be consistent for same object"""
        obj = mock_document.get_object("test_box")

        hash1 = extractor._compute_object_hash(obj)
        hash2 = extractor._compute_object_hash(obj)

        assert hash1 == hash2, "Hash should be consistent"

    def test_hash_changes_with_parameters(self, extractor, mock_document):
        """Hash should change when parameters change"""
        obj = mock_document.get_object("test_box")

        hash1 = extractor._compute_object_hash(obj)

        # Modify parameters
        obj.parameters.Length = 20.0
        hash2 = extractor._compute_object_hash(obj)

        assert hash1 != hash2, "Hash should change when parameters change"

    def test_cached_features_returned_when_fresh(self, extractor, mock_document):
        """Cached features should be returned when hash matches"""
        obj = mock_document.get_object("test_box")

        # Add cached features
        features = extractor._extract_box_features(obj)
        obj.geometryFeatures = features

        # Get hash
        current_hash = extractor._compute_object_hash(obj)
        obj.geometryFeatures[0]['hash'] = current_hash

        # Extract should return cached features
        result = extractor.extract_object_features("test_box", force_recompute=False)

        assert result.extraction_method.value == "cached", "Should use cached features"
        assert len(result.features) == len(features), "Should return same cached features"

    def test_features_recomputed_when_stale(self, extractor, mock_document):
        """Features should be recomputed when hash doesn't match"""
        obj = mock_document.get_object("test_box")

        # Add cached features with wrong hash
        obj.geometryFeatures = [{"type": "Feature::Point", "name": "old", "hash": "wrong_hash"}]

        # Extract should recompute
        result = extractor.extract_object_features("test_box", force_recompute=False)

        assert result.extraction_method.value in ["parameter", "brep"], "Should recompute features"
        assert len(result.features) > 1, "Should have extracted new features"


class TestExtractAllFeatures:
    """Tests for batch extraction"""

    def test_extract_all_objects(self, extractor, mock_document):
        """Should extract features for all objects"""
        results = extractor.extract_all_features()

        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        assert "test_box" in results
        assert "test_cylinder" in results
        assert "test_sphere" in results
        assert "test_cone" in results
        assert "test_torus" in results

    def test_extract_selected_objects(self, extractor, mock_document):
        """Should extract features for selected objects only"""
        results = extractor.extract_all_features(objects=["test_box", "test_sphere"])

        assert len(results) == 2, f"Expected 2 results, got {len(results)}"
        assert "test_box" in results
        assert "test_sphere" in results
        assert "test_cylinder" not in results

    def test_force_recompute(self, extractor, mock_document):
        """Force recompute should ignore cached features"""
        obj = mock_document.get_object("test_box")
        obj.geometryFeatures = [{"type": "Feature::Point", "name": "old", "hash": "any_hash"}]

        results = extractor.extract_all_features(force_recompute=True)

        assert results["test_box"].extraction_method.value in ["parameter", "brep"]


class TestErrorHandling:
    """Tests for error handling"""

    def test_nonexistent_object(self, extractor):
        """Should raise error for nonexistent object"""
        with pytest.raises(ValueError, match="not found"):
            extractor.extract_object_features("nonexistent")

    def test_extraction_error_in_batch(self, extractor, mock_document):
        """Should continue with error result for failed extraction"""
        results = extractor.extract_all_features(objects=["test_box", "nonexistent"])

        assert "test_box" in results
        assert "nonexistent" in results
        assert results["nonexistent"].extraction_method.value == "error"
        assert len(results["nonexistent"].errors) > 0


class TestBRepExtraction:
    """Tests for BRep-based extraction (with mocked OCC)"""

    @patch('feature_extraction.FeatureExtractionService._reconstruct_occ_shape')
    def test_brep_extraction_for_cut(self, mock_reconstruct, extractor, mock_document):
        """Boolean operations should use BRep extraction"""
        # This test requires mocking the OCC shape reconstruction
        # For now, we just verify the method path is chosen
        cut_obj = MockJCadObject(
            name="test_cut",
            shape=ShapeType.Cut,
            parameters=MockParameters(
                Placement=MockPlacement(Position=[0, 0, 0], Axis=[0, 0, 1], Angle=0)
            )
        )
        mock_document.add_object(cut_obj)

        # BRep extraction will fail without actual OCC, but we check the path
        result = extractor.extract_object_features("test_cut")

        # Should attempt BRep extraction (may fail without OCC)
        assert result.extraction_method.value in ["brep", "error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
