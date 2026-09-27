"""Run integration tests in a newly created local Neo4j home, then terminate it.

Requires a Neo4j distribution and compatible Java already installed. Does not
read or alter any existing database data/configuration. Fixture credentials are
disabled only on a dynamically assigned loopback Bolt port; HTTP is disabled.
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def native_runtime_identity(java):
    """Reject translated/mismatched runtimes before comparative CPU timing.

    Java's running VM properties, rather than the bundle name, identify the
    selected architecture (including universal executables). On macOS also check
    hardware support so two processes under Rosetta cannot pass as native.
    """
    aliases = {"aarch64": "arm64", "arm64": "arm64", "amd64": "x86_64",
               "x86_64": "x86_64"}
    python_arch = platform.machine().lower()
    hardware_arch = python_arch
    if sys.platform == "darwin":
        hardware = subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                                  capture_output=True, text=True, check=False, timeout=10)
        if hardware.returncode == 0 and hardware.stdout.strip() == "1":
            hardware_arch = "arm64"
    result = subprocess.run([str(java), "-XshowSettings:properties", "-version"],
                            capture_output=True, text=True, check=True, timeout=20)
    properties = {}
    for line in (result.stdout + result.stderr).splitlines():
        key, separator, value = line.strip().partition(" = ")
        if separator:
            properties[key] = value
    java_arch = properties.get("os.arch", "unknown").lower()
    normalized = [aliases.get(arch) for arch in (hardware_arch, python_arch, java_arch)]
    if None in normalized or len(set(normalized)) != 1:
        raise ValueError("Comparative timing requires matching native architectures: "
                         f"hardware={hardware_arch}, Python={python_arch}, Java={java_arch}")
    return {"hardware_architecture": hardware_arch, "python_architecture": python_arch,
            "java_architecture": java_arch, "native_architecture": normalized[0],
            "java_runtime_version": properties.get("java.runtime.version"),
            "java_vendor": properties.get("java.vendor")}


@contextmanager
def disposable_database(neo4j_home, java, *, transaction_timeout="30s", gds_jar=None,
                        heap_megabytes=256, entrypoint="org.neo4j.server.CommunityEntryPoint",
                        gds_progress_retention_seconds=0):
    """Yield a fresh loopback-only database; always terminate and delete its data."""
    from neo4j import GraphDatabase
    from neo4j.exceptions import DriverError, Neo4jError

    if type(heap_megabytes) is not int or heap_megabytes < 128:
        raise ValueError("heap_megabytes must be an integer of at least 128")
    if (type(gds_progress_retention_seconds) is not int or gds_progress_retention_seconds < 0
            or (gds_progress_retention_seconds and gds_jar is None)):
        raise ValueError("GDS task retention requires nonnegative integer seconds and a GDS jar")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="orbweaver-query-neo4j-") as directory:
        root = Path(directory)
        conf = root / "conf"
        conf.mkdir()
        settings = {
            "server.directories.data": str(root / "data"),
            "server.directories.logs": str(root / "logs"),
            "server.directories.run": str(root / "run"),
            "server.directories.plugins": str(root / "plugins"),
            "server.directories.import": str(root / "import"),
            "server.directories.transaction.logs.root": str(root / "transactions"),
            "server.bolt.listen_address": f"127.0.0.1:{port}",
            "server.bolt.advertised_address": f"127.0.0.1:{port}",
            "server.http.enabled": "false", "server.https.enabled": "false",
            "dbms.security.auth_enabled": "false",
            "server.memory.pagecache.size": "64m",
            "dbms.usage_report.enabled": "false",
            "db.transaction.timeout": transaction_timeout,
        }
        if gds_jar is not None:
            plugins = root / "plugins"
            plugins.mkdir()
            shutil.copyfile(gds_jar, plugins / "graph-data-science.jar")
            settings["dbms.security.procedures.allowlist"] = "gds.*"
            settings["dbms.security.procedures.unrestricted"] = "gds.*"
            if gds_progress_retention_seconds:
                settings["gds.progress_tracking_retention_period"] = f"{gds_progress_retention_seconds}s"
        (conf / "neo4j.conf").write_text("".join(f"{k}={v}\n" for k, v in settings.items()))
        uri = f"bolt://127.0.0.1:{port}"
        with (root / "console.log").open("w+") as log:
            process = subprocess.Popen([
                str(java), "-Xms128m", f"-Xmx{heap_megabytes}m", "-Djol.skipHotspotSAAttach=true",
                "--add-opens=java.base/java.nio=ALL-UNNAMED",
                "--add-opens=java.base/java.io=ALL-UNNAMED",
                "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
                "--add-opens=java.base/java.util.concurrent=ALL-UNNAMED",
                "--enable-native-access=ALL-UNNAMED", "--add-modules=jdk.incubator.vector",
                "-cp", os.pathsep.join((str(neo4j_home / "lib" / "*"),
                                       str(root / "plugins" / "*"))),
                entrypoint, f"--home-dir={neo4j_home}",
                f"--config-dir={conf}", "--console-mode",
            ], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.seek(0)
                        debug = root / "logs" / "debug.log"
                        detail = "\n".join(line for line in debug.read_text().splitlines()
                                           if any(w in line for w in ("ERROR", "WARN", "Exception"))) \
                            if debug.exists() else ""
                        raise RuntimeError(log.read() + detail)
                    try:
                        with GraphDatabase.driver(uri, auth=None, connection_timeout=1) as driver:
                            driver.verify_connectivity()
                        break
                    except (DriverError, Neo4jError, OSError):
                        time.sleep(.3)
                else:
                    log.seek(0)
                    raise RuntimeError("Disposable database did not start: " + log.read())
                yield uri
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--neo4j-home", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--entrypoint", default="org.neo4j.server.CommunityEntryPoint",
                        help="Use org.neo4j.server.Neo4jCommunity for Neo4j 2026.09")
    parser.add_argument("--installed", action="store_true",
                        help="Test the installed wheel instead of the source checkout")
    args = parser.parse_args()
    print(json.dumps(native_runtime_identity(args.java)), flush=True)
    with disposable_database(args.neo4j_home, args.java, entrypoint=args.entrypoint) as uri:
        package = Path(__file__).resolve().parents[1]
        env = {**os.environ, "ORBWEAVER_QUERY_TEST_URI": uri}
        command = [sys.executable, *(["-I"] if args.installed else []),
                   "-m", "pytest", "-q", str(package / "tests" / "test_neo4j_live.py")]
        if args.installed:
            command += ["-o", "pythonpath="]
        return subprocess.run(command, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
