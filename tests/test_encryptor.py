import pytest

from ncepu_cloud_client.security.encryptor import Encryptor


def test_encryptor_roundtrip(tmp_path):
    source = tmp_path / "secret.txt"
    source.write_text("hello encrypted cloud", encoding="utf-8")
    try:
        encryptor = Encryptor("passphrase")
    except RuntimeError as exc:
        pytest.skip(str(exc))
    encrypted = encryptor.encrypt_file(source)
    assert encrypted.suffix == ".ncepuenc"
    restored = tmp_path / "restored.txt"
    encryptor.decrypt_file(encrypted, restored)
    assert restored.read_text(encoding="utf-8") == "hello encrypted cloud"

