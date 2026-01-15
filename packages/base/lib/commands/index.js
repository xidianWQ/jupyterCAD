var __rest = (this && this.__rest) || function (s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
        t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function")
        for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
            if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
        }
    return t;
};
import { JCadWorkerSupportedFormat } from '@jupytercad/schema';
import { showErrorMessage } from '@jupyterlab/apputils';
import { PathExt } from '@jupyterlab/coreutils';
import { filterIcon, redoIcon, undoIcon } from '@jupyterlab/ui-components';
import { Menu } from '@lumino/widgets';
import { v4 as uuid } from 'uuid';
import { DEFAULT_MESH_COLOR } from '../3dview/helpers';
import { FormDialog } from '../formdialog';
import keybindings from '../keybindings.json';
import { SketcherDialog } from '../sketcher/sketcherdialog';
import { axesIcon, boxIcon, chamferIcon, clippingIcon, coneIcon, cutIcon, cylinderIcon, explodedViewIcon, extrusionIcon, filletIcon, intersectionIcon, pencilSolidIcon, requestAPI, sphereIcon, torusIcon, transformIcon, unionIcon, videoSolidIcon, wireframeIcon } from '../tools';
import { JupyterCadDocumentWidget } from '../widget';
import { addDocumentActionCommands, addShapeCreationCommands, addShapeOperationCommands, DocumentActionCommandIDs, ShapeCreationCommandMap, ShapeOperationCommandMap } from './operationcommands';
import { getSelectedEdges, getSelectedMeshName, getSelectedObject, newName, PARTS } from './tools';
const OPERATORS = {
    cut: {
        title: 'Cut parameters',
        shape: 'Part::Cut',
        default: (model) => {
            var _a, _b, _c;
            const objects = model.getAllObject();
            const selected = ((_b = (_a = model.localState) === null || _a === void 0 ? void 0 : _a.selected) === null || _b === void 0 ? void 0 : _b.value) || {};
            const sel0 = getSelectedMeshName(selected, 0);
            const sel1 = getSelectedMeshName(selected, 1);
            const baseName = sel0 || objects[0].name || '';
            const baseModel = model.sharedModel.getObjectByName(baseName);
            return {
                Name: newName('Cut', model),
                Base: baseName,
                Tool: sel1 || objects[1].name || '',
                Refine: false,
                Color: ((_c = baseModel === null || baseModel === void 0 ? void 0 : baseModel.parameters) === null || _c === void 0 ? void 0 : _c.Color) || DEFAULT_MESH_COLOR,
                Placement: { Position: [0, 0, 0], Axis: [0, 0, 1], Angle: 0 }
            };
        }
    },
    extrusion: {
        title: 'Extrusion parameters',
        shape: 'Part::Extrusion',
        default: (model) => {
            var _a, _b, _c;
            const objects = model.getAllObject();
            const selected = ((_b = (_a = model.localState) === null || _a === void 0 ? void 0 : _a.selected) === null || _b === void 0 ? void 0 : _b.value) || {};
            const sel0 = getSelectedMeshName(selected, 0);
            const baseName = sel0 || objects[0].name || '';
            const baseModel = model.sharedModel.getObjectByName(baseName);
            return {
                Name: newName('Extrusion', model),
                Base: baseName,
                Dir: [0, 0, 1],
                LengthFwd: 10,
                LengthRev: 0,
                Solid: false,
                Color: ((_c = baseModel === null || baseModel === void 0 ? void 0 : baseModel.parameters) === null || _c === void 0 ? void 0 : _c.Color) || DEFAULT_MESH_COLOR,
                Placement: { Position: [0, 0, 0], Axis: [0, 0, 1], Angle: 0 }
            };
        }
    },
    union: {
        title: 'Fuse parameters',
        shape: 'Part::MultiFuse',
        default: (model) => {
            var _a, _b, _c;
            const objects = model.getAllObject();
            const selected = ((_b = (_a = model.localState) === null || _a === void 0 ? void 0 : _a.selected) === null || _b === void 0 ? void 0 : _b.value) || {};
            const selectedShapes = Object.keys(selected).map(key => key);
            // Fallback to at least two objects if selection is empty
            const baseShapes = selectedShapes.length > 0
                ? selectedShapes
                : [objects[0].name || '', objects[1].name || ''];
            const baseModel = model.sharedModel.getObjectByName(baseShapes[0]);
            return {
                Name: newName('Union', model),
                Shapes: baseShapes,
                Refine: false,
                Color: ((_c = baseModel === null || baseModel === void 0 ? void 0 : baseModel.parameters) === null || _c === void 0 ? void 0 : _c.Color) || DEFAULT_MESH_COLOR,
                Placement: { Position: [0, 0, 0], Axis: [0, 0, 1], Angle: 0 }
            };
        }
    },
    intersection: {
        title: 'Intersection parameters',
        shape: 'Part::MultiCommon',
        default: (model) => {
            var _a, _b, _c;
            const objects = model.getAllObject();
            const selected = ((_b = (_a = model.localState) === null || _a === void 0 ? void 0 : _a.selected) === null || _b === void 0 ? void 0 : _b.value) || {};
            const sel0 = getSelectedMeshName(selected, 0);
            const sel1 = getSelectedMeshName(selected, 1);
            const baseName = sel0 || objects[0].name || '';
            const baseModel = model.sharedModel.getObjectByName(baseName);
            return {
                Name: newName('Intersection', model),
                Shapes: [baseName, sel1 || objects[1].name || ''],
                Refine: false,
                Color: ((_c = baseModel === null || baseModel === void 0 ? void 0 : baseModel.parameters) === null || _c === void 0 ? void 0 : _c.Color) || DEFAULT_MESH_COLOR,
                Placement: { Position: [0, 0, 0], Axis: [0, 0, 1], Angle: 0 }
            };
        }
    },
    chamfer: {
        title: 'Chamfer parameters',
        shape: 'Part::Chamfer',
        default: (model) => {
            var _a, _b, _c;
            const objects = model.getAllObject();
            const selectedEdges = getSelectedEdges((_b = (_a = model.localState) === null || _a === void 0 ? void 0 : _a.selected) === null || _b === void 0 ? void 0 : _b.value);
            const baseName = (selectedEdges === null || selectedEdges === void 0 ? void 0 : selectedEdges.shape) || objects[0].name || '';
            const baseModel = model.sharedModel.getObjectByName(baseName);
            return {
                Name: newName('Chamfer', model),
                Base: baseName,
                Edge: (selectedEdges === null || selectedEdges === void 0 ? void 0 : selectedEdges.edgeIndices) || [],
                Dist: 0.2,
                Color: ((_c = baseModel === null || baseModel === void 0 ? void 0 : baseModel.parameters) === null || _c === void 0 ? void 0 : _c.Color) || DEFAULT_MESH_COLOR,
                Placement: { Position: [0, 0, 0], Axis: [0, 0, 1], Angle: 0 }
            };
        }
    },
    fillet: {
        title: 'Fillet parameters',
        shape: 'Part::Fillet',
        default: (model) => {
            var _a, _b, _c;
            const objects = model.getAllObject();
            const sel = getSelectedEdges((_b = (_a = model.localState) === null || _a === void 0 ? void 0 : _a.selected) === null || _b === void 0 ? void 0 : _b.value);
            const baseName = (sel === null || sel === void 0 ? void 0 : sel.shape) || objects[0].name || '';
            const baseModel = model.sharedModel.getObjectByName(baseName);
            return {
                Name: newName('Fillet', model),
                Base: baseName,
                Edge: (sel === null || sel === void 0 ? void 0 : sel.edgeIndices) || [],
                Radius: 0.2,
                Color: ((_c = baseModel === null || baseModel === void 0 ? void 0 : baseModel.parameters) === null || _c === void 0 ? void 0 : _c.Color) || DEFAULT_MESH_COLOR,
                Placement: { Position: [0, 0, 0], Axis: [0, 0, 1], Angle: 0 }
            };
        }
    }
};
const EXPORT_FORM = {
    title: 'Export to .jcad',
    schema: {
        type: 'object',
        required: ['Name'],
        additionalProperties: false,
        properties: {
            Name: {
                title: 'File name',
                description: 'The exported file name',
                type: 'string'
            }
        }
    },
    default: (model) => {
        return {
            Name: PathExt.basename(model.filePath).replace(PathExt.extname(model.filePath), '.jcad')
        };
    },
    syncData: (model) => {
        return (props) => {
            var _a;
            const endpoint = (_a = model.sharedModel) === null || _a === void 0 ? void 0 : _a.toJcadEndpoint;
            if (!endpoint) {
                showErrorMessage('Error', 'Missing endpoint.');
                return;
            }
            const { Name } = props;
            requestAPI(endpoint, {
                method: 'POST',
                body: JSON.stringify({ path: model.filePath, newName: Name })
            });
        };
    }
};
// [新增] 将 ArrayBuffer 转为 Base64
function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}
function loadKeybindings(commands, keybindings) {
    keybindings.forEach(binding => {
        commands.addKeyBinding({
            command: binding.command,
            keys: binding.keys,
            selector: binding.selector
        });
    });
}
function getSelectedObjectId(widget) {
    var _a;
    const selected = (_a = widget.model.sharedModel.awareness.getLocalState()) === null || _a === void 0 ? void 0 : _a.selected;
    if (selected && (selected === null || selected === void 0 ? void 0 : selected.value)) {
        const selectedKey = Object.keys(selected === null || selected === void 0 ? void 0 : selected.value)[0];
        const selectedItem = selected === null || selected === void 0 ? void 0 : selected.value[selectedKey];
        if (selectedItem.type === 'edge' && selectedItem.parent) {
            return selectedItem.parent;
        }
        return selectedKey;
    }
    return '';
}
/**
 * Add the FreeCAD commands to the application's command registry.
 */
export function addCommands(app, tracker, translator, formSchemaRegistry, workerRegistry, completionProviderManager) {
    workerRegistry.getWorker;
    const trans = translator.load('jupyterlab');
    const { commands } = app;
    Private.updateFormSchema(formSchemaRegistry);
    addShapeCreationCommands({ tracker, commands, trans });
    addShapeOperationCommands({ tracker, commands, trans });
    addDocumentActionCommands({ tracker, commands, trans });
    // 新增：检查本地目录是否存在的函数
    const ensureDirectoryExists = async (path) => {
        var _a;
        try {
            await app.serviceManager.contents.get(path, { content: false });
        }
        catch (error) {
            if (((_a = error.response) === null || _a === void 0 ? void 0 : _a.status) === 404) {
                await app.serviceManager.contents.save(path, { type: 'directory' });
            }
            else {
                throw error;
            }
        }
    };
    // 新增：将文件保存在本地目录的函数
    const saveFile = async (path, content, format = 'base64') => {
        await app.serviceManager.contents.save(path, { type: 'file', format, content });
        console.log(`Saved successfully: ${path}`);
    };
    // 新增：定义一个通用的连接函数
    const connectExportSignal = (widget, source) => {
        // 1. 获取 Panel
        const panel = widget.content;
        // 2. 检查是否已经绑定过 (避免重复绑定)
        if (widget._glbSignalConnected) {
            // console.log(`[Command] Already connected for ${widget.id} (Source: ${source})`);
            return true;
        }
        // 3. 尝试获取 ViewModel
        // 注意：需要确保 widget.ts 中的 JupyterCadPanel 类定义了 getter currentViewModel
        const viewModel = panel === null || panel === void 0 ? void 0 : panel.currentViewModel;
        if (!viewModel) {
            console.warn(`[Command] ViewModel not ready yet for ${widget.id} (Source: ${source}). Will retry later.`);
            return false;
        }
        // 4. 绑定信号
        viewModel.exportAsGLBSignal.connect(async (sender, args) => {
            const { content, thumbnail } = args;
            try {
                const docPath = widget.model.filePath;
                const currentDir = PathExt.dirname(docPath);
                const basename = PathExt.basename(docPath, PathExt.extname(docPath));
                const glbDir = PathExt.join(currentDir, 'converted');
                const imageDir = PathExt.join(currentDir, 'thumbnails');
                // 并行检查/创建目录
                await Promise.all([ensureDirectoryExists(glbDir), ensureDirectoryExists(imageDir)]);
                // 保存 GLB
                const glbPath = PathExt.join(glbDir, `${basename}.glb`);
                await saveFile(glbPath, arrayBufferToBase64(content));
                // 保存缩略图 (如果存在)
                if (thumbnail) {
                    const imagePath = PathExt.join(imageDir, `${basename}.png`);
                    await saveFile(imagePath, thumbnail.split(',')[1]);
                }
            }
            catch (error) {
                console.error('Failed to save GLB file and its thumbnail:', error);
            }
        });
        // 标记为已绑定
        widget._glbSignalConnected = true;
        return true;
    };
    commands.addCommand(CommandIDs.toggleConsole, {
        label: trans.__('Toggle console'),
        isVisible: () => tracker.currentWidget instanceof JupyterCadDocumentWidget,
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        isToggled: () => {
            var _a;
            return ((_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.content.consoleOpened) === true;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            await Private.toggleConsole(tracker);
            commands.notifyCommandChanged(CommandIDs.toggleConsole);
        }
    });
    commands.addCommand(CommandIDs.executeConsole, {
        label: trans.__('Execute console'),
        isVisible: () => tracker.currentWidget instanceof JupyterCadDocumentWidget,
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => Private.executeConsole(tracker)
    });
    commands.addCommand(CommandIDs.removeConsole, {
        label: trans.__('Remove console'),
        isVisible: () => tracker.currentWidget instanceof JupyterCadDocumentWidget,
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => Private.removeConsole(tracker)
    });
    commands.addCommand(CommandIDs.invokeCompleter, {
        label: trans.__('Display the completion helper.'),
        isVisible: () => tracker.currentWidget instanceof JupyterCadDocumentWidget,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => {
            var _a;
            const currentWidget = tracker.currentWidget;
            if (!currentWidget || !completionProviderManager) {
                return;
            }
            const id = (_a = currentWidget.content.consolePanel) === null || _a === void 0 ? void 0 : _a.id;
            if (id) {
                return completionProviderManager.invoke(id);
            }
        }
    });
    commands.addCommand(CommandIDs.selectCompleter, {
        label: trans.__('Select the completion suggestion.'),
        isVisible: () => tracker.currentWidget instanceof JupyterCadDocumentWidget,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => {
            var _a;
            const currentWidget = tracker.currentWidget;
            if (!currentWidget || !completionProviderManager) {
                return;
            }
            const id = (_a = currentWidget.content.consolePanel) === null || _a === void 0 ? void 0 : _a.id;
            if (id) {
                return completionProviderManager.select(id);
            }
        }
    });
    commands.addCommand(CommandIDs.redo, {
        label: trans.__('Redo'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: args => {
            const current = tracker.currentWidget;
            if (current) {
                return current.model.sharedModel.redo();
            }
        },
        icon: redoIcon
    });
    commands.addCommand(CommandIDs.undo, {
        label: trans.__('Undo'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: args => {
            const current = tracker.currentWidget;
            if (current) {
                return current.model.sharedModel.undo();
            }
        },
        icon: undoIcon
    });
    commands.addCommand(CommandIDs.newSketch, {
        label: trans.__('New Sketch'),
        icon: pencilSolidIcon,
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async (args) => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const props = {
                sharedModel: current.model.sharedModel,
                closeCallback: {
                    handler: () => {
                        /* Awful hack to allow the body can close the dialog*/
                    }
                }
            };
            const dialog = new SketcherDialog(props);
            props.closeCallback.handler = () => dialog.close();
            await dialog.launch();
        }
    });
    commands.addCommand(CommandIDs.removeObject, {
        label: trans.__('Remove Object'),
        isEnabled: () => {
            const current = tracker.currentWidget;
            return current ? current.model.sharedModel.editable : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const objectId = getSelectedObjectId(current);
            if (!objectId) {
                console.warn('No object is selected.');
                return;
            }
            commands.execute(DocumentActionCommandIDs.removeObjectWithParams, {
                filePath: current.model.filePath,
                objectId
            });
        }
    });
    commands.addCommand(CommandIDs.newBox, {
        label: trans.__('New Box'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: boxIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.createPart('box', tracker, commands)
    });
    commands.addCommand(CommandIDs.newCylinder, {
        label: trans.__('New Cylinder'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: cylinderIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.createPart('cylinder', tracker, commands)
    });
    commands.addCommand(CommandIDs.newSphere, {
        label: trans.__('New Sphere'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: sphereIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.createPart('sphere', tracker, commands)
    });
    commands.addCommand(CommandIDs.newCone, {
        label: trans.__('New Cone'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: coneIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.createPart('cone', tracker, commands)
    });
    commands.addCommand(CommandIDs.newTorus, {
        label: trans.__('New Torus'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: torusIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.createPart('torus', tracker, commands)
    });
    commands.addCommand(CommandIDs.extrusion, {
        label: trans.__('Extrusion'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: extrusionIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.launchOperatorDialog('extrusion', tracker, commands)
    });
    commands.addCommand(CommandIDs.cut, {
        label: trans.__('Cut'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: cutIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.launchOperatorDialog('cut', tracker, commands)
    });
    commands.addCommand(CommandIDs.union, {
        label: trans.__('Union'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: unionIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.launchOperatorDialog('union', tracker, commands)
    });
    commands.addCommand(CommandIDs.intersection, {
        label: trans.__('Intersection'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: intersectionIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.launchOperatorDialog('intersection', tracker, commands)
    });
    commands.addCommand(CommandIDs.wireframe, {
        label: trans.__('Toggle Wireframe'),
        isEnabled: () => {
            return tracker.currentWidget !== null;
        },
        isToggled: () => {
            var _a;
            const current = (_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.content;
            return (current === null || current === void 0 ? void 0 : current.wireframe) || false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            var _a;
            const current = (_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.content;
            if (!current) {
                return;
            }
            current.wireframe = !current.wireframe;
            commands.notifyCommandChanged(CommandIDs.wireframe);
        },
        icon: wireframeIcon
    });
    tracker.currentChanged.connect(() => {
        commands.notifyCommandChanged(CommandIDs.wireframe);
    });
    commands.addCommand(CommandIDs.transform, {
        label: trans.__('Toggle Transform Controls'),
        isEnabled: () => {
            const current = tracker.currentWidget;
            if (!current || !current.model.sharedModel.editable) {
                return false;
            }
            const viewModel = current.content.currentViewModel;
            if (!viewModel) {
                return false;
            }
            const viewSettings = viewModel.viewSettings;
            return viewSettings.explodedView
                ? !viewSettings.explodedView.enabled
                : true;
        },
        isToggled: () => {
            var _a;
            const current = (_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.content;
            return (current === null || current === void 0 ? void 0 : current.transform) || false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            var _a;
            const current = (_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.content;
            if (!current) {
                return;
            }
            current.transform = !current.transform;
            commands.notifyCommandChanged(CommandIDs.transform);
        },
        icon: transformIcon
    });
    tracker.currentChanged.connect(() => {
        commands.notifyCommandChanged(CommandIDs.transform);
    });
    commands.addCommand(CommandIDs.chamfer, {
        label: trans.__('Make chamfer'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: chamferIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.launchOperatorDialog('chamfer', tracker, commands)
    });
    commands.addCommand(CommandIDs.fillet, {
        label: trans.__('Make fillet'),
        isEnabled: () => {
            return tracker.currentWidget
                ? tracker.currentWidget.model.sharedModel.editable
                : false;
        },
        icon: filletIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.launchOperatorDialog('fillet', tracker, commands)
    });
    commands.addCommand(CommandIDs.updateAxes, {
        label: trans.__('Axes Helper'),
        isEnabled: () => Boolean(tracker.currentWidget),
        icon: axesIcon,
        isToggled: () => {
            const current = tracker.currentWidget;
            if (!current) {
                return false;
            }
            return current.model.jcadSettings.showAxesHelper;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            var _a;
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            try {
                const settings = await current.model.getSettings();
                if (settings === null || settings === void 0 ? void 0 : settings.composite) {
                    const currentValue = (_a = settings.composite.showAxesHelper) !== null && _a !== void 0 ? _a : false;
                    await settings.set('showAxesHelper', !currentValue);
                }
                else {
                    const currentValue = current.model.jcadSettings.showAxesHelper;
                    current.model.jcadSettings.showAxesHelper = !currentValue;
                }
                current.model.emitSettingChanged('showAxesHelper');
                commands.notifyCommandChanged(CommandIDs.updateAxes);
            }
            catch (err) {
                console.error('Failed to toggle Axes Helper:', err);
            }
        }
    });
    commands.addCommand(CommandIDs.updateExplodedView, {
        label: trans.__('Exploded View'),
        isEnabled: () => Boolean(tracker.currentWidget),
        icon: explodedViewIcon,
        isToggled: () => {
            const current = tracker.currentWidget;
            if (!current) {
                return false;
            }
            const viewModel = current.content.currentViewModel;
            if (!viewModel) {
                return false;
            }
            const viewSettings = viewModel.viewSettings;
            return (viewSettings === null || viewSettings === void 0 ? void 0 : viewSettings.explodedView)
                ? viewSettings.explodedView.enabled
                : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const panel = current.content;
            if (panel.explodedView.enabled) {
                panel.explodedView = Object.assign(Object.assign({}, panel.explodedView), { enabled: false });
            }
            else {
                panel.explodedView = Object.assign(Object.assign({}, panel.explodedView), { enabled: true });
            }
            commands.notifyCommandChanged(CommandIDs.updateExplodedView);
            // Notify change so that toggle button for transform disables if needed
            commands.notifyCommandChanged(CommandIDs.transform);
        }
    });
    commands.addCommand(CommandIDs.updateCameraSettings, {
        label: () => {
            const current = tracker.currentWidget;
            if (!current) {
                return trans.__('Switch Camera Projection');
            }
            const currentType = current.model.jcadSettings.cameraType;
            return currentType === 'Perspective'
                ? trans.__('Switch to orthographic projection')
                : trans.__('Switch to perspective projection');
        },
        isEnabled: () => Boolean(tracker.currentWidget),
        icon: videoSolidIcon,
        isToggled: () => {
            const current = tracker.currentWidget;
            return (current === null || current === void 0 ? void 0 : current.model.jcadSettings.cameraType) === 'Orthographic';
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            try {
                const settings = await current.model.getSettings();
                if (settings === null || settings === void 0 ? void 0 : settings.composite) {
                    // If settings exist, toggle there
                    const currentType = settings.composite.cameraType;
                    const newType = currentType === 'Perspective' ? 'Orthographic' : 'Perspective';
                    await settings.set('cameraType', newType);
                }
                else {
                    // Fallback: directly toggle model's own jcadSettings
                    const currentType = current.model.jcadSettings.cameraType;
                    current.model.jcadSettings.cameraType =
                        currentType === 'Perspective' ? 'Orthographic' : 'Perspective';
                    current.model.emitSettingChanged('cameraType');
                }
                commands.notifyCommandChanged(CommandIDs.updateCameraSettings);
            }
            catch (err) {
                console.error('Failed to toggle camera projection:', err);
            }
        }
    });
    commands.addCommand(CommandIDs.updateClipView, {
        label: trans.__('Clipping'),
        isEnabled: () => {
            return Boolean(tracker.currentWidget);
        },
        isToggled: () => {
            var _a, _b;
            const current = (_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.content;
            return ((_b = current === null || current === void 0 ? void 0 : current.clipView) === null || _b === void 0 ? void 0 : _b.enabled) || false;
        },
        icon: clippingIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const panel = current.content;
            panel.clipView = panel.clipView || {
                enabled: false,
                showClipPlane: true
            };
            panel.clipView.enabled = !panel.clipView.enabled;
            const { enabled, showClipPlane } = panel.clipView;
            panel.clipView = { enabled: enabled, showClipPlane: showClipPlane };
            commands.notifyCommandChanged(CommandIDs.updateClipView);
        }
    });
    tracker.currentChanged.connect(() => {
        commands.notifyCommandChanged(CommandIDs.updateClipView);
    });
    commands.addCommand(CommandIDs.splitScreen, {
        label: trans.__('Split screen'),
        isEnabled: () => Boolean(tracker.currentWidget),
        icon: filterIcon,
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            if (current.content.splitScreen) {
                current.content.splitScreen = {
                    enabled: !current.content.splitScreen.enabled
                };
            }
        }
    });
    commands.addCommand(CommandIDs.exportJcad, {
        label: trans.__('Export to .jcad'),
        isEnabled: () => {
            var _a, _b, _c;
            return Boolean((_c = (_b = (_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.model) === null || _b === void 0 ? void 0 : _b.sharedModel) === null || _c === void 0 ? void 0 : _c.toJcadEndpoint);
        },
        iconClass: 'fa fa-file-export',
        describedBy: { args: { type: 'object', properties: {} } },
        execute: async () => {
            var _a, _b;
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const dialog = new FormDialog({
                model: current.model,
                title: EXPORT_FORM.title,
                schema: EXPORT_FORM.schema,
                sourceData: EXPORT_FORM.default((_a = tracker.currentWidget) === null || _a === void 0 ? void 0 : _a.model),
                syncData: EXPORT_FORM.syncData((_b = tracker.currentWidget) === null || _b === void 0 ? void 0 : _b.model),
                cancelButton: true
            });
            await dialog.launch();
        }
    });
    commands.addCommand(CommandIDs.copyObject, {
        label: trans.__('Copy Object'),
        isEnabled: () => {
            const current = tracker.currentWidget;
            return current ? current.model.sharedModel.editable : false;
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const objectId = getSelectedObjectId(current);
            const sharedModel = current.model.sharedModel;
            const objectData = sharedModel.getObjectByName(objectId);
            if (!objectData) {
                console.warn('Could not retrieve object data.');
                return;
            }
            current.model.setCopiedObject(objectData);
        }
    });
    commands.addCommand(CommandIDs.pasteObject, {
        label: trans.__('Paste Object'),
        isEnabled: () => {
            const current = tracker.currentWidget;
            const clipboard = current === null || current === void 0 ? void 0 : current.model.getCopiedObject();
            const editable = current === null || current === void 0 ? void 0 : current.model.sharedModel.editable;
            return !!(current && clipboard && editable);
        },
        describedBy: { args: { type: 'object', properties: {} } },
        execute: () => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const sharedModel = current.model.sharedModel;
            const copiedObject = current.model.getCopiedObject();
            if (!copiedObject) {
                console.error('No object in clipboard to paste.');
                return;
            }
            const clipboard = copiedObject;
            const originalName = clipboard.name || 'Unnamed Object';
            let newName = originalName;
            let counter = 1;
            while (sharedModel.objects.some(obj => obj.name === newName)) {
                newName = `${originalName} Copy${counter > 1 ? ` ${counter}` : ''}`;
                counter++;
            }
            const jcadModel = current.model;
            const newObject = Object.assign(Object.assign({}, clipboard), { name: newName, visible: true });
            sharedModel.addObject(newObject);
            jcadModel.syncSelected({ [newObject.name]: { type: 'shape' } }, uuid());
        }
    });
    commands.addCommand(CommandIDs.exportAsSTL, {
        label: trans.__('Export as STL'),
        isEnabled: () => Boolean(tracker.currentWidget),
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.executeExport(app, tracker, 'STL')
    });
    commands.addCommand(CommandIDs.exportAsBREP, {
        label: trans.__('Export as BREP'),
        isEnabled: () => Boolean(tracker.currentWidget),
        describedBy: { args: { type: 'object', properties: {} } },
        execute: Private.executeExport(app, tracker, 'BREP')
    });
    // 新增：对当前已存在的窗口执行绑定 (解决刷新后无效的问题)
    tracker.forEach(widget => {
        connectExportSignal(widget, 'ExistingWidget');
    });
    // 修改：对未来新打开的窗口执行绑定
    tracker.widgetAdded.connect((sender, widget) => {
        // 延迟 1 秒尝试绑定，给 ViewModel 初始化留出时间
        setTimeout(() => {
            connectExportSignal(widget, 'WidgetAdded');
        }, 1000);
    });
    // // 新增：注册 exportAsGLB 命令
    // commands.addCommand(CommandIDs.exportAsGLB, {
    //   label: trans.__('Export as GLB'),
    //   isEnabled: () => Boolean(tracker.currentWidget),
    //   describedBy: { args: { type: 'object', properties: {} } },
    //   execute: () => {
    //     const current = tracker.currentWidget;
    //     if (current) {
    //       // 调用 Panel 上的 exportAsGLB 方法 (我们需要在 widget.ts 中实现它)
    //       // 使用 as any 绕过类型检查，或者更新 Panel 的接口定义
    //       (current.content as any).exportAsGLB();
    //     }
    //   }
    // });
    // 修改：只需要触发视图逻辑即可
    commands.addCommand(CommandIDs.exportAsGLB, {
        label: trans.__('Export to .glb'),
        isEnabled: () => Boolean(tracker.currentWidget),
        execute: async () => {
            const current = tracker.currentWidget;
            if (current) {
                console.log('[Command] Export button clicked. ensuring signal connection...');
                // 1. 在触发导出前，强制尝试绑定信号
                // 如果之前初始化时失败了，现在这里肯定能成功
                connectExportSignal(current, 'ExecuteButton');
                // 2. 触发 Panel 上的导出逻辑
                if (current.content.exportAsGLB) {
                    // 显式传入 true，确保点击按钮时触发下载
                    current.content.exportAsGLB(true);
                }
                else {
                    console.error('[Command] exportAsGLB method missing on panel!');
                }
            }
        }
    });
    // Create the export submenu
    const exportMenu = new Menu({ commands: app.commands });
    exportMenu.title.label = 'Export as';
    exportMenu.addItem({ command: CommandIDs.exportAsSTL });
    exportMenu.addItem({ command: CommandIDs.exportAsBREP });
    exportMenu.addItem({ command: CommandIDs.exportAsGLB }); // 新增
    app.contextMenu.addItem({
        type: 'submenu',
        submenu: exportMenu,
        selector: '.jpcad-object-tree-item',
        rank: 10
    });
    loadKeybindings(commands, keybindings);
}
/**
 * The command IDs used by the FreeCAD plugin.
 */
export var CommandIDs;
(function (CommandIDs) {
    CommandIDs.redo = 'jupytercad:redo';
    CommandIDs.undo = 'jupytercad:undo';
    CommandIDs.newSketch = 'jupytercad:sketch';
    CommandIDs.removeObject = 'jupytercad:removeObject';
    CommandIDs.newBox = 'jupytercad:newBox';
    CommandIDs.newCylinder = 'jupytercad:newCylinder';
    CommandIDs.newSphere = 'jupytercad:newSphere';
    CommandIDs.newCone = 'jupytercad:newCone';
    CommandIDs.newTorus = 'jupytercad:newTorus';
    CommandIDs.cut = 'jupytercad:cut';
    CommandIDs.extrusion = 'jupytercad:extrusion';
    CommandIDs.union = 'jupytercad:union';
    CommandIDs.intersection = 'jupytercad:intersection';
    CommandIDs.wireframe = 'jupytercad:wireframe';
    CommandIDs.transform = 'jupytercad:transform';
    CommandIDs.copyObject = 'jupytercad:copyObject';
    CommandIDs.pasteObject = 'jupytercad:pasteObject';
    CommandIDs.chamfer = 'jupytercad:chamfer';
    CommandIDs.fillet = 'jupytercad:fillet';
    CommandIDs.updateAxes = 'jupytercad:updateAxes';
    CommandIDs.updateExplodedView = 'jupytercad:updateExplodedView';
    CommandIDs.updateCameraSettings = 'jupytercad:updateCameraSettings';
    CommandIDs.updateClipView = 'jupytercad:updateClipView';
    CommandIDs.splitScreen = 'jupytercad:splitScreen';
    CommandIDs.exportJcad = 'jupytercad:exportJcad';
    CommandIDs.toggleConsole = 'jupytercad:toggleConsole';
    CommandIDs.invokeCompleter = 'jupytercad:invokeConsoleCompleter';
    CommandIDs.removeConsole = 'jupytercad:removeConsole';
    CommandIDs.executeConsole = 'jupytercad:executeConsole';
    CommandIDs.selectCompleter = 'jupytercad:selectConsoleCompleter';
    CommandIDs.exportAsSTL = 'jupytercad:stl:export-as-stl';
    CommandIDs.exportAsBREP = 'jupytercad:stl:export-as-brep';
    CommandIDs.exportAsGLB = 'jupytercad:export-as-glb'; // 新增
})(CommandIDs || (CommandIDs = {}));
var Private;
(function (Private) {
    Private.FORM_SCHEMA = {};
    function updateFormSchema(formSchemaRegistry) {
        if (Object.keys(Private.FORM_SCHEMA).length > 0) {
            return;
        }
        const formSchema = formSchemaRegistry.getSchemas();
        formSchema.forEach((val, key) => {
            if (key === 'Placement of the box') {
                return;
            }
            const value = (Private.FORM_SCHEMA[key] = JSON.parse(JSON.stringify(val)));
            value['required'] = ['Name', ...value['required']];
            value['properties'] = Object.assign({ Name: { type: 'string', description: 'The Name of the Object' } }, value['properties']);
        });
    }
    Private.updateFormSchema = updateFormSchema;
    function createPart(part, tracker, commands) {
        return async (args) => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const value = PARTS[part];
            current.model.syncFormData(value);
            const syncSelectedField = (id, value, parentType) => {
                let property = null;
                if (id) {
                    const prefix = id.split('_')[0];
                    property = id.substring(prefix.length);
                }
                current.model.syncSelectedPropField({
                    id: property,
                    value,
                    parentType
                });
            };
            const dialog = new FormDialog({
                model: current.model,
                title: value.title,
                sourceData: value.default(current.model),
                schema: Private.FORM_SCHEMA[value.shape],
                syncData: async (props) => {
                    const { Name } = props, parameters = __rest(props, ["Name"]);
                    const shapeName = value.shape;
                    const commandId = ShapeCreationCommandMap[shapeName];
                    if (commands && commandId) {
                        return await commands.execute(commandId, {
                            Name,
                            filePath: current.model.filePath,
                            parameters
                        });
                    }
                },
                cancelButton: () => {
                    current.model.syncFormData(undefined);
                },
                syncSelectedPropField: syncSelectedField
            });
            await dialog.launch();
        };
    }
    Private.createPart = createPart;
    function launchOperatorDialog(operator, tracker, commands) {
        return async (args) => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const op = OPERATORS[operator];
            // Fill form schema with available objects
            const form_schema = JSON.parse(JSON.stringify(Private.FORM_SCHEMA[op.shape]));
            const allObjects = current.model.getAllObject().map(o => o.name);
            for (const prop in form_schema['properties']) {
                const fcType = form_schema['properties'][prop]['fcType'];
                if (fcType) {
                    const propDef = form_schema['properties'][prop];
                    switch (fcType) {
                        case 'App::PropertyLink':
                            propDef['enum'] = allObjects;
                            break;
                        case 'App::PropertyLinkList':
                            propDef['items']['enum'] = allObjects;
                            break;
                        default:
                    }
                }
            }
            const operatorCommandId = ShapeOperationCommandMap[op.shape];
            if (!operatorCommandId) {
                return;
            }
            const syncData = async (props) => {
                const { Name } = props, parameters = __rest(props, ["Name"]);
                await commands.execute(operatorCommandId, {
                    Name,
                    filePath: current.model.filePath,
                    parameters
                });
            };
            const dialog = new FormDialog({
                model: current.model,
                title: op.title,
                sourceData: op.default(current.model),
                schema: form_schema,
                syncData,
                cancelButton: true
            });
            await dialog.launch();
        };
    }
    Private.launchOperatorDialog = launchOperatorDialog;
    const exportOperator = {
        title: 'Export to STL/BREP',
        syncData: (model) => {
            return (props) => {
                const { Name, Type, LinearDeflection, AngularDeflection } = props, rest = __rest(props, ["Name", "Type", "LinearDeflection", "AngularDeflection"]);
                const shapeFormat = Type === 'BREP'
                    ? JCadWorkerSupportedFormat.BREP
                    : JCadWorkerSupportedFormat.STL;
                // Choose workerId based on format
                const workerId = shapeFormat === JCadWorkerSupportedFormat.BREP
                    ? 'jupytercad-brep:worker'
                    : 'jupytercad-stl:worker';
                // Only include mesh parameters for STL
                const parameters = Type === 'STL'
                    ? Object.assign(Object.assign({}, rest), { Type, LinearDeflection, AngularDeflection }) : Object.assign(Object.assign({}, rest), { Type });
                const objectModel = {
                    shape: 'Post::Export',
                    parameters,
                    visible: true,
                    name: Name,
                    shapeMetadata: { shapeFormat, workerId }
                };
                const sharedModel = model.sharedModel;
                if (sharedModel) {
                    sharedModel.transact(() => {
                        if (!sharedModel.objectExists(objectModel.name)) {
                            sharedModel.addObject(objectModel);
                        }
                        else {
                            showErrorMessage('The object already exists', 'There is an existing object with the same name.');
                        }
                    });
                }
            };
        }
    };
    function executeExport(app, tracker, exportType) {
        return async (args) => {
            const current = tracker.currentWidget;
            if (!current) {
                return;
            }
            const model = current.model;
            if (!model) {
                return;
            }
            const formSchema = {
                type: 'object',
                properties: {
                    Object: {
                        type: 'string',
                        description: 'The object to export',
                        enum: []
                    },
                    Type: {
                        type: 'string',
                        default: 'STL',
                        enum: ['BREP', 'STL'],
                        description: 'The filetype for export (Brep/Stl)'
                    },
                    LinearDeflection: {
                        type: 'number',
                        description: 'Linear deflection (smaller = more triangles)',
                        minimum: 0.0001,
                        maximum: 1.0,
                        default: 0.1
                    },
                    AngularDeflection: {
                        type: 'number',
                        description: 'Angular deflection in radians',
                        minimum: 0.01,
                        maximum: 1.0,
                        default: 0.5
                    }
                },
                required: ['Object', 'Type'],
                additionalProperties: false
            };
            const formJsonSchema = JSON.parse(JSON.stringify(formSchema));
            const objects = model.getAllObject();
            const objectNames = objects.map(obj => obj.name);
            if (objectNames.length === 0) {
                showErrorMessage('No Objects', 'There are no objects in the document to export.');
                return;
            }
            formJsonSchema['required'] = ['Name', ...formJsonSchema['required']];
            formJsonSchema['properties'] = Object.assign({ Name: { type: 'string', description: 'The Name of the Export Object' } }, formJsonSchema['properties']);
            formJsonSchema['properties']['Object']['enum'] = objectNames;
            // Remove Type field from form since user already chose it
            delete formJsonSchema['properties']['Type'];
            formJsonSchema['required'] = formJsonSchema['required'].filter((field) => field !== 'Type');
            // Hide mesh params for BREP
            if (exportType === 'BREP') {
                delete formJsonSchema['properties']['LinearDeflection'];
                delete formJsonSchema['properties']['AngularDeflection'];
            }
            const clickedObjectName = getSelectedObject(app, model, objectNames);
            const sourceData = Object.assign({ Name: clickedObjectName
                    ? `${clickedObjectName}_${exportType}`
                    : `${exportType}`, Object: clickedObjectName, Type: exportType }, (exportType === 'STL'
                ? { LinearDeflection: 0.1, AngularDeflection: 0.5 }
                : {}));
            const dialog = new FormDialog({
                model: current.model,
                title: exportOperator.title,
                sourceData,
                schema: formJsonSchema,
                syncData: exportOperator.syncData(current.model),
                cancelButton: true
            });
            await dialog.launch();
        };
    }
    Private.executeExport = executeExport;
    function executeConsole(tracker) {
        const current = tracker.currentWidget;
        if (!current || !(current instanceof JupyterCadDocumentWidget)) {
            return;
        }
        current.content.executeConsole();
    }
    Private.executeConsole = executeConsole;
    function removeConsole(tracker) {
        const current = tracker.currentWidget;
        if (!current || !(current instanceof JupyterCadDocumentWidget)) {
            return;
        }
        current.content.removeConsole();
    }
    Private.removeConsole = removeConsole;
    async function toggleConsole(tracker) {
        const current = tracker.currentWidget;
        if (!current || !(current instanceof JupyterCadDocumentWidget)) {
            return;
        }
        await current.content.toggleConsole(current.model.filePath);
    }
    Private.toggleConsole = toggleConsole;
})(Private || (Private = {}));
