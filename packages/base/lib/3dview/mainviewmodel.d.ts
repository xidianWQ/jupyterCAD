import { IAnnotation, IDict, IJCadWorkerRegistry, IJupyterCadModel, IMainMessage, IPostOperatorInput, IPostResult, IDryRunResponsePayload, IJCadContent } from '@jupytercad/schema';
import { ObservableMap } from '@jupyterlab/observables';
import { JSONObject, JSONValue } from '@lumino/coreutils';
import { IDisposable } from '@lumino/disposable';
import { ISignal } from '@lumino/signaling';
export declare class MainViewModel implements IDisposable {
    constructor(options: MainViewModel.IOptions);
    get isDisposed(): boolean;
    get id(): string;
    get renderSignal(): ISignal<this, {
        shapes: any;
        postShapes?: IDict<IPostResult> | null;
        postResult?: IDict<IPostOperatorInput>;
    }>;
    get exportAsGLBSignal(): ISignal<this, {
        content: ArrayBuffer;
        name: string;
        thumbnail?: string;
    }>;
    emitExportAsGLB(content: ArrayBuffer, name: string, thumbnail?: string): void;
    get afterShowSignal(): ISignal<this, null>;
    emitAfterShow(): void;
    get workerBusy(): ISignal<this, boolean>;
    get jcadModel(): IJupyterCadModel;
    get viewSettingChanged(): ISignal<ObservableMap<JSONValue>, import("@jupyterlab/observables").IObservableMap.IChangedArgs<JSONValue>>;
    get viewSettings(): JSONObject;
    dispose(): void;
    initSignal(): void;
    initWorker(): void;
    messageHandler(msg: IMainMessage): void;
    sendRawGeometryToWorker(postResult: IDict<IPostOperatorInput>): void;
    /**
     * Try to update an object, performing a dry run first to make sure it's feasible.
     */
    maybeUpdateObjectParameters(name: string, properties: {
        [key: string]: any;
    }): Promise<boolean>;
    /**
     * Send a payload to the worker to test its feasibility.
     *
     * Return true is the payload is valid, false otherwise.
     */
    dryRun(content: IJCadContent): Promise<IDryRunResponsePayload>;
    postProcessWorkerHandler(msg: IMainMessage): void;
    addAnnotation(value: IAnnotation): void;
    private _postMessage;
    private _onSharedObjectsChanged;
    private _dryRunResponses;
    private _jcadModel;
    private _viewSetting;
    private _workerRegistry;
    private _worker;
    private _postWorkerId;
    private _firstRender;
    private _id;
    private _renderSignal;
    private _exportAsGLBSignal;
    private _afterShowSignal;
    private _workerBusy;
    private _isDisposed;
}
export declare namespace MainViewModel {
    interface IOptions {
        jcadModel: IJupyterCadModel;
        viewSetting: ObservableMap<JSONValue>;
        workerRegistry: IJCadWorkerRegistry;
    }
}
