import io
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer_archives import ArchiveError, archive_operation


def test_zip_round_trip_multiple_files_and_empty_directories(tmp_path):
    folder = tmp_path / 'folder'
    (folder / 'empty').mkdir(parents=True)
    (folder / 'olá.txt').write_text('content')
    item = tmp_path / 'single.txt'
    item.write_text('other')
    zipped = tmp_path / 'result.zip'
    result = archive_operation('compress', [str(folder), str(item)], str(zipped))
    assert result['type'] == 'file'
    dest = tmp_path / 'extracted'
    archive_operation('extract', [str(zipped)], str(dest))
    assert (dest / 'folder/olá.txt').read_text() == 'content'
    assert (dest / 'folder/empty').is_dir()
    assert (dest / 'single.txt').read_text() == 'other'


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'safe/../../outside', 'a\\..\\outside'])
def test_rejects_archive_traversal_and_cleans_new_destination(tmp_path, name):
    source = tmp_path / 'bad.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('valid.txt', 'valid')
        archive.writestr(name, 'invalid')
    dest = tmp_path / 'extracted'
    with pytest.raises(ArchiveError):
        archive_operation('extract', [str(source)], str(dest))
    assert not dest.exists()
    assert not (tmp_path / 'outside').exists()


def test_refuses_existing_destination_and_source_symlinks(tmp_path):
    item = tmp_path / 'a'
    item.write_text('original')
    with pytest.raises(ArchiveError, match='already exists'):
        archive_operation('compress', [str(item)], str(item))
    assert item.read_text() == 'original'
    link = tmp_path / 'link'
    link.symlink_to(item)
    dest = tmp_path / 'out.zip'
    with pytest.raises(ArchiveError, match='Links'):
        archive_operation('compress', [str(link)], str(dest))
    assert not dest.exists()


def test_tar_extraction_and_link_refusal(tmp_path):
    source = tmp_path / 'a.tar.gz'
    with tarfile.open(source, 'w:gz') as archive:
        member = tarfile.TarInfo('folder/file')
        member.size = 3
        archive.addfile(member, io.BytesIO(b'abc'))
    dest = tmp_path / 'out'
    archive_operation('extract', [str(source)], str(dest))
    assert (dest / 'folder/file').read_bytes() == b'abc'
    with tarfile.open(source, 'w:gz') as archive:
        member = tarfile.TarInfo('link')
        member.type = tarfile.SYMTYPE
        member.linkname = '/etc/passwd'
        archive.addfile(member)
    with pytest.raises(ArchiveError, match='links'):
        archive_operation('extract', [str(source)], str(tmp_path / 'rejected'))
    assert not (tmp_path / 'rejected').exists()


def test_limits_and_destination_inside_source(tmp_path, monkeypatch):
    import explorer_archives
    folder = tmp_path / 'folder'
    folder.mkdir()
    (folder / 'file').write_text('large')
    with pytest.raises(ArchiveError, match='inside'):
        archive_operation('compress', [str(folder)], str(folder / 'out.zip'))
    monkeypatch.setattr(explorer_archives, 'MAX_BYTES', 2)
    with pytest.raises(ArchiveError, match='limit'):
        archive_operation('compress', [str(folder)], str(tmp_path / 'out.zip'))
    assert not (tmp_path / 'out.zip').exists()
