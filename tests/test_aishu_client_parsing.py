import base64

from ncepu_cloud_client.api.aishu_client import AishuCloudClient
from ncepu_cloud_client.api.errors import AuthError, CloudError, NotFoundError, PermissionDeniedError
from ncepu_cloud_client.api.models import CloudItem, CloudItemType, TokenBundle
from ncepu_cloud_client.auth.oauth import build_authorize_url
from ncepu_cloud_client.auth.login_flow import official_entry_url, open_login_pages
from ncepu_cloud_client.config.settings import Settings


def test_authorize_url_includes_extra_oauth_params():
    settings = Settings()
    settings.api.auth_url = "https://pan.ncepu.edu.cn"
    settings.api.client_id = "client-1"
    settings.api.redirect_uri = "http://127.0.0.1:8765/callback"
    settings.api.extra_oauth_params = {"tenant": "ncepu", "prompt": "login"}

    url = build_authorize_url(settings.api, "state-1")

    assert url.startswith("https://pan.ncepu.edu.cn/oauth2/auth?")
    assert "client_id=client-1" in url
    assert "tenant=ncepu" in url
    assert "prompt=login" in url


def test_authorize_url_does_not_force_prompt_none_for_ncepu_pan():
    settings = Settings()
    settings.api.auth_url = "https://pan.ncepu.edu.cn"
    settings.api.client_id = "client-1"
    settings.api.redirect_uri = "http://127.0.0.1:8765/callback"

    url = build_authorize_url(settings.api, "state-1")

    assert "prompt=none" not in url


def test_login_flow_opens_official_entry_before_oauth(monkeypatch):
    settings = Settings()
    settings.api.base_url = "https://pan.ncepu.edu.cn"
    settings.api.auth_url = "https://pan.ncepu.edu.cn"
    settings.api.client_id = "client-1"
    opened = []

    monkeypatch.setattr("ncepu_cloud_client.auth.login_flow.webbrowser.open", opened.append)

    open_login_pages(settings.api, "state-1")

    assert official_entry_url(settings.api) == "https://pan.ncepu.edu.cn"
    assert opened[0] == "https://pan.ncepu.edu.cn"
    assert opened[1].startswith("https://pan.ncepu.edu.cn/oauth2/auth?")


def test_absolute_url_uses_api_prefix():
    settings = Settings()
    settings.api.base_url = "https://cloud.ncepu.edu.cn"
    settings.api.api_prefix = "/api"
    client = AishuCloudClient(settings)
    assert client._absolute("/efast/v1/dir/list") == "https://cloud.ncepu.edu.cn/api/efast/v1/dir/list"


def test_basic_auth_header_url_encodes_client_values():
    header = AishuCloudClient._basic_auth_header("client id", "sec/ret")
    encoded = header.removeprefix("Basic ")
    assert base64.b64decode(encoded).decode("utf-8") == "client%20id:sec%2Fret"


def test_token_request_retries_basic_when_server_rejects_post(monkeypatch):
    settings = Settings()
    settings.api.client_id = "client-1"
    settings.api.client_secret = "secret-1"
    settings.api.oauth_client_auth_method = "body"
    client = AishuCloudClient(settings)
    calls = []

    class FakeResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def fake_raw_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return FakeResponse(
                401,
                "The OAuth 2.0 Client supports client authentication method "
                "'client_secret_basic' but method 'client_secret_post' was requested",
            )
        return FakeResponse(200, "{}")

    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    response = client._token_request({"grant_type": "authorization_code", "code": "code-1"})

    assert response.status_code == 200
    assert calls[0][2]["data"]["client_id"] == "client-1"
    assert calls[0][2]["data"]["client_secret"] == "secret-1"
    assert "Authorization" in calls[1][2]["headers"]
    assert calls[1][2]["data"] == {"grant_type": "authorization_code", "code": "code-1"}


def test_refresh_for_access_token_skips_when_another_thread_refreshed(monkeypatch):
    client = AishuCloudClient(Settings())
    called = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="new-access", refresh_token="new-refresh")

    client.token_store = FakeTokenStore()
    monkeypatch.setattr(client, "_refresh_token_unlocked", lambda: called.append(True))

    client._refresh_for_access_token("old-access")

    assert called == []


def test_request_retries_with_tokenid_query_when_header_auth_fails(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="access-1", refresh_token="refresh-1")

    class FakeResponse:
        status_code = 200
        content = b'{"items":[]}'

        def __init__(self, status_code):
            self.status_code = status_code
            self.text = "{}"

        def json(self):
            return {"items": []}

    def fake_raw_request(method, url, auth, **kwargs):
        calls.append((method, url, auth, kwargs))
        return FakeResponse(401 if len(calls) == 1 else 200)

    client.token_store = FakeTokenStore()
    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    assert client._request("GET", "/efast/v1/entry-doc-lib") == {"items": []}

    assert calls[0][2] is True
    assert calls[1][2] is False
    assert "tokenid=access-1" in calls[1][1]


def test_request_prefers_tokenid_after_successful_tokenid_fallback(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="access-1", refresh_token="refresh-1")

    class FakeResponse:
        content = b'{"items":[]}'
        text = "{}"

        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {"items": []}

    def fake_raw_request(method, url, auth, **kwargs):
        calls.append((method, url, auth))
        if len(calls) == 1:
            return FakeResponse(401)
        return FakeResponse(200)

    client.token_store = FakeTokenStore()
    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    client._request("GET", "/efast/v1/entry-doc-lib")
    client._request("GET", "/efast/v1/quota/user")

    assert calls[0][2] is True
    assert calls[1][2] is False
    assert calls[2][2] is False
    assert "tokenid=access-1" in calls[2][1]


def test_request_uses_cookie_token_type_as_cookie_header(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="sid=1; uid=2", token_type="Cookie")

    class FakeResponse:
        status_code = 200
        content = b'{"items":[]}'
        text = "{}"

        def json(self):
            return {"items": []}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def request(self, method, url, headers=None, **kwargs):
            calls.append(headers)
            return FakeResponse()

        def close(self):
            return None

    client.token_store = FakeTokenStore()
    monkeypatch.setattr("ncepu_cloud_client.api.aishu_client.httpx.Client", FakeHttpClient)

    client._raw_request("GET", "https://pan.ncepu.edu.cn/api/efast/v1/entry-doc-lib", auth=True)

    assert calls[0]["Cookie"] == "sid=1; uid=2"
    assert "Authorization" not in calls[0]


def test_token_from_data_accepts_anyshare_token_aliases():
    bundle = AishuCloudClient._token_from_data(
        {
            "data": {
                "tokenId": "access-1",
                "refreshtoken": "refresh-1",
                "expirses_in": 3600,
                "tokentype": "Bearer",
            }
        }
    )

    assert bundle.access_token == "access-1"
    assert bundle.refresh_token == "refresh-1"
    assert bundle.token_type == "Bearer"
    assert bundle.expires_at is not None


def test_token_from_data_normalizes_bearer_token_type():
    bundle = AishuCloudClient._token_from_data(
        {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "token_type": "bearer",
        }
    )

    assert bundle.token_type == "Bearer"


def test_search_result_item_parsing():
    item = AishuCloudClient._item_from_raw(
        {
            "doc_id": "gns://root/file",
            "basename": "report",
            "extension": ".pdf",
            "parent_path": "gns://root",
            "size": 42,
            "modified_at": 1596438315191542,
        }
    )
    assert item.id == "gns://root/file"
    assert item.name == "report.pdf"
    assert item.type == CloudItemType.FILE


def test_extract_list_supports_search_files_key():
    data = {"files": [{"basename": "a", "extension": ".txt"}]}
    assert AishuCloudClient._extract_list(data) == [{"basename": "a", "extension": ".txt"}]


def test_search_falls_back_to_listing_when_search_api_unavailable(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        raise NotFoundError("search API unavailable")

    def fake_list_dir(remote_path=None, parent_id=None):
        calls.append((remote_path, parent_id))
        if parent_id is None:
            return [
                CloudItem(id="gns://root/course", name="课程资料", type=CloudItemType.DIRECTORY, path="gns://root/course"),
                CloudItem(id="gns://root/readme.txt", name="说明.txt", type=CloudItemType.FILE, path="gns://root/readme.txt"),
            ]
        if parent_id == "gns://root/course":
            return [
                CloudItem(id="gns://root/course/report.docx", name="课程设计报告.docx", type=CloudItemType.FILE, path="gns://root/course/report.docx")
            ]
        return []

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "list_dir", fake_list_dir)

    items = client.search("报告")

    assert [item.name for item in items] == ["课程设计报告.docx"]
    assert calls == [("/", None), ("gns://root/course", "gns://root/course")]


def test_search_fallback_skips_permission_denied_subfolders(monkeypatch):
    client = AishuCloudClient(Settings())

    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: (_ for _ in ()).throw(NotFoundError("no search")))

    def fake_list_dir(remote_path=None, parent_id=None):
        if parent_id is None:
            return [
                CloudItem(id="gns://root/public", name="公共文件夹", type=CloudItemType.DIRECTORY, path="gns://root/public"),
                CloudItem(id="gns://root/report.pdf", name="课程报告.pdf", type=CloudItemType.FILE, path="gns://root/report.pdf"),
            ]
        raise PermissionDeniedError("no permission")

    monkeypatch.setattr(client, "list_dir", fake_list_dir)

    assert [item.name for item in client.search("报告")] == ["课程报告.pdf"]


def test_list_dir_uses_official_post_dir_list(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"items": [{"id": "folder-1", "name": "课程资料", "type": "folder"}]}

    monkeypatch.setattr(client, "_request", fake_request)
    items = client.list_dir(remote_path="/我的文档", parent_id="doc-lib-1")

    assert calls == [
        (
            "POST",
            "/efast/v1/dir/list",
            {"json": {"docid": "doc-lib-1"}},
        )
    ]
    assert items[0].type == CloudItemType.DIRECTORY


def test_folder_item_prefers_anyshare_docid_for_navigation():
    item = AishuCloudClient._item_from_raw(
        {
            "id": "internal-id",
            "docid": "gns://root/课程资料",
            "displayName": "课程资料",
            "isFolder": True,
            "parent_path": "gns://root",
        }
    )

    assert item.id == "gns://root/课程资料"
    assert item.path == "gns://root/课程资料"
    assert item.name == "课程资料"
    assert item.type == CloudItemType.DIRECTORY


def test_list_dir_sends_gns_docid_when_entering_folder(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"items": []}

    monkeypatch.setattr(client, "_request", fake_request)

    client.list_dir(remote_path="gns://root/课程资料", parent_id="gns://root/课程资料")

    payload = calls[0][2]["json"]
    assert payload["docid"] == "gns://root/课程资料"


def test_dir_list_payloads_include_combined_gns_fields():
    payloads = AishuCloudClient._dir_list_payloads("gns://root/课程资料", "gns://root/课程资料")

    assert {"docid": "gns://root/课程资料"} == payloads[0]
    assert {
        "path": "gns://root/课程资料",
        "parentId": "gns://root/课程资料",
        "parent_id": "gns://root/课程资料",
        "id": "gns://root/课程资料",
        "itemId": "gns://root/课程资料",
        "docid": "gns://root/课程资料",
        "docId": "gns://root/课程资料",
    } in payloads


def test_list_dir_tries_next_payload_when_docid_returns_empty(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return {"items": []}
        return {"items": [{"id": "child-1", "name": "子目录", "type": "folder"}]}

    monkeypatch.setattr(client, "_request", fake_request)
    items = client.list_dir(remote_path="gns://root/课程资料", parent_id="gns://root/课程资料")

    assert calls[0] == {"docid": "gns://root/课程资料"}
    assert calls[1] == {"docId": "gns://root/课程资料"}
    assert items[0].name == "子目录"


def test_list_dir_root_shows_entry_doc_libraries(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        return {
            "items": [
                {
                    "docLibId": "lib-1",
                    "libraryName": "个人文档库",
                    "rootItemId": "gns://doc-lib/root",
                    "rootPath": "gns://doc-lib/root",
                }
            ]
        }

    monkeypatch.setattr(client, "_request", fake_request)
    items = client.list_dir("/")

    assert calls == [("GET", "/efast/v1/entry-doc-lib")]
    assert items[0].id == "gns://doc-lib/root"
    assert items[0].name == "个人文档库"
    assert items[0].type == CloudItemType.DIRECTORY
    assert items[0].path == "gns://doc-lib/root"


def test_list_dir_root_parses_official_entry_doc_library_schema(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        return [
            {
                "id": "gns://official/personal",
                "name": "我的文档库",
                "type": "user_doc_lib",
                "rev": "rev-1",
            },
            {
                "id": "gns://official/shared",
                "name": "共享文档库",
                "type": "shared_user_doc_lib",
                "rev": "rev-2",
            },
        ]

    monkeypatch.setattr(client, "_request", fake_request)
    items = client.list_dir("/")

    assert calls == [("GET", "/efast/v1/entry-doc-lib")]
    assert [item.id for item in items] == ["gns://official/personal", "gns://official/shared"]
    assert [item.name for item in items] == ["我的文档库", "共享文档库"]
    assert [item.path for item in items] == ["gns://official/personal", "gns://official/shared"]


def test_list_libraries_combines_nested_personal_and_public_groups(monkeypatch):
    client = AishuCloudClient(Settings())

    def fake_request(method, path, **kwargs):
        return {
            "data": {
                "personalDocLibs": [
                    {
                        "docLibId": "personal-lib",
                        "docLibName": "个人文档库",
                        "rootItemId": "gns://personal/root",
                        "rootPath": "gns://personal/root",
                    }
                ],
                "publicDocLibs": [
                    {
                        "docLibId": "public-lib",
                        "docLibName": "公共文件夹",
                        "docid": "gns://public/root",
                        "path": "gns://public/root",
                    }
                ],
            }
        }

    monkeypatch.setattr(client, "_request", fake_request)

    items = client.list_dir("/")

    assert [item.name for item in items] == ["个人文档库", "公共文件夹"]
    assert [item.id for item in items] == ["gns://personal/root", "gns://public/root"]
    assert [item.path for item in items] == ["gns://personal/root", "gns://public/root"]


def test_resolve_default_root_prefers_personal_library(monkeypatch):
    client = AishuCloudClient(Settings())

    monkeypatch.setattr(
        client,
        "list_dir",
        lambda remote_path=None, parent_id=None: [
            CloudItem(id="gns://public/root", name="共享文档库", type=CloudItemType.DIRECTORY, path="gns://public/root", raw={"type": "shared_user_doc_lib"}),
            CloudItem(id="gns://personal/root", name="我的文档库", type=CloudItemType.DIRECTORY, path="gns://personal/root", raw={"type": "user_doc_lib"}),
        ],
    )

    root = client.resolve_default_root()

    assert root.id == "gns://personal/root"


def test_mkdir_uses_parent_docid_payload(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs["json"]))
        return {"data": {"docid": "gns://root/new-folder", "name": "new-folder", "type": "folder"}}

    monkeypatch.setattr(client, "_request", fake_request)

    item = client.mkdir("gns://root/new-folder")

    assert item.name == "new-folder"
    assert calls[0] == (
        "POST",
        "/efast/v1/dir/create",
        {"docid": "gns://root", "docId": "gns://root", "name": "new-folder"},
    )


def test_mkdir_retries_payload_shape_after_json_error(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            raise CloudError("JSON 格式错误")
        return {"data": {"docid": "gns://root/new-folder", "name": "new-folder", "type": "folder"}}

    monkeypatch.setattr(client, "_request", fake_request)

    item = client.mkdir("gns://root/new-folder")

    assert item.name == "new-folder"
    assert calls[0]["docid"] == "gns://root"
    assert calls[1]["dirname"] == "new-folder"


def test_mkdir_falls_back_to_form_json_payload(monkeypatch):
    client = AishuCloudClient(Settings())
    form_payloads = []

    def fake_request(method, path, **kwargs):
        if "json" in kwargs:
            raise CloudError("JSON 格式错误")
        form_payloads.append(kwargs["data"])
        return {"data": {"docid": "gns://root/new-folder", "dirName": "new-folder", "type": "folder"}}

    monkeypatch.setattr(client, "_request", fake_request)

    item = client.mkdir("gns://root/new-folder")

    assert item.name == "new-folder"
    assert form_payloads[0]["json"].startswith("{")


def test_list_dir_falls_back_to_paged_folder_objects(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if path == "/efast/v1/dir/list":
            raise NotFoundError("dir/list unavailable")
        return {"items": [{"id": "file-1", "name": "report.pdf", "type": "file"}]}

    monkeypatch.setattr(client, "_request", fake_request)
    items = client.list_dir(parent_id="gns://root/folder")

    assert calls[-1] == ("GET", "/efast/v1/folders/gns%3A%2F%2Froot%2Ffolder/sub_objects")
    assert items[0].name == "report.pdf"


def test_download_file_uses_official_osdownload_post(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="access-1", refresh_token="refresh-1")

    client.token_store = FakeTokenStore()

    class FakeStreamResponse:
        headers = {"content-length": "5"}

        def __init__(self):
            self.closed = False

        def iter_bytes(self):
            yield b"abc"
            yield b"de"

        def close(self):
            self.closed = True

    stream_response = FakeStreamResponse()

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"data": {"downloadUrl": "https://download.example/report.pdf"}}

    def fake_raw_request(method, url, auth, stream=False, **kwargs):
        calls.append((method, url, {"auth": auth, "stream": stream, **kwargs}))
        return stream_response

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    target = tmp_path / "report.pdf"
    client.download_file("gns://root/report.pdf", target)

    assert target.read_bytes() == b"abcde"
    assert stream_response.closed is True
    assert calls[0] == (
        "POST",
        "/efast/v1/file/osdownload",
        {
            "json": {
                "docid": "gns://root/report.pdf",
                "docId": "gns://root/report.pdf",
                "tokenid": "access-1",
                "tokenId": "access-1",
                "access_token": "access-1",
                "accessToken": "access-1",
            }
        },
    )
    assert calls[1] == ("GET", "https://download.example/report.pdf", {"auth": True, "stream": True})


def test_download_retries_payload_shape_when_token_body_is_required(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="access-1", refresh_token="refresh-1")

    client.token_store = FakeTokenStore()

    def fake_request(method, path, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            raise AuthError("token body rejected")
        return {"data": {"downloadUrl": "https://download.example/report.pdf"}}

    monkeypatch.setattr(client, "_request", fake_request)

    data = client._request_download("gns://root/report.pdf")

    assert data["data"]["downloadUrl"] == "https://download.example/report.pdf"
    assert calls[0]["docid"] == "gns://root/report.pdf"
    assert calls[0]["tokenid"] == "access-1"
    assert calls[1] == {
        "docid": "gns://root/report.pdf",
        "tokenid": "access-1",
        "tokenId": "access-1",
        "access_token": "access-1",
        "accessToken": "access-1",
    }


def test_download_file_accepts_official_authrequest(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="access-1", refresh_token="refresh-1")

    class FakeStreamResponse:
        headers = {"content-length": "4"}

        def iter_bytes(self):
            yield b"data"

        def close(self):
            return None

    client.token_store = FakeTokenStore()

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {
            "data": {
                "authrequest": [
                    "GET",
                    "https://storage.example/report.pdf",
                    "Authorization: AWS signed",
                ]
            }
        }

    def fake_raw_request(method, url, auth, stream=False, headers=None, **kwargs):
        calls.append((method, url, {"auth": auth, "stream": stream, "headers": headers}))
        return FakeStreamResponse()

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    target = tmp_path / "report.pdf"
    client.download_file("gns://root/report.pdf", target)

    assert target.read_bytes() == b"data"
    assert calls[1] == (
        "GET",
        "https://storage.example/report.pdf",
        {"auth": False, "stream": True, "headers": {"Authorization": "AWS signed"}},
    )


def test_file_operations_include_token_body(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    class FakeTokenStore:
        def load(self):
            return TokenBundle(access_token="access-1", refresh_token="refresh-1")

    client.token_store = FakeTokenStore()

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs["json"]))
        return {"data": {"docid": "gns://root/new.txt", "name": "new.txt", "type": "file"}}

    monkeypatch.setattr(client, "_request", fake_request)

    item = client.rename("gns://root/old.txt", "new.txt")

    assert item.name == "new.txt"
    assert calls[0][1] == "/efast/v1/file/rename"
    assert calls[0][2]["docid"] == "gns://root/old.txt"
    assert calls[0][2]["newName"] == "new.txt"
    assert calls[0][2]["tokenid"] == "access-1"


def test_upload_file_uses_official_authrequest(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    api_calls = []
    raw_calls = []
    source = tmp_path / "report.txt"
    source.write_bytes(b"abc")
    progress = []

    def fake_request(method, path, **kwargs):
        api_calls.append((method, path, kwargs))
        if path == "/efast/v1/file/osbeginupload":
            return {
                "data": {
                    "authrequest": [
                        "PUT",
                        "https://storage.example/upload",
                        "Content-Type: application/octet-stream",
                        "Authorization: AWS fake-signature",
                    ],
                    "docid": "gns://root/report.txt",
                    "rev": "rev-1",
                    "name": "report.txt",
                }
            }
        return {"data": {"docid": "gns://root/report.txt", "name": "report.txt", "length": 3}}

    def fake_raw_request(method, url, auth, **kwargs):
        raw_calls.append((method, url, auth, kwargs))

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    item = client.upload_file(source, "gns://root", progress_cb=lambda done, total: progress.append((done, total)))

    begin_payload = api_calls[0][2]["json"]
    finish_payload = api_calls[1][2]["json"]
    assert begin_payload["docid"] == "gns://root"
    assert begin_payload["length"] == 3
    assert finish_payload["docid"] == "gns://root/report.txt"
    assert finish_payload["rev"] == "rev-1"
    assert raw_calls == [
        (
            "PUT",
            "https://storage.example/upload",
            False,
            {
                "headers": {
                    "Content-Type": "application/octet-stream",
                    "Authorization": "AWS fake-signature",
                },
                "content": b"abc",
            },
        )
    ]
    assert progress == [(3, 3)]
    assert item.id == "gns://root/report.txt"
    assert item.type == CloudItemType.FILE


def test_upload_resolves_mock_root_to_first_real_library(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    source = tmp_path / "report.txt"
    source.write_bytes(b"abc")
    api_calls = []

    monkeypatch.setattr(
        client,
        "list_dir",
        lambda remote_path=None, parent_id=None: [
            CloudItem(id="gns://doc-lib/root", name="个人文档库", type=CloudItemType.DIRECTORY, path="gns://doc-lib/root")
        ],
    )

    def fake_request(method, path, **kwargs):
        api_calls.append((method, path, kwargs))
        if path == "/efast/v1/file/osbeginupload":
            return {
                "data": {
                    "authrequest": ["PUT", "https://storage.example/upload"],
                    "docid": "gns://doc-lib/root/report.txt",
                    "name": "report.txt",
                }
            }
        return {"data": {"docid": "gns://doc-lib/root/report.txt", "name": "report.txt", "length": 3}}

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", lambda *args, **kwargs: None)

    client.upload_file(source, "root")

    assert api_calls[0][2]["json"]["docid"] == "gns://doc-lib/root"


def test_upload_root_prefers_personal_library(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    source = tmp_path / "report.txt"
    source.write_bytes(b"abc")
    begin_docids = []

    monkeypatch.setattr(
        client,
        "list_dir",
        lambda remote_path=None, parent_id=None: [
            CloudItem(id="gns://public/root", name="共享文档库", type=CloudItemType.DIRECTORY, path="gns://public/root", raw={"type": "shared_user_doc_lib"}),
            CloudItem(id="gns://personal/root", name="我的文档库", type=CloudItemType.DIRECTORY, path="gns://personal/root", raw={"type": "user_doc_lib"}),
        ],
    )

    def fake_request(method, path, **kwargs):
        if path == "/efast/v1/file/osbeginupload":
            docid = kwargs["json"]["docid"]
            begin_docids.append(docid)
            if docid == "gns://public/root":
                raise PermissionDeniedError("CheckPerm Failed")
            return {
                "data": {
                    "authrequest": ["PUT", "https://storage.example/upload"],
                    "docid": "gns://personal/root/report.txt",
                    "name": "report.txt",
                }
            }
        return {"data": {"docid": "gns://personal/root/report.txt", "name": "report.txt", "length": 3}}

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", lambda *args, **kwargs: None)

    item = client.upload_file(source, "root")

    assert begin_docids == ["gns://personal/root"]
    assert item.id == "gns://personal/root/report.txt"


def test_upload_root_retries_next_candidate_when_first_is_readonly(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    source = tmp_path / "report.txt"
    source.write_bytes(b"abc")
    begin_docids = []

    monkeypatch.setattr(
        client,
        "_candidate_root_items",
        lambda: [
            CloudItem(id="gns://public/root", name="共享文档库", type=CloudItemType.DIRECTORY, path="gns://public/root", raw={"type": "shared_user_doc_lib"}),
            CloudItem(id="gns://personal/root", name="我的文档库", type=CloudItemType.DIRECTORY, path="gns://personal/root", raw={"type": "user_doc_lib"}),
        ],
    )

    def fake_request(method, path, **kwargs):
        if path == "/efast/v1/file/osbeginupload":
            docid = kwargs["json"]["docid"]
            begin_docids.append(docid)
            if docid == "gns://public/root":
                raise PermissionDeniedError("CheckPerm Failed")
            return {
                "data": {
                    "authrequest": ["PUT", "https://storage.example/upload"],
                    "docid": "gns://personal/root/report.txt",
                    "name": "report.txt",
                }
            }
        return {"data": {"docid": "gns://personal/root/report.txt", "name": "report.txt", "length": 3}}

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", lambda *args, **kwargs: None)

    item = client.upload_file(source, "root")

    assert begin_docids == ["gns://public/root", "gns://personal/root"]
    assert item.id == "gns://personal/root/report.txt"


def test_upload_file_uses_multipart_protocol(monkeypatch, tmp_path):
    client = AishuCloudClient(Settings())
    monkeypatch.setattr(client, "MULTIPART_UPLOAD_THRESHOLD", 4)
    monkeypatch.setattr(client, "MULTIPART_CHUNK_SIZE", 3)
    source = tmp_path / "big.bin"
    source.write_bytes(b"abcdefg")
    api_calls = []
    raw_calls = []
    progress = []

    def fake_request(method, path, **kwargs):
        api_calls.append((method, path, kwargs))
        if path == "/efast/v1/file/osinitmultiupload":
            return {"data": {"uploadid": "upload-1", "docid": "gns://root/big.bin"}}
        if path == "/efast/v1/file/osuploadpart":
            part_number = kwargs["json"]["partnum"]
            return {
                "data": {
                    "authrequest": ["PUT", f"https://storage.example/part-{part_number}"],
                    "etag": f"etag-{part_number}",
                }
            }
        return {"data": {"docid": "gns://root/big.bin", "name": "big.bin", "length": 7}}

    def fake_raw_request(method, url, auth, **kwargs):
        raw_calls.append((method, url, auth, kwargs["content"]))

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_raw_request", fake_raw_request)

    item = client.upload_file(source, "gns://root", progress_cb=lambda done, total: progress.append((done, total)))

    assert [call[1] for call in api_calls] == [
        "/efast/v1/file/osinitmultiupload",
        "/efast/v1/file/osuploadpart",
        "/efast/v1/file/osuploadpart",
        "/efast/v1/file/osuploadpart",
        "/efast/v1/file/oscompleteupload",
    ]
    assert [call[3] for call in raw_calls] == [b"abc", b"def", b"g"]
    assert progress == [(3, 7), (6, 7), (7, 7)]
    complete_payload = api_calls[-1][2]["json"]
    assert complete_payload["uploadid"] == "upload-1"
    assert complete_payload["parts"][0]["etag"] == "etag-1"
    assert item.id == "gns://root/big.bin"


def test_get_item_by_path_uses_official_post_getinfo(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"data": {"id": "file-1", "name": "实验.docx", "type": "file"}}

    monkeypatch.setattr(client, "_request", fake_request)
    item = client.get_item_by_path("/我的文档/实验.docx")

    assert item is not None
    assert item.name == "实验.docx"
    assert calls == [("POST", "/efast/v1/file/getinfobypath", {"json": {"path": "/我的文档/实验.docx"}})]


def test_get_item_fields_quotes_id_and_falls_back_to_v2(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if len(calls) == 1:
            raise NotFoundError("v1 item fields unavailable")
        return {"data": {"name": "实验.docx", "size": 100}}

    monkeypatch.setattr(client, "_request", fake_request)
    fields = client.get_item_fields("gns://root/实验.docx", ["name", "size"])

    assert fields == {"name": "实验.docx", "size": 100}
    assert calls == [
        ("GET", "/efast/v1/items/gns%3A%2F%2Froot%2F%E5%AE%9E%E9%AA%8C.docx/name,size"),
        ("GET", "/efast/v2/items/gns%3A%2F%2Froot%2F%E5%AE%9E%E9%AA%8C.docx/name,size"),
    ]


def test_list_libraries_falls_back_to_doc_lib_management(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if path == "/efast/v1/doc-lib/user":
            return {"items": [{"docLibId": "lib-1", "libraryName": "个人文档库"}]}
        return {"items": []}

    monkeypatch.setattr(client, "_request", fake_request)
    libraries = client.list_libraries()

    assert libraries[0].id == "lib-1"
    assert calls[:3] == [
        ("GET", "/efast/v1/entry-doc-lib"),
        ("GET", "/efast/v1/owned-doc-lib"),
        ("GET", "/efast/v1/doc-lib/user"),
    ]


def test_list_libraries_ignores_unauthorized_doc_lib_management_fallback(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if path in {"/efast/v1/entry-doc-lib", "/efast/v1/owned-doc-lib"}:
            return {"items": []}
        raise AuthError("management API rejected the user token")

    monkeypatch.setattr(client, "_request", fake_request)

    assert client.list_libraries() == []
    assert calls == [
        ("GET", "/efast/v1/entry-doc-lib"),
        ("GET", "/efast/v1/owned-doc-lib"),
        ("GET", "/efast/v1/doc-lib/user"),
        ("GET", "/efast/v1/doc-lib/department"),
        ("GET", "/efast/v1/doc-lib/custom"),
        ("GET", "/efast/v1/doc-lib/knowledge"),
    ]


def test_doc_lib_quota_uses_official_path_and_nested_quota(monkeypatch):
    client = AishuCloudClient(Settings())
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        return {"quota": {"allocated": 580000000, "used": 240000000}}

    monkeypatch.setattr(client, "_request", fake_request)
    quota = client.get_doc_lib_quota("gns://doc-lib/1")

    assert quota.total == 580000000
    assert quota.used == 240000000
    assert calls == [("GET", "/efast/v1/quota/doc-lib/gns%3A%2F%2Fdoc-lib%2F1")]
