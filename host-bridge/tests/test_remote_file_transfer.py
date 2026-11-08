import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_local_paths_confined_and_sensitive_denied(tmp_path):
    from remote_file_transfer import safe_local_path
    root = tmp_path / 'work'
    root.mkdir()
    ordinary = root / 'artifact.txt'
    ordinary.write_text('artifact')
    assert safe_local_path(str(ordinary), [str(root)]) == ordinary
    outside = tmp_path / 'outside'
    outside.write_text('secret')
    (root / 'escape').symlink_to(outside)
    for path in [root / 'escape', root / '..' / 'outside', root / '.env', root / 'id_ed25519', Path('/root/.ssh/id_ed25519')]:
        with pytest.raises(HTTPException):
            safe_local_path(str(path), [str(root)])


@pytest.mark.asyncio
async def test_stream_upload_download_hash_atomic_and_conflict(tmp_path, monkeypatch):
    import remote_file_transfer as transfer
    import remote_fs
    monkeypatch.setattr(remote_fs, 'ssh_args', lambda target: ['sh', '-c'])
    monkeypatch.setattr(remote_fs, '_CONTROL_DIR', str(tmp_path / 'control'))
    target = remote_fs.SshTarget('example.test', 'user', 22, None)
    source = tmp_path / 'source.bin'
    source.write_bytes(b'example artifact\x00' * 10000)
    remote = tmp_path / 'remote.bin'
    result = await transfer.transfer_file(target, 'upload', source, str(remote), False)
    assert result['size'] == source.stat().st_size
    assert len(result['sha256']) == 64
    assert remote.read_bytes() == source.read_bytes()
    with pytest.raises(HTTPException) as conflict:
        await transfer.transfer_file(target, 'upload', source, str(remote), False)
    assert conflict.value.status_code == 409
    destination = tmp_path / 'download.bin'
    downloaded = await transfer.transfer_file(target, 'download', destination, str(remote), False)
    assert downloaded == result
    assert destination.read_bytes() == source.read_bytes()
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.asyncio
async def test_size_rejection_and_interruption_leave_final_absent(tmp_path, monkeypatch):
    import remote_file_transfer as transfer
    import remote_fs
    monkeypatch.setattr(remote_fs, 'ssh_args', lambda target: ['sh', '-c'])
    monkeypatch.setattr(remote_fs, '_CONTROL_DIR', str(tmp_path / 'control'))
    monkeypatch.setattr(transfer, 'MAX_BYTES', 8)
    source = tmp_path / 'source'
    source.write_bytes(b'123456789')
    remote = tmp_path / 'remote'
    target = remote_fs.SshTarget('example.test', 'user', 22, None)
    with pytest.raises(HTTPException) as error:
        await transfer.transfer_file(target, 'upload', source, str(remote), False)
    assert error.value.status_code == 413
    assert not remote.exists()


@pytest.mark.asyncio
async def test_interrupted_upload_cleans_remote_part_and_never_publishes(tmp_path, monkeypatch):
    import remote_file_transfer as transfer
    import remote_fs
    # Keep the real upload shell/trap/rename logic; interrupt its input.
    original = remote_fs.remote_command
    monkeypatch.setattr(remote_fs, 'remote_command', lambda script, *args: original(
        'cat(){ head -c 4; return 1; };\n' + script, *args))
    monkeypatch.setattr(remote_fs, 'ssh_args', lambda target: ['sh', '-c'])
    monkeypatch.setattr(remote_fs, '_CONTROL_DIR', str(tmp_path / 'control'))
    source = tmp_path / 'source'
    source.write_bytes(b'123456789')
    remote = tmp_path / 'final'
    with pytest.raises(HTTPException):
        await transfer.transfer_file(remote_fs.SshTarget('test', 'user', 22, None), 'upload', source, str(remote), False)
    assert not remote.exists()
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.asyncio
async def test_download_hash_mismatch_does_not_replace_existing_destination(tmp_path, monkeypatch):
    import remote_file_transfer as transfer
    import remote_fs
    monkeypatch.setattr(remote_fs, 'ssh_args', lambda target: ['sh', '-c'])
    async def wrong_metadata(*args, **kwargs):
        return 0, b'4 ' + b'0' * 64, ''
    monkeypatch.setattr(remote_fs, 'run', wrong_metadata)
    remote = tmp_path / 'remote'
    remote.write_bytes(b'data')
    local = tmp_path / 'local'
    local.write_bytes(b'original')
    with pytest.raises(HTTPException) as error:
        await transfer.transfer_file(remote_fs.SshTarget('test', 'user', 22, None), 'download', local, str(remote), True)
    assert error.value.status_code == 409
    assert local.read_bytes() == b'original'
    assert not list(tmp_path.glob('*.part'))


def test_broad_root_symlink_secret_alias_and_sensitive_destinations(tmp_path):
    from remote_file_transfer import safe_local_path
    root = tmp_path / 'work'
    root.mkdir()
    secret = root / '.env.production'
    secret.write_text('secret')
    (root / 'alias').symlink_to(secret)
    for raw, roots in [(str(root / 'output'), ['/tmp']), (str(root / 'alias'), [str(root)]),
                       (str(root / '.hermes' / 'output'), [str(root)])]:
        with pytest.raises(HTTPException):
            safe_local_path(raw, roots)


@pytest.mark.asyncio
@pytest.mark.parametrize('direction', ['upload', 'download'])
async def test_disguised_private_key_is_never_published(tmp_path, monkeypatch, direction):
    import remote_file_transfer as transfer
    import remote_fs
    monkeypatch.setattr(remote_fs, 'ssh_args', lambda target: ['sh', '-c'])
    monkeypatch.setattr(remote_fs, '_CONTROL_DIR', str(tmp_path / 'control'))
    source = tmp_path / 'ordinary-artifact'
    source.write_bytes(b'-----BEGIN OPENSSH PRIVATE KEY-----\nprivate material\n')
    destination = tmp_path / 'destination'
    with pytest.raises(HTTPException) as error:
        await transfer.transfer_file(remote_fs.SshTarget('test', 'user', 22, None), direction,
            source if direction == 'upload' else destination,
            str(destination if direction == 'upload' else source), False)
    assert error.value.status_code == 403
    assert not destination.exists()


def test_run_directory_creation_is_private_and_rejects_symlink_parents(tmp_path):
    from remote_file_transfer import ensure_private_directory
    directory = tmp_path / 'owned' / 'run'
    ensure_private_directory(directory)
    assert directory.is_dir()
    assert directory.stat().st_mode & 0o777 == 0o700
    outside = tmp_path / 'outside'
    outside.mkdir()
    (tmp_path / 'link').symlink_to(outside, target_is_directory=True)
    with pytest.raises((OSError, HTTPException)):
        ensure_private_directory(tmp_path / 'link' / 'run')
    assert not (outside / 'run').exists()
