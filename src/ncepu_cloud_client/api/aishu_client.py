from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from ncepu_cloud_client.api.base import CloudDriveClient, ProgressCallback
from ncepu_cloud_client.api.errors import (
    AuthError,
    CloudError,
    ConfigError,
    ConflictError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TokenExpiredError,
)
from ncepu_cloud_client.api.models import CloudItem, CloudItemType, CloudLibrary, CloudQuota, TokenBundle
from ncepu_cloud_client.auth.login_flow import wait_for_oauth_code
from ncepu_cloud_client.auth.token_store import TokenStore
from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.utils.logger import get_logger, mask_sensitive, redact_url

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

logger = get_logger("api.aishu")


class AishuCloudClient(CloudDriveClient):
    """可配置的华电云盘/爱数真实 RESTful API 适配器。

    这一层是项目对真实云盘的“防腐层”：UI 和同步模块只依赖 CloudDriveClient 抽象，
    不直接关心爱数接口的字段名差异、认证方式差异和错误响应格式。
    """

    MULTIPART_UPLOAD_THRESHOLD = 32 * 1024 * 1024
    MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024

    def __init__(self, settings: Settings, token_store: TokenStore | None = None):
        self.settings = settings
        self.token_store = token_store or TokenStore(settings.security)
        self._refresh_lock = threading.RLock()
        self._preferred_api_auth = "bearer"

    def login(self) -> None:
        self._ensure_httpx()
        if not self.settings.api.client_id or not self.settings.api.client_secret:
            raise ConfigError("缺少 client_id/client_secret，请在设置页或 config.toml 中配置。")
        code = wait_for_oauth_code(self.settings.api, timeout_seconds=self.settings.api.timeout_seconds * 6)
        self.exchange_code(code)

    def exchange_code(self, code: str) -> TokenBundle:
        api = self.settings.api
        if not api.client_id or not api.client_secret:
            raise ConfigError("缺少 client_id/client_secret，无法换取 token。")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": api.redirect_uri,
        }
        response = self._token_request(data)
        bundle = self._token_from_response(response)
        self.token_store.save(bundle)
        return bundle

    def register_oauth_client(self, client_name: str = "NCEPU Cloud Client") -> dict[str, Any]:
        api = self.settings.api
        payload = {
            "client_name": client_name,
            "grant_types": ["authorization_code", "implicit", "refresh_token"],
            "response_types": ["token id_token", "code", "token"],
            "scope": api.oauth_scope,
            "redirect_uris": [api.redirect_uri],
            "post_logout_redirect_uris": [api.redirect_uri],
            "metadata": {
                "device": {
                    "name": client_name,
                    "client_type": "windows",
                    "description": "NCEPU Cloud Client desktop app",
                }
            },
        }
        response = self._raw_request("POST", f"{api.auth_url.rstrip('/')}/oauth2/clients", json=payload, auth=False)
        return response.json()

    def logout(self) -> None:
        bundle = self.token_store.load()
        if bundle and bundle.access_token:
            try:
                self._raw_request(
                    "POST",
                    f"{self.settings.api.auth_url.rstrip('/')}/oauth2/revoke",
                    data={"token": bundle.access_token},
                    auth=False,
                    headers={"Authorization": self._basic_auth_header(self.settings.api.client_id, self.settings.api.client_secret)}
                    if self.settings.api.client_id and self.settings.api.client_secret
                    else {},
                )
            except CloudError:
                pass
        self.token_store.clear()

    def refresh_token(self) -> None:
        with self._refresh_lock:
            self._refresh_token_unlocked()

    def _refresh_token_unlocked(self) -> None:
        api = self.settings.api
        bundle = self.token_store.load()
        if not bundle or not bundle.refresh_token:
            raise TokenExpiredError("没有 refresh_token，请重新登录。")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": bundle.refresh_token,
        }
        response = self._token_request(data)
        self.token_store.save(self._token_from_response(response))

    def login_sso(self, credential_params: dict[str, Any]) -> TokenBundle:
        api = self.settings.api
        if not api.client_id or not api.sso_credential_id:
            raise ConfigError("缺少 client_id 或 sso_credential_id，无法执行 SSO 登录。")
        payload = {
            "client_id": api.client_id,
            "redirect_uri": api.redirect_uri,
            "response_type": "code",
            "scope": api.oauth_scope,
            "udids": [],
            "credential": {"id": api.sso_credential_id, "params": credential_params},
        }
        response = self._raw_request("POST", f"{api.auth_url.rstrip('/')}/authentication/v1/sso", json=payload, auth=False)
        data = response.json()
        if data.get("access_token") or data.get("accessToken"):
            bundle = self._token_from_data(data)
            self.token_store.save(bundle)
            return bundle
        code = data.get("code")
        if not code:
            raise AuthError("SSO 登录未返回 code 或 access_token。")
        return self.exchange_code(code)

    def list_libraries(self) -> list[CloudLibrary]:
        # 不同版本的 AnyShare/爱数部署暴露的文档库入口不完全一致。
        # 因此先走主入口，再走 owned-doc-lib，最后走几个分类文档库兜底接口。
        try:
            data = self._request("GET", "/efast/v1/entry-doc-lib")
        except NotFoundError:
            data = {}
        items = self._extract_libraries(data)
        if not items:
            try:
                owned = self._request("GET", "/efast/v1/owned-doc-lib")
            except NotFoundError:
                owned = {}
            items = self._extract_libraries(owned)
        if not items:
            items = self._list_doc_lib_fallbacks()
        return [self._library_from_raw(item) for item in items]

    def resolve_default_root(self) -> CloudItem:
        for item in self._candidate_root_items():
            return item
        raise NotFoundError("未能获取可访问的文档库根目录，请确认账号有云盘权限并重新登录。")

    def get_quota(self) -> CloudQuota:
        data = self._request("GET", "/efast/v1/quota/user")
        return self._quota_from_data(data)

    def get_doc_lib_quota(self, doc_lib_id: str) -> CloudQuota:
        data = self._request("GET", f"/efast/v1/quota/doc-lib/{quote(doc_lib_id, safe='')}")
        return self._quota_from_data(data)

    @staticmethod
    def _quota_from_data(data: Any) -> CloudQuota:
        raw = AishuCloudClient._extract_object(data)
        quota = raw.get("quota") if isinstance(raw.get("quota"), dict) else {}
        total = AishuCloudClient._first_int(raw, "total", "totalSize", "capacity", "space", "allocated") or AishuCloudClient._first_int(quota, "allocated", "total")
        used = AishuCloudClient._first_int(raw, "used", "usedSize", "usage", "usedSpace")
        if not used:
            used = AishuCloudClient._first_int(quota, "used")
        return CloudQuota(total=total, used=used, raw=raw)

    def list_dir(self, remote_path: str | None = None, parent_id: str | None = None) -> list[CloudItem]:
        if not parent_id and remote_path in (None, "", "/"):
            # 根目录在 UI 中展示为“可访问的文档库列表”，
            # 不是某一个真实文件夹，这样能同时看到个人、共享、部门等入口。
            libraries = self.list_libraries()
            if libraries:
                return [self._library_to_item(library) for library in libraries]
        payloads = self._dir_list_payloads(remote_path, parent_id)
        first_empty: list[CloudItem] | None = None
        last_error: CloudError | None = None
        for payload in payloads:
            try:
                # dir/list 对 docid、docId、parentId、path 等参数的支持在不同部署上有差异。
                # 这里按多个 payload 重试，是为了让同一套客户端适配更多学校网盘版本。
                data = self._request("POST", "/efast/v1/dir/list", json=payload)
                items = [self._item_from_raw(item) for item in self._extract_list(data)]
                if items:
                    return items
                if first_empty is None:
                    first_empty = items
            except CloudError as exc:
                if isinstance(exc, (AuthError, PermissionDeniedError, TokenExpiredError, NetworkError, RateLimitError, ServerError)):
                    raise
                last_error = exc
        try:
            if first_empty is not None:
                return first_empty
            if not parent_id:
                if last_error:
                    raise last_error
                raise NotFoundError("目录不存在或目录浏览协议不可用。")
            # 部分旧接口不支持 /dir/list，但支持 folders/{id}/sub_objects。
            # 作为最后兜底可以提高公共文档库和特殊目录的可访问性。
            data = self._request("GET", f"/efast/v1/folders/{quote(parent_id, safe='')}/sub_objects")
            return [self._item_from_raw(item) for item in self._extract_list(data)]
        except NotFoundError:
            if last_error:
                raise last_error
            raise

    @staticmethod
    def _dir_list_payloads(remote_path: str | None, parent_id: str | None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []

        def add(payload: dict[str, Any]) -> None:
            if payload and payload not in payloads:
                payloads.append(payload)

        if parent_id:
            # 同一个远端目录 id 在不同 API 文档或实际响应中可能叫 docid/docId/id/itemId。
            # 都尝试一遍，比在 UI 层猜字段更可靠。
            add({"docid": parent_id})
            add({"docId": parent_id})
            add({"id": parent_id})
            add({"itemId": parent_id})
            add({"parentId": parent_id})
        if remote_path:
            add({"path": remote_path})
            if remote_path.startswith("gns://"):
                # gns:// 是 AnyShare 常见的全局命名空间标识，
                # 某些接口把它当路径，某些接口把它当 docid。
                add({"docid": remote_path})
                add({"docId": remote_path})
        combined: dict[str, Any] = {}
        if remote_path:
            combined["path"] = remote_path
            if remote_path.startswith("gns://"):
                combined["docid"] = remote_path
                combined["docId"] = remote_path
        if parent_id:
            combined["parentId"] = parent_id
            combined["parent_id"] = parent_id
            combined["id"] = parent_id
            combined["itemId"] = parent_id
            combined["docid"] = parent_id
            combined["docId"] = parent_id
        add(combined)
        if not payloads:
            payloads.append({})
        return payloads

    def mkdir(self, remote_path: str) -> CloudItem:
        last_error: CloudError | None = None
        payloads = self._mkdir_payloads(remote_path)
        if payloads and payloads[0].get("docid") == "root":
            payloads = self._mkdir_payloads(remote_path, self._resolve_upload_dir_id("root"))
        request_kwargs = [{"json": payload} for payload in payloads]
        request_kwargs.extend({"data": {"json": json.dumps(payload, ensure_ascii=False)}} for payload in payloads)
        request_kwargs.extend({"data": payload} for payload in payloads)
        for kwargs in request_kwargs:
            try:
                data = self._request("POST", "/efast/v1/dir/create", **kwargs)
                raw = self._extract_object(data)
                if not raw and "json" in kwargs:
                    raw = kwargs["json"]
                return self._item_from_raw(raw)
            except CloudError as exc:
                if isinstance(exc, (AuthError, PermissionDeniedError, TokenExpiredError, NetworkError, RateLimitError, ServerError)):
                    raise
                last_error = exc
        if last_error:
            raise last_error
        raise CloudError("创建文件夹失败：无法生成有效请求参数。")

    @staticmethod
    def _mkdir_payloads(remote_path: str, default_parent_id: str = "root") -> list[dict[str, Any]]:
        path_text = remote_path.strip().rstrip("/")
        name = Path(path_text).name
        parent = str(Path(path_text).parent).replace("\\", "/")
        if path_text.startswith("gns://"):
            marker = path_text.rfind("/")
            if marker > len("gns://") - 1:
                parent = path_text[:marker]
                name = path_text[marker + 1 :]
        if parent in ("", ".", "/"):
            parent = default_parent_id
        payloads: list[dict[str, Any]] = []

        def add(payload: dict[str, Any]) -> None:
            clean = {key: value for key, value in payload.items() if value not in (None, "")}
            if clean and clean not in payloads:
                payloads.append(clean)

        # 爱数 dir/create 的不同部署对父目录字段名不完全一致。
        # 优先使用 docid/parentDocid 这种真实目录标识，最后才退回 path。
        add({"docid": parent, "docId": parent, "name": name})
        add({"docid": parent, "docId": parent, "dirname": name, "dirName": name})
        add({"parentDocid": parent, "parentDocId": parent, "name": name})
        add({"parentId": parent, "parent_id": parent, "name": name})
        add({"id": parent, "itemId": parent, "name": name})
        add({"path": path_text, "name": name})
        return payloads

    def delete(self, item_id: str) -> None:
        try:
            self._request_file_operation("POST", "/efast/v1/file/delete", item_id)
        except NotFoundError:
            self._request_file_operation("POST", "/efast/v1/dir/delete", item_id)

    def rename(self, item_id: str, new_name: str) -> CloudItem:
        extra = {"name": new_name, "newName": new_name, "new_name": new_name}
        try:
            data = self._request_file_operation("POST", "/efast/v1/file/rename", item_id, extra)
        except NotFoundError:
            data = self._request_file_operation("POST", "/efast/v1/dir/rename", item_id, extra)
        return self._item_from_raw(self._extract_object(data))

    def move(self, item_id: str, target_dir_id: str) -> CloudItem:
        extra = {"targetDirId": target_dir_id, "target_dir_id": target_dir_id, "targetDocid": target_dir_id, "targetDocId": target_dir_id}
        try:
            data = self._request_file_operation("POST", "/efast/v1/file/move", item_id, extra)
        except NotFoundError:
            data = self._request_file_operation("POST", "/efast/v1/dir/move", item_id, extra)
        return self._item_from_raw(self._extract_object(data))

    def copy(self, item_id: str, target_dir_id: str) -> CloudItem:
        extra = {"targetDirId": target_dir_id, "target_dir_id": target_dir_id, "targetDocid": target_dir_id, "targetDocId": target_dir_id}
        try:
            data = self._request_file_operation("POST", "/efast/v1/file/copy", item_id, extra)
        except NotFoundError:
            data = self._request_file_operation("POST", "/efast/v1/dir/copy", item_id, extra)
        return self._item_from_raw(self._extract_object(data))

    def _request_file_operation(self, method: str, path: str, item_id: str, extra: dict[str, Any] | None = None) -> Any:
        last_error: CloudError | None = None
        for _ in range(2):
            access_token = self._current_access_token()
            for payload in self._file_operation_payloads(item_id, extra, access_token):
                try:
                    return self._request(method, path, json=payload)
                except AuthError as exc:
                    last_error = exc
                except NotFoundError:
                    raise
                except CloudError as exc:
                    if isinstance(exc, (PermissionDeniedError, NetworkError, RateLimitError, ServerError)):
                        raise
                    last_error = exc
            try:
                self._refresh_for_access_token(access_token)
            except AuthError as exc:
                last_error = exc
                break
        if last_error:
            raise last_error
        raise AuthError(f"{path} 授权失败，请重新登录。")

    @staticmethod
    def _file_operation_payloads(item_id: str, extra: dict[str, Any] | None, access_token: str | None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        extra_payload = extra or {}

        def add(base: dict[str, Any]) -> None:
            payload = {**base, **extra_payload}
            if access_token:
                payload.update(AishuCloudClient._token_payload(access_token))
            if payload not in payloads:
                payloads.append(payload)

        add({"docid": item_id, "docId": item_id})
        add({"docid": item_id})
        add({"docId": item_id})
        add({"id": item_id, "itemId": item_id, "docid": item_id, "docId": item_id})
        add({"id": item_id, "itemId": item_id})
        add({"path": item_id})
        return payloads

    def upload_file(self, local_path: Path, remote_dir_id: str, remote_name: str | None = None, progress_cb: ProgressCallback | None = None) -> CloudItem:
        last_permission_error: PermissionDeniedError | None = None
        for resolved_dir_id in self._resolve_upload_dir_candidates(remote_dir_id):
            try:
                return self._upload_file_to_dir(local_path, resolved_dir_id, remote_name, progress_cb)
            except PermissionDeniedError as exc:
                if remote_dir_id not in ("", "/", "root"):
                    raise
                last_permission_error = exc
                logger.warning("upload root candidate is not writable, trying next one: %s", exc)
        if last_permission_error:
            raise PermissionDeniedError(f"{last_permission_error}\n\n当前账号没有向默认文档库上传的权限，请在同步任务中填写“我的文档库”下可写目录的 gns:// ID。")
        raise NotFoundError("未找到可用于上传的远端文档库。")

    def _upload_file_to_dir(self, local_path: Path, remote_dir_id: str, remote_name: str | None = None, progress_cb: ProgressCallback | None = None) -> CloudItem:
        total = local_path.stat().st_size
        name = remote_name or local_path.name
        if total >= self.MULTIPART_UPLOAD_THRESHOLD:
            try:
                return self._upload_file_multipart(local_path, remote_dir_id, name, total, progress_cb)
            except NotFoundError:
                logger.warning("multipart upload API unavailable, falling back to normal upload")
        begin = self._request("POST", "/efast/v1/file/osbeginupload", json=self._upload_begin_payload(remote_dir_id, name, total))
        begin_obj = self._extract_object(begin)
        upload_url = self._first_str(begin_obj, "uploadUrl", "upload_url", "url")
        auth_request = begin_obj.get("authrequest") or begin_obj.get("authRequest")
        if upload_url or auth_request:
            content = local_path.read_bytes()
            self._upload_to_storage(auth_request, upload_url, content, auth=not auth_request)
            if progress_cb:
                progress_cb(total, total)
            data = self._request("POST", "/efast/v1/file/osendupload", json=self._upload_finish_payload(begin_obj, remote_dir_id, name, total))
            return self._item_from_raw(self._extract_object(data) or begin_obj)
        with local_path.open("rb") as fh:
            files = {"file": (name, fh)}
            data = self._request("POST", "/efast/v1/file/osendupload", data=self._upload_begin_payload(remote_dir_id, name, total), files=files)
        if progress_cb:
            progress_cb(total, total)
        return self._item_from_raw(self._extract_object(data))

    def _resolve_upload_dir_id(self, remote_dir_id: str) -> str:
        return self._resolve_upload_dir_candidates(remote_dir_id)[0]

    def _resolve_upload_dir_candidates(self, remote_dir_id: str) -> list[str]:
        if remote_dir_id not in ("", "/", "root"):
            return [remote_dir_id]
        candidates: list[str] = []
        for item in self._candidate_root_items():
            if item.id and item.id not in candidates:
                candidates.append(item.id)
        return candidates or [self.resolve_default_root().id]

    def _candidate_root_items(self) -> list[CloudItem]:
        items = [item for item in self.list_dir("/") if item.is_dir and item.id]
        return sorted(items, key=self._writable_root_score, reverse=True)

    @staticmethod
    def _writable_root_score(item: CloudItem) -> int:
        raw = item.raw or {}
        text = " ".join(
            str(value).lower()
            for value in (
                item.name,
                item.id,
                item.path,
                raw.get("type"),
                raw.get("docLibType"),
                raw.get("libraryType"),
                raw.get("name"),
                raw.get("libraryName"),
                raw.get("docLibName"),
            )
            if value
        )
        score = 0
        if "user_doc_lib" in text or "personal" in text or "private" in text:
            score += 100
        if any(word in text for word in ("我的文档库", "个人文档库", "我的", "个人")):
            score += 80
        if any(word in text for word in ("shared", "public", "department", "knowledge", "共享", "公共", "部门", "学校", "资源库")):
            score -= 80
        return score

    def _upload_file_multipart(
        self,
        local_path: Path,
        remote_dir_id: str,
        name: str,
        total: int,
        progress_cb: ProgressCallback | None = None,
    ) -> CloudItem:
        chunk_size = min(self.MULTIPART_CHUNK_SIZE, total or self.MULTIPART_CHUNK_SIZE)
        init_payload = {**self._upload_begin_payload(remote_dir_id, name, total), "partSize": chunk_size, "partsize": chunk_size}
        init = self._request("POST", "/efast/v1/file/osinitmultiupload", json=init_payload)
        init_obj = self._extract_object(init)
        upload_id = self._first_str(init_obj, "uploadId", "uploadid", "multiUploadId", "multiuploadid", "id")
        if not upload_id:
            raise CloudError("大文件上传初始化未返回 uploadId。")
        docid = self._first_str(init_obj, "docid", "docId", "id") or remote_dir_id
        part_records: list[dict[str, Any]] = []
        sent = 0
        part_number = 1
        with local_path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                part_payload = {
                    "docid": docid,
                    "docId": docid,
                    "uploadid": upload_id,
                    "uploadId": upload_id,
                    "partnum": part_number,
                    "partNumber": part_number,
                    "partsize": len(chunk),
                    "partSize": len(chunk),
                    "offset": sent,
                    "length": len(chunk),
                    "size": len(chunk),
                }
                part = self._request("POST", "/efast/v1/file/osuploadpart", json=part_payload)
                part_obj = self._extract_object(part)
                upload_url = self._first_str(part_obj, "uploadUrl", "upload_url", "url")
                auth_request = part_obj.get("authrequest") or part_obj.get("authRequest")
                if upload_url or auth_request:
                    self._upload_to_storage(auth_request, upload_url, chunk, auth=not auth_request)
                else:
                    raise CloudError("大文件分片上传协议未返回对象存储 URL。")
                sent += len(chunk)
                if progress_cb:
                    progress_cb(sent, total)
                part_records.append(self._part_record(part_number, part_obj))
                part_number += 1
        complete_payload = {
            "docid": docid,
            "docId": docid,
            "uploadid": upload_id,
            "uploadId": upload_id,
            "name": name,
            "length": total,
            "size": total,
            "parts": part_records,
        }
        data = self._request("POST", "/efast/v1/file/oscompleteupload", json=complete_payload)
        return self._item_from_raw(self._extract_object(data) or init_obj)

    @staticmethod
    def _upload_begin_payload(remote_dir_id: str, name: str, total: int) -> dict[str, Any]:
        return {
            "docid": remote_dir_id,
            "docId": remote_dir_id,
            "dirId": remote_dir_id,
            "parentId": remote_dir_id,
            "length": total,
            "size": total,
            "name": name,
            "reqmethod": "PUT",
            "ondup": 2,
        }

    @staticmethod
    def _upload_finish_payload(begin_obj: dict[str, Any], remote_dir_id: str, name: str, total: int) -> dict[str, Any]:
        upload_id = AishuCloudClient._first_str(begin_obj, "uploadId", "uploadid", "id")
        docid = AishuCloudClient._first_str(begin_obj, "docid", "docId") or remote_dir_id
        payload = AishuCloudClient._upload_begin_payload(remote_dir_id, name, total)
        payload.update({"docid": docid, "docId": docid})
        if upload_id:
            payload["uploadId"] = upload_id
            payload["uploadid"] = upload_id
        rev = AishuCloudClient._first_str(begin_obj, "rev", "revision")
        if rev:
            payload["rev"] = rev
        return payload

    @staticmethod
    def _part_record(part_number: int, part_obj: dict[str, Any]) -> dict[str, Any]:
        record = {"partnum": part_number, "partNumber": part_number}
        etag = AishuCloudClient._first_str(part_obj, "etag", "ETag", "eTag")
        if etag:
            record["etag"] = etag
            record["ETag"] = etag
        return record

    def _upload_to_storage(self, auth_request: Any, upload_url: str | None, content: bytes, auth: bool) -> None:
        method, url, headers = self._parse_auth_request(auth_request)
        target_url = url or upload_url
        if not target_url:
            raise CloudError("上传协议未返回对象存储 URL。")
        self._raw_request(method or "PUT", target_url, auth=auth, headers=headers, content=content)

    @staticmethod
    def _parse_auth_request(auth_request: Any) -> tuple[str, str | None, dict[str, str]]:
        method = "PUT"
        url: str | None = None
        headers: dict[str, str] = {}
        if isinstance(auth_request, (list, tuple)):
            if len(auth_request) >= 1 and auth_request[0]:
                method = str(auth_request[0]).upper()
            if len(auth_request) >= 2 and auth_request[1]:
                url = str(auth_request[1])
            headers.update(AishuCloudClient._headers_from_auth_request(auth_request[2:]))
        elif isinstance(auth_request, dict):
            method = str(auth_request.get("method") or auth_request.get("reqmethod") or method).upper()
            url_value = auth_request.get("url") or auth_request.get("uploadUrl") or auth_request.get("upload_url")
            url = str(url_value) if url_value else None
            headers.update(AishuCloudClient._headers_from_auth_request(auth_request.get("headers") or auth_request.get("header") or {}))
        return method, url, headers

    @staticmethod
    def _headers_from_auth_request(raw_headers: Any) -> dict[str, str]:
        headers: dict[str, str] = {}
        if isinstance(raw_headers, dict):
            return {str(key): str(value) for key, value in raw_headers.items()}
        if isinstance(raw_headers, (list, tuple)):
            for item in raw_headers:
                if isinstance(item, dict):
                    headers.update({str(key): str(value) for key, value in item.items()})
                elif isinstance(item, str) and ":" in item:
                    key, value = item.split(":", 1)
                    headers[key.strip()] = value.strip()
        return headers

    def download_file(self, item_id: str, local_path: Path, progress_cb: ProgressCallback | None = None) -> Path:
        data = self._request_download(item_id)
        obj = self._extract_object(data)
        # 下载通常分两步：业务接口返回临时对象存储地址，然后客户端再去拉取文件流。
        # 字段名随版本不同可能是 downloadUrl/storageUrl/location 等，所以要统一抽取。
        download_url = self._first_str(
            obj,
            "downloadUrl",
            "downloadURL",
            "downloadurl",
            "download_url",
            "downLoadUrl",
            "storageUrl",
            "storage_url",
            "href",
            "location",
            "url",
        )
        auth_request = obj.get("authrequest") or obj.get("authRequest")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if download_url or auth_request:
            self._download_from_storage(auth_request, download_url, local_path, progress_cb)
            return local_path
        content = obj.get("content")
        if isinstance(content, str):
            local_path.write_text(content, encoding="utf-8")
        else:
            raise CloudError("下载接口未返回 downloadUrl，请检查 API 文档配置。")
        return local_path

    def _request_download(self, item_id: str) -> Any:
        last_error: CloudError | None = None
        for _ in range(2):
            access_token = self._current_access_token()
            for payload in self._download_payloads(item_id, access_token):
                try:
                    # 官方 osdownload 接口有的部署要求 token 同时出现在请求体中。
                    # _download_payloads 会把 docid 和 token 的几种常见字段名都补上。
                    return self._request("POST", "/efast/v1/file/osdownload", json=payload)
                except AuthError as exc:
                    last_error = exc
                except CloudError as exc:
                    if isinstance(exc, (PermissionDeniedError, NetworkError, RateLimitError, ServerError)):
                        raise
                    last_error = exc
            try:
                self._refresh_for_access_token(access_token)
            except AuthError as exc:
                last_error = exc
                break
        if last_error:
            raise last_error
        raise AuthError("下载授权失败，请重新登录。")

    @staticmethod
    def _download_payloads(item_id: str, access_token: str | None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []

        def add(payload: dict[str, Any]) -> None:
            if access_token:
                payload = {**payload, **AishuCloudClient._token_payload(access_token)}
            if payload not in payloads:
                payloads.append(payload)

        add({"docid": item_id, "docId": item_id})
        add({"docid": item_id})
        add({"docId": item_id})
        add({"id": item_id, "itemId": item_id, "docid": item_id, "docId": item_id})
        add({"id": item_id, "itemId": item_id})
        add({"path": item_id})
        return payloads

    @staticmethod
    def _token_payload(access_token: str) -> dict[str, str]:
        return {
            "tokenid": access_token,
            "tokenId": access_token,
            "access_token": access_token,
            "accessToken": access_token,
        }

    def _download_from_storage(self, auth_request: Any, download_url: str | None, local_path: Path, progress_cb: ProgressCallback | None) -> None:
        method, signed_url, headers = self._parse_auth_request(auth_request)
        target_url = signed_url or download_url
        if not target_url:
            raise CloudError("下载协议未返回对象存储 URL。")
        request_kwargs: dict[str, Any] = {"stream": True}
        if headers:
            request_kwargs["headers"] = headers
        request_method = method if auth_request else "GET"
        response = self._raw_request(request_method or "GET", target_url, auth=not auth_request, **request_kwargs)
        try:
            total = int(response.headers.get("content-length", "0"))
            written = 0
            with local_path.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
                    written += len(chunk)
                    if progress_cb:
                        progress_cb(written, total)
        finally:
            response.close()
            client = getattr(response, "_ncepu_client", None)
            if client is not None:
                client.close()

    def get_item_by_path(self, remote_path: str) -> CloudItem | None:
        data = self._request("POST", "/efast/v1/file/getinfobypath", json={"path": remote_path})
        obj = self._extract_object(data)
        return None if not obj else self._item_from_raw(obj)

    def get_item_fields(self, item_id: str, fields: list[str]) -> dict:
        field_part = ",".join(fields)
        item_segment = quote(item_id, safe="")
        field_segment = quote(field_part, safe=",")
        try:
            data = self._request("GET", f"/efast/v1/items/{item_segment}/{field_segment}")
        except NotFoundError:
            data = self._request("GET", f"/efast/v2/items/{item_segment}/{field_segment}")
        return self._extract_object(data)

    def search(self, keyword: str) -> list[CloudItem]:
        keyword = keyword.strip()
        if not keyword:
            return []
        last_error: CloudError | None = None
        for path in ("/ecosearch/v1/file-search", "/ecosearch/v1/search"):
            for payload in self._search_payloads(keyword):
                try:
                    data = self._request("POST", path, json=payload)
                except CloudError as exc:
                    if isinstance(exc, (AuthError, TokenExpiredError, NetworkError, RateLimitError, ServerError)):
                        raise
                    last_error = exc
                    continue
                items = [self._item_from_raw(item) for item in self._extract_list(data)]
                if items:
                    return items
        fallback = self._search_by_listing(keyword)
        if fallback or last_error is None or isinstance(last_error, NotFoundError):
            return fallback
        raise last_error

    @staticmethod
    def _search_payloads(keyword: str) -> list[dict[str, Any]]:
        return [
            {"keyword": keyword, "type": "doc", "rows": 50, "start": 0},
            {"q": keyword, "type": "doc", "rows": 50, "start": 0},
            {"query": keyword, "type": "doc", "limit": 50, "offset": 0},
            {"name": keyword, "rows": 50, "start": 0},
        ]

    def _search_by_listing(self, keyword: str, max_dirs: int = 200, max_results: int = 200) -> list[CloudItem]:
        needle = keyword.casefold()
        results: list[CloudItem] = []
        visited: set[str] = set()
        queue: list[CloudItem] = self.list_dir("/")
        scanned_dirs = 0
        while queue and scanned_dirs < max_dirs and len(results) < max_results:
            item = queue.pop(0)
            item_key = item.id or item.path or item.name
            if item_key in visited:
                continue
            visited.add(item_key)
            if needle in item.name.casefold():
                results.append(item)
                if len(results) >= max_results:
                    break
            if not item.is_dir or not item.id:
                continue
            scanned_dirs += 1
            try:
                queue.extend(self.list_dir(remote_path=item.path, parent_id=item.id))
            except CloudError as exc:
                if isinstance(exc, (AuthError, TokenExpiredError, NetworkError, RateLimitError, ServerError)):
                    raise
                logger.debug("skip directory during fallback search: %s", exc)
        return results

    def _token_request(self, data: dict[str, Any]):
        api = self.settings.api
        url = f"{api.auth_url.rstrip('/')}/oauth2/token"
        method = api.oauth_client_auth_method
        response = self._token_request_with_method(url, data, method)
        if method != "basic" and self._token_response_prefers_basic(response):
            logger.info("token endpoint rejected client_secret_post, retrying with client_secret_basic")
            response = self._token_request_with_method(url, data, "basic")
        return response

    def _token_request_with_method(self, url: str, data: dict[str, Any], method: str):
        api = self.settings.api
        if method == "basic":
            auth_header = self._basic_auth_header(api.client_id, api.client_secret)
            return self._raw_request("POST", url, data=data, auth=False, headers={"Authorization": auth_header}, raise_status=False)
        data = {**data, "client_id": api.client_id, "client_secret": api.client_secret}
        return self._raw_request("POST", url, data=data, auth=False, raise_status=False)

    @staticmethod
    def _token_response_prefers_basic(response) -> bool:
        if response.status_code != 401:
            return False
        text = mask_sensitive(response.text)
        return "client_secret_basic" in text and "client_secret_post" in text

    @staticmethod
    def _basic_auth_header(client_id: str, client_secret: str) -> str:
        import base64
        from urllib.parse import quote

        raw = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _request(self, method: str, path: str, retry_auth: bool = True, **kwargs: Any) -> Any:
        bundle = self.token_store.load()
        original_access_token = bundle.access_token if bundle else None
        url = self._absolute(path)
        response = None
        if self._preferred_api_auth == "tokenid":
            # 如果前面已经证明 tokenid 查询参数可用，就优先使用它，减少一次 401 往返。
            response = self._request_with_tokenid(method, url, original_access_token, **kwargs)
        if response is None:
            # 官方文档推荐使用 Authorization: Bearer。部分 AnyShare 部署也接受
            # tokenid 查询参数，因此 401 时会在下面走兼容重试。
            response = self._raw_request(method, url, auth=True, raise_status=False, **kwargs)
        if response.status_code == 401 and retry_auth:
            # 第一次 401 不马上判定 token 失效，先尝试另一种认证传参形式。
            # 这是为了兼容学校网盘部署中“文档写 Bearer，实际接口要 tokenid”的情况。
            response = self._request_with_tokenid(method, url, original_access_token, **kwargs) or response
        if response.status_code == 401 and retry_auth:
            # 对失败的 token 只刷新一次。如果其他线程已经刷新过，
            # _refresh_for_access_token 会直接返回。
            self._refresh_for_access_token(original_access_token)
            bundle = self.token_store.load()
            latest_access_token = bundle.access_token if bundle else None
            response = None
            if self._preferred_api_auth == "tokenid":
                response = self._request_with_tokenid(method, url, latest_access_token, **kwargs)
            if response is None:
                response = self._raw_request(method, url, auth=True, raise_status=False, **kwargs)
                if response.status_code == 401:
                    response = self._request_with_tokenid(method, url, latest_access_token, **kwargs) or response
        self._raise_for_status(response, path)
        if not response.content:
            return {}
        return response.json()

    def _current_access_token(self) -> str | None:
        bundle = self.token_store.load()
        if bundle and bundle.token_type.lower() == "cookie":
            return None
        return bundle.access_token if bundle and bundle.access_token else None

    def _request_with_tokenid(self, method: str, url: str, access_token: str | None, **kwargs: Any):
        if not access_token:
            return None
        response = self._raw_request(method, self._with_tokenid(url, access_token), auth=False, raise_status=False, **kwargs)
        if response.status_code < 400:
            # 记录成功的认证方式，后续请求可避免先 Bearer 再 tokenid 的额外往返。
            self._preferred_api_auth = "tokenid"
            return response
        return None

    @staticmethod
    def _with_tokenid(url: str, access_token: str) -> str:
        parsed = urlsplit(url)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key.lower() != "tokenid"]
        query.append(("tokenid", access_token))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))

    def _refresh_for_access_token(self, original_access_token: str | None) -> None:
        with self._refresh_lock:
            latest = self.token_store.load()
            if original_access_token and latest and latest.access_token and latest.access_token != original_access_token:
                # 其他线程已经刷新过 token，本线程不再重复刷新，避免并发刷新互相覆盖。
                return
            self._refresh_token_unlocked()

    def _raw_request(self, method: str, url: str, auth: bool, stream: bool = False, raise_status: bool = True, **kwargs: Any):
        self._ensure_httpx()
        headers = kwargs.pop("headers", {})
        if auth:
            bundle = self.token_store.load()
            if not bundle or not bundle.access_token:
                raise AuthError("未登录或 token 不存在，请先登录。")
            if bundle.token_type.lower() == "cookie":
                # Cookie 凭据只用于显式兜底或手动场景；正常 OAuth REST 调用使用 Bearer token。
                headers["Cookie"] = bundle.access_token
            else:
                headers["Authorization"] = f"{bundle.token_type} {bundle.access_token}"
        timeout = self.settings.api.timeout_seconds
        proxies = self._proxy_config()
        client = None
        returned_stream = False
        try:
            client_kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": True}
            if proxies:
                client_kwargs["proxy"] = proxies.get("https") or proxies.get("http")
            # 每次请求创建短生命周期 httpx.Client，逻辑简单且便于及时释放连接。
            # 对流式下载会把 client 挂到 response 上，等文件写完后再关闭。
            client = httpx.Client(**client_kwargs)
            logger.debug("HTTP %s %s", method, redact_url(url))
            response = client.request(method, url, headers=headers, **kwargs)
            if raise_status:
                self._raise_for_status(response, url)
            if stream:
                returned_stream = True
                setattr(response, "_ncepu_client", client)
                return response
            return response
        except httpx.TimeoutException as exc:
            raise NetworkError(f"网络超时: {redact_url(url)}") from exc
        except httpx.ProxyError as exc:
            raise NetworkError(f"代理连接失败: {redact_url(url)}") from exc
        except httpx.HTTPError as exc:
            raise NetworkError(f"网络请求失败: {redact_url(url)}: {mask_sensitive(str(exc))}") from exc
        finally:
            if client is not None and not returned_stream:
                client.close()

    def _raise_for_status(self, response, path: str) -> None:
        status = response.status_code
        if status < 400:
            return
        message = self._error_message(response, path)
        if status == 401:
            raise AuthError(f"{message}。请重新登录；如果刚切换账号，请先退出登录以清除旧 token 后再登录。")
        if status == 403:
            raise PermissionDeniedError(message)
        if status == 404:
            raise NotFoundError(message)
        if status == 409:
            raise ConflictError(message)
        if status == 429:
            raise RateLimitError(message)
        if status >= 500:
            raise ServerError(message)
        raise CloudError(message)

    @staticmethod
    def _error_message(response, path: str) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                code = data.get("code", "")
                text = mask_sensitive(str(data.get("message") or data.get("cause") or response.text[:300]))
                cause = mask_sensitive(str(data.get("cause"))) if data.get("cause") else None
                suffix = f"；原因: {cause}" if cause and cause != text else ""
                return f"{path} HTTP {response.status_code} {code}: {text}{suffix}"
        except Exception:
            pass
        return f"{path} HTTP {response.status_code}: {mask_sensitive(response.text[:300])}"

    def _absolute(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        prefix = self.settings.api.api_prefix.strip("/")
        relative = path.lstrip("/")
        if prefix and not relative.startswith(prefix + "/"):
            relative = f"{prefix}/{relative}"
        return f"{self.settings.api.base_url.rstrip('/')}/{relative}"

    def _proxy_config(self) -> dict[str, str]:
        proxy = self.settings.proxy
        if not proxy.enabled:
            return {}
        result: dict[str, str] = {}
        if proxy.http:
            result["http"] = self._with_proxy_auth(proxy.http)
        if proxy.https:
            result["https"] = self._with_proxy_auth(proxy.https)
        return result

    def _with_proxy_auth(self, url: str) -> str:
        proxy = self.settings.proxy
        if not proxy.username or "@" in urlsplit(url).netloc:
            return url
        parsed = urlsplit(url)
        user = quote(proxy.username, safe="")
        password = quote(proxy.password, safe="")
        netloc = f"{user}:{password}@{parsed.netloc}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    def _list_doc_lib_fallbacks(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        # 文档库接口按用途拆分：个人、部门、自定义、知识库。
        # 某个账号没有权限的接口可能返回 403/404，跳过即可，不影响其他库展示。
        for path in (
            "/efast/v1/doc-lib/user",
            "/efast/v1/doc-lib/department",
            "/efast/v1/doc-lib/custom",
            "/efast/v1/doc-lib/knowledge",
        ):
            try:
                data = self._request("GET", path)
            except (AuthError, NotFoundError, PermissionDeniedError):
                logger.debug("doc library fallback unavailable: %s", path)
                continue
            extracted = self._extract_libraries(data)
            if extracted:
                items.extend(extracted)
                continue
            obj = self._extract_object(data)
            if obj:
                items.append(obj)
        return items

    def _token_from_response(self, response) -> TokenBundle:
        self._raise_for_status(response, "/oauth2/token")
        return self._token_from_data(response.json())

    @staticmethod
    def _token_from_data(data: dict[str, Any]) -> TokenBundle:
        raw = AishuCloudClient._extract_object(data)
        expires_in = (
            raw.get("expires_in")
            or raw.get("expiresIn")
            or raw.get("expirses_in")
            or raw.get("expires")
            or raw.get("expiresInSeconds")
        )
        token_type = str(raw.get("token_type") or raw.get("tokenType") or raw.get("tokentype") or "Bearer")
        if token_type.lower() == "bearer":
            token_type = "Bearer"
        elif token_type.lower() == "cookie":
            token_type = "Cookie"
        return TokenBundle(
            access_token=(
                raw.get("access_token")
                or raw.get("accessToken")
                or raw.get("tokenid")
                or raw.get("tokenId")
                or raw.get("access_token_id")
                or raw.get("accessTokenId")
                or ""
            ),
            refresh_token=raw.get("refresh_token") or raw.get("refreshToken") or raw.get("refreshtoken") or "",
            expires_at=time.time() + int(expires_in) if expires_in else None,
            token_type=token_type,
        )

    @staticmethod
    def _extract_object(data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            for key in ("data", "result", "item", "quota"):
                value = data.get(key)
                if isinstance(value, dict):
                    return value
            return data
        return {}

    @staticmethod
    def _extract_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "list", "data", "result", "records", "files", "image_info"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    nested = AishuCloudClient._extract_list(value)
                    if nested:
                        return nested
        return []

    @staticmethod
    def _extract_libraries(data: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(raw: dict[str, Any]) -> None:
            key = (
                AishuCloudClient._library_root_id_from_raw(raw)
                or AishuCloudClient._first_str(raw, "docLibId", "libraryId", "id", "name", "libraryName", "docLibName", "displayName")
            )
            if not key or key in seen:
                return
            seen.add(key)
            items.append(raw)

        def walk(value: Any) -> None:
            # 真实接口返回结构可能是 data.items，也可能是 result.list，
            # 甚至多层嵌套。递归遍历可以把解析逻辑集中在适配层。
            if isinstance(value, list):
                for entry in value:
                    walk(entry)
                return
            if not isinstance(value, dict):
                return
            if AishuCloudClient._looks_like_library(value):
                add(value)
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    walk(nested)

        walk(data)
        return items

    @staticmethod
    def _looks_like_library(raw: dict[str, Any]) -> bool:
        # 判断“像不像文档库”不能只看一个字段，因为不同版本返回字段差异较大。
        # 这里综合 type、root id、名称字段来判断，并在 _extract_libraries 中去重。
        doc_lib_types = {
            "user_doc_lib",
            "department_doc_lib",
            "custom_doc_lib",
            "shared_user_doc_lib",
            "knowledge_doc_lib",
        }
        type_text = str(raw.get("type") or "").lower()
        if type_text in doc_lib_types and raw.get("id") and any(key in raw for key in ("name", "displayName", "title")):
            return True
        library_keys = {
            "docLibId",
            "libraryId",
            "libId",
            "rootId",
            "rootItemId",
            "rootDocid",
            "rootDocId",
            "rootPath",
            "docLibName",
            "libraryName",
        }
        if any(key in raw for key in library_keys):
            return True
        has_name = any(key in raw for key in ("name", "displayName", "title", "spaceName"))
        return has_name and any(key in raw for key in ("docid", "docId", "doc_id", "gns"))

    @staticmethod
    def _item_from_raw(raw: dict[str, Any]) -> CloudItem:
        item_type = AishuCloudClient._first_str(raw, "type", "itemType", "entryType", "kind", "objectType", "objType", "fileType")
        type_text = str(item_type or "").lower()
        if type_text in {"dir", "directory", "folder"} or AishuCloudClient._first_truthy(raw, "isDir", "is_dir", "isFolder", "is_folder"):
            kind = CloudItemType.DIRECTORY
        elif type_text in {"file", "document"} or AishuCloudClient._first_truthy(raw, "isFile", "is_file") or raw.get("docid") or raw.get("doc_id") or raw.get("extension"):
            kind = CloudItemType.FILE
        else:
            kind = CloudItemType.UNKNOWN
        item_id = AishuCloudClient._item_id_from_raw(raw)
        return CloudItem(
            id=item_id,
            name=AishuCloudClient._name_from_raw(raw),
            type=kind,
            size=AishuCloudClient._first_optional_int(raw, "size", "fileSize", "length"),
            path=AishuCloudClient._item_path_from_raw(raw, item_id),
            parent_id=AishuCloudClient._first_str(raw, "parentId", "parent_id", "dirId", "dir_id", "parentDocid", "parent_docid", "parent_path"),
            modified_at=str(raw.get("modifiedAt") or raw.get("updateTime") or raw.get("mtime") or raw.get("modified_at") or ""),
            raw=raw,
        )

    @staticmethod
    def _item_id_from_raw(raw: dict[str, Any]) -> str:
        return (
            AishuCloudClient._first_str(
                raw,
                "docid",
                "docId",
                "doc_id",
                "gns",
                "id",
                "itemId",
                "item_id",
                "entryId",
                "entry_id",
                "objectId",
                "object_id",
                "nodeId",
                "node_id",
                "folderId",
                "folder_id",
                "fileId",
                "file_id",
            )
            or ""
        )

    @staticmethod
    def _item_path_from_raw(raw: dict[str, Any], item_id: str) -> str | None:
        return (
            AishuCloudClient._first_str(
                raw,
                "path",
                "fullPath",
                "full_path",
                "itemPath",
                "item_path",
                "docid",
                "docId",
                "doc_id",
                "gns",
                "parent_path",
            )
            or item_id
            or None
        )

    @staticmethod
    def _library_from_raw(raw: dict[str, Any]) -> CloudLibrary:
        return CloudLibrary(
            id=AishuCloudClient._first_str(raw, "docLibId", "libraryId", "libId", "spaceId", "id")
            or AishuCloudClient._library_root_id_from_raw(raw)
            or "",
            name=str(
                raw.get("name")
                or raw.get("libraryName")
                or raw.get("docLibName")
                or raw.get("libName")
                or raw.get("displayName")
                or raw.get("spaceName")
                or raw.get("title")
                or "文档库"
            ),
            owner=raw.get("owner") or raw.get("ownerName"),
            raw=raw,
        )

    @staticmethod
    def _library_to_item(library: CloudLibrary) -> CloudItem:
        raw = library.raw or {}
        item_id = AishuCloudClient._library_root_id_from_raw(raw) or library.id
        path = (
            AishuCloudClient._first_str(
                raw,
                "rootPath",
                "root_path",
                "path",
                "fullPath",
                "full_path",
                "itemPath",
                "item_path",
                "gns",
                "docid",
                "docId",
                "doc_id",
            )
            or item_id
        )
        return CloudItem(
            id=item_id,
            name=library.name,
            type=CloudItemType.DIRECTORY,
            path=path,
            raw=raw,
        )

    @staticmethod
    def _library_root_id_from_raw(raw: dict[str, Any]) -> str | None:
        return AishuCloudClient._first_str(
            raw,
            "rootId",
            "rootItemId",
            "root_id",
            "root_item_id",
            "rootDocid",
            "rootDocId",
            "root_docid",
            "root_doc_id",
            "docid",
            "docId",
            "doc_id",
            "gns",
            "itemId",
            "entryId",
            "id",
            "libraryId",
            "docLibId",
        )

    @staticmethod
    def _first_int(raw: dict[str, Any], *keys: str) -> int:
        return AishuCloudClient._first_optional_int(raw, *keys) or 0

    @staticmethod
    def _name_from_raw(raw: dict[str, Any]) -> str:
        name = (
            raw.get("name")
            or raw.get("fileName")
            or raw.get("file_name")
            or raw.get("displayName")
            or raw.get("display_name")
            or raw.get("objectName")
            or raw.get("object_name")
            or raw.get("docName")
            or raw.get("doc_name")
            or raw.get("dirname")
            or raw.get("dirName")
            or raw.get("folderName")
            or raw.get("title")
        )
        if name:
            return str(name)
        basename = raw.get("basename")
        extension = raw.get("extension") or ""
        if basename:
            return f"{basename}{extension}"
        return ""

    @staticmethod
    def _first_optional_int(raw: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = raw.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _first_str(raw: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = raw.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @staticmethod
    def _first_truthy(raw: dict[str, Any], *keys: str) -> bool:
        for key in keys:
            value = raw.get(key)
            if value is True:
                return True
            if isinstance(value, str) and value.lower() in {"true", "1", "yes"}:
                return True
            if isinstance(value, int) and value == 1:
                return True
        return False

    @staticmethod
    def _ensure_httpx() -> None:
        if httpx is None:
            raise RuntimeError("httpx 未安装，请执行 pip install -r requirements.txt")
