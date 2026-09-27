"""Comparative timings must not mix native and translated runtimes."""

import importlib.util
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def checker(monkeypatch):
    path = Path(__file__).resolve().parents[1]/'tools/disposable_neo4j.py'
    spec = importlib.util.spec_from_file_location('architecture_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    return module


def configure(monkeypatch, module, python, java, arm_hardware=True):
    monkeypatch.setattr(module.platform, 'machine', lambda: python)

    def run(command, **kwargs):
        if command[0] == 'sysctl':
            return subprocess.CompletedProcess(command, 0, str(int(arm_hardware)), '')
        assert command == ['/fixture/java', '-XshowSettings:properties', '-version']
        assert kwargs['check'] and kwargs['timeout'] > 0
        return subprocess.CompletedProcess(command, 0, '',
            f'    os.arch = {java}\n    java.runtime.version = 21.0.10+7-LTS\n'
            '    java.vendor = Eclipse Adoptium\n')

    monkeypatch.setattr(module.subprocess, 'run', run)


@pytest.mark.parametrize(('python', 'java', 'arm'), [
    ('arm64', 'aarch64', True), ('x86_64', 'amd64', False),
])
def test_accepts_native_aliases(checker, monkeypatch, python, java, arm):
    configure(monkeypatch, checker, python, java, arm)
    identity = checker.native_runtime_identity(Path('/fixture/java'))
    assert identity['native_architecture'] == python
    assert identity['java_runtime_version'] == '21.0.10+7-LTS'


@pytest.mark.parametrize(('python', 'java'), [
    ('arm64', 'x86_64'), ('x86_64', 'x86_64'), ('x86_64', 'aarch64'),
    ('arm64', 'unknown'),
])
def test_rejects_translated_or_unknown_runtime(checker, monkeypatch, python, java):
    configure(monkeypatch, checker, python, java)
    with pytest.raises(ValueError, match='matching native architectures'):
        checker.native_runtime_identity(Path('/fixture/java'))


def test_checks_linux_vm_properties(checker, monkeypatch):
    configure(monkeypatch, checker, 'aarch64', 'aarch64')
    monkeypatch.setattr(checker.sys, 'platform', 'linux')
    assert checker.native_runtime_identity(Path('/fixture/java'))['native_architecture'] == 'arm64'


def test_vm_failure_is_not_an_architecture_pass(checker, monkeypatch):
    configure(monkeypatch, checker, 'arm64', 'aarch64')
    monkeypatch.setattr(checker.sys, 'platform', 'linux')

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(checker.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        checker.native_runtime_identity(Path('/fixture/java'))
