/**
 * Conversion utilities between JCAD Schema and Assembly Schema
 * for DTEditor integration
 */
import { IJCadObject, IGeometryFeature } from './_interface/jcad';
/**
 * JCAD Placement interface (axis-angle representation)
 */
interface JCADPlacement {
    Position: number[];
    Axis: number[];
    Angle: number;
}
/**
 * Placement converter utility
 * Handles conversion between JCAD Placement and Assembly feature position/axis/normal
 */
export declare class PlacementConverter {
    /**
     * JCAD Placement → Assembly position
     */
    static jcadToAssemblyPosition(placement: JCADPlacement): [number, number, number];
    /**
     * JCAD Placement → Assembly axis
     */
    static jcadToAssemblyAxis(placement: JCADPlacement): [number, number, number];
    /**
     * Assembly center → JCAD Position
     */
    static assemblyCenterToJCADPosition(center: number[]): JCADPlacement;
    /**
     * Assembly position/axis → JCAD Placement
     */
    static assemblyPositionAxisToJCADPlacement(position: number[], axis: number[]): JCADPlacement;
    /**
     * Assembly position/normal → JCAD Placement
     */
    static assemblyPositionNormalToJCADPlacement(position: number[], normal: number[]): JCADPlacement;
    /**
     * Vector normalization
     */
    static normalize(v: number[]): number[];
    /**
     * Calculate vector length
     */
    static vectorLength(v: number[]): number;
    /**
     * Dot product of two vectors
     */
    static dot(v1: number[], v2: number[]): number;
    /**
     * Cross product of two vectors
     */
    static cross(v1: number[], v2: number[]): number[];
}
/**
 * JCAD to Assembly converter
 * Extracts assembly features from JCAD objects
 */
export declare class JCADToAssemblyConverter {
    /**
     * Extract assembly features from a JCAD object
     */
    static extractFeatures(jcadObject: IJCadObject): IGeometryFeature[];
    /**
     * Convert Box to assembly features (extract faces)
     *
     * Returns 6 face features for the 6 faces of the box
     */
    private static convertBox;
}
/**
 * Assembly to JCAD converter
 * Creates JCAD objects from assembly features
 */
export declare class AssemblyToJCADConverter {
    /**
     * Create a JCAD object from an assembly feature
     */
    static createJCADObject(feature: IGeometryFeature, objectName: string): IJCadObject;
}
/**
 * Unified geometry feature converter
 * Provides batch conversion and validation utilities
 */
export declare class GeometryFeatureConverter {
    /**
     * Batch convert JCAD objects to assembly features
     */
    static jcadBatchToAssembly(jcadObjects: IJCadObject[]): IGeometryFeature[];
    /**
     * Create JCAD assembly from assembly features
     */
    static assemblyToJCADAssembly(features: IGeometryFeature[]): IJCadObject[];
    /**
     * Validate feature completeness
     */
    static validateFeature(feature: IGeometryFeature): boolean;
    /**
     * Get required fields for a feature type
     */
    static getRequiredFields(featureType: string): string[];
}
/**
 * Parameter mapping reference
 * Documents the mapping between JCAD and Assembly parameters
 */
export declare const ParameterMapping: {};
export {};
