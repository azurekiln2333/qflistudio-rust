// Behavior checks against the actual plain ArkTS platform-channel host.
// This does not replace an ArkTS package build or device execution.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const ts = require(process.env.QFLI_OHOS_TYPESCRIPT ||
  'D:/ProgramFiles/Huawei/DevEco Studio/tools/hvigor/hvigor-ohos-plugin/node_modules/typescript');
const hostPath = process.env.QFLI_OHOS_HOST_SOURCE || path.join(__dirname,
  '../ohos/entry/src/main/ets/entryability/EntryAbility.ets');
const pickerPath = path.join(__dirname,
  '../ohos/entry/src/main/ets/entryability/PickerBridge.ets');

function loadNativeModule(source, fileName, modules) {
  const compiled = ts.transpileModule(source, {
    fileName: path.basename(fileName, '.ets') + '.ts', reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  });
  assert.deepEqual(compiled.diagnostics || [], []);
  const module = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports,
    require: name => {
      assert.ok(Object.hasOwn(modules, name), `Unexpected native import: ${name}`);
      return modules[name];
    },
  }, { filename: fileName, timeout: 1000 });
  return module.exports;
}

function loadHost(source = fs.readFileSync(hostPath, 'utf8')) {
  const state = { events: [], external: [], shares: [], pickers: [], registrations: 0 };
  let handler;
  const context = {
    config: { colorMode: 1 },
    eventHub: { emit: (...args) => state.events.push(args) },
    startAbility: (...args) => {
      state.external.push(args);
      return Promise.resolve();
    },
  };
  class FlutterAbility {
    constructor() { this.context = context; }
    configureFlutterEngine() { state.baseConfigured = true; }
    onWindowStageCreate() { state.baseWindowCreated = true; }
  }
  // Exercise the production method predicate. Native picker I/O stays mocked;
  // these checks establish host delegation, not a device picker operation.
  const pickerBridge = loadNativeModule(fs.readFileSync(pickerPath, 'utf8'), pickerPath, {
    '@ohos.app.ability.common': {},
    '@ohos.file.fs': {},
    '@ohos.file.picker': {},
    '@ohos.file.photoAccessHelper': {},
    '@ohos/flutter_ohos': {},
  });
  const modules = {
    '@ohos/flutter_ohos': {
      FlutterAbility,
      MethodChannel: class {
        constructor(messenger, name) { state.channel = name; }
        setMethodCallHandler(value) { handler = value; }
      },
    },
    '@kit.ShareKit': { systemShare: {
      SharedData: class { constructor(record) { this.record = record; } },
      ShareController: class {
        constructor(data) { this.data = data; }
        show(owner, options) {
          state.shares.push({ data: this.data, owner, options });
          return Promise.resolve();
        }
      },
    } },
    '@kit.AbilityKit': { ConfigurationConstant: { ColorMode: { COLOR_MODE_DARK: 1 } } },
    '@kit.ArkUI': { router: { pushUrl: (...args) => {
      state.external.push(args);
      return Promise.resolve();
    } } },
    '@kit.BasicServicesKit': {},
    '../plugins/GeneratedPluginRegistrant': {
      GeneratedPluginRegistrant: { registerWith: () => state.registrations++ },
    },
    './PickerBridge': {
      isPickerMethod: pickerBridge.isPickerMethod,
      handlePickerCall: (owner, call, result) => {
        state.pickers.push({ owner, call });
        result.success(['local.rs']);
      },
    },
  };
  const host = loadNativeModule(source, hostPath, modules);
  const ability = new host.default();
  ability.configureFlutterEngine({ dartExecutor: { getBinaryMessenger: () => ({}) } });
  assert.equal(state.channel, 'qflistudio/platform');
  assert.equal(state.registrations, 1);
  assert.equal(state.baseConfigured, true);
  function invoke(method, args = {}, forbidArguments = false) {
    const calls = [];
    handler.onMethodCall({ method, argument: name => {
      assert.equal(forbidArguments, false, 'Blocked method inspected its arguments');
      return args[name];
    } }, {
      success: value => calls.push({ kind: 'success', value }),
      error: (code, message, details) => calls.push({ kind: 'error', code, message, details }),
      notImplemented: () => calls.push({ kind: 'notImplemented' }),
    });
    return calls;
  }
  return { state, context, ability, invoke };
}

for (const method of ['openAgreement', 'openUrl']) {
  test(`${method} refuses before reading arguments or invoking an external service`, () => {
    const { state, invoke } = loadHost();
    const calls = invoke(method, {}, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].kind, 'error');
    assert.equal(calls[0].code, 'OFFLINE_ONLY');
    assert.equal(state.external.length, 0);
    assert.equal(state.shares.length, 0);
    assert.equal(state.pickers.length, 0);
  });
}

test('startup progress preserves finite clamping and rejects invalid values', () => {
  const { state, invoke } = loadHost();
  for (const progress of [-2, 0.4, 3]) {
    assert.equal(invoke('startupProgress', { progress })[0].kind, 'success');
  }
  assert.deepEqual(state.events, [
    ['EVENT_STARTUP_PROGRESS', 0], ['EVENT_STARTUP_PROGRESS', 0.4],
    ['EVENT_STARTUP_PROGRESS', 1],
  ]);
  for (const progress of [NaN, Infinity, '1', null, undefined]) {
    assert.equal(invoke('startupProgress', { progress })[0].code, 'INVALID_PROGRESS');
  }
  assert.equal(state.events.length, 3);
});

test('local text sharing remains available', async () => {
  const { state, context, invoke } = loadHost();
  const calls = invoke('shareText', { title: 'Rust', text: '你好 🦀' });
  await Promise.resolve();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].kind, 'success');
  assert.equal(state.shares.length, 1);
  assert.equal(state.shares[0].owner, context);
  assert.equal(state.shares[0].data.record.content, '你好 🦀');
  assert.equal(state.shares[0].data.record.utd, 'general.plain-text');
  assert.equal(state.external.length, 0);
});

test('picker delegation and unknown-method response remain available', () => {
  const { state, context, invoke } = loadHost();
  for (const method of ['pickDocument', 'saveDocument', 'pickPhotos', 'readUri', 'writeUri']) {
    assert.deepEqual(invoke(method), [{ kind: 'success', value: ['local.rs'] }]);
    assert.equal(state.pickers.at(-1).owner, context);
    assert.equal(state.pickers.at(-1).call.method, method);
  }
  assert.equal(state.pickers.length, 5);
  assert.deepEqual(invoke('pickFiles'), [{ kind: 'notImplemented' }]);
  assert.deepEqual(invoke('unknown'), [{ kind: 'notImplemented' }]);
  assert.equal(state.pickers.length, 5);
  assert.equal(state.external.length, 0);
});

test('native startup window styling still delegates to Flutter', () => {
  const { state, ability } = loadHost();
  const colors = [];
  ability.onWindowStageCreate({ getMainWindowSync: () => ({
    setWindowBackgroundColor: color => colors.push(color),
  }) });
  assert.deepEqual(colors, ['#FF111418']);
  assert.equal(state.baseWindowCreated, true);
});

