"""Shared constants and process helpers for the application installer workflow."""

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from collections import deque


ROOT = Path(__file__).resolve().parents[2]
APP_NAME = "QFLIRustCore"
APP_ID = "com.azurekiln.qfli.rustcore"
BINARY_NAME = "qfli_rust"
HOMEPAGE = "https://github.com/azurekiln2333/qflistudio-rust"
ARTIFACT_PREFIX = "app-installer"
ANNOTATION_LIMIT = 4000
LOG_LIMIT = 2 * 1024 * 1024
CORE_REPOSITORY = "azurekiln2333/qflistudio-core"
CORE_DIRECTORY = "qflistudio-core"
# Pins already used by the native workflow and the sibling app workflow.
# The cloud checks must verify their action.yml runtime before publication.
ACTION_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
    "actions/setup-java": "de7274f081f381c8f8158605e0321c36c376e2e6",
    "actions/upload-artifact": "cf430e030ddbb5b0abf93d22962f4752f3646cd9",
    "actions/download-artifact": "9000827ccba6bdab643e8b6fd33ac0654aef8333",
}


def require_hosted_runner():
    """Never turn an accidental local invocation into a build or restore."""
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or not os.environ.get("RUNNER_TEMP")):
        raise RuntimeError("Application CI operations require a GitHub-hosted runner")

# Application job (platform, arch) -> native runtime archives it embeds.
# Desktop applications start the system cargo and rustc, so they embed none.
TARGETS = {
    ("android", "arm64-x64"): ("android-arm64", "android-x64"),
    ("ios", "arm64"): ("ios-arm64",),
    ("ohos", "arm64"): ("ohos-arm64",),
    ("linux", "x64"): (),
    ("windows", "x64"): (),
    ("macos", "arm64"): (),
    ("macos", "x64"): (),
}
PACKAGE_NAMES = {
    ("android", "arm64-x64"): (f"{APP_NAME}-android-arm64-v8a-test-signed.apk",
                               f"{APP_NAME}-android-x86_64-test-signed.apk"),
    ("ios", "arm64"): (f"{APP_NAME}-ios-arm64-unsigned.ipa",),
    ("ohos", "arm64"): (f"{APP_NAME}-ohos-arm64-v8a-unsigned.hap",),
    ("linux", "x64"): (f"{APP_NAME}-linux-x64.deb",),
    ("windows", "x64"): (f"{APP_NAME}-windows-x64-setup.exe",),
    ("macos", "arm64"): (f"{APP_NAME}-macos-arm64.dmg",),
    ("macos", "x64"): (f"{APP_NAME}-macos-x64.dmg",),
}
# Runtime architecture -> ABI directory of Android and OHOS packages.
ABIS = {"arm64": "arm64-v8a", "x64": "x86_64"}
SIGNING = {
    "android": "debug_key_for_testing_not_store_release",
    "ios": "unsigned_requires_signing_before_device_installation",
    "ohos": "unsigned_requires_signing_before_device_installation",
    "macos": "ad_hoc_not_notarized",
    "linux": "not_applicable",
    "windows": "unsigned_executable",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes keep LF on Windows, so a record hashes the same on every runner.
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def read_version(pubspec=None):
    """Return the pubspec version, for example 1.0.0+1."""
    text = Path(pubspec or ROOT / "pubspec.yaml").read_text(encoding="utf-8")
    match = re.search(r"(?m)^version:\s*(\d+\.\d+\.\d+(?:\+\d+)?)\s*$", text)
    if not match:
        raise RuntimeError("pubspec.yaml does not state a numeric version")
    return match.group(1)


def output_root(platform, arch):
    return ROOT / "build/app-artifacts" / f"{ARTIFACT_PREFIX}-{platform}-{arch}"


def add_target_arguments(parser):
    parser.add_argument("--platform", default=os.environ.get("QFLI_PLATFORM"))
    parser.add_argument("--arch", default=os.environ.get("QFLI_ARCH"))
    parser.add_argument("--output-dir", type=Path)


def resolve_target(args, parser):
    """Reject every platform and arch pair outside the workflow matrix."""
    if (args.platform, args.arch) not in TARGETS:
        choices = ", ".join(f"{platform}/{arch}" for platform, arch in TARGETS)
        parser.error(f"unsupported target {args.platform}/{args.arch}; choose one of {choices}")
    args.output = (args.output_dir or output_root(args.platform, args.arch)).resolve()
    return args


def runtime_manifest_path(key, root=ROOT):
    return Path(root) / "assets/miri" / f"manifest.{key}.json"


def runtime_library_paths(manifest):
    """Schema 2 records a library path; schema 1 (OHOS) records only its name."""
    return [entry.get("path") or entry["name"] for entry in manifest["nativeLibraries"]]


def redact(text):
    """Remove credentials from a diagnostic before it leaves the runner."""
    text = re.sub(r"(?s)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                  "[private key redacted]", text)
    text = re.sub(
        r"(?im)^.*(?:authorization\s*:|\b(?:[a-z_]*password|[a-z_]*token|"
        r"[a-z_]*secret|keypass|storepass|private[_-]?key)[\"']?\s*[:=]).*$",
        "[sensitive diagnostic line redacted]", text)
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
                  "[token redacted]", text)

    def redact_url(match):
        value = match.group(0)
        value = re.sub(r"(https?://)[^/@]+@", r"\1[redacted]@", value, flags=re.IGNORECASE)
        return value.split("?", 1)[0] + ("?[redacted]" if "?" in value else "")

    text = re.sub(r"https?://[^\s<>\"']+", redact_url, text, flags=re.IGNORECASE)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def annotation(level, message, *, heading=None, title=None):
    """Format one workflow command; redact before truncation so no credential prefix is lost."""
    if level not in ("error", "warning", "notice"):
        raise ValueError(f"Unknown annotation level: {level}")
    body = redact(message)[-ANNOTATION_LIMIT:]
    if heading:
        body = redact(heading) + "\n" + body
    # Escape data, in this order, to prevent output from becoming workflow commands.
    body = body.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    properties = ""
    if title:
        value = redact(title)[:120]
        for raw, escaped in (("%", "%25"), ("\r", "%0D"), ("\n", "%0A"), (":", "%3A"), (",", "%2C")):
            value = value.replace(raw, escaped)
        properties = " title=" + value
    return f"::{level}{properties}::{body}"


def annotate(level, message, *, heading=None, title=None):
    """Job logs need a login; annotations stay readable through the public checks API."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print_console(annotation(level, message, heading=heading, title=title))


def annotate_command_failure(log, returncode, output):
    # Exclude the command heading; it can repeat a long argument list.
    tail = output.split("\n\n", 1)[-1] if output.startswith("Command: ") else output
    annotate("error", tail, heading=f"Command failed ({returncode}); see {Path(log).name}")


def report_failure(output, stage, failure):
    """Keep a stage failure as a report and surface it as an annotation."""
    report = Path(output) / "reports" / f"{stage}-failure.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(redact(str(failure))[-LOG_LIMIT:], encoding="utf-8")
    annotate("error", failure, heading=f"Stage {stage} failed; see {report.name}")
    return report


def print_console(text):
    """Keep diagnostics printable on legacy consoles; UTF-8 report files stay exact."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    printable = text.encode(encoding, errors="backslashreplace").decode(encoding)
    print(printable, flush=True)


def print_untrusted(text):
    """Print tool output without letting it issue workflow commands."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        print_console(text)
        return
    token = secrets.token_hex(16)
    print_console(f"::stop-commands::{token}")
    try:
        print_console(text)
    finally:
        print_console(f"::{token}::")


def bounded_log(source):
    """Redact before retaining a bounded tail; raw output never enters artifacts."""
    lines = deque()
    length = 0
    private_key = False
    with Path(source).open(encoding="utf-8", errors="replace") as stream:
        while True:
            line = stream.readline(65537)
            if not line:
                break
            private_key = private_key or "-----BEGIN " in line and "PRIVATE KEY-----" in line
            if private_key:
                if "-----END " in line and "PRIVATE KEY-----" in line:
                    private_key = False
                clean = "[private key redacted]\n"
            elif len(line) > 65536:
                clean = "[oversized diagnostic line omitted]\n"
            else:
                clean = redact(line)
            if len(line) > 65536 and not line.endswith("\n"):
                while line and not line.endswith("\n"):
                    line = stream.readline(65537)
            lines.append(clean)
            length += len(clean.encode("utf-8"))
            while length > LOG_LIMIT and lines:
                length -= len(lines.popleft().encode("utf-8"))
    return "".join(lines)


def run(command, log, *, cwd=ROOT, env=None, timeout=3600):
    """Execute only in cloud; publish at most 2 MiB of redacted output per log."""
    require_hosted_runner()
    command = [str(part) for part in command]
    log = Path(log)
    heading = "Command: " + redact(repr(command)) + "\n\n"
    print_untrusted("+ " + redact(" ".join(command)))
    log.parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    returncode = None
    with tempfile.TemporaryDirectory(prefix="qfli-command-", dir=os.environ["RUNNER_TEMP"]) as temporary:
        raw = Path(temporary) / "output.log"
        with raw.open("w", encoding="utf-8") as stream:
            try:
                returncode = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                            stderr=subprocess.STDOUT, timeout=timeout,
                                            check=False).returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                stream.flush()
                output = bounded_log(raw)
                log.write_text(heading + output, encoding="utf-8")
                print_untrusted(output[-12000:])
    if timed_out:
        annotate("error", output, heading=f"Command timed out after {timeout} s; see {log.name}")
        raise RuntimeError(f"Command timed out after {timeout} s; see {log.name}")
    if returncode:
        annotate_command_failure(log, returncode, output)
        raise RuntimeError(f"Command failed ({returncode}); see {log.name}")
    return output


def step_summary(text):
    """Append Markdown to the job summary page when the runner offers one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(text if text.endswith("\n") else text + "\n")
