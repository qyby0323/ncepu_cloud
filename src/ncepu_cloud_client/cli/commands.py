from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ncepu_cloud_client.app.bootstrap import bootstrap
from ncepu_cloud_client.api.errors import CloudError
from ncepu_cloud_client.api.models import TokenBundle
from ncepu_cloud_client.auth.token_store import TokenStore
from ncepu_cloud_client.sync.models import SyncDirection
from ncepu_cloud_client.services.sync_service import SyncService
from ncepu_cloud_client.utils.file_utils import human_size


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ncepu-cloud", description="华电云盘客户端 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login")
    token_login = sub.add_parser("token-login")
    token_login.add_argument("access_token")
    token_login.add_argument("--refresh-token", default="")
    sso_login = sub.add_parser("sso-login")
    sso_login.add_argument("--params-json", required=True, help="JSON object for credential.params")
    register = sub.add_parser("register-client")
    register.add_argument("--name", default="NCEPU Cloud Client")
    sub.add_parser("quota")
    doc_quota = sub.add_parser("doc-lib-quota")
    doc_quota.add_argument("doc_lib_id")
    sub.add_parser("libraries")
    list_parser = sub.add_parser("list")
    list_parser.add_argument("path", nargs="?", default="/")
    search = sub.add_parser("search")
    search.add_argument("keyword")
    mkdir = sub.add_parser("mkdir")
    mkdir.add_argument("remote_path")
    delete = sub.add_parser("delete")
    delete.add_argument("item")
    rename = sub.add_parser("rename")
    rename.add_argument("item")
    rename.add_argument("new_name")
    move = sub.add_parser("move")
    move.add_argument("item")
    move.add_argument("target_dir")
    copy = sub.add_parser("copy")
    copy.add_argument("item")
    copy.add_argument("target_dir")
    fields = sub.add_parser("fields")
    fields.add_argument("item")
    fields.add_argument("fields", nargs="+")
    upload = sub.add_parser("upload")
    upload.add_argument("local_path")
    upload.add_argument("remote_dir", nargs="?", default="/")
    download = sub.add_parser("download")
    download.add_argument("remote_path")
    download.add_argument("local_path")
    sync_add = sub.add_parser("sync-add")
    sync_add.add_argument("local_dir")
    sync_add.add_argument("remote_dir", nargs="?", default="root")
    sync_add.add_argument("--ignore-rule", action="append", default=[], help="当前同步任务的过滤规则，可重复传入。")
    sub.add_parser("sync-start")
    args = parser.parse_args(argv)

    settings, client = bootstrap()
    try:
        if args.command == "login":
            client.login()
            print("登录成功")
        elif args.command == "token-login":
            TokenStore(settings.security).save(TokenBundle(access_token=args.access_token, refresh_token=args.refresh_token))
            print("token 已保存")
        elif args.command == "sso-login":
            if not hasattr(client, "login_sso"):
                raise CloudError("当前 adapter 不支持 SSO。")
            params = json.loads(args.params_json)
            client.login_sso(params)
            print("SSO 登录成功")
        elif args.command == "register-client":
            if not hasattr(client, "register_oauth_client"):
                raise CloudError("当前 adapter 不支持动态注册。")
            result = client.register_oauth_client(args.name)
            print("动态注册结果，请妥善保存 client_secret：")
            for key in ("client_id", "client_secret"):
                if key in result:
                    print(f"{key}: {result[key]}")
        elif args.command == "quota":
            quota = client.get_quota()
            print(f"已用 {human_size(quota.used)} / 总容量 {human_size(quota.total)}")
        elif args.command == "doc-lib-quota":
            quota = client.get_doc_lib_quota(args.doc_lib_id)
            print(f"文档库 {args.doc_lib_id}: 已用 {human_size(quota.used)} / 总容量 {human_size(quota.total)}")
        elif args.command == "libraries":
            for library in client.list_libraries():
                print(f"{library.id}\t{library.name}\t{library.owner or '-'}")
        elif args.command == "list":
            for item in client.list_dir(remote_path=args.path):
                _print_item(item)
        elif args.command == "search":
            for item in client.search(args.keyword):
                _print_item(item)
        elif args.command == "mkdir":
            item = client.mkdir(args.remote_path)
            print(f"创建完成: {item.name} ({item.id})")
        elif args.command == "delete":
            item_id = _resolve_item_id(client, args.item)
            client.delete(item_id)
            print(f"删除完成: {item_id}")
        elif args.command == "rename":
            item_id = _resolve_item_id(client, args.item)
            item = client.rename(item_id, args.new_name)
            print(f"重命名完成: {item.name} ({item.id})")
        elif args.command == "move":
            item_id = _resolve_item_id(client, args.item)
            target_id = _resolve_dir_id(client, args.target_dir)
            item = client.move(item_id, target_id)
            print(f"移动完成: {item.name} ({item.id})")
        elif args.command == "copy":
            item_id = _resolve_item_id(client, args.item)
            target_id = _resolve_dir_id(client, args.target_dir)
            item = client.copy(item_id, target_id)
            print(f"复制完成: {item.name} ({item.id})")
        elif args.command == "fields":
            item_id = _resolve_item_id(client, args.item)
            data = client.get_item_fields(item_id, args.fields)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "upload":
            remote_id = _resolve_dir_id(client, args.remote_dir)
            item = client.upload_file(Path(args.local_path), remote_id)
            print(f"上传完成: {item.name} ({item.id})")
        elif args.command == "download":
            item = client.get_item_by_path(args.remote_path)
            if not item:
                raise CloudError(f"云端文件不存在: {args.remote_path}")
            path = client.download_file(item.id, Path(args.local_path))
            print(f"下载完成: {path}")
        elif args.command == "sync-add":
            service = SyncService(client, settings=settings)
            task_id = service.add_task(
                name=Path(args.local_dir).name,
                local_root=Path(args.local_dir),
                remote_root_id=args.remote_dir,
                remote_root_path=args.remote_dir,
                direction=SyncDirection.BIDIRECTIONAL,
                ignore_rules="\n".join(args.ignore_rule),
            )
            print(f"同步任务已创建: {task_id}")
        elif args.command == "sync-start":
            service = SyncService(client, settings=settings)
            service.start()
            print("同步引擎已启动，按 Ctrl+C 停止。")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                service.stop()
    except Exception as exc:
        print(f"错误: {exc}")
        return 2
    return 0


def _print_item(item) -> None:
    kind = "DIR " if item.is_dir else "FILE"
    print(f"{kind}\t{item.id}\t{human_size(item.size)}\t{item.name}\t{item.path or '-'}")


def _resolve_item_id(client, value: str) -> str:
    if value.startswith("/"):
        item = client.get_item_by_path(value)
        if not item:
            raise CloudError(f"云端对象不存在: {value}")
        return item.id
    return value


def _resolve_dir_id(client, value: str) -> str:
    if value in ("/", "root"):
        return "root"
    return _resolve_item_id(client, value)


if __name__ == "__main__":
    raise SystemExit(main())
