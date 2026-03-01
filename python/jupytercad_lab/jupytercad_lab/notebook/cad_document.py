from __future__ import annotations

import os
import sys
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import math

from pycrdt import Array, Doc, Map, Text
from pydantic import BaseModel
from ypywidgets.comm import CommWidget

from uuid import uuid4
from .converter import generate_model_thumbnail

from jupytercad_core.schema import (
    IBox,
    ICone,
    ICut,
    ICylinder,
    IExtrusion,
    IFuse,
    IIntersection,
    ISphere,
    IChamfer,
    IFillet,
    ITorus,
    ISketchObject,
    Parts,
    ShapeMetadata,
    IAny,
    SCHEMA_VERSION,
)
from jupytercad_core.schema.interfaces import geomLineSegment, geomCircle

logger = logging.getLogger(__file__)
if logger.hasHandlers():
    logger.handlers.clear()

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class CadDocument(CommWidget):
    """
    Create a new CadDocument object.

    :param path: the path to the file that you would like to open.
    If not provided, a new empty document will be created.
    """

    def __init__(self, path: Optional[str] = None):
        comm_metadata = CadDocument._path_to_comm(path)

        ydoc = Doc()

        super().__init__(
            comm_metadata=dict(ymodel_name="@jupytercad:widget", **comm_metadata),
            ydoc=ydoc,
        )

        self.ydoc["schemaVersion"] = self._schemaVersion = Text(SCHEMA_VERSION)
        self.ydoc["objects"] = self._objects_array = Array()
        self.ydoc["metadata"] = self._metadata = Map()
        self.ydoc["outputs"] = self._outputs = Map()
        self.ydoc["options"] = self._options = Map()

    @property
    def objects(self) -> List[str]:
        """
        Get the list of objects that the document contains as a list of strings.
        """
        if self._objects_array:
            return [x["name"] for x in self._objects_array]
        return []

    @classmethod
    def import_from_file(cls, path: str | Path) -> CadDocument:
        """
        Import a CadDocument from a .jcad file.

        :param path: The path to the file.
        :return: A new CadDocument instance.
        """
        instance = cls()
        with open(path, "r") as f:
            jcad_content = json.load(f)

        instance.ydoc["objects"] = instance._objects_array = Array(
            [Map(obj) for obj in jcad_content.get("objects", [])]
        )
        instance.ydoc["options"] = instance._options = Map(
            jcad_content.get("options", {})
        )
        instance.ydoc["metadata"] = instance._metadata = Map(
            jcad_content.get("metadata", {})
        )
        instance.ydoc["outputs"] = instance._outputs = Map(
            jcad_content.get("outputs", {})
        )

        return instance

    def save(
        self,
        path: str | Path,
        extract_features: bool = True,
        extraction_level: str = "standard",
        force_recompute: bool = False
    ) -> None:
        """
        Save the CadDocument to a .jcad file on the local filesystem.

        :param path: The path to the file.
        :param extract_features: Whether to extract low-level geometric features for SolveSpace constraint solver (default: True).
        :param extraction_level: Feature extraction level - "full", "standard" (default), or "minimal".
                               - full: Point, Edge, Plane, Circle, Arc, Face
                               - standard: Circle, Arc, Plane, Point
                               - minimal: Circle, Plane only
        :param force_recompute: Force feature recomputation even if cached features exist
        """
        # Extract features if requested
        if extract_features:
            from .feature_extraction import FeatureExtractionService, ExtractionOptions, ExtractionLevel

            # Map string level to ExtractionLevel enum
            level_map = {
                "full": ExtractionLevel.FULL,
                "standard": ExtractionLevel.STANDARD,
                "minimal": ExtractionLevel.MINIMAL
            }
            level = level_map.get(extraction_level, ExtractionLevel.STANDARD)

            options = ExtractionOptions(extraction_level=level)
            extractor = FeatureExtractionService(self, options=options)
            results = extractor.extract_all_features(force_recompute=force_recompute)

            # Update objects with extracted features
            for obj_name, result in results.items():
                if result.features and result.extraction_method.value != "error":
                    obj_map = self._get_yobject_by_name(obj_name)
                    if obj_map:
                        # Get current object data
                        obj_data = obj_map.to_py()

                        # Add geometryFeatures to the object
                        obj_data["geometryFeatures"] = result.features

                        # Update the YMap with modified data
                        for key, value in obj_data.items():
                            obj_map[key] = value

                        logger.info(f"Extracted {len(result.features)} features for {obj_name} using {result.extraction_method.value} method (level: {extraction_level})")
                elif result.extraction_method.value == "error":
                    logger.warning(f"Feature extraction failed for {obj_name}: {result.errors}")

        content = {
            "schemaVersion": SCHEMA_VERSION,
            "objects": self._objects_array.to_py(),
            "options": self._options.to_py(),
            "metadata": self._metadata.to_py(),
            "outputs": self._outputs.to_py(),
        }
        with open(path, "w") as f:
            json.dump(content, f, indent=4)

    def export(self, path: str) -> None:
        """
        Export the visible objects in the document to a GLB file.
        """
        try:
            from OCC.Core.TDocStd import TDocStd_Document
            from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorGen
            from OCC.Core.RWGltf import RWGltf_CafWriter
            from OCC.Core.TCollection import TCollection_ExtendedString, TCollection_AsciiString
            from OCC.Core.Quantity import Quantity_Color as Quantities_Color, Quantity_TOC_RGB as Quantities_TOC_RGB
            from OCC.Core.TColStd import TColStd_IndexedDataMapOfStringString
            from OCC.Core.Message import Message_ProgressRange
            # [重要修复] 引入 BRepMesh 用于生成网格
            from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        except ImportError:
            logger.error("Export requires pythonocc-core to be installed.")
            return

        doc = TDocStd_Document(TCollection_ExtendedString("JupyterCAD"))
        shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
        color_tool = XCAFDoc_DocumentTool.ColorTool(doc.Main())
        
        has_shape = False
        created_shapes = {} # Cache for reconstructed shapes

        # Reconstruct and add visible shapes
        for name in self.objects:
             obj = self.get_object(name)
             if not obj: continue

             # Reconstruct shape (needed for boolean ops even if hidden)
             shape = self._reconstruct_occ_shape(obj, created_shapes)
             
             if shape:
                 created_shapes[name] = shape
                 
                 # Only export if visible
                 if obj.visible:
                     # [重要修复] 生成网格 (Triangulation)，GLB 必须包含网格数据
                     # 0.01 是线性偏差 (Linear Deflection)，越小越平滑
                     mesh_gen = BRepMesh_IncrementalMesh(shape, 0.01)
                     mesh_gen.Perform()

                     # Add to XCAF Doc
                     label = shape_tool.AddShape(shape, False)
                     has_shape = True
                     
                     # Set Color
                     if hasattr(obj, "parameters") and hasattr(obj.parameters, "Color"):
                        hex_color = obj.parameters.Color 
                        if hex_color and hex_color.startswith("#"):
                            try:
                                r = int(hex_color[1:3], 16) / 255.0
                                g = int(hex_color[3:5], 16) / 255.0
                                b = int(hex_color[5:7], 16) / 255.0
                                col = Quantities_Color(r, g, b, Quantities_TOC_RGB)
                                color_tool.SetColor(label, col, XCAFDoc_ColorGen)
                            except ValueError:
                                pass
        
        if has_shape:
            writer = RWGltf_CafWriter(TCollection_AsciiString(path), True)
            # Pass all required arguments for modern pythonocc
            writer.Perform(doc, TColStd_IndexedDataMapOfStringString(), Message_ProgressRange())
            logger.info(f"Successfully exported GLB to {path}")
            
            thumbnail_path = os.path.splitext(path.replace("converted", "thumbnails"))[0] + ".png"
            generate_model_thumbnail(path, thumbnail_path)
        else:
            logger.warning("No visible shapes to export.")

    def _reconstruct_occ_shape(self, obj, existing_shapes) -> Optional[Any]:
        """
        Reconstruct the OpenCascade TopoDS_Shape for a given object.
        """
        try:
            from OCC.Core.BRepPrimAPI import (
                BRepPrimAPI_MakeBox,
                BRepPrimAPI_MakeCylinder,
                BRepPrimAPI_MakeSphere,
                BRepPrimAPI_MakeCone,
                BRepPrimAPI_MakeTorus,
            )
            from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
            from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax2, gp_Trsf, gp_Ax1
            from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform, BRepBuilderAPI_Copy
            from OCC.Core.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        except ImportError:
            logger.error("Reconstruction requires pythonocc-core.")
            return None
        
        # Helper: Apply Refine (UnifySameDomain)
        def apply_refine(shape):
            unif = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
            unif.Build()
            return unif.Shape()

        # Helper: Apply Placement (Position, Rotation)
        def apply_placement(shape, placement):
            if shape is None: return None
            
            pos = placement.Position # [x, y, z]
            axis = placement.Axis    # [x, y, z]
            angle = placement.Angle  # degrees
            
            trsf = gp_Trsf()
            
            # 1. Rotation (around Origin)
            if axis and (axis[0] != 0 or axis[1] != 0 or axis[2] != 0):
                 occ_axis = gp_Ax1(gp_Pnt(0,0,0), gp_Dir(axis[0], axis[1], axis[2]))
                 trsf.SetRotation(occ_axis, math.radians(angle))
            
            # 2. Translation (Move the rotated shape to position)
            if pos:
                trsf.SetTranslationPart(gp_Vec(pos[0], pos[1], pos[2]))
            
            return BRepBuilderAPI_Transform(shape, trsf, True).Shape()

        # Resolve shape type enum to string
        shape_type = obj.shape.value if hasattr(obj.shape, "value") else str(obj.shape)
        params = obj.parameters
        occ_shape = None

        try:
            if shape_type == "Part::Box":
                occ_shape = BRepPrimAPI_MakeBox(params.Length, params.Width, params.Height).Shape()

            elif shape_type == "Part::Cylinder":
                occ_shape = BRepPrimAPI_MakeCylinder(params.Radius, params.Height, math.radians(params.Angle)).Shape()
            
            elif shape_type == "Part::Sphere":
                occ_shape = BRepPrimAPI_MakeSphere(params.Radius, math.radians(params.Angle3)).Shape()

            elif shape_type == "Part::Cone":
                occ_shape = BRepPrimAPI_MakeCone(params.Radius1, params.Radius2, params.Height, math.radians(params.Angle)).Shape()
                
            elif shape_type == "Part::Torus":
                occ_shape = BRepPrimAPI_MakeTorus(params.Radius1, params.Radius2, math.radians(params.Angle3)).Shape()

            elif shape_type == "Part::Cut":
                base = existing_shapes.get(params.Base)
                tool = existing_shapes.get(params.Tool)
                
                if base and tool:
                    # 使用 BRepBuilderAPI_Copy 复制形状，避免修改原始数据
                    base_copy = BRepBuilderAPI_Copy(base).Shape()
                    tool_copy = BRepBuilderAPI_Copy(tool).Shape()
                    
                    algo = BRepAlgoAPI_Cut(base_copy, tool_copy)
                    # [关键修复] 设置模糊容差，解决重合面切割失败的问题
                    algo.SetFuzzyValue(1.e-6) 
                    algo.Build()
                    
                    if algo.IsDone():
                        occ_shape = algo.Shape()
                        if hasattr(params, "Refine") and params.Refine:
                            occ_shape = apply_refine(occ_shape)
                    else:
                        logger.warning(f"Cut operation failed for {obj.name}")

            elif shape_type == "Part::MultiFuse":
                shapes_list = params.Shapes
                valid_shapes = [existing_shapes.get(s) for s in shapes_list if existing_shapes.get(s)]
                
                if len(valid_shapes) >= 2:
                    current_shape = BRepBuilderAPI_Copy(valid_shapes[0]).Shape()
                    
                    for i in range(1, len(valid_shapes)):
                        next_shape = BRepBuilderAPI_Copy(valid_shapes[i]).Shape()
                        algo = BRepAlgoAPI_Fuse(current_shape, next_shape)
                        algo.SetFuzzyValue(1.e-6)
                        algo.Build()
                        if algo.IsDone():
                            current_shape = algo.Shape()
                    
                    occ_shape = current_shape
                    if hasattr(params, "Refine") and params.Refine:
                        occ_shape = apply_refine(occ_shape)

            elif shape_type == "Part::MultiCommon":
                shapes_list = params.Shapes
                valid_shapes = [existing_shapes.get(s) for s in shapes_list if existing_shapes.get(s)]
                
                if len(valid_shapes) >= 2:
                    current_shape = BRepBuilderAPI_Copy(valid_shapes[0]).Shape()
                    for i in range(1, len(valid_shapes)):
                        next_shape = BRepBuilderAPI_Copy(valid_shapes[i]).Shape()
                        algo = BRepAlgoAPI_Common(current_shape, next_shape)
                        algo.SetFuzzyValue(1.e-6)
                        algo.Build()
                        if algo.IsDone():
                            current_shape = algo.Shape()
                    
                    occ_shape = current_shape
                    if hasattr(params, "Refine") and params.Refine:
                        occ_shape = apply_refine(occ_shape)

        except Exception as e:
            logger.error(f"Error reconstructing object {obj.name} ({shape_type}): {e}")
            return None
        
        # Finally, apply the placement
        if occ_shape and hasattr(params, 'Placement'):
            occ_shape = apply_placement(occ_shape, params.Placement)
            
        return occ_shape
    
    @classmethod
    def _path_to_comm(cls, filePath: Optional[str]) -> Dict:
        path = None
        format = None
        contentType = None

        if filePath is not None:
            path = filePath
            file_name = Path(path).name
            try:
                ext = file_name.split(".")[1].lower()
            except Exception:
                raise ValueError("Can not detect file extension!")
            if ext == "fcstd":
                format = "base64"
                contentType = "FCStd"
            elif ext == "jcad":
                format = "text"
                contentType = "jcad"
            else:
                raise ValueError("File extension is not supported!")
        return dict(
            path=path, format=format, contentType=contentType, createydoc=path is None
        )

    def get_object(self, name: str) -> Optional["PythonJcadObject"]:
        if self.check_exist(name):
            data = self._get_yobject_by_name(name).to_py()
            return OBJECT_FACTORY.create_object(data, self)

    def _get_color(self, shape_id: str | int) -> str:
        shape = self.get_object(shape_id)
        if hasattr(shape, "parameters") and hasattr(shape.parameters, "Color"):
            color = shape.parameters.Color
            return color
        else:
            return "#808080"

    def remove(self, name: str) -> CadDocument:
        index = self._get_yobject_index_by_name(name)
        if self._objects_array and index != -1:
            self._objects_array.pop(index)
        return self

    def rename(self, old_name: str, new_name: str) -> CadDocument:
        if new_name == old_name:
            return self
        new_obj = self.get_object(old_name)
        new_obj.name = new_name
        self.add_object(new_obj).remove(old_name)
        return self

    def add_object(self, new_object: "PythonJcadObject") -> CadDocument:
        if self._objects_array is not None and not self.check_exist(new_object.name):
            obj_dict = json.loads(new_object.model_dump_json())
            obj_dict["visible"] = True
            new_map = Map(obj_dict)
            self._objects_array.append(new_map)
        else:
            logger.error(f"Object {new_object.name} already exists")
        return self

    def add_annotation(
        self,
        parent: str,
        message: str,
        *,
        position: Optional[List[float]] = None,
        user: Optional[Dict] = None,
    ) -> Optional[str]:
        new_id = f"annotation_${uuid4()}"
        parent_obj = self.get_object(parent)
        if parent_obj is None:
            raise ValueError("Parent object not found")

        if position is None:
            position = (
                parent_obj.metadata.centerOfMass
                if parent_obj.metadata is not None
                else [0, 0, 0]
            )
        contents = [{"user": user, "value": message}]
        if self._metadata is not None:
            self._metadata[new_id] = json.dumps(
                {
                    "position": position,
                    "contents": contents,
                    "parent": parent,
                }
            )
            return new_id

    def remove_annotation(self, annotation_id: str) -> None:
        if self._metadata is not None:
            del self._metadata[annotation_id]

    def add_step_file(
        self,
        path: str,
        name: str = "",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        shape_name = name if name else Path(path).stem
        if self.check_exist(shape_name):
            logger.error(f"Object {shape_name} already exists")
            return

        with open(path, "r") as fobj:
            data = fobj.read()

        data = {
            "shape": "Part::Any",
            "name": shape_name,
            "parameters": {
                "Content": data,
                "Type": "STEP",
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
            "visible": True,
        }

        self._objects_array.append(Map(data))

        return self

    def add_occ_shape(
        self,
        shape,
        name: str = "",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        try:
            from OCC.Core.BRepTools import breptools
        except ImportError:
            raise RuntimeError("Cannot add an OpenCascade shape if it's not installed.")

        shape_name = name if name else self._new_name("OCCShape")
        if self.check_exist(shape_name):
            logger.error(f"Object {shape_name} already exists")
            return

        with tempfile.NamedTemporaryFile() as tmp:
            breptools.Write(shape, tmp.name, True, False, 1)
            brepdata = tmp.read().decode("ascii")

        data = {
            "shape": "Part::Any",
            "name": shape_name,
            "parameters": {
                "Content": brepdata,
                "Type": "brep",
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
            "visible": True,
        }

        self._objects_array.append(Map(data))

        return self

    def add_box(
        self,
        name: str = "",
        length: float = 1,
        width: float = 1,
        height: float = 1,
        color: str = "#808080",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        data = {
            "shape": Parts.Part__Box.value,
            "name": name if name else self._new_name("Box"),
            "parameters": {
                "Length": length,
                "Width": width,
                "Height": height,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def add_cone(
        self,
        name: str = "",
        radius1: float = 1,
        radius2: float = 0.5,
        height: float = 1,
        angle: float = 360,
        color: str = "#808080",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        data = {
            "shape": Parts.Part__Cone.value,
            "name": name if name else self._new_name("Cone"),
            "parameters": {
                "Radius1": radius1,
                "Radius2": radius2,
                "Height": height,
                "Angle": angle,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def add_cylinder(
        self,
        name: str = "",
        radius: float = 1,
        height: float = 1,
        angle: float = 360,
        color: str = "#808080",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        data = {
            "shape": Parts.Part__Cylinder.value,
            "name": name if name else self._new_name("Cylinder"),
            "parameters": {
                "Radius": radius,
                "Height": height,
                "Angle": angle,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def add_sphere(
        self,
        name: str = "",
        radius: float = 5,
        angle1: float = -90,
        angle2: float = 90,
        angle3: float = 360,
        color: str = "#808080",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        data = {
            "shape": Parts.Part__Sphere.value,
            "name": name if name else self._new_name("Sphere"),
            "parameters": {
                "Radius": radius,
                "Angle1": angle1,
                "Angle2": angle2,
                "Angle3": angle3,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def add_torus(
        self,
        name: str = "",
        radius1: float = 10,
        radius2: float = 2,
        angle1: float = -180,
        angle2: float = 180,
        angle3: float = 360,
        color: str = "#808080",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        data = {
            "shape": Parts.Part__Torus.value,
            "name": name if name else self._new_name("Torus"),
            "parameters": {
                "Radius1": radius1,
                "Radius2": radius2,
                "Angle1": angle1,
                "Angle2": angle2,
                "Angle3": angle3,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def add_sketch(
        self,
        name: str = "",
        geometry: List[
            Union[geomCircle.IGeomCircle, geomLineSegment.IGeomLineSegment]
        ] = [],
        attachment_offset_position: List[float] = [0, 0, 0],
        attachment_offset_rotation_axis: List[float] = [0, 0, 1],
        attachment_offset_rotation_angle: float = 0,
        color: str = "#808080",
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        data = {
            "shape": Parts.Sketcher__SketchObject.value,
            "name": name if name else self._new_name("Sketch"),
            "parameters": {
                "AttachmentOffset": {
                    "Position": attachment_offset_position,
                    "Axis": attachment_offset_rotation_axis,
                    "Angle": attachment_offset_rotation_angle,
                },
                "Geometry": geometry,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def cut(
        self,
        name: str = "",
        base: str | int = None,
        tool: str | int = None,
        refine: bool = False,
        color: Optional[str] = None,
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        base, tool = self._get_boolean_operands(base, tool)

        if color is None:
            color = self._get_color(base)

        data = {
            "shape": Parts.Part__Cut.value,
            "name": name if name else self._new_name("Cut"),
            "parameters": {
                "Base": base,
                "Tool": tool,
                "Refine": refine,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        self.set_visible(base, False)
        self.set_visible(tool, False)
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def fuse(
        self,
        name: str = "",
        shape1: str | int = None,
        shape2: str | int = None,
        refine: bool = False,
        color: Optional[str] = None,
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        shape1, shape2 = self._get_boolean_operands(shape1, shape2)

        if color is None:
            color = self._get_color(shape1)

        data = {
            "shape": Parts.Part__MultiFuse.value,
            "name": name if name else self._new_name("Fuse"),
            "parameters": {
                "Shapes": [shape1, shape2],
                "Refine": refine,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        self.set_visible(shape1, False)
        self.set_visible(shape2, False)
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def intersect(
        self,
        name: str = "",
        shape1: str | int = None,
        shape2: str | int = None,
        refine: bool = False,
        color: Optional[str] = None,
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        shape1, shape2 = self._get_boolean_operands(shape1, shape2)

        if color is None:
            color = self._get_color(shape1)

        data = {
            "shape": Parts.Part__MultiCommon.value,
            "name": name if name else self._new_name("Intersection"),
            "parameters": {
                "Shapes": [shape1, shape2],
                "Refine": refine,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        self.set_visible(shape1, False)
        self.set_visible(shape2, False)
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def extrude(
        self,
        name: str = "",
        shape: str | int = None,
        direction: List[float] = [0, 0, 1],
        length_fwd: float = 10,
        length_rev: float = 0,
        solid: bool = False,
        color: Optional[str] = None,
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        shape = self._get_operand(shape)

        if color is None:
            color = self._get_color(shape)

        data = {
            "shape": Parts.Part__Extrusion.value,
            "name": name if name else self._new_name("Extrusion"),
            "parameters": {
                "Base": shape,
                "Dir": direction,
                "LengthFwd": length_fwd,
                "LengthRev": length_rev,
                "Solid": solid,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        self.set_visible(shape, False)
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def chamfer(
        self,
        name: str = "",
        shape: str | int = None,
        edge: int = 0,
        dist: float = 0.1,
        color: Optional[str] = None,
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        shape = self._get_operand(shape)

        if color is None:
            color = self._get_color(shape)

        data = {
            "shape": Parts.Part__Chamfer.value,
            "name": name if name else self._new_name("Chamfer"),
            "parameters": {
                "Base": shape,
                "Edge": edge,
                "Dist": dist,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        self.set_visible(shape, False)
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def fillet(
        self,
        name: str = "",
        shape: str | int = None,
        edge: int = 0,
        radius: float = 0.1,
        color: Optional[str] = None,
        position: List[float] = [0, 0, 0],
        rotation_axis: List[float] = [0, 0, 1],
        rotation_angle: float = 0,
    ) -> CadDocument:
        shape = self._get_operand(shape)

        if color is None:
            color = self._get_color(shape)

        data = {
            "shape": Parts.Part__Fillet.value,
            "name": name if name else self._new_name("Fillet"),
            "parameters": {
                "Base": shape,
                "Edge": edge,
                "Radius": radius,
                "Color": color,
                "Placement": {
                    "Position": position,
                    "Axis": rotation_axis,
                    "Angle": rotation_angle,
                },
            },
        }
        self.set_visible(shape, False)
        return self.add_object(OBJECT_FACTORY.create_object(data, self))

    def _get_operand(self, shape: str | int | None, default_idx: int = -1):
        if isinstance(shape, str):
            if shape not in self.objects:
                raise ValueError(f"Unknown object {shape}")
        elif isinstance(shape, int):
            shape = self.objects[shape]
        else:
            shape = self.objects[default_idx]

        return shape

    def _get_boolean_operands(self, shape1: str | int | None, shape2: str | int | None):
        if len(self.objects) < 2:
            raise ValueError(
                "Cannot apply boolean operator if there are less than two objects in the document."  # noqa E501
            )

        shape1 = self._get_operand(shape1, -2)
        shape2 = self._get_operand(shape2, -1)

        return shape1, shape2

    def set_visible(self, name: str, value):
        obj: Optional[Map] = self._get_yobject_by_name(name)
        if obj is None:
            raise RuntimeError(f"No object named {name}")
        obj["visible"] = value

    def set_color(self, name: str, value: str):
        obj: Optional[Map] = self._get_yobject_by_name(name)
        if obj is None:
            raise RuntimeError(f"No object named {name}")
        parameters = obj.get("parameters", {})
        parameters["Color"] = value
        obj["parameters"] = parameters

    def check_exist(self, name: str) -> bool:
        if self.objects:
            return name in self.objects
        return False

    def _get_yobject_by_name(self, name: str) -> Optional[Map]:
        if self._objects_array:
            for index, item in enumerate(self._objects_array):
                if item["name"] == name:
                    return self._objects_array[index]
        return None

    def _get_yobject_index_by_name(self, name: str) -> int:
        if self._objects_array:
            for index, item in enumerate(self._objects_array):
                if item["name"] == name:
                    return index
        return -1

    def _new_name(self, obj_type: str) -> str:
        n = 1
        name = f"{obj_type} 1"
        objects = self.objects

        while name in objects:
            name = f"{obj_type} {n}"
            n += 1

        return name


class PythonJcadObject(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    name: str
    visible: bool = True
    shape: Parts
    parameters: Union[
        IAny,
        IBox,
        ICone,
        ICut,
        ICylinder,
        IExtrusion,
        IIntersection,
        IFuse,
        ISphere,
        ITorus,
        ISketchObject,
        IFillet,
        IChamfer,
    ]
    metadata: Optional[ShapeMetadata]
    _caddoc = Optional[CadDocument]
    _parent = Optional[CadDocument]

    def __init__(__pydantic_self__, parent, **data: Any) -> None:  # noqa
        super().__init__(**data)
        __pydantic_self__._caddoc = CadDocument()
        __pydantic_self__._caddoc.add_object(__pydantic_self__)
        __pydantic_self__._parent = parent


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class ObjectFactoryManager(metaclass=SingletonMeta):
    def __init__(self):
        self._factories: Dict[str, type[BaseModel]] = {}

    def register_factory(self, shape_type: str, cls: type[BaseModel]) -> None:
        if shape_type not in self._factories:
            self._factories[shape_type] = cls

    def create_object(
        self, data: Dict, parent: Optional[CadDocument] = None
    ) -> Optional[PythonJcadObject]:
        object_type = data.get("shape", None)
        name: str = data.get("name", None)
        meta = data.get("shapeMetadata", None)
        visible = data.get("visible", True)
        
        if object_type and object_type in self._factories:
            Model = self._factories[object_type]
            args = {}
            params = data["parameters"]
            for field in Model.model_fields:
                args[field] = params.get(field, None)
            obj_params = Model(**args)
            return PythonJcadObject(
                parent=parent,
                name=name,
                shape=object_type,
                parameters=obj_params,
                metadata=meta,
                visible=visible
            )

        return None


OBJECT_FACTORY = ObjectFactoryManager()

OBJECT_FACTORY.register_factory(Parts.Part__Any.value, IAny)
OBJECT_FACTORY.register_factory(Parts.Part__Box.value, IBox)
OBJECT_FACTORY.register_factory(Parts.Part__Cone.value, ICone)
OBJECT_FACTORY.register_factory(Parts.Part__Cut.value, ICut)
OBJECT_FACTORY.register_factory(Parts.Part__Cylinder.value, ICylinder)
OBJECT_FACTORY.register_factory(Parts.Part__Extrusion.value, IExtrusion)
OBJECT_FACTORY.register_factory(Parts.Part__MultiCommon.value, IIntersection)
OBJECT_FACTORY.register_factory(Parts.Part__MultiFuse.value, IFuse)
OBJECT_FACTORY.register_factory(Parts.Part__Sphere.value, ISphere)
OBJECT_FACTORY.register_factory(Parts.Part__Torus.value, ITorus)
OBJECT_FACTORY.register_factory(Parts.Sketcher__SketchObject.value, ISketchObject)
OBJECT_FACTORY.register_factory(Parts.Part__Chamfer.value, IChamfer)
OBJECT_FACTORY.register_factory(Parts.Part__Fillet.value, IFillet)