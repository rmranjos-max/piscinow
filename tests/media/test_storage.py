import re

import pytest

from piscinow.media.storage import (
    LocalMediaStorage, MemoryMediaStorage, S3MediaStorage, StorageError, build_media_storage, new_key,
)


class FakeS3Client:
    def __init__(self, fail=False):
        self.objects, self.calls, self.fail = {}, [], fail

    def put_object(self, **kwargs):
        if self.fail:
            raise RuntimeError("network down")
        self.calls.append(("put", kwargs))
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

    def delete_object(self, **kwargs):
        if self.fail:
            raise RuntimeError("network down")
        self.calls.append(("delete", kwargs))
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)


def test_keys_are_random_unguessable_and_carry_no_original_name():
    first, second = new_key("produtos"), new_key("produtos")

    assert first != second
    assert re.fullmatch(r"produtos/[0-9a-f]{32}\.jpg", first)


def test_a_key_prefix_with_strange_characters_is_refused():
    for bad in ("../etc", "a b", "", "produtos/..", "/abs"):
        with pytest.raises(ValueError):
            new_key(bad)


def test_memory_storage_keeps_and_deletes_and_builds_a_url():
    storage = MemoryMediaStorage()
    storage.save("produtos/a.jpg", b"dados", "image/jpeg")

    assert storage.files["produtos/a.jpg"] == b"dados"
    assert storage.url("produtos/a.jpg") == "/midia/produtos/a.jpg"
    storage.delete("produtos/a.jpg")
    storage.delete("produtos/a.jpg")  # deleting twice is harmless
    assert storage.files == {}


def test_local_storage_writes_inside_its_folder_and_reads_back(tmp_path):
    storage = LocalMediaStorage(tmp_path)
    storage.save("produtos/a.jpg", b"dados", "image/jpeg")

    assert (tmp_path / "produtos" / "a.jpg").read_bytes() == b"dados"
    assert storage.path_for("produtos/a.jpg") == tmp_path / "produtos" / "a.jpg"
    storage.delete("produtos/a.jpg")
    assert not (tmp_path / "produtos" / "a.jpg").exists()


@pytest.mark.parametrize("key", ["../fora.jpg", "produtos/../../fora.jpg", "/etc/passwd", "produtos\\..\\fora.jpg", ""])
def test_local_storage_never_leaves_its_folder(tmp_path, key):
    storage = LocalMediaStorage(tmp_path / "midia")

    with pytest.raises(ValueError):
        storage.save(key, b"x", "image/jpeg")
    assert storage.path_for(key) is None


def test_s3_storage_uploads_with_the_content_type_and_a_long_cache(tmp_path):
    client = FakeS3Client()
    storage = S3MediaStorage(client=client, bucket="piscinow-midia", public_base_url="https://midia.exemplo.com/")

    storage.save("produtos/a.jpg", b"dados", "image/jpeg")

    [(action, sent)] = client.calls
    assert action == "put"
    assert (sent["Bucket"], sent["Key"], sent["Body"], sent["ContentType"]) == ("piscinow-midia", "produtos/a.jpg", b"dados", "image/jpeg")
    assert "immutable" in sent["CacheControl"]
    assert storage.url("produtos/a.jpg") == "https://midia.exemplo.com/produtos/a.jpg"


def test_s3_failures_become_a_storage_error_with_a_plain_message():
    storage = S3MediaStorage(client=FakeS3Client(fail=True), bucket="b", public_base_url="https://m.exemplo.com")

    with pytest.raises(StorageError):
        storage.save("produtos/a.jpg", b"dados", "image/jpeg")
    with pytest.raises(StorageError):
        storage.delete("produtos/a.jpg")


def test_the_factory_builds_local_storage_by_default(tmp_path):
    storage = build_media_storage(kind="local", local_dir=str(tmp_path))

    assert isinstance(storage, LocalMediaStorage)


def test_the_factory_refuses_s3_without_its_full_configuration():
    with pytest.raises(ValueError) as raised:
        build_media_storage(kind="s3", s3_bucket="b")

    assert "PISCINOW_S3_" in str(raised.value)


def test_the_factory_refuses_an_unknown_kind():
    with pytest.raises(ValueError):
        build_media_storage(kind="ftp")
