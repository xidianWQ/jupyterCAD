/**
 * Conversion utilities between JCAD Schema and Assembly Schema
 * for DTEditor integration
 */
/**
 * Placement converter utility
 * Handles conversion between JCAD Placement and Assembly feature position/axis/normal
 */
export class PlacementConverter {
    /**
     * JCAD Placement → Assembly position
     */
    static jcadToAssemblyPosition(placement) {
        const pos = placement.Position;
        return [pos[0], pos[1], pos[2]];
    }
    /**
     * JCAD Placement → Assembly axis
     */
    static jcadToAssemblyAxis(placement) {
        const normalized = this.normalize([...placement.Axis]);
        return [normalized[0], normalized[1], normalized[2]];
    }
    /**
     * Assembly center → JCAD Position
     */
    static assemblyCenterToJCADPosition(center) {
        return {
            Position: [center[0], center[1], center[2]],
            Axis: [0, 0, 1],
            Angle: 0
        };
    }
    /**
     * Assembly position/axis → JCAD Placement
     */
    static assemblyPositionAxisToJCADPlacement(position, axis) {
        const normalized = this.normalize([...axis]);
        return {
            Position: [position[0], position[1], position[2]],
            Axis: [normalized[0], normalized[1], normalized[2]],
            Angle: 0
        };
    }
    /**
     * Assembly position/normal → JCAD Placement
     */
    static assemblyPositionNormalToJCADPlacement(position, normal) {
        const normalized = this.normalize([...normal]);
        return {
            Position: [position[0], position[1], position[2]],
            Axis: [normalized[0], normalized[1], normalized[2]],
            Angle: 0
        };
    }
    /**
     * Vector normalization
     */
    static normalize(v) {
        const len = Math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2);
        if (len === 0)
            return [0, 0, 1];
        return [v[0] / len, v[1] / len, v[2] / len];
    }
    /**
     * Calculate vector length
     */
    static vectorLength(v) {
        return Math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2);
    }
    /**
     * Dot product of two vectors
     */
    static dot(v1, v2) {
        return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2];
    }
    /**
     * Cross product of two vectors
     */
    static cross(v1, v2) {
        return [
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0]
        ];
    }
}
/**
 * JCAD to Assembly converter
 * Extracts assembly features from JCAD objects
 */
export class JCADToAssemblyConverter {
    /**
     * Extract assembly features from a JCAD object
     */
    static extractFeatures(jcadObject) {
        // If the object already has geometryFeatures, use them
        if (jcadObject.geometryFeatures && jcadObject.geometryFeatures.length > 0) {
            return jcadObject.geometryFeatures;
        }
        // Otherwise, automatically extract features based on shape type
        const features = [];
        switch (jcadObject.shape) {
            case 'Part::Box':
                features.push(...this.convertBox(jcadObject));
                break;
            default:
                // For other shapes, no automatic extraction
                break;
        }
        return features;
    }
    /**
     * Convert Box to assembly features (extract faces)
     *
     * Returns 6 face features for the 6 faces of the box
     */
    static convertBox(obj) {
        const params = obj.parameters;
        const placement = params.Placement;
        const [x, y, z] = placement.Position;
        const [l, w, h] = [params.Length, params.Width, params.Height];
        // Return 6 face features
        return [
            {
                type: 'Feature::Face',
                name: `${obj.name}_top`,
                normal: [0, 1, 0],
                center: [x, y + h / 2, z],
                metadata: { originalObject: obj.name, face: 'top' }
            },
            {
                type: 'Feature::Face',
                name: `${obj.name}_bottom`,
                normal: [0, -1, 0],
                center: [x, y - h / 2, z],
                metadata: { originalObject: obj.name, face: 'bottom' }
            },
            {
                type: 'Feature::Face',
                name: `${obj.name}_front`,
                normal: [0, 0, 1],
                center: [x, y, z + w / 2],
                metadata: { originalObject: obj.name, face: 'front' }
            },
            {
                type: 'Feature::Face',
                name: `${obj.name}_back`,
                normal: [0, 0, -1],
                center: [x, y, z - w / 2],
                metadata: { originalObject: obj.name, face: 'back' }
            },
            {
                type: 'Feature::Face',
                name: `${obj.name}_right`,
                normal: [1, 0, 0],
                center: [x + l / 2, y, z],
                metadata: { originalObject: obj.name, face: 'right' }
            },
            {
                type: 'Feature::Face',
                name: `${obj.name}_left`,
                normal: [-1, 0, 0],
                center: [x - l / 2, y, z],
                metadata: { originalObject: obj.name, face: 'left' }
            }
        ];
    }
}
/**
 * Assembly to JCAD converter
 * Creates JCAD objects from assembly features
 */
export class AssemblyToJCADConverter {
    /**
     * Create a JCAD object from an assembly feature
     */
    static createJCADObject(feature, objectName) {
        throw new Error(`Unsupported feature type for JCAD creation: ${feature.type}`);
    }
}
/**
 * Unified geometry feature converter
 * Provides batch conversion and validation utilities
 */
export class GeometryFeatureConverter {
    /**
     * Batch convert JCAD objects to assembly features
     */
    static jcadBatchToAssembly(jcadObjects) {
        const features = [];
        for (const obj of jcadObjects) {
            // If object has geometryFeatures, use them directly
            if (obj.geometryFeatures && obj.geometryFeatures.length > 0) {
                features.push(...obj.geometryFeatures);
            }
            else {
                // Otherwise, automatically extract
                features.push(...JCADToAssemblyConverter.extractFeatures(obj));
            }
        }
        return features;
    }
    /**
     * Create JCAD assembly from assembly features
     */
    static assemblyToJCADAssembly(features) {
        var _a;
        const jcadObjects = [];
        for (const feature of features) {
            const objectName = ((_a = feature.metadata) === null || _a === void 0 ? void 0 : _a.originalObject) ||
                `${feature.type}_${feature.name}`;
            try {
                const jcadObj = AssemblyToJCADConverter.createJCADObject(feature, objectName);
                jcadObjects.push(jcadObj);
            }
            catch (e) {
                console.warn(`Failed to convert feature ${feature.name}:`, e);
            }
        }
        return jcadObjects;
    }
    /**
     * Validate feature completeness
     */
    static validateFeature(feature) {
        const requiredFields = {
            'Feature::Circle': ['center', 'normal', 'radius'],
            'Feature::Face': ['normal', 'center']
        };
        const required = requiredFields[feature.type];
        if (!required)
            return false;
        for (const field of required) {
            if (!(field in feature) || feature[field] === undefined) {
                return false;
            }
        }
        return true;
    }
    /**
     * Get required fields for a feature type
     */
    static getRequiredFields(featureType) {
        const fieldMap = {
            'Feature::Circle': ['center', 'normal', 'radius'],
            'Feature::Face': ['normal', 'center'],
            'Feature::Point': ['position'],
            'Feature::Edge': ['position'] // simplified
        };
        return fieldMap[featureType] || [];
    }
}
/**
 * Parameter mapping reference
 * Documents the mapping between JCAD and Assembly parameters
 */
export const ParameterMapping = {
// Note: Cylinder, Sphere, Cone, Torus features are not supported for export
};
