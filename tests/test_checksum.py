from ncepu_cloud_client.sync.checksum import sha256_file


def test_sha256_is_stable(tmp_path):
    file_path = tmp_path / "data.txt"
    file_path.write_text("ncepu cloud", encoding="utf-8")
    assert sha256_file(file_path) == sha256_file(file_path)
    assert len(sha256_file(file_path)) == 64

