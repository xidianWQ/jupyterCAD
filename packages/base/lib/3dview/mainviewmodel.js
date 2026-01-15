import { JCadWorkerSupportedFormat, MainAction, WorkerAction } from '@jupytercad/schema';
import { showErrorMessage } from '@jupyterlab/apputils';
import { PromiseDelegate, UUID } from '@lumino/coreutils';
import { Signal } from '@lumino/signaling';
import { v4 as uuid } from 'uuid';
export class MainViewModel {
    constructor(options) {
        this._dryRunResponses = {};
        this._postWorkerId = new Map();
        this._firstRender = true;
        this._renderSignal = new Signal(this);
        // [新增] 信号实例
        this._exportAsGLBSignal = new Signal(this);
        this._afterShowSignal = new Signal(this);
        this._workerBusy = new Signal(this);
        this._isDisposed = false;
        this._jcadModel = options.jcadModel;
        this._viewSetting = options.viewSetting;
        this._workerRegistry = options.workerRegistry;
    }
    get isDisposed() {
        return this._isDisposed;
    }
    get id() {
        return this._id;
    }
    get renderSignal() {
        return this._renderSignal;
    }
    // [新增] 定义导出信号
    get exportAsGLBSignal() {
        return this._exportAsGLBSignal;
    }
    // [新增] 发射信号的方法
    emitExportAsGLB(content, name, thumbnail) {
        this._exportAsGLBSignal.emit({ content, name, thumbnail });
    }
    get afterShowSignal() {
        return this._afterShowSignal;
    }
    emitAfterShow() {
        this._afterShowSignal.emit(null);
    }
    get workerBusy() {
        return this._workerBusy;
    }
    get jcadModel() {
        return this._jcadModel;
    }
    get viewSettingChanged() {
        return this._viewSetting.changed;
    }
    get viewSettings() {
        const settings = {};
        for (const key of this._viewSetting.keys()) {
            settings[key] = this._viewSetting.get(key) || null;
        }
        return settings;
    }
    dispose() {
        if (this._isDisposed) {
            return;
        }
        this._jcadModel.sharedObjectsChanged.disconnect(this._onSharedObjectsChanged, this);
        this._isDisposed = true;
    }
    initSignal() {
        this._jcadModel.sharedObjectsChanged.connect(this._onSharedObjectsChanged, this);
    }
    initWorker() {
        this._worker = this._workerRegistry.getDefaultWorker();
        this._id = this._worker.register({
            messageHandler: this.messageHandler.bind(this)
        });
        this._workerRegistry.getAllWorkers().forEach(wk => {
            const id = wk.register({
                messageHandler: this.postProcessWorkerHandler.bind(this)
            });
            this._postWorkerId.set(id, wk);
        });
    }
    messageHandler(msg) {
        switch (msg.action) {
            case MainAction.DISPLAY_SHAPE: {
                const { result, postResult } = msg.payload;
                const rawPostResult = {};
                const threejsPostResult = {};
                Object.entries(postResult).forEach(([key, val]) => {
                    var _a, _b;
                    const format = (_b = (_a = val.jcObject) === null || _a === void 0 ? void 0 : _a.shapeMetadata) === null || _b === void 0 ? void 0 : _b.shapeFormat;
                    if (format === JCadWorkerSupportedFormat.BREP) {
                        rawPostResult[key] = val;
                    }
                    else if (format === JCadWorkerSupportedFormat.GLTF) {
                        threejsPostResult[key] = val;
                    }
                    else if (format === JCadWorkerSupportedFormat.STL) {
                        rawPostResult[key] = val;
                    }
                });
                if (this._firstRender) {
                    const postShapes = this._jcadModel.sharedModel
                        .outputs;
                    this._renderSignal.emit({
                        shapes: result,
                        postShapes,
                        postResult: threejsPostResult
                    });
                    this._firstRender = false;
                }
                else {
                    this._renderSignal.emit({
                        shapes: result,
                        postShapes: null,
                        postResult: threejsPostResult
                    });
                    this.sendRawGeometryToWorker(rawPostResult);
                }
                this._workerBusy.emit(false);
                break;
            }
            case MainAction.DRY_RUN_RESPONSE: {
                this._dryRunResponses[msg.payload.id].resolve(msg.payload);
                break;
            }
            case MainAction.INITIALIZED: {
                if (!this._jcadModel) {
                    return;
                }
                const content = this._jcadModel.getContent();
                this._workerBusy.emit(true);
                this._postMessage({
                    action: WorkerAction.LOAD_FILE,
                    payload: {
                        content
                    }
                });
            }
        }
    }
    sendRawGeometryToWorker(postResult) {
        Object.values(postResult).forEach(res => {
            this._postWorkerId.forEach((wk, id) => {
                var _a, _b;
                const shape = res.jcObject.shape;
                if (!shape) {
                    return;
                }
                const { shapeFormat, workerId } = (_b = (_a = res.jcObject) === null || _a === void 0 ? void 0 : _a.shapeMetadata) !== null && _b !== void 0 ? _b : {};
                const worker = this._workerRegistry.getWorker(workerId !== null && workerId !== void 0 ? workerId : '');
                if (wk !== worker) {
                    return;
                }
                if (wk.shapeFormat === shapeFormat) {
                    wk.postMessage({
                        id,
                        action: WorkerAction.POSTPROCESS,
                        payload: res
                    });
                }
            });
        });
    }
    /**
     * Try to update an object, performing a dry run first to make sure it's feasible.
     */
    async maybeUpdateObjectParameters(name, properties) {
        var _a, _b;
        // getContent already returns a deep copy of the content, we can change it safely here
        const updatedContent = this.jcadModel.getContent();
        for (const object of updatedContent.objects) {
            if (object.name === name) {
                object.parameters = Object.assign(Object.assign({}, object.parameters), properties);
            }
        }
        // Try a dry run
        const dryRunResult = await this.dryRun(updatedContent);
        if (dryRunResult.status === 'error') {
            showErrorMessage('Failed to update the desired shape', 'The tool was unable to update the desired shape due to invalid parameter values. The values you entered may not be compatible with the dimensions of your piece.');
            return false;
        }
        // Dry run was successful, ready to apply the update now
        const meta = (_b = (_a = dryRunResult.shapeMetadata) === null || _a === void 0 ? void 0 : _a[name]) !== null && _b !== void 0 ? _b : {};
        const obj = this.jcadModel.sharedModel.getObjectByName(name);
        if (obj) {
            this.jcadModel.sharedModel.updateObjectByName(name, {
                data: {
                    key: 'parameters',
                    value: Object.assign(Object.assign({}, obj.parameters), properties)
                },
                meta
            });
        }
        return true;
    }
    /**
     * Send a payload to the worker to test its feasibility.
     *
     * Return true is the payload is valid, false otherwise.
     */
    async dryRun(content) {
        await this._worker.ready;
        const id = UUID.uuid4();
        this._dryRunResponses[id] = new PromiseDelegate();
        this._workerBusy.emit(true);
        this._postMessage({
            action: WorkerAction.DRY_RUN,
            payload: {
                id,
                content
            }
        });
        const response = await this._dryRunResponses[id].promise;
        delete this._dryRunResponses[id];
        this._workerBusy.emit(false);
        return response;
    }
    postProcessWorkerHandler(msg) {
        switch (msg.action) {
            case MainAction.DISPLAY_POST: {
                const postShapes = {};
                msg.payload.forEach(element => {
                    const { jcObject, postResult } = element;
                    this._jcadModel.sharedModel.setOutput(jcObject.name, postResult);
                    postShapes[jcObject.name] = postResult;
                });
                this._renderSignal.emit({ shapes: null, postShapes });
                break;
            }
        }
    }
    addAnnotation(value) {
        var _a;
        (_a = this._jcadModel.annotationModel) === null || _a === void 0 ? void 0 : _a.addAnnotation(uuid(), value);
    }
    _postMessage(msg) {
        if (this._worker) {
            const newMsg = Object.assign(Object.assign({}, msg), { id: this._id });
            this._worker.postMessage(newMsg);
        }
    }
    async _onSharedObjectsChanged(_, change) {
        if (change.objectChange) {
            await this._worker.ready;
            const content = this._jcadModel.getContent();
            this._workerBusy.emit(true);
            this._postMessage({
                action: WorkerAction.LOAD_FILE,
                payload: {
                    content
                }
            });
        }
    }
}
