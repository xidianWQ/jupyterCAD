import { CommandRegistry } from '@lumino/commands';
import { ContextMenu } from '@lumino/widgets';
import * as Color from 'd3-color';
import * as React from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js';
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import { ViewHelper } from 'three/examples/jsm/helpers/ViewHelper';
import { FloatingAnnotation } from '../annotation';
import { getCSSVariableColor, throttle } from '../tools';
import { FollowIndicator } from './followindicator';
import { DEFAULT_EDGE_COLOR, DEFAULT_EDGE_COLOR_CSS, DEFAULT_LINEWIDTH, DEFAULT_MESH_COLOR, DEFAULT_MESH_COLOR_CSS, SELECTED_LINEWIDTH, BOUNDING_BOX_COLOR, BOUNDING_BOX_COLOR_CSS, SELECTION_BOUNDING_BOX, buildShape, computeExplodedState, projectVector, getQuaternion, SPLITVIEW_BACKGROUND_COLOR, SPLITVIEW_BACKGROUND_COLOR_CSS } from './helpers';
import { Spinner } from './spinner';
const CAMERA_NEAR = 1e-6;
const CAMERA_FAR = 1e27;
// The amount of pixels a mouse move can do until we stop considering it's a click
const CLICK_THRESHOLD = 5;
// 添加此辅助函数用于触发浏览器下载
function downloadGLB(buffer, filename) {
    const blob = new Blob([buffer], { type: 'model/gltf-binary' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}
export class MainView extends React.Component {
    constructor(props) {
        super(props);
        this.addContextMenu = () => {
            const commands = new CommandRegistry();
            commands.addCommand('add-annotation', {
                describedBy: {
                    args: {
                        type: 'object',
                        properties: {}
                    }
                },
                execute: () => {
                    if (!this._pointer3D) {
                        return;
                    }
                    const position = new THREE.Vector3().copy(this._pointer3D.mesh.position);
                    // If in exploded view, we scale down to the initial position (to before exploding the view)
                    if (this.explodedViewEnabled) {
                        const explodedState = computeExplodedState({
                            mesh: this._pointer3D.mesh,
                            boundingGroup: this._boundingGroup,
                            factor: this._explodedView.factor
                        });
                        position.add(explodedState.vector.multiplyScalar(-explodedState.distance));
                    }
                    this._mainViewModel.addAnnotation({
                        position: [position.x, position.y, position.z],
                        label: 'New annotation',
                        contents: [],
                        parent: this._pointer3D.parent.name
                    });
                },
                label: 'Add annotation',
                isEnabled: () => {
                    return !!this._pointer3D;
                }
            });
            this._contextMenu = new ContextMenu({ commands });
            this._contextMenu.addItem({
                command: 'add-annotation',
                selector: 'canvas',
                rank: 1
            });
        };
        this.sceneSetup = () => {
            var _a, _b;
            if (this._divRef.current !== null) {
                DEFAULT_MESH_COLOR.set(getCSSVariableColor(DEFAULT_MESH_COLOR_CSS));
                DEFAULT_EDGE_COLOR.set(getCSSVariableColor(DEFAULT_EDGE_COLOR_CSS));
                BOUNDING_BOX_COLOR.set(getCSSVariableColor(BOUNDING_BOX_COLOR_CSS));
                SPLITVIEW_BACKGROUND_COLOR.set(getCSSVariableColor(SPLITVIEW_BACKGROUND_COLOR_CSS));
                if (this._mainViewModel.viewSettings.cameraSettings) {
                    const cameraSettings = this._mainViewModel.viewSettings
                        .cameraSettings;
                    if (cameraSettings.type === 'Perspective') {
                        this._camera = new THREE.PerspectiveCamera(50, 2, CAMERA_NEAR, CAMERA_FAR);
                    }
                    else if (cameraSettings.type === 'Orthographic') {
                        const width = ((_a = this._divRef.current) === null || _a === void 0 ? void 0 : _a.clientWidth) || 0;
                        const height = ((_b = this._divRef.current) === null || _b === void 0 ? void 0 : _b.clientHeight) || 0;
                        this._camera = new THREE.OrthographicCamera(width / -2, width / 2, height / 2, height / -2);
                        this._camera.updateProjectionMatrix();
                    }
                }
                this._camera.position.set(8, 8, 8);
                this._camera.up.set(0, 0, 1);
                this._scene = new THREE.Scene();
                this._ambientLight = new THREE.AmbientLight(0xffffff, 0.5); // soft white light
                this._scene.add(this._ambientLight);
                this._cameraLight = new THREE.PointLight(0xffffff, 1);
                this._cameraLight.decay = 0;
                this._camera.add(this._cameraLight);
                this._scene.add(this._camera);
                this._renderer = new THREE.WebGLRenderer({
                    alpha: true,
                    antialias: true,
                    stencil: true,
                    logarithmicDepthBuffer: true
                });
                this._clock = new THREE.Clock();
                // this._renderer.setPixelRatio(window.devicePixelRatio);
                this._renderer.autoClear = false;
                this._renderer.setClearColor(0x000000, 0);
                this._renderer.setSize(500, 500, false);
                this._divRef.current.appendChild(this._renderer.domElement); // mount using React ref
                this._syncPointer = throttle((position, parent) => {
                    if (position && parent) {
                        this._model.syncPointer({
                            parent,
                            x: position.x,
                            y: position.y,
                            z: position.z
                        });
                    }
                    else {
                        this._model.syncPointer(undefined);
                    }
                }, 100);
                this._renderer.domElement.addEventListener('pointermove', this._onPointerMove.bind(this));
                this._renderer.domElement.addEventListener('contextmenu', e => {
                    e.preventDefault();
                    e.stopPropagation();
                });
                document.addEventListener('keydown', e => {
                    this._onKeyDown(e);
                });
                // Not enabling damping since it makes the syncing between cameraL and camera trickier
                this._controls = new OrbitControls(this._camera, this._renderer.domElement);
                this._controls.target.set(this._scene.position.x, this._scene.position.y, this._scene.position.z);
                this._renderer.domElement.addEventListener('mousedown', e => {
                    this._mouseDrag.start.set(e.clientX, e.clientY);
                    this._mouseDrag.button = e.button;
                });
                this._renderer.domElement.addEventListener('mouseup', e => {
                    this._mouseDrag.end.set(e.clientX, e.clientY);
                    const distance = this._mouseDrag.end.distanceTo(this._mouseDrag.start);
                    if (distance <= CLICK_THRESHOLD) {
                        if (this._mouseDrag.button === 0) {
                            this._onClick(e);
                        }
                        else if (this._mouseDrag.button === 2) {
                            this._contextMenu.open(e);
                        }
                    }
                });
                this._controls.addEventListener('change', () => {
                    this._updateAnnotation();
                });
                this._controls.addEventListener('change', throttle(() => {
                    var _a;
                    // Not syncing camera state if following someone else
                    if ((_a = this._model.localState) === null || _a === void 0 ? void 0 : _a.remoteUser) {
                        return;
                    }
                    this._model.syncCamera({
                        position: this._camera.position.toArray([]),
                        rotation: [
                            this._camera.rotation.x,
                            this._camera.rotation.y,
                            this._camera.rotation.z
                        ],
                        up: this._camera.up.toArray([])
                    }, this._mainViewModel.id);
                }, 100));
                // Setting up the clip plane transform controls
                this._clipPlaneTransformControls = new TransformControls(this._camera, this._renderer.domElement);
                // Create half transparent plane mesh for controls
                this._clippingPlaneMeshControl = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
                    color: DEFAULT_MESH_COLOR,
                    opacity: 0.2,
                    transparent: true,
                    side: THREE.DoubleSide
                }));
                this._clippingPlaneMeshControl.visible = false;
                // Setting the fake plane position
                const target = new THREE.Vector3(0, 0, 1);
                this._clippingPlane.coplanarPoint(target);
                this._clippingPlaneMeshControl.geometry.translate(target.x, target.y, target.z);
                this._clippingPlaneMeshControl.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), this._clippingPlane.normal);
                this._scene.add(this._clippingPlaneMeshControl);
                // Disable the orbit control whenever we do transformation
                this._clipPlaneTransformControls.addEventListener('dragging-changed', event => {
                    this._controls.enabled = !event.value;
                });
                // Update the clipping plane whenever the transform UI move
                this._clipPlaneTransformControls.addEventListener('change', () => {
                    let normal = new THREE.Vector3(0, 0, 1);
                    normal = normal.applyEuler(this._clippingPlaneMeshControl.rotation);
                    // This is to prevent z-fighting
                    // We can't use the WebGL polygonOffset because of the logarithmic depth buffer
                    // Long term, when using the new WebGPURenderer, we could update the formula of the
                    // logarithmic depth computation to emulate the polygonOffset in the shaders directly
                    // refLength divided by 1000 looks like it's working fine to emulate a polygonOffset for now
                    const translation = this._refLength ? 0.001 * this._refLength : 0;
                    this._clippingPlane.setFromNormalAndCoplanarPoint(normal, this._clippingPlaneMeshControl.position);
                    this._clippingPlane.translate(normal.multiply(new THREE.Vector3(translation, translation, translation)));
                });
                this._clipPlaneTransformControls.attach(this._clippingPlaneMeshControl);
                this._scene.add(this._clipPlaneTransformControls);
                this._clipPlaneTransformControls.enabled = false;
                this._clipPlaneTransformControls.visible = false;
                this._transformControls = new TransformControls(this._camera, this._renderer.domElement);
                // Disable the orbit control whenever we do transformation
                this._transformControls.addEventListener('dragging-changed', event => {
                    this._controls.enabled = !event.value;
                });
                // Update the currently transformed object in the shared model once finished moving
                this._transformControls.addEventListener('mouseUp', async () => {
                    const updatedObject = this._selectedMeshes[0];
                    const objectName = updatedObject.name;
                    const updatedPosition = new THREE.Vector3();
                    updatedObject.getWorldPosition(updatedPosition);
                    const updatedQuaternion = new THREE.Quaternion();
                    updatedObject.getWorldQuaternion(updatedQuaternion);
                    const s = Math.sqrt(1 - updatedQuaternion.w * updatedQuaternion.w);
                    let updatedRotation;
                    if (s > 1e-6) {
                        updatedRotation = [
                            [
                                updatedQuaternion.x / s,
                                updatedQuaternion.y / s,
                                updatedQuaternion.z / s
                            ],
                            2 * Math.acos(updatedQuaternion.w) * (180 / Math.PI)
                        ];
                    }
                    else {
                        updatedRotation = [[0, 0, 1], 0];
                    }
                    const obj = this._model.sharedModel.getObjectByName(objectName);
                    if (obj && obj.parameters && obj.parameters.Placement) {
                        const newPosition = [
                            updatedPosition.x,
                            updatedPosition.y,
                            updatedPosition.z
                        ];
                        const done = await this._mainViewModel.maybeUpdateObjectParameters(objectName, Object.assign(Object.assign({}, obj.parameters), { Placement: Object.assign(Object.assign({}, obj.parameters.Placement), { Position: newPosition, Axis: updatedRotation[0], Angle: updatedRotation[1] }) }));
                        // If the dry run failed, we bring back the object to its original position
                        if (!done && updatedObject.parent) {
                            const origPosition = obj.parameters.Placement.Position;
                            // Undo positioning
                            updatedObject.parent.position.copy(new THREE.Vector3(0, 0, 0));
                            updatedObject.parent.applyQuaternion(updatedQuaternion.invert());
                            // Redo original positioning
                            updatedObject.parent.applyQuaternion(getQuaternion(obj));
                            updatedObject.parent.position.copy(new THREE.Vector3(origPosition[0], origPosition[1], origPosition[2]));
                        }
                    }
                });
                this._scene.add(this._transformControls);
                this._transformControls.setMode('translate');
                this._transformControls.setSpace('local');
                this._transformControls.enabled = false;
                this._transformControls.visible = false;
                this._createViewHelper();
            }
        };
        this.animate = () => {
            var _a, _b, _c;
            this._requestID = window.requestAnimationFrame(this.animate);
            const delta = this._clock.getDelta();
            for (const material of this._edgeMaterials) {
                material.resolution.set(this._renderer.domElement.width, this._renderer.domElement.height);
            }
            if (this._clippingPlaneMesh !== null) {
                this._clippingPlane.coplanarPoint(this._clippingPlaneMesh.position);
                this._clippingPlaneMesh.lookAt(this._clippingPlaneMesh.position.x - this._clippingPlane.normal.x, this._clippingPlaneMesh.position.y - this._clippingPlane.normal.y, this._clippingPlaneMesh.position.z - this._clippingPlane.normal.z);
            }
            if (this._viewHelper.animating) {
                this._viewHelper.update(delta);
            }
            this._controls.update();
            this._renderer.setRenderTarget(null);
            this._renderer.clear();
            if (this._sceneL && this._cameraL) {
                this._cameraL.matrixWorld.copy(this._camera.matrixWorld);
                this._cameraL.matrixWorld.decompose(this._cameraL.position, this._cameraL.quaternion, this._cameraL.scale);
                this._cameraL.updateProjectionMatrix();
                this._renderer.setScissor(0, 0, this._sliderPos, ((_a = this._divRef.current) === null || _a === void 0 ? void 0 : _a.clientHeight) || 0);
                this._renderer.render(this._sceneL, this._cameraL);
                this._renderer.setScissor(this._sliderPos, 0, ((_b = this._divRef.current) === null || _b === void 0 ? void 0 : _b.clientWidth) || 0, ((_c = this._divRef.current) === null || _c === void 0 ? void 0 : _c.clientHeight) || 0);
            }
            this._renderer.render(this._scene, this._camera);
            this._viewHelper.render(this._renderer);
            this.updateCameraRotation();
        };
        this.resizeCanvasToDisplaySize = () => {
            if (this._divRef.current !== null) {
                this._renderer.setSize(this._divRef.current.clientWidth, this._divRef.current.clientHeight, false);
                if (this._camera instanceof THREE.PerspectiveCamera) {
                    this._camera.aspect =
                        this._divRef.current.clientWidth / this._divRef.current.clientHeight;
                }
                else if (this._camera instanceof THREE.OrthographicCamera) {
                    this._camera.left = this._divRef.current.clientWidth / -2;
                    this._camera.right = this._divRef.current.clientWidth / 2;
                    this._camera.top = this._divRef.current.clientHeight / 2;
                    this._camera.bottom = this._divRef.current.clientHeight / -2;
                }
                this._camera.updateProjectionMatrix();
                if (this._sceneL && this._cameraL) {
                    this._sceneL.remove(this._cameraL);
                    this._cameraL = this._camera.clone();
                    this._sceneL.add(this._cameraL);
                }
            }
        };
        this.generateScene = () => {
            this.sceneSetup();
            this.animate();
            this.resizeCanvasToDisplaySize();
        };
        this._shapeToMesh = (payload) => {
            if (this._meshGroup !== null) {
                this._scene.remove(this._meshGroup);
            }
            if (this._explodedViewLinesHelperGroup !== null) {
                this._scene.remove(this._explodedViewLinesHelperGroup);
            }
            if (this._clippingPlaneMesh !== null) {
                this._scene.remove(this._clippingPlaneMesh);
            }
            const selectedNames = Object.keys(this._currentSelection || {});
            this._selectedMeshes = [];
            this._boundingGroup = new THREE.Box3();
            this._edgeMaterials = [];
            this._meshGroup = new THREE.Group();
            Object.entries(payload).forEach(([objName, data]) => {
                var _a, _b, _c, _d;
                const selected = selectedNames.includes(objName);
                const obj = this._model.sharedModel.getObjectByName(objName);
                const objColor = (_a = obj === null || obj === void 0 ? void 0 : obj.parameters) === null || _a === void 0 ? void 0 : _a.Color;
                const isWireframe = this.state.wireframe;
                // TODO Have a more generic way to spot non-solid objects
                const isSolid = !((obj === null || obj === void 0 ? void 0 : obj.shape) === 'Part::Extrusion' && !((_b = obj === null || obj === void 0 ? void 0 : obj.parameters) === null || _b === void 0 ? void 0 : _b['Solid']));
                const output = buildShape({
                    objName,
                    data,
                    clippingPlanes: this._clippingPlanes,
                    isSolid,
                    isWireframe,
                    objColor
                });
                if (output) {
                    const { meshGroup, mainMesh, edgesMeshes } = output;
                    if (meshGroup.userData.jcObject.visible) {
                        this._boundingGroup.expandByObject(meshGroup);
                    }
                    // Save original color for the main mesh
                    if ((_c = mainMesh.material) === null || _c === void 0 ? void 0 : _c.color) {
                        const originalMeshColor = new THREE.Color(objColor || DEFAULT_MESH_COLOR);
                        if (!selected) {
                            mainMesh.material.color = originalMeshColor;
                        }
                        mainMesh.userData.originalColor = originalMeshColor.clone();
                    }
                    if (selected) {
                        const boundingBox = meshGroup === null || meshGroup === void 0 ? void 0 : meshGroup.getObjectByName(SELECTION_BOUNDING_BOX);
                        if (boundingBox) {
                            boundingBox.visible = true;
                        }
                        if (!meshGroup.userData.jcObject.visible) {
                            meshGroup.visible = true;
                            mainMesh.material.opacity = 0.5;
                            mainMesh.material.transparent = true;
                        }
                        this._selectedMeshes.push(mainMesh);
                    }
                    edgesMeshes.forEach(el => {
                        var _a;
                        this._edgeMaterials.push(el.material);
                        const meshColor = new THREE.Color(objColor);
                        const luminance = 0.2126 * meshColor.r + 0.7152 * meshColor.g + 0.0722 * meshColor.b;
                        let originalEdgeColor;
                        // Handling edge color based upon mesh luminance
                        if (luminance >= 0 && luminance <= 0.05) {
                            originalEdgeColor = new THREE.Color(0.2, 0.2, 0.2);
                        }
                        else if (luminance < 0.1) {
                            const scaleFactor = 3 + (0.1 - luminance) * 3;
                            originalEdgeColor = meshColor.clone().multiplyScalar(scaleFactor);
                        }
                        else if (luminance < 0.5) {
                            const scaleFactor = 1.3 + (0.5 - luminance) * 1.3;
                            originalEdgeColor = meshColor.clone().multiplyScalar(scaleFactor);
                        }
                        else {
                            const scaleFactor = 0.7 - (luminance - 0.5) * 0.3;
                            originalEdgeColor = meshColor.clone().multiplyScalar(scaleFactor);
                        }
                        if (selectedNames.includes(el.name)) {
                            this._selectedMeshes.push(el);
                            el.material.color = BOUNDING_BOX_COLOR;
                            el.material.linewidth = SELECTED_LINEWIDTH;
                            el.userData.originalColor = originalEdgeColor.clone();
                        }
                        else {
                            if (objColor && ((_a = el.material) === null || _a === void 0 ? void 0 : _a.color)) {
                                el.material.color = originalEdgeColor;
                                el.material.linewidth = DEFAULT_LINEWIDTH;
                                el.userData.originalColor = originalEdgeColor.clone();
                            }
                        }
                    });
                    (_d = this._meshGroup) === null || _d === void 0 ? void 0 : _d.add(meshGroup);
                }
            });
            this._updateTransformControls(selectedNames);
            // Update the reflength.
            this._updateRefLength(this._refLength === null);
            // Set the expoded view if it's enabled
            this._setupExplodedView();
            // Clip plane rendering
            const planeGeom = new THREE.PlaneGeometry(this._refLength * 1000, // *1000 is a bit arbitrary and extreme but that does not impact performance or anything
            this._refLength * 1000);
            const planeMat = new THREE.MeshPhongMaterial({
                color: DEFAULT_EDGE_COLOR,
                stencilWrite: true,
                stencilRef: 0,
                stencilFunc: THREE.NotEqualStencilFunc,
                stencilFail: THREE.ReplaceStencilOp,
                stencilZFail: THREE.ReplaceStencilOp,
                stencilZPass: THREE.ReplaceStencilOp,
                side: THREE.DoubleSide,
                wireframe: this.state.wireframe
            });
            this._clippingPlaneMesh = new THREE.Mesh(planeGeom, planeMat);
            this._clippingPlaneMesh.visible = this._clipSettings.enabled;
            this._clippingPlaneMesh.onAfterRender = renderer => {
                renderer.clearStencil();
            };
            this._scene.add(this._clippingPlaneMesh);
            this._scene.add(this._meshGroup);
            if (this._loadingTimeout) {
                clearTimeout(this._loadingTimeout);
                this._loadingTimeout = null;
            }
            this.setState(old => (Object.assign(Object.assign({}, old), { loading: false })));
        };
        this._onSharedMetadataChanged = (_, changes) => {
            const newState = Object.assign({}, this.state.annotations);
            changes.forEach((val, key) => {
                if (!key.startsWith('annotation')) {
                    return;
                }
                const data = this._model.sharedModel.getMetadata(key);
                let open = true;
                if (this.state.firstLoad) {
                    open = false;
                }
                if (data && (val.action === 'add' || val.action === 'update')) {
                    const jsonData = JSON.parse(data);
                    jsonData['open'] = open;
                    newState[key] = jsonData;
                }
                else if (val.action === 'delete') {
                    delete newState[key];
                }
            });
            this.setState(old => (Object.assign(Object.assign({}, old), { annotations: newState, firstLoad: false })));
        };
        this._onClientSharedStateChanged = (sender, clients) => {
            var _a, _b, _c, _d, _e, _f, _g;
            const remoteUser = (_a = this._model.localState) === null || _a === void 0 ? void 0 : _a.remoteUser;
            // If we are in following mode, we update our camera and selection
            if (remoteUser) {
                const remoteState = clients.get(remoteUser);
                if (!remoteState) {
                    return;
                }
                if (((_b = remoteState.user) === null || _b === void 0 ? void 0 : _b.username) !== ((_c = this.state.remoteUser) === null || _c === void 0 ? void 0 : _c.username)) {
                    this.setState(old => (Object.assign(Object.assign({}, old), { remoteUser: remoteState.user })));
                }
                // Sync selected
                if ((_d = remoteState.selected) === null || _d === void 0 ? void 0 : _d.value) {
                    this._updateSelected(remoteState.selected.value);
                }
                // Sync camera
                const remoteCamera = remoteState.camera;
                if (remoteCamera === null || remoteCamera === void 0 ? void 0 : remoteCamera.value) {
                    const { position, rotation, up } = remoteCamera.value;
                    this._camera.position.set(position[0], position[1], position[2]);
                    this._camera.rotation.set(rotation[0], rotation[1], rotation[2]);
                    this._camera.up.set(up[0], up[1], up[2]);
                }
            }
            else {
                // If we are unfollowing a remote user, we reset our camera to its old position
                if (this.state.remoteUser !== null) {
                    this.setState(old => (Object.assign(Object.assign({}, old), { remoteUser: null })));
                    const camera = (_f = (_e = this._model.localState) === null || _e === void 0 ? void 0 : _e.camera) === null || _f === void 0 ? void 0 : _f.value;
                    if (camera) {
                        const position = camera.position;
                        const rotation = camera.rotation;
                        const up = camera.up;
                        this._camera.position.set(position[0], position[1], position[2]);
                        this._camera.rotation.set(rotation[0], rotation[1], rotation[2]);
                        this._camera.up.set(up[0], up[1], up[2]);
                    }
                }
                // Sync local selection if needed
                const localState = this._model.localState;
                if ((_g = localState === null || localState === void 0 ? void 0 : localState.selected) === null || _g === void 0 ? void 0 : _g.value) {
                    this._updateSelected(localState.selected.value);
                }
            }
            // Displaying collaborators pointers
            clients.forEach((clientState, clientId) => {
                var _a, _b;
                const pointer = (_a = clientState.pointer) === null || _a === void 0 ? void 0 : _a.value;
                // We already display our own cursor on mouse move
                if (this._model.getClientId() === clientId) {
                    return;
                }
                let collaboratorPointer = this._collaboratorPointers[clientId];
                if (pointer) {
                    const parent = (_b = this._meshGroup) === null || _b === void 0 ? void 0 : _b.getObjectByName(pointer.parent);
                    if (!collaboratorPointer) {
                        const mesh = this._createPointer(clientState.user);
                        collaboratorPointer = this._collaboratorPointers[clientId] = {
                            mesh,
                            parent
                        };
                        this._scene.add(mesh);
                    }
                    collaboratorPointer.mesh.visible = true;
                    // If we are in exploded view, we display the collaborator cursor at the exploded position
                    if (this.explodedViewEnabled) {
                        const explodedState = computeExplodedState({
                            mesh: parent,
                            boundingGroup: this._boundingGroup,
                            factor: this._explodedView.factor
                        });
                        const explodeVector = explodedState.vector.multiplyScalar(explodedState.distance);
                        collaboratorPointer.mesh.position.copy(new THREE.Vector3(pointer.x + explodeVector.x, pointer.y + explodeVector.y, pointer.z + explodeVector.z));
                    }
                    else {
                        collaboratorPointer.mesh.position.copy(new THREE.Vector3(pointer.x, pointer.y, pointer.z));
                    }
                    collaboratorPointer.parent = parent;
                }
                else {
                    if (this._collaboratorPointers[clientId]) {
                        this._collaboratorPointers[clientId].mesh.visible = false;
                    }
                }
            });
        };
        this._handleThemeChange = () => {
            DEFAULT_MESH_COLOR.set(getCSSVariableColor(DEFAULT_MESH_COLOR_CSS));
            DEFAULT_EDGE_COLOR.set(getCSSVariableColor(DEFAULT_EDGE_COLOR_CSS));
            BOUNDING_BOX_COLOR.set(getCSSVariableColor(BOUNDING_BOX_COLOR_CSS));
            SPLITVIEW_BACKGROUND_COLOR.set(getCSSVariableColor(SPLITVIEW_BACKGROUND_COLOR_CSS));
            this._clippingPlaneMeshControl.material.color = DEFAULT_MESH_COLOR;
        };
        this._handleWindowResize = () => {
            this.resizeCanvasToDisplaySize();
            this._updateAnnotation();
        };
        this._handleSnapChange = (key) => (event) => {
            const value = parseFloat(event.target.value);
            if (!isNaN(value)) {
                // enforce > 0 for rotation
                if (key === 'rotationSnapValue' && value <= 0) {
                    return;
                }
                this.setState({ [key]: value });
            }
        };
        this._handleExplodedViewChange = (event) => {
            const newValue = parseFloat(event.target.value);
            this.setState({ explodedViewFactor: newValue });
            this._explodedView.factor = newValue;
            this._setupExplodedView();
        };
        this._divRef = React.createRef(); // Reference of render div
        this._mainViewRef = React.createRef(); // Reference of the main view element
        this._selectedMeshes = [];
        this._meshGroup = null; // The list of ThreeJS meshes
        this._boundingGroup = new THREE.Box3();
        // TODO Make this a shared property
        this._explodedView = { enabled: false, factor: 0 };
        this._explodedViewLinesHelperGroup = null; // The list of line helpers for the exploded view
        this._clipSettings = { enabled: false, showClipPlane: true };
        this._clippingPlaneMesh = null; // Plane mesh used for "filling the gaps"
        this._clippingPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0); // Mathematical object for clipping computation
        this._clippingPlanes = [this._clippingPlane];
        this._edgeMaterials = [];
        this._currentSelection = null;
        this._raycaster = new THREE.Raycaster();
        this._requestID = null; // ID of window.requestAnimationFrame
        this._refLength = null; // Length of bounding box of current object
        this._mouseDrag = {
            start: new THREE.Vector2(),
            end: new THREE.Vector2()
        }; // Current mouse drag
        this._pointer3D = null;
        this._targetPosition = null;
        this._viewHelperDiv = null;
        this._sliderPos = 0;
        this._slideInit = false;
        this._sceneL = undefined;
        this._cameraL = undefined; // Threejs camera
        this._geometry = new THREE.BufferGeometry();
        this._geometry.setDrawRange(0, 3 * 10000);
        this._mainViewModel = this.props.viewModel;
        this._mainViewModel.viewSettingChanged.connect(this._onViewChanged, this);
        this._model = this._mainViewModel.jcadModel;
        this._pointer = new THREE.Vector2();
        this._collaboratorPointers = {};
        this._model.themeChanged.connect(this._handleThemeChange, this);
        this._mainViewModel.jcadModel.sharedOptionsChanged.connect(this._onSharedOptionsChanged, this);
        this._mainViewModel.jcadModel.clientStateChanged.connect(this._onClientSharedStateChanged, this);
        this._mainViewModel.jcadModel.sharedMetadataChanged.connect(this._onSharedMetadataChanged, this);
        this._mainViewModel.renderSignal.connect(this._requestRender, this);
        this._mainViewModel.workerBusy.connect(this._workerBusyHandler, this);
        this._mainViewModel.afterShowSignal.connect(this._handleWindowResize, this);
        this._raycaster.params.Line2 = { threshold: 50 };
        this.state = {
            id: this._mainViewModel.id,
            loading: true,
            annotations: {},
            firstLoad: true,
            wireframe: false,
            transform: false,
            clipEnabled: false,
            explodedViewEnabled: false,
            explodedViewFactor: 0,
            rotationSnapValue: 10,
            translationSnapValue: 1,
            transformMode: 'translate'
        };
        this._model.settingsChanged.connect(this._handleSettingsChange, this);
    }
    componentDidMount() {
        this.generateScene();
        this.addContextMenu();
        this._mainViewModel.initWorker();
        this._mainViewModel.initSignal();
        window.addEventListener('jupytercadObjectSelection', (e) => {
            const customEvent = e;
            if (customEvent.detail.mainViewModelId === this._mainViewModel.id) {
                this.lookAtPosition(customEvent.detail.objPosition);
            }
        });
        this._transformControls.rotationSnap = THREE.MathUtils.degToRad(this.state.rotationSnapValue);
        this._transformControls.translationSnap = this.state.translationSnapValue;
        this._keyDownHandler = (event) => {
            if (event.key === 'r') {
                const newMode = this._transformControls.mode || 'translate';
                if (this.state.transformMode !== newMode) {
                    this.setState({ transformMode: newMode });
                }
            }
        };
        document.addEventListener('keydown', this._keyDownHandler);
    }
    componentDidUpdate(oldProps, oldState) {
        this.resizeCanvasToDisplaySize();
        if (oldState.rotationSnapValue !== this.state.rotationSnapValue) {
            this._transformControls.rotationSnap = THREE.MathUtils.degToRad(this.state.rotationSnapValue);
        }
        if (oldState.translationSnapValue !== this.state.translationSnapValue) {
            this._transformControls.translationSnap = this.state.translationSnapValue;
        }
    }
    componentWillUnmount() {
        window.cancelAnimationFrame(this._requestID);
        window.removeEventListener('resize', this._handleWindowResize);
        this._mainViewModel.viewSettingChanged.disconnect(this._onViewChanged, this);
        this._controls.dispose();
        this._model.themeChanged.disconnect(this._handleThemeChange, this);
        this._model.sharedOptionsChanged.disconnect(this._onSharedOptionsChanged, this);
        this._mainViewModel.jcadModel.clientStateChanged.disconnect(this._onClientSharedStateChanged, this);
        this._mainViewModel.jcadModel.sharedMetadataChanged.disconnect(this._onSharedMetadataChanged, this);
        this._mainViewModel.renderSignal.disconnect(this._requestRender, this);
        this._mainViewModel.workerBusy.disconnect(this._workerBusyHandler, this);
        this._mainViewModel.dispose();
        document.removeEventListener('keydown', this._keyDownHandler);
    }
    _createAxesHelper() {
        var _a;
        if (this._refLength) {
            (_a = this._sceneAxe) === null || _a === void 0 ? void 0 : _a.removeFromParent();
            const axesHelper = new THREE.AxesHelper(this._refLength * 5);
            const material = axesHelper.material;
            material.depthTest = false;
            axesHelper.renderOrder = 1;
            this._sceneAxe = axesHelper;
            this._sceneAxe.visible = this._model.jcadSettings.showAxesHelper;
            this._scene.add(this._sceneAxe);
        }
    }
    _createViewHelper() {
        var _a, _b;
        // Remove the existing ViewHelperDiv if it already exists
        if (this._viewHelperDiv &&
            ((_a = this._divRef.current) === null || _a === void 0 ? void 0 : _a.contains(this._viewHelperDiv))) {
            this._divRef.current.removeChild(this._viewHelperDiv);
        }
        // Create new ViewHelper
        this._viewHelper = new ViewHelper(this._camera, this._renderer.domElement);
        this._viewHelper.center = this._controls.target;
        this._viewHelper.setLabels('X', 'Y', 'Z');
        const viewHelperDiv = document.createElement('div');
        viewHelperDiv.style.position = 'absolute';
        viewHelperDiv.style.right = '0px';
        viewHelperDiv.style.bottom = '0px';
        viewHelperDiv.style.height = '128px';
        viewHelperDiv.style.width = '128px';
        this._viewHelperDiv = viewHelperDiv;
        (_b = this._divRef.current) === null || _b === void 0 ? void 0 : _b.appendChild(this._viewHelperDiv);
        this._viewHelperDiv.addEventListener('pointerup', event => this._viewHelper.handleClick(event));
    }
    lookAtPosition(position) {
        this._targetPosition = new THREE.Vector3(position[0], position[1], position[2]);
    }
    updateCameraRotation() {
        if (this._targetPosition && this._camera && this._controls) {
            const currentTarget = this._controls.target.clone();
            const rotationSpeed = 0.1;
            currentTarget.lerp(this._targetPosition, rotationSpeed);
            this._controls.target.copy(currentTarget);
            if (currentTarget.distanceTo(this._targetPosition) < 0.01) {
                this._targetPosition = null;
            }
            this._controls.update();
        }
    }
    _updateAnnotation() {
        Object.keys(this.state.annotations).forEach(key => {
            var _a;
            const el = document.getElementById(key);
            if (el) {
                const annotation = (_a = this._model.annotationModel) === null || _a === void 0 ? void 0 : _a.getAnnotation(key);
                let screenPosition = new THREE.Vector2();
                if (annotation) {
                    screenPosition = this._computeAnnotationPosition(annotation);
                }
                el.style.left = `${Math.round(screenPosition.x)}px`;
                el.style.top = `${Math.round(screenPosition.y)}px`;
            }
        });
    }
    _handleSettingsChange(_, changedKey) {
        if (changedKey === 'showAxesHelper' && this._sceneAxe) {
            this._sceneAxe.visible = this._model.jcadSettings.showAxesHelper;
        }
        if (changedKey === 'cameraType') {
            this._updateCamera();
        }
    }
    _onPointerMove(e) {
        const rect = this._renderer.domElement.getBoundingClientRect();
        this._pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this._pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        const picked = this._pick();
        // Update our 3D pointer locally so there is no visual latency in the local pointer movement
        if (!this._pointer3D && this._model.localState && picked) {
            this._pointer3D = {
                parent: picked.mesh,
                mesh: this._createPointer(this._model.localState.user)
            };
            this._scene.add(this._pointer3D.mesh);
        }
        if (picked) {
            if (!this._pointer3D) {
                this._syncPointer(undefined, undefined);
                return;
            }
            this._pointer3D.mesh.visible = true;
            this._pointer3D.mesh.position.copy(picked.position);
            this._pointer3D.parent = picked.mesh;
            // If in exploded view, we scale down to the initial position (to before exploding the view)
            if (this.explodedViewEnabled) {
                const explodedState = computeExplodedState({
                    mesh: this._pointer3D.parent,
                    boundingGroup: this._boundingGroup,
                    factor: this._explodedView.factor
                });
                picked.position.add(explodedState.vector.multiplyScalar(-explodedState.distance));
            }
            // If clipping is enabled and picked position is hidden
            this._syncPointer(picked.position, picked.mesh.name);
        }
        else {
            if (this._pointer3D) {
                this._pointer3D.mesh.visible = false;
            }
            this._syncPointer(undefined, undefined);
        }
    }
    _pick() {
        var _a, _b;
        if (this._meshGroup === null || !this._meshGroup.children) {
            return null;
        }
        this._raycaster.setFromCamera(this._pointer, this._camera);
        const intersects = this._raycaster.intersectObjects(this._meshGroup.children);
        if (intersects.length > 0) {
            // Find the first intersection with a visible object
            for (const intersect of intersects) {
                // Object is hidden or a bounding box
                if (!intersect.object.visible ||
                    !((_a = intersect.object.parent) === null || _a === void 0 ? void 0 : _a.visible) ||
                    intersect.object.name === SELECTION_BOUNDING_BOX ||
                    (this._transformControls.enabled &&
                        intersect.object.name.startsWith('edge'))) {
                    continue;
                }
                // Object is clipped
                const planePoint = new THREE.Vector3();
                this._clippingPlane.coplanarPoint(planePoint);
                planePoint.sub(intersect.point);
                if (this._clipSettings.enabled &&
                    planePoint.dot(this._clippingPlane.normal) > 0) {
                    continue;
                }
                let intersectMesh = intersect.object;
                if (intersect.object.name.includes('-front')) {
                    intersectMesh = intersect.object.parent.getObjectByName(intersect.object.name.replace('-front', ''));
                }
                if (intersect.object.name.includes('-back')) {
                    intersectMesh = intersect.object.parent.getObjectByName(intersect.object.name.replace('-back', ''));
                }
                return {
                    mesh: intersectMesh,
                    position: (_b = intersect.pointOnLine) !== null && _b !== void 0 ? _b : intersect.point
                };
            }
        }
        return null;
    }
    _onClick(e) {
        var _a, _b;
        const selection = this._pick();
        const selectedMeshesNames = new Set(this._selectedMeshes.map(sel => sel.name));
        if (selection) {
            const selectionName = selection.mesh.name;
            if (e.ctrlKey) {
                if (selectedMeshesNames.has(selectionName)) {
                    selectedMeshesNames.delete(selectionName);
                }
                else {
                    selectedMeshesNames.add(selectionName);
                }
            }
            else {
                const alreadySelected = selectedMeshesNames.has(selectionName);
                selectedMeshesNames.clear();
                if (!alreadySelected) {
                    selectedMeshesNames.add(selectionName);
                }
            }
            const names = Array.from(selectedMeshesNames);
            const newSelection = {};
            for (const name of names) {
                newSelection[name] = (_b = (_a = this._meshGroup) === null || _a === void 0 ? void 0 : _a.getObjectByName(name)) === null || _b === void 0 ? void 0 : _b.userData;
            }
            this._updateSelected(newSelection);
            this._model.syncSelected(newSelection, this._mainViewModel.id);
        }
        else {
            this._updateSelected({});
            this._model.syncSelected({}, this._mainViewModel.id);
        }
    }
    _onKeyDown(event) {
        // TODO Make these Lumino commands? Or not?
        if (this._clipSettings.enabled || this._transformControls.enabled) {
            const toggleMode = (control) => {
                control.setMode(control.mode === 'rotate' ? 'translate' : 'rotate');
            };
            if (event.key === 'r' && this._clipSettings.enabled) {
                event.preventDefault();
                event.stopPropagation();
                toggleMode(this._clipPlaneTransformControls);
            }
            if (event.key === 'r' && this._transformControls.enabled) {
                event.preventDefault();
                event.stopPropagation();
                toggleMode(this._transformControls);
            }
        }
    }
    _updateRefLength(updateCamera = false) {
        if (this._meshGroup && this._meshGroup.children.length) {
            const boxSizeVec = new THREE.Vector3();
            this._boundingGroup.getSize(boxSizeVec);
            this._refLength =
                Math.max(boxSizeVec.x, boxSizeVec.y, boxSizeVec.z) / 5 || 1;
            this._updatePointersScale(this._refLength);
            if (updateCamera) {
                this._camera.lookAt(this._scene.position);
                this._camera.position.set(10 * this._refLength, 10 * this._refLength, 10 * this._refLength);
            }
            // Update clip plane size
            this._clippingPlaneMeshControl.geometry = new THREE.PlaneGeometry(this._refLength * 10, this._refLength * 10);
            this._createAxesHelper();
        }
        else {
            this._refLength = null;
        }
    }
    async _objToMesh(name, postResult) {
        var _a;
        const { binary, format, value } = postResult;
        let obj = undefined;
        if (format === 'STL') {
            let buff;
            if (binary) {
                const str = `data:application/octet-stream;base64,${value}`;
                const b = await fetch(str);
                buff = await b.arrayBuffer();
            }
            else {
                buff = value;
            }
            const loader = new STLLoader();
            obj = loader.parse(buff);
        }
        if (!obj) {
            return;
        }
        const material = new THREE.MeshPhongMaterial({
            color: DEFAULT_MESH_COLOR,
            wireframe: this.state.wireframe
        });
        const mesh = new THREE.Mesh(obj, material);
        const lineGeo = new THREE.WireframeGeometry(mesh.geometry);
        const mat = new THREE.LineBasicMaterial({ color: 'black' });
        const wireframe = new THREE.LineSegments(lineGeo, mat);
        mesh.add(wireframe);
        mesh.name = name;
        if (this._meshGroup) {
            this._meshGroup.add(mesh);
            (_a = this._boundingGroup) === null || _a === void 0 ? void 0 : _a.expandByObject(mesh);
        }
        this._updateRefLength(true);
    }
    _workerBusyHandler(_, busy) {
        if (this._loadingTimeout) {
            clearTimeout(this._loadingTimeout);
        }
        if (busy) {
            this._loadingTimeout = setTimeout(() => {
                // Do not show loading animation for the first 250
                this.setState(old => (Object.assign(Object.assign({}, old), { loading: true })));
            }, 250);
        }
        else {
            this.setState(old => (Object.assign(Object.assign({}, old), { loading: false })));
        }
    }
    async _requestRender(sender, renderData) {
        var _a;
        const { shapes, postShapes, postResult } = renderData;
        if (shapes !== null && shapes !== undefined) {
            this._shapeToMesh(shapes);
            const options = {
                binary: true,
                onlyVisible: false
            };
            if (postResult && this._meshGroup) {
                const exporter = new GLTFExporter();
                const promises = [];
                // 隐藏边框
                const hiddenObjects = [];
                this._meshGroup.traverse((child) => {
                    if (child.name.startsWith('edge-') && child.visible) {
                        child.visible = false;
                        hiddenObjects.push(child);
                    }
                });
                Object.values(postResult).forEach(pos => {
                    var _a;
                    const objName = (_a = pos.jcObject.parameters) === null || _a === void 0 ? void 0 : _a['Object'];
                    if (!objName) {
                        return;
                    }
                    const threeShape = this._meshGroup.getObjectByName(`${objName}-group`);
                    if (!threeShape) {
                        return;
                    }
                    const promise = new Promise(resolve => {
                        exporter.parse(threeShape, exported => {
                            pos.postShape = exported;
                            resolve();
                        }, () => {
                            // Intentionally empty: no error handling needed for this case
                        }, // Empty function to handle errors
                        options);
                    });
                    promises.push(promise);
                });
                try {
                    await Promise.all(promises);
                    this._mainViewModel.sendRawGeometryToWorker(postResult);
                }
                finally {
                    // 恢复显示
                    hiddenObjects.forEach(obj => obj.visible = true);
                }
            }
        }
        if (postShapes !== null && postShapes !== undefined) {
            Object.entries(postShapes).forEach(([objName, postResult]) => {
                this._objToMesh(objName, postResult);
            });
        }
        const localState = this._model.localState;
        if ((_a = localState === null || localState === void 0 ? void 0 : localState.selected) === null || _a === void 0 ? void 0 : _a.value) {
            this._updateSelected(localState.selected.value);
        }
    }
    _updatePointersScale(refLength) {
        var _a;
        (_a = this._pointer3D) === null || _a === void 0 ? void 0 : _a.mesh.scale.set(refLength / 10, refLength / 10, refLength / 10);
        for (const clientId in this._collaboratorPointers) {
            this._collaboratorPointers[clientId].mesh.scale.set(refLength / 10, refLength / 10, refLength / 10);
        }
    }
    _createPointer(user) {
        var _a, _b;
        let clientColor = null;
        if ((_a = user === null || user === void 0 ? void 0 : user.color) === null || _a === void 0 ? void 0 : _a.startsWith('var')) {
            clientColor = Color.color(getComputedStyle(document.documentElement).getPropertyValue(user.color.slice(4, -1)));
        }
        else {
            clientColor = Color.color((_b = user === null || user === void 0 ? void 0 : user.color) !== null && _b !== void 0 ? _b : 'steelblue');
        }
        const geometry = new THREE.SphereGeometry(1, 32, 32);
        const material = new THREE.MeshBasicMaterial({
            color: clientColor
                ? new THREE.Color(clientColor.r / 255, clientColor.g / 255, clientColor.b / 255)
                : 'black'
        });
        const mesh = new THREE.Mesh(geometry, material);
        if (this._refLength) {
            mesh.scale.set(this._refLength / 10, this._refLength / 10, this._refLength / 10);
        }
        return mesh;
    }
    _updateSelected(selection) {
        var _a, _b, _c, _d, _e, _f, _g;
        const selectionChanged = JSON.stringify(selection) !== JSON.stringify(this._currentSelection);
        if (!selectionChanged) {
            return;
        }
        this._currentSelection = Object.assign({}, selection);
        const selectedNames = Object.keys(selection);
        // Reset original color and remove bounding boxes for old selection
        for (const selectedMesh of this._selectedMeshes) {
            let originalColor = selectedMesh.userData.originalColor;
            if (!originalColor) {
                originalColor = selectedMesh.material.color.clone();
                selectedMesh.userData.originalColor = originalColor;
            }
            if ((_a = selectedMesh.material) === null || _a === void 0 ? void 0 : _a.color) {
                selectedMesh.material.color = originalColor;
            }
            const parentGroup = (_c = (_b = this._meshGroup) === null || _b === void 0 ? void 0 : _b.getObjectByName(selectedMesh.name)) === null || _c === void 0 ? void 0 : _c.parent;
            const boundingBox = parentGroup === null || parentGroup === void 0 ? void 0 : parentGroup.getObjectByName(SELECTION_BOUNDING_BOX);
            if (boundingBox) {
                boundingBox.visible = false;
            }
            if (!parentGroup.userData.jcObject.visible) {
                parentGroup.visible = false;
                selectedMesh.material.opacity = 1;
                selectedMesh.material.transparent = false;
            }
            const material = selectedMesh.material;
            if (material === null || material === void 0 ? void 0 : material.linewidth) {
                material.linewidth = DEFAULT_LINEWIDTH;
            }
        }
        // Set new selection
        this._selectedMeshes = [];
        for (const selectionName of selectedNames) {
            const selectedMesh = (_d = this._meshGroup) === null || _d === void 0 ? void 0 : _d.getObjectByName(selectionName);
            if (!selectedMesh) {
                continue;
            }
            this._selectedMeshes.push(selectedMesh);
            if (selectedMesh.name.startsWith('edge')) {
                // Highlight edges using the old method
                if (!selectedMesh.userData.originalColor) {
                    selectedMesh.userData.originalColor =
                        selectedMesh.material.color.clone();
                }
                if ((_e = selectedMesh === null || selectedMesh === void 0 ? void 0 : selectedMesh.material) === null || _e === void 0 ? void 0 : _e.color) {
                    selectedMesh.material.color = BOUNDING_BOX_COLOR;
                }
                const material = selectedMesh.material;
                if (material === null || material === void 0 ? void 0 : material.linewidth) {
                    material.linewidth = SELECTED_LINEWIDTH;
                }
                selectedMesh.material.wireframe = false;
            }
            else {
                // Highlight non-edges using a bounding box
                const parentGroup = (_g = (_f = this._meshGroup) === null || _f === void 0 ? void 0 : _f.getObjectByName(selectedMesh.name)) === null || _g === void 0 ? void 0 : _g.parent;
                if (!parentGroup.userData.jcObject.visible) {
                    parentGroup.visible = true;
                    selectedMesh.material.opacity = 0.5;
                    selectedMesh.material.transparent = true;
                }
                const boundingBox = parentGroup === null || parentGroup === void 0 ? void 0 : parentGroup.getObjectByName(SELECTION_BOUNDING_BOX);
                if (boundingBox) {
                    boundingBox.visible = true;
                }
            }
        }
        this._updateTransformControls(selectedNames);
    }
    /*
     * Attach the transform controls to the current selection, or detach it
     */
    _updateTransformControls(selection) {
        var _a, _b, _c, _d;
        if (selection.length === 1 && !this._explodedView.enabled) {
            const selectedMeshName = selection[0];
            if (selectedMeshName.startsWith('edge')) {
                const selectedMesh = (_a = this._meshGroup) === null || _a === void 0 ? void 0 : _a.getObjectByName(selectedMeshName);
                if ((_b = selectedMesh.parent) === null || _b === void 0 ? void 0 : _b.name) {
                    const parentName = selectedMesh.parent.name;
                    // Not using getObjectByName, we want the full group
                    // TODO Improve this detection of the full group. startsWith looks brittle
                    const parent = (_c = this._meshGroup) === null || _c === void 0 ? void 0 : _c.children.find(child => child.name.startsWith(parentName));
                    if (parent) {
                        this._transformControls.attach(parent);
                        this._transformControls.visible = this.state.transform;
                        this._transformControls.enabled = this.state.transform;
                    }
                }
                return;
            }
            // Not using getObjectByName, we want the full group
            // TODO Improve this detection of the full group. startsWith looks brittle
            const selectedMesh = (_d = this._meshGroup) === null || _d === void 0 ? void 0 : _d.children.find(child => child.name.startsWith(selectedMeshName));
            if (selectedMesh) {
                this._transformControls.attach(selectedMesh);
                this._transformControls.visible = this.state.transform;
                this._transformControls.enabled = this.state.transform;
                return;
            }
        }
        // Detach TransformControls from the previous selection
        this._transformControls.detach();
        this._transformControls.visible = false;
        this._transformControls.enabled = false;
    }
    _onSharedOptionsChanged(sender, change) {
        var _a, _b;
        const objects = sender.sharedModel.objects;
        if (objects) {
            for (const objData of objects) {
                const objName = objData.name;
                const obj = (_a = this._meshGroup) === null || _a === void 0 ? void 0 : _a.getObjectByName(objName);
                if (!obj) {
                    continue;
                }
                const isVisible = objData.visible;
                const objColor = obj === null || obj === void 0 ? void 0 : obj.material.color;
                obj.parent.visible = isVisible;
                obj.parent.userData.visible = isVisible;
                const explodedLineHelper = (_b = this._explodedViewLinesHelperGroup) === null || _b === void 0 ? void 0 : _b.getObjectByName(objName);
                if (explodedLineHelper) {
                    explodedLineHelper.visible = isVisible;
                }
                if (obj.material.color) {
                    if ('color' in objData) {
                        const rgba = objData.color;
                        const color = new THREE.Color(rgba[0], rgba[1], rgba[2]);
                        obj.material.color = color;
                    }
                    else {
                        obj.material.color = objColor || DEFAULT_MESH_COLOR;
                    }
                }
            }
        }
    }
    _onViewChanged(sender, change) {
        var _a;
        if (change.key === 'explodedView') {
            const explodedView = change.newValue;
            if (change.type !== 'remove' && explodedView) {
                this.setState(oldState => (Object.assign(Object.assign({}, oldState), { explodedViewEnabled: explodedView.enabled, explodedViewFactor: explodedView.factor })), () => {
                    this._explodedView = explodedView;
                    this._setupExplodedView();
                });
            }
        }
        // 新增
        if (change.key === 'exportAsGLB') {
            const value = change.newValue;
            // 如果是代码传来的字符串，默认下载；如果是对象，读取 download 属性
            const shouldDownload = typeof value === 'string' ? true : ((_a = value === null || value === void 0 ? void 0 : value.download) !== null && _a !== void 0 ? _a : true);
            this._exportSceneToGLB(shouldDownload);
        }
        if (change.key === 'clipView') {
            const clipSettings = change.newValue;
            if (change.type !== 'remove' && clipSettings) {
                this.setState(oldState => (Object.assign(Object.assign({}, oldState), { clipEnabled: clipSettings.enabled })), () => {
                    this._clipSettings = clipSettings;
                    this._updateClipping();
                });
            }
        }
        if (change.key === 'splitScreen') {
            const splitSettings = change.newValue;
            this._updateSplit(!!(splitSettings === null || splitSettings === void 0 ? void 0 : splitSettings.enabled));
        }
        if (change.key === 'wireframe') {
            const wireframeEnabled = change.newValue;
            if (wireframeEnabled !== undefined) {
                this.setState(old => (Object.assign(Object.assign({}, old), { wireframe: wireframeEnabled })), () => {
                    if (this._meshGroup) {
                        this._meshGroup.traverse(child => {
                            if (child instanceof THREE.Mesh) {
                                child.material.wireframe = wireframeEnabled;
                                child.material.needsUpdate = true;
                            }
                        });
                    }
                });
            }
        }
        if (change.key === 'transform') {
            const transformEnabled = change.newValue;
            if (transformEnabled !== undefined) {
                this.setState(old => (Object.assign(Object.assign({}, old), { transform: transformEnabled })), () => {
                    this._updateTransformControls(Object.keys(this._currentSelection || {}));
                });
            }
        }
    }
    get explodedViewEnabled() {
        return this._explodedView.enabled && this._explodedView.factor !== 0;
    }
    _setupExplodedView() {
        var _a, _b, _c, _d, _e, _f;
        if (this.explodedViewEnabled) {
            const center = new THREE.Vector3();
            this._boundingGroup.getCenter(center);
            (_a = this._explodedViewLinesHelperGroup) === null || _a === void 0 ? void 0 : _a.removeFromParent();
            this._explodedViewLinesHelperGroup = new THREE.Group();
            for (const group of (_b = this._meshGroup) === null || _b === void 0 ? void 0 : _b.children) {
                const groupMetadata = group.userData;
                const positionArray = (_c = groupMetadata.jcObject.parameters) === null || _c === void 0 ? void 0 : _c.Placement.Position;
                const explodedState = computeExplodedState({
                    mesh: group.getObjectByName(group.name.replace('-group', '')),
                    boundingGroup: this._boundingGroup,
                    factor: this._explodedView.factor
                });
                group.position.copy(new THREE.Vector3(positionArray[0] + explodedState.vector.x * explodedState.distance, positionArray[1] + explodedState.vector.y * explodedState.distance, positionArray[2] + explodedState.vector.z * explodedState.distance));
                // Draw lines
                const material = new THREE.LineBasicMaterial({
                    color: DEFAULT_EDGE_COLOR,
                    linewidth: DEFAULT_LINEWIDTH
                });
                const geometry = new THREE.BufferGeometry().setFromPoints([
                    explodedState.oldGeometryCenter,
                    explodedState.newGeometryCenter
                ]);
                const line = new THREE.Line(geometry, material);
                line.name = group.name;
                line.visible = group.visible;
                this._explodedViewLinesHelperGroup.add(line);
            }
            this._scene.add(this._explodedViewLinesHelperGroup);
        }
        else {
            // Reset objects to their original positions
            for (const group of (_d = this._meshGroup) === null || _d === void 0 ? void 0 : _d.children) {
                const groupMetadata = group.userData;
                const positionArray = (_e = groupMetadata.jcObject.parameters) === null || _e === void 0 ? void 0 : _e.Placement.Position;
                group.position.copy(new THREE.Vector3(positionArray[0], positionArray[1], positionArray[2]));
            }
            (_f = this._explodedViewLinesHelperGroup) === null || _f === void 0 ? void 0 : _f.removeFromParent();
        }
        this._updateTransformControls(Object.keys(this._currentSelection || {}));
    }
    _updateCamera() {
        var _a, _b;
        const position = new THREE.Vector3().copy(this._camera.position);
        const up = new THREE.Vector3().copy(this._camera.up);
        const target = this._controls.target.clone();
        this._camera.remove(this._cameraLight);
        this._scene.remove(this._camera);
        if (this._model.jcadSettings.cameraType === 'Perspective') {
            this._camera = new THREE.PerspectiveCamera(50, 2, CAMERA_NEAR, CAMERA_FAR);
        }
        else {
            const width = ((_a = this._divRef.current) === null || _a === void 0 ? void 0 : _a.clientWidth) || 0;
            const height = ((_b = this._divRef.current) === null || _b === void 0 ? void 0 : _b.clientHeight) || 0;
            const distance = position.distanceTo(target);
            const zoomFactor = 1000 / distance;
            this._camera = new THREE.OrthographicCamera(width / -2, width / 2, height / 2, height / -2);
            this._camera.zoom = zoomFactor;
            this._camera.updateProjectionMatrix();
        }
        this._camera.add(this._cameraLight);
        this._createViewHelper();
        this._scene.add(this._camera);
        this._controls.object = this._camera;
        this._camera.position.copy(position);
        this._camera.up.copy(up);
        if (this._sceneL && this._cameraL) {
            this._sceneL.remove(this._cameraL);
            this._cameraL = this._camera.clone();
            this._sceneL.add(this._cameraL);
        }
        this._transformControls.camera = this._camera;
        this._clipPlaneTransformControls.camera = this._camera;
        this.resizeCanvasToDisplaySize();
    }
    _updateSplit(enabled) {
        var _a, _b, _c;
        if (enabled) {
            if (!this._meshGroup) {
                return;
            }
            this._renderer.setScissorTest(true);
            this._sliderPos = ((_b = (_a = this._divRef.current) === null || _a === void 0 ? void 0 : _a.clientWidth) !== null && _b !== void 0 ? _b : 0) / 2;
            this._sceneL = new THREE.Scene();
            this._sceneL.background = SPLITVIEW_BACKGROUND_COLOR;
            this._sceneL.add(this._ambientLight.clone()); // soft white light
            this._cameraL = this._camera.clone();
            this._sceneL.add(this._cameraL);
            this._sceneL.add(this._meshGroup.clone());
            this.initSlider(true);
        }
        else {
            this._renderer.setScissorTest(false);
            (_c = this._sceneL) === null || _c === void 0 ? void 0 : _c.clear();
            this._sceneL = undefined;
            this._cameraL = undefined;
            this.initSlider(false);
        }
    }
    initSlider(display) {
        if (!this._mainViewRef.current) {
            return;
        }
        const slider = this._mainViewRef.current.querySelector('.jpcad-SplitSlider');
        const sliderLabelLeft = this._mainViewRef.current.querySelector('#split-label-left');
        const sliderLabelRight = this._mainViewRef.current.querySelector('#split-label-right');
        if (display) {
            slider.style.display = 'unset';
            sliderLabelLeft.style.display = 'unset';
            sliderLabelRight.style.display = 'unset';
            slider.style.left = this._sliderPos - slider.offsetWidth / 2 + 'px';
        }
        else {
            slider.style.display = 'none';
            sliderLabelLeft.style.display = 'none';
            sliderLabelRight.style.display = 'none';
        }
        if (!this._slideInit) {
            this._slideInit = true;
            let currentX = 0;
            let currentPost = 0;
            const onPointerDown = (e) => {
                e.preventDefault();
                this._controls.enabled = false;
                currentX = e.clientX;
                currentPost = this._sliderPos;
                window.addEventListener('pointermove', onPointerMove);
                window.addEventListener('pointerup', onPointerUp);
            };
            const onPointerUp = e => {
                e.preventDefault();
                this._controls.enabled = true;
                currentX = 0;
                currentPost = 0;
                window.removeEventListener('pointermove', onPointerMove);
                window.removeEventListener('pointerup', onPointerUp);
            };
            const onPointerMove = (e) => {
                e.preventDefault();
                if (!this._divRef.current || !slider) {
                    return;
                }
                this._sliderPos = currentPost + e.clientX - currentX;
                slider.style.left = this._sliderPos - slider.offsetWidth / 2 + 'px';
            };
            slider.style.touchAction = 'none'; // disable touch scroll
            slider.addEventListener('pointerdown', onPointerDown);
        }
    }
    // 新增
    _exportSceneToGLB(download) {
        if (this._meshGroup) {
            const exporter = new GLTFExporter();
            const options = {
                binary: true,
                onlyVisible: true,
                truncateDrawRange: false
            };
            // 临时隐藏边框线 (LineSegments2 使用的 ShaderMaterial 不被支持)
            const hiddenObjects = [];
            this._meshGroup.traverse((child) => {
                if (child.name.startsWith('edge-') && child.visible) {
                    child.visible = false;
                    hiddenObjects.push(child);
                }
            });
            exporter.parse(this._meshGroup, (exported) => {
                // 导出完成后立即恢复显示
                hiddenObjects.forEach((obj) => obj.visible = true);
                if (exported instanceof ArrayBuffer) {
                    // 临时调整渲染尺寸 (第三个参数 false 表示不改变 Canvas 的 CSS 样式大小，防止页面闪烁)
                    const originalSize = new THREE.Vector2();
                    this._renderer.getSize(originalSize);
                    const scaleFactor = 2;
                    this._renderer.setSize(originalSize.x * scaleFactor, originalSize.y * scaleFactor, false);
                    
                    // 截取缩略图, 强制渲染一次以确保缓冲区有最新的图像
                    this._renderer.render(this._scene, this._camera);
                    const thumbnail = this._renderer.domElement.toDataURL('image/png');
                    this._renderer.setSize(originalSize.x, originalSize.y, false);
                    // 释放信号 (用于保存到后端/本地文件系统)
                    const filename = `${new Date().getTime()}.glb`;
                    this._mainViewModel.emitExportAsGLB(exported, filename, thumbnail);
                    if (download) { // 根据 download 参数决定是否触发浏览器下载
                        downloadGLB(exported, filename);
                    }
                }
            }, (error) => {
                hiddenObjects.forEach((obj) => obj.visible = true);
                console.error('An error occurred during GLB export:', error);
            }, options);
        }
    }
    _updateClipping() {
        if (this._clipSettings.enabled) {
            this._renderer.localClippingEnabled = true;
            this._clipPlaneTransformControls.enabled = true;
            this._clipPlaneTransformControls.visible = true;
            this._clipPlaneTransformControls.attach(this._clippingPlaneMeshControl);
            this._clipPlaneTransformControls.position.copy(new THREE.Vector3(0, 0, 0));
            this._clippingPlaneMeshControl.visible = this._clipSettings.showClipPlane;
            if (this._clippingPlaneMesh) {
                this._clippingPlaneMesh.visible = true;
            }
        }
        else {
            this._renderer.localClippingEnabled = false;
            this._clipPlaneTransformControls.enabled = false;
            this._clipPlaneTransformControls.visible = false;
            this._clippingPlaneMeshControl.visible = false;
            if (this._clippingPlaneMesh) {
                this._clippingPlaneMesh.visible = false;
            }
        }
    }
    _computeAnnotationPosition(annotation) {
        var _a;
        const parent = (_a = this._meshGroup) === null || _a === void 0 ? void 0 : _a.getObjectByName(annotation.parent);
        const position = new THREE.Vector3(annotation.position[0], annotation.position[1], annotation.position[2]);
        // If in exploded view, we explode the annotation position as well
        if (this.explodedViewEnabled && parent) {
            const explodedState = computeExplodedState({
                mesh: parent,
                boundingGroup: this._boundingGroup,
                factor: this._explodedView.factor
            });
            const explodeVector = explodedState.vector.multiplyScalar(explodedState.distance);
            position.add(explodeVector);
        }
        const canvas = this._renderer.domElement;
        const screenPosition = projectVector({
            vector: position,
            camera: this._camera,
            width: canvas.width,
            height: canvas.height
        });
        return screenPosition;
    }
    render() {
        const isTransformOrClipEnabled = this.state.transform || this.state.clipEnabled;
        return (React.createElement("div", { className: "jcad-Mainview data-jcad-keybinding", tabIndex: -2, style: {
                border: this.state.remoteUser
                    ? `solid 3px ${this.state.remoteUser.color}`
                    : 'unset'
            }, ref: this._mainViewRef },
            React.createElement(Spinner, { loading: this.state.loading }),
            React.createElement(FollowIndicator, { remoteUser: this.state.remoteUser }),
            Object.entries(this.state.annotations).map(([key, annotation]) => {
                if (!this._model.annotationModel) {
                    return null;
                }
                const screenPosition = this._computeAnnotationPosition(annotation);
                return (React.createElement("div", { key: key, id: key, style: {
                        left: screenPosition.x,
                        top: screenPosition.y
                    }, className: 'jcad-Annotation-Wrapper' },
                    React.createElement(FloatingAnnotation, { itemId: key, model: this._model.annotationModel, open: false })));
            }),
            React.createElement("div", { className: "jpcad-SplitSlider", style: { display: 'none' } }),
            React.createElement("div", { ref: this._divRef, style: {
                    width: '100%',
                    height: 'calc(100%)'
                } }),
            (isTransformOrClipEnabled || this.state.explodedViewEnabled) && (React.createElement("div", { style: {
                    position: 'absolute',
                    bottom: '10px',
                    left: '10px',
                    display: 'flex',
                    flexDirection: 'column',
                    padding: '8px',
                    backgroundColor: 'rgba(0, 0, 0, 0.5)',
                    color: 'white',
                    borderRadius: '4px',
                    fontSize: '12px',
                    gap: '8px'
                } },
                isTransformOrClipEnabled && (React.createElement("div", null,
                    React.createElement("div", { style: { marginBottom: '2px' } }, this.state.transformMode === 'rotate'
                        ? 'Press R to switch to translation mode'
                        : 'Press R to switch to rotation mode'),
                    this.state.transformMode === 'translate' &&
                        this._refLength && (React.createElement("div", null,
                        React.createElement("label", { style: { marginRight: '8px' } }, "Translation Snap:"),
                        React.createElement("div", { style: { display: 'flex', alignItems: 'center' } },
                            React.createElement("input", { type: "range", min: "0", max: this._refLength * 10, step: this._refLength / 100, value: this.state.translationSnapValue, onChange: this._handleSnapChange('translationSnapValue'), style: { width: '120px', marginRight: '8px' } }),
                            React.createElement("input", { type: "number", min: "0", max: this._refLength * 10, step: this._refLength / 100, value: this.state.translationSnapValue, onChange: this._handleSnapChange('translationSnapValue'), style: {
                                    width: '50px',
                                    padding: '4px',
                                    borderRadius: '4px',
                                    border: '1px solid #ccc',
                                    fontSize: '12px'
                                } })))),
                    this.state.transformMode === 'rotate' && (React.createElement("div", null,
                        React.createElement("label", { style: { marginRight: '8px' } }, "Rotation Snap (\u00B0):"),
                        React.createElement("div", { style: { display: 'flex', alignItems: 'center' } },
                            React.createElement("input", { type: "range", min: "0", max: "180", step: "1", value: this.state.rotationSnapValue, onChange: this._handleSnapChange('rotationSnapValue'), style: { width: '120px', marginRight: '8px' } }),
                            React.createElement("input", { type: "number", min: "0", max: "180", step: "1", value: this.state.rotationSnapValue, onChange: this._handleSnapChange('rotationSnapValue'), style: {
                                    width: '50px',
                                    padding: '4px',
                                    borderRadius: '4px',
                                    border: '1px solid #ccc',
                                    fontSize: '12px'
                                } })))))),
                this.state.explodedViewEnabled && (React.createElement("div", null,
                    React.createElement("div", { style: { marginBottom: '4px' } }, "Exploded view factor:"),
                    React.createElement("div", { style: { display: 'flex', alignItems: 'center' } },
                        React.createElement("input", { type: "range", min: "0", max: "5", step: "0.1", value: this.state.explodedViewFactor, onChange: this._handleExplodedViewChange, style: { width: '120px', marginRight: '8px' } }),
                        React.createElement("span", { style: { minWidth: '30px', textAlign: 'right' } }, this.state.explodedViewFactor)))))),
            React.createElement("div", { id: 'split-label-left', style: {
                    position: 'absolute',
                    top: '10px',
                    left: '10px',
                    display: 'none'
                } }, "Original document"),
            React.createElement("div", { id: 'split-label-right', style: {
                    position: 'absolute',
                    top: '10px',
                    right: '10px',
                    display: 'none'
                } }, "Suggested document")));
    }
}
