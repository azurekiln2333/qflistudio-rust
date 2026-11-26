"""Prepare/run the single production unsigned OHOS build; never grants ownership.

Without --execute this only prints a plan. Parent must bind a fresh serial grant,
verify the actual tool terminal, and separately authorize any HDC delivery.
"""
from __future__ import annotations
import time
ORIGIN = time.monotonic()
# The parent owns the original tool-terminal observation and publication.
# Module-entry time excludes unmeasured interpreter/tool startup; the parent
# must compare its actual invocation timestamp against the fresh 600 s grant.
WORK_SECONDS = 520
JOB_CLEANUP_SECONDS = 550
FINALIZATION_SECONDS = 580
PLANNED_TOTAL_SECONDS = 600
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CORE = ROOT.parent / "qfli_studio_core"
SDK = Path("D:/ProgramFiles/flutter_ohos/bin/cache")
DEVECO = Path("D:/ProgramFiles/Huawei/DevEco Studio")
CHILD_ENV_HOMES = {
    "JAVA_HOME": str(DEVECO / "jbr"),
    "NODE_HOME": str(DEVECO / "tools/node"),
    "DEVECO_SDK_HOME": str(DEVECO / "sdk"),
}
CHILD_PATH_PREFIX = [str(DEVECO / path) for path in
                     ("tools/node", "tools/ohpm/bin", "tools/hvigor/bin")]
CONFIG = ROOT / "ohos/hvigor/hvigor-config.json5"
APP_SCOPE = ROOT / "ohos/AppScope/app.json5"
PRESERVED_BUILD_NUMBER = 1000000
HAPS = (ROOT / "ohos/entry/build/default/outputs/default/entry-default-unsigned.hap",
        ROOT / "build/ohos/hap/entry-default-unsigned.hap")


def sha(path, deadline=None):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Input snapshot deadline reached: " + str(path))
            h.update(block)
    return h.hexdigest()


def file_identity(path, deadline=None):
    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "exists": False}
    s = path.stat()
    return {"path": str(path), "exists": True, "bytes": s.st_size,
            "mtimeNs": s.st_mtime_ns, "sha256": sha(path, deadline)}


def git_identity(root, deadline=None):
    def read(*args):
        remaining = 5 if deadline is None else min(5, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Git identity deadline reached: " + str(root))
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, timeout=remaining, check=True)
        return p.stdout
    status = read("status", "--porcelain=v1", "--untracked-files=normal")
    return {"path": str(root), "head": read("rev-parse", "HEAD").strip(),
            "wipEntries": len(status.splitlines()),
            "statusSha256": hashlib.sha256(status.encode()).hexdigest()}



# Flutter rewrites these generated inputs; preserve their identities separately
# from authored source. No broad "generated" exemption applies to lib/**/*.dart.
GENERATED_OHOS = {
    "ohos/entry/src/main/resources/rawfile/buildinfo.json5",
    "ohos/entry/src/main/ets/plugins/GeneratedPluginRegistrant.ets",
    "ohos/entry/libs/arm64-v8a/libapp.so",
}


def inputs_snapshot(deadline):
    entries = {}
    generated = {}
    selected = [("repo", ROOT, ROOT / "pubspec.yaml"),
                ("repo", ROOT, ROOT / "pubspec.lock"),
                ("repo", ROOT, ROOT / "assets/miri/manifest.ohos-arm64.json"),
                ("repo", ROOT, ROOT / "assets/app_icon.png"),
                ("repo", ROOT, CONFIG),
                ("core", CORE, CORE / "pubspec.yaml"),
                ("core", CORE, CORE / "pubspec.lock")]
    for label, root in (("repo", ROOT), ("core", CORE)):
        selected.extend((label, root, path) for path in (root / "lib").rglob("*.dart"))
    selected.extend(("repo", ROOT, path) for path in (ROOT / "assets/content_rust").rglob("*")
                    if path.is_file())
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Input snapshot deadline reached before path inventory")
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "ohos"],
        capture_output=True, check=True, timeout=min(5, remaining)).stdout.decode("utf-8").split("\0")
    for name in tracked:
        if not name:
            continue
        parts = Path(name).parts
        if any(part in {"build", ".hvigor", "oh_modules", "node_modules", "generated"} for part in parts):
            continue
        if Path(name).name.startswith("Generated"):
            GENERATED_OHOS.add(name.replace("\\", "/"))
            continue
        if name.replace("\\", "/") not in GENERATED_OHOS:
            selected.append(("repo", ROOT, ROOT / name))
    selected.extend(("repo", ROOT, path) for path in (ROOT / "ohos/entry/libs/arm64-v8a").glob("*.so")
                    if path.relative_to(ROOT).as_posix() not in GENERATED_OHOS)
    for label, root, path in sorted(set(selected), key=lambda x: (x[0], str(x[2]))):
        if time.monotonic() >= deadline:
            raise TimeoutError("Input snapshot deadline reached before " + str(path))
        key = label + "/" + path.relative_to(root).as_posix()
        if path.is_file():
            stat = path.stat()
            value = {"path": key, "exists": True, "bytes": stat.st_size,
                     "sha256": sha(path, deadline)}
            # Catch concurrent changes while hashing, rather than bind a mixed read.
            after = path.stat()
            if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError("Input changed while hashing: " + key)
            entries[key] = value
        else:
            entries[key] = {"path": key, "exists": False}
    for name in sorted(GENERATED_OHOS):
        path = ROOT / name
        key = "repo/" + name
        generated[key] = {"path": key, "exists": path.is_file()}
        if path.is_file():
            generated[key].update(bytes=path.stat().st_size, sha256=sha(path, deadline))
    return {"authoredAndNative": entries, "generatedSeparate": generated}


def inputs_diff(before, after):
    left, right = before["authoredAndNative"], after["authoredAndNative"]
    return [{"path": path, "before": left.get(path), "after": right.get(path)}
            for path in sorted(left.keys() | right.keys()) if left.get(path) != right.get(path)]


def outer_identity():
    k = C.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = W.HANDLE
    k.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    k.GetProcessTimes.restype = W.BOOL
    stamps = [W.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(k.GetCurrentProcess(), *(C.byref(s) for s in stamps)):
        raise C.WinError(C.get_last_error())
    return {"pid": os.getpid(), "creationFiletime100ns": str(
        (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime),
        "terminal": False, "requiresParentActualToolTerminal": True}


def memory():
    class Status(C.Structure):
        _fields_ = [("length", W.DWORD), ("load", W.DWORD)] + [
            (name, C.c_ulonglong) for name in ("totalPhysical", "availablePhysical",
            "totalPageFile", "availablePageFile", "totalVirtual", "availableVirtual", "extended")]
    s = Status()
    s.length = C.sizeof(s)
    k = C.WinDLL("kernel32", use_last_error=True)
    if not k.GlobalMemoryStatusEx(C.byref(s)):
        raise C.WinError(C.get_last_error())
    return {name: getattr(s, name) for name in ("totalPhysical", "availablePhysical",
            "totalPageFile", "availablePageFile")}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--claim-id", help="Fresh parent-verified channel event; not authorization by itself")
    p.add_argument("--no-pub", action="store_true", help="Skip normal release regeneration only if separately justified")
    p.add_argument("--invocation-correlation", help="Parent correlation label; not an actual tool execution/session identifier")
    args = p.parse_args()
    command = [str(SDK / "dart-sdk/bin/dart.exe"), str(SDK / "flutter_tools.snapshot"),
               "build", "hap", "--release", "--target-platform", "ohos-arm64",
               "--build-number", str(PRESERVED_BUILD_NUMBER)]
    if args.no_pub:
        command.append("--no-pub")
    command += ["--no-codesign", "--dart-define=QFLI_DIAG_TABBAR=false", "-t", "lib/main.dart"]
    if not args.execute:
        print(json.dumps({"preparedOnly": True, "command": command, "cwd": str(ROOT),
            "workSecondsFromModuleOrigin": WORK_SECONDS,
            "jobCleanupEndSecondsFromModuleOrigin": JOB_CLEANUP_SECONDS,
            "finalizationEndSecondsFromModuleOrigin": FINALIZATION_SECONDS,
            "plannedTotalWindowSeconds": PLANNED_TOTAL_SECONDS,
            "parentTerminalAndPublicationReserveAfterCleanupSeconds": PLANNED_TOTAL_SECONDS - JOB_CLEANUP_SECONDS,
            "parentPublicationReserveAfterFinalizationSeconds": PLANNED_TOTAL_SECONDS - FINALIZATION_SECONDS,
            "toolStartupExcludedAndParentMustMeasureActualTotal": True,
            "unsigned": True, "deviceAction": None,
            "required": "fresh parent serial claim; actual outer tool terminal before release"}, indent=2))
        return 0
    if not args.claim_id:
        p.error("--execute requires a fresh parent-verified --claim-id")
    run = HERE / ("production-delivery-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    report = {"claimId": args.claim_id, "invocationCorrelation": args.invocation_correlation, "outerExecId": None,
              "unsigned": True, "command": command, "cwd": str(ROOT),
              "budgetOrigin": "Python module monotonic origin; excludes Python/tool startup",
              "workSeconds": WORK_SECONDS, "jobCleanupEndSeconds": JOB_CLEANUP_SECONDS,
              "finalizationEndSeconds": FINALIZATION_SECONDS,
              "plannedTotalWindowSeconds": PLANNED_TOTAL_SECONDS,
              "parentTerminalAndPublicationReserveAfterCleanupSeconds": PLANNED_TOTAL_SECONDS - JOB_CLEANUP_SECONDS,
              "parentPublicationReserveAfterFinalizationSeconds": PLANNED_TOTAL_SECONDS - FINALIZATION_SECONDS,
              "toolStartupExcludedAndParentMustMeasureActualTotal": True,
              "deviceAction": None, "resourceReleaseCandidate": False,
              "buildSucceeded": False, "artifactValid": None,
              "requiresIndependentHapInspection": True,
              "requiresParentActualToolTerminal": True,
              "parentMustAppendActualExecIdAfterLaunch": True,
              "knownBuildLimitation": "This Flutter OHOS fork includes integration_test even with pub enabled; no SDK or generated registrant patch is applied",
              "report": str(run / "report.json")}
    original = None
    app_scope_original = None
    app_scope_model = None
    temporary = None
    changed = False
    result = None
    build_entered = False
    held = []
    closed = []
    code = 1
    def persist():
        report["elapsedSeconds"] = time.monotonic() - ORIGIN
        (run / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    def restore_app_scope_after_empty():
        # Only the caller's exact Job0 observation admits this narrow metadata
        # restoration. Never overwrite a logical change from Flutter or peers.
        try:
            current = APP_SCOPE.read_bytes()
            if report.get("appScopeRestoredExact") is True and current == app_scope_original:
                return True
            proof = {"path": str(APP_SCOPE),
                     "originalSha256": hashlib.sha256(app_scope_original).hexdigest(),
                     "beforeRestoreSha256": hashlib.sha256(current).hexdigest()}
            report["appScopeRestoration"] = proof
            equivalent = json.loads(current.decode("utf-8-sig")) == app_scope_model
            proof["logicalIdentityUnchanged"] = equivalent
            if not equivalent:
                proof["conflict"] = "AppScope logical content changed; preserve current bytes and original backup"
                report["appScopeRestoredExact"] = False
                return False
            if APP_SCOPE.read_bytes() != current:
                proof["conflict"] = "AppScope changed during restoration check; preserve current bytes"
                report["appScopeRestoredExact"] = False
                return False
            proof["restoredFormattingBytes"] = current != app_scope_original
            if current != app_scope_original:
                APP_SCOPE.write_bytes(app_scope_original)
            restored = APP_SCOPE.read_bytes()
            proof["afterRestoreSha256"] = hashlib.sha256(restored).hexdigest()
            report["appScopeRestoredExact"] = restored == app_scope_original
            return report["appScopeRestoredExact"]
        except Exception as error:
            report["appScopeRestorationError"] = repr(error)
            report["appScopeRestoredExact"] = False
            return False
    try:
        report["outer"] = outer_identity()
        print("OUTER", json.dumps(report["outer"]), "REPORT", report["report"], flush=True)
        app_scope_original = APP_SCOPE.read_bytes()
        app_scope_model = json.loads(app_scope_original.decode("utf-8-sig"))
        if app_scope_model.get("app", {}).get("versionCode") != PRESERVED_BUILD_NUMBER:
            raise RuntimeError("AppScope versionCode differs from explicitly preserved build number; do not mutate identity")
        (run / "app-scope.original.bin").write_bytes(app_scope_original)
        report["originalAppScopeSha256"] = hashlib.sha256(app_scope_original).hexdigest()
        report["preservedBuildNumber"] = PRESERVED_BUILD_NUMBER
        original = CONFIG.read_bytes()
        config = json.loads(original.decode("utf-8-sig"))
        config.setdefault("properties", {})["enableSignTask"] = False
        temporary = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()
        (run / "hvigor-config.original.bin").write_bytes(original)
        report["originalConfigSha256"] = hashlib.sha256(original).hexdigest()
        report["temporaryConfigSha256"] = hashlib.sha256(temporary).hexdigest()
        report["sourceBefore"] = git_identity(ROOT, ORIGIN + WORK_SECONDS)
        report["coreBefore"] = git_identity(CORE, ORIGIN + WORK_SECONDS)
        report["beforeHaps"] = [file_identity(x, ORIGIN + WORK_SECONDS) for x in HAPS]
        report["memoryBefore"] = memory()
        report["inputSnapshotBefore"] = inputs_snapshot(ORIGIN + WORK_SECONDS)
        (run / "inputs-before.json").write_text(json.dumps(report["inputSnapshotBefore"], indent=2), encoding="utf-8")
        report["helpers"] = [file_identity(HERE / x) for x in
            ("rust_owned_job.py", "run-rust-owned-window.py", "run-production-debugoff-20261028.py")]
        report["childEnvironmentOverrides"] = dict(CHILD_ENV_HOMES)
        report["childPathPrefix"] = list(CHILD_PATH_PREFIX)
        report["environmentChangeScope"] = "Owned child environment only; no parent or persistent environment mutation"
        for directory in [*CHILD_ENV_HOMES.values(), *CHILD_PATH_PREFIX]:
            if not Path(directory).is_dir():
                raise RuntimeError("Missing DevEco environment prerequisite: " + directory)
        for required in (Path(command[0]), Path(command[1]), ROOT / "lib/main.dart",
                         DEVECO / "jbr/bin/java.exe", DEVECO / "tools/node/node.exe"):
            if not required.is_file():
                raise RuntimeError("Missing build prerequisite: " + str(required))
        sys.path.insert(0, str(HERE))
        runner = runpy.run_path(str(HERE / "run-rust-owned-window.py"), run_name="production_delivery_library")
        OriginalJob = runner["run_owned"].__globals__["OwnedJob"]
        class CustodianJob(OriginalJob):
            def __init__(self):
                super().__init__()
                self.confirmed_empty = False
                self.handle_close_evidence = []
                self.all_handles_closed = False
                self.closed_record_published = False
            def retained_handles(self):
                return {"jobHandle": int(self.job) if self.job is not None else None,
                        "processHandle": int(self.process) if self.process is not None else None,
                        "process": dict(self.record),
                        "allHandlesClosed": self.all_handles_closed}
            def retain(self):
                if self not in held:
                    held.append(self)
            def start(self, command, directory, env, stdout, stderr):
                child_env = dict(env)
                inherited_path = next((v for k, v in child_env.items() if k.lower() == "path"), "")
                for key in list(child_env):
                    if key.lower() == "path":
                        del child_env[key]
                child_env.update(CHILD_ENV_HOMES)
                child_env["PATH"] = os.pathsep.join([*CHILD_PATH_PREFIX, inherited_path])
                return super().start(command, directory, child_env, stdout, stderr)
            def empty(self):
                self.confirmed_empty = False
                answer = super().empty()
                self.confirmed_empty = answer
                return answer
            def close(self):
                if self.all_handles_closed:
                    return True
                if not self.confirmed_empty:
                    # Keep exact handles alive on uncertain cleanup. Parent must
                    # treat the live outer as HOLD, never publish a release.
                    self.retain()
                    return False
                # Check each real CloseHandle result. A successful handle is
                # cleared immediately and is never closed again on a retry.
                # Retain the Job until the process handle has closed, so any
                # partial close still leaves an exact live Job custodian.
                for attribute, kind in (("process", "process"), ("job", "job")):
                    handle = getattr(self, attribute)
                    if handle is None:
                        continue
                    C.set_last_error(0)
                    succeeded = bool(self.k.CloseHandle(handle))
                    evidence = {"kind": kind, "handle": int(handle),
                                "succeeded": succeeded,
                                "lastError": 0 if succeeded else C.get_last_error()}
                    self.handle_close_evidence.append(evidence)
                    self.record["handleCloseEvidence"] = list(self.handle_close_evidence)
                    if not succeeded:
                        self.record["checkedAllHandlesClosed"] = False
                        self.retain()
                        return False
                    setattr(self, attribute, None)
                self.all_handles_closed = self.process is None and self.job is None
                self.record["checkedAllHandlesClosed"] = self.all_handles_closed
                if self.all_handles_closed and not self.closed_record_published:
                    closed.append(dict(self.record))
                    self.closed_record_published = True
                if not self.all_handles_closed:
                    self.retain()
                return self.all_handles_closed
        runner["run_owned"].__globals__["OwnedJob"] = CustodianJob
        persist()
        if CONFIG.read_bytes() != original:
            raise RuntimeError("Hvigor config changed during preflight")
        if time.monotonic() >= ORIGIN + WORK_SECONDS:
            raise RuntimeError("Work deadline reached before build")
        CONFIG.write_bytes(temporary)
        changed = True
        report["configTemporaryApplied"] = True
        persist()
        build_entered = True
        result = runner["run_owned"]("production-ohos-unsigned", command, ROOT,
                    run / "build.log", ORIGIN + WORK_SECONDS, ORIGIN + JOB_CLEANUP_SECONDS)
        report["build"] = result
        report["closedOwnedRoots"] = closed
        if held:
            report["state"] = "HOLD_UNCERTAIN_OWNED_JOB"
            report["heldOwnedRoots"] = [dict(j.record) for j in held]
            report["heldOwnedHandles"] = [j.retained_handles() for j in held]
            report["budgetFailed"] = time.monotonic() >= ORIGIN + FINALIZATION_SECONDS
            persist()
            print("HOLD", json.dumps(report), flush=True)
            next_hold_publication = time.monotonic()
            while held:
                for job in list(held):
                    try:
                        if job.empty() and job.close():
                            held.remove(job)
                    except Exception as error:
                        report["custodianObservationError"] = repr(error)
                if held:
                    if time.monotonic() >= next_hold_publication:
                        report["heldOwnedRoots"] = [dict(j.record) for j in held]
                        report["heldOwnedHandles"] = [j.retained_handles() for j in held]
                        persist()
                        next_hold_publication = time.monotonic() + 1
                    if not report.get("budgetFailed") and time.monotonic() >= ORIGIN + FINALIZATION_SECONDS:
                        report["budgetFailed"] = True
                        report["deadlineExceeded"] = True
                        persist()
                        print("HOLD_BUDGET_FAILED", report["report"], flush=True)
                    time.sleep(0.1)
            report["holdResolved"] = True
            report["heldOwnedRoots"] = []
            report["heldOwnedHandles"] = []
            report["closedOwnedRoots"] = closed
            result["emptyJob"] = True
            # Earlier uncertainty remains a failed run; never convert to PASS.
            result["exit"] = 125
        code = result["exit"]
        # Compare authored inputs only after undoing this launcher's own config
        # mutation. Restore requires this exact owned Job's empty observation.
        if result.get("emptyJob") is True and not held and CONFIG.read_bytes() == temporary:
            CONFIG.write_bytes(original)
            report["configRestoredExact"] = CONFIG.read_bytes() == original
        elif changed:
            report["configRestoredExact"] = False
            report["configConflict"] = "Cannot restore before input comparison; current bytes are not this launcher's temporary bytes"
            code = code or 1
        if result.get("emptyJob") is True and not held:
            if not restore_app_scope_after_empty():
                code = code or 1
        report["inputSnapshotAfter"] = inputs_snapshot(ORIGIN + FINALIZATION_SECONDS)
        (run / "inputs-after.json").write_text(json.dumps(report["inputSnapshotAfter"], indent=2), encoding="utf-8")
        report["sourceInputDiffs"] = inputs_diff(report["inputSnapshotBefore"], report["inputSnapshotAfter"])
        if report["sourceInputDiffs"]:
            report["sourceInputDrift"] = True
            code = code or 1
        report["afterHaps"] = [file_identity(x, ORIGIN + FINALIZATION_SECONDS) for x in HAPS]
        report["sourceAfter"] = git_identity(ROOT, ORIGIN + FINALIZATION_SECONDS)
        report["coreAfter"] = git_identity(CORE, ORIGIN + FINALIZATION_SECONDS)
        report["newUnsignedHaps"] = [after for before, after in zip(report["beforeHaps"], report["afterHaps"])
            if after.get("exists") and (not before.get("exists") or after.get("mtimeNs") != before.get("mtimeNs"))]
        if code == 0 and not report["newUnsignedHaps"]:
            code = 1
            report["failure"] = "Build exit0 but no newly written unsigned output"
    except BaseException as error:
        report["error"] = repr(error)
        code = 1
    finally:
        safe = (not build_entered) or (result is not None and result.get("emptyJob") is True and not held)
        if changed and safe:
            if report.get("configRestoredExact") is True and CONFIG.read_bytes() == original:
                pass
            elif CONFIG.read_bytes() == temporary:
                CONFIG.write_bytes(original)
                report["configRestoredExact"] = CONFIG.read_bytes() == original
            else:
                report["configRestoredExact"] = False
                report["configConflict"] = "Current bytes differ from this launcher's temporary bytes; original preserved in run directory"
                code = code or 1
        elif changed:
            report["configRestoredExact"] = False
            report["state"] = "HOLD_UNCERTAIN_OWNED_JOB"
            code = 125
        else:
            report["configUnchanged"] = CONFIG.read_bytes() == original if original is not None else None
        if safe and build_entered and app_scope_original is not None:
            if not restore_app_scope_after_empty():
                code = code or 1
        report["deadlineExceeded"] = time.monotonic() > ORIGIN + FINALIZATION_SECONDS
        if report["deadlineExceeded"]:
            code = code or 124
        report["exit"] = code
        report["resourceReleaseCandidate"] = bool(result and result.get("emptyJob") and not held
            and report.get("configRestoredExact") and report.get("appScopeRestoredExact") and closed
            and all(item.get("checkedAllHandlesClosed") is True for item in closed))
        report["budgetFailed"] = bool(report.get("budgetFailed") or report["deadlineExceeded"]
            or (result and result.get("deadlineExceeded")))
        report["buildSucceeded"] = bool(code == 0 and result and result.get("exit") == 0
            and report.get("newUnsignedHaps") and report.get("configRestoredExact")
            and report.get("appScopeRestoredExact")
            and not report.get("sourceInputDiffs"))
        report["resourceReleaseSemantics"] = "Candidate concerns empty/closed owned Jobs and restored config only; failed builds may release resources. Parent must observe actual outer tool terminal before release."
        report["outerTerminal"] = False
        persist()
        summary = {key: report.get(key) for key in ("report", "outer", "exit", "buildSucceeded",
            "artifactValid", "requiresIndependentHapInspection", "resourceReleaseCandidate", "budgetFailed",
            "configRestoredExact", "appScopeRestoredExact", "outerTerminal", "requiresParentActualToolTerminal", "state", "error")}
        print("PRODUCTION_RESULT", json.dumps(summary, separators=(",", ":")), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
