from __future__ import annotations

from pathlib import Path
from typing import Callable

from ncepu_cloud_client.api.base import CloudDriveClient
from ncepu_cloud_client.api.models import CloudItem
from ncepu_cloud_client.ui.components.file_table import FileTable
from ncepu_cloud_client.utils.file_utils import human_size

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ListDirWorker(QThread):
    """在 Qt UI 线程之外执行远端目录加载。

    Qt 的主线程负责绘制窗口、响应按钮和处理信号槽。
    远端目录加载包含网络 I/O，必须放到 QThread 中，否则网络慢时界面会卡死。
    """

    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, path: str, parent_id: str | None, previous_state: tuple[str, str | None] | None = None):
        super().__init__()
        self.client = client
        self.path = path
        self.parent_id = parent_id
        self.previous_state = previous_state

    def run(self) -> None:
        try:
            # worker 线程不能直接改 UI，只通过 Signal 把结果发回主线程。
            self.loaded.emit(self.client.list_dir(remote_path=self.path, parent_id=self.parent_id))
        except Exception as exc:
            self.failed.emit(str(exc))


class SearchWorker(QThread):
    """异步执行云端搜索，保证输入和导航保持响应。

    搜索可能走真实搜索接口，也可能回退为递归遍历目录。
    两种路径都可能耗时，因此和目录加载一样放到后台线程。
    """

    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, keyword: str):
        super().__init__()
        self.client = client
        self.keyword = keyword

    def run(self) -> None:
        try:
            self.loaded.emit(self.client.search(self.keyword))
        except Exception as exc:
            self.failed.emit(str(exc))


class ActionWorker(QThread):
    """封装删除、重命名、移动、复制等一次性云端变更操作。

    这些操作虽然看起来只是按钮点击，但真实 API 仍然需要网络往返。
    抽成通用 worker 可以避免每个按钮重复写线程和异常处理代码。
    """

    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, action: Callable[[], None]):
        super().__init__()
        self.action = action

    def run(self) -> None:
        try:
            self.action()
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class UploadWorker(QThread):
    """上传用户选择的本地文件，避免阻塞 UI 事件循环。

    上传可能包含本地读文件、初始化上传、对象存储传输和完成确认几个阶段。
    进度通过 Signal 回传给页面，页面只负责显示百分比。
    """

    finished_ok = Signal()
    progress = Signal(int)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, local_path: Path, current_path: str, current_parent_id: str | None):
        super().__init__()
        self.client = client
        self.local_path = local_path
        self.current_path = current_path
        self.current_parent_id = current_parent_id

    def run(self) -> None:
        try:
            # current_parent_id 优先，因为爱数接口更稳定地接受 docid/gns 这类目录标识；
            # 如果只有路径，则先查询路径对应的目录对象。
            current = self.client.get_item_by_path(self.current_path) if self.current_path != "/" and not self.current_parent_id else None
            remote_id = self.current_parent_id or (current.id if current else "root")
            self.client.upload_file(self.local_path, remote_id, progress_cb=self._progress)
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))

    def _progress(self, done: int, total: int) -> None:
        self.progress.emit(int(done / total * 100) if total else 0)


class DownloadWorker(QThread):
    """下载云端文件，避免阻塞 UI 事件循环。

    下载通常先向业务 API 请求临时下载地址，再从对象存储读取字节流。
    这类流式 I/O 不应该在主线程里执行。
    """

    finished_ok = Signal()
    progress = Signal(int)
    failed = Signal(str)

    def __init__(self, client: CloudDriveClient, item_id: str, target: Path):
        super().__init__()
        self.client = client
        self.item_id = item_id
        self.target = target

    def run(self) -> None:
        try:
            self.client.download_file(self.item_id, self.target, progress_cb=self._progress)
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))

    def _progress(self, done: int, total: int) -> None:
        self.progress.emit(int(done / total * 100) if total else 0)


class CloudFilesPage(QWidget):
    def __init__(self, client: CloudDriveClient):
        super().__init__()
        self.client = client
        self.current_path = "/"
        self.current_parent_id: str | None = None
        self.history: list[tuple[str, str | None]] = []
        self._workers: list[QThread] = []
        self.worker: QThread | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("云端文件")
        title.setObjectName("PageTitle")
        subtitle = QLabel("浏览、搜索和管理华电云盘中的文件。")
        subtitle.setObjectName("MutedText")
        self.status = QLabel("就绪")
        self.status.setObjectName("MutedText")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        header.addWidget(self.status)

        path_row = QHBoxLayout()
        action_row = QHBoxLayout()
        path_row.setSpacing(10)
        action_row.setSpacing(8)
        self.breadcrumb = QLabel("/")
        self.breadcrumb.setObjectName("MutedText")
        self.breadcrumb.setMinimumWidth(180)
        self.search = QLineEdit()
        self.search.setObjectName("TopSearch")
        self.search.setPlaceholderText("搜索文件名")
        self.search.returnPressed.connect(self.do_search)
        path_row.addWidget(self.breadcrumb)
        path_row.addWidget(self.search, 1)
        search_button = QPushButton("搜索")
        search_button.clicked.connect(self.do_search)
        path_row.addWidget(search_button)

        primary_actions = [
            ("返回上级", self.go_parent, "GhostButton"),
            ("刷新", self.refresh, "GhostButton"),
            ("新建文件夹", self.mkdir, ""),
            ("上传文件", self.upload_file, "PrimaryButton"),
            ("下载", self.download_selected, ""),
            ("重命名", self.rename_selected, ""),
        ]
        for text, slot, object_name in primary_actions:
            button = QPushButton(text)
            button.clicked.connect(slot)
            if object_name:
                button.setObjectName(object_name)
            action_row.addWidget(button)
        more = QPushButton("更多")
        more_menu = QMenu(more)
        for text, slot in [
            ("打开", self.open_selected),
            ("移动", self.move_selected),
            ("复制", self.copy_selected),
            ("删除", self.delete_selected),
        ]:
            action = more_menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=slot: s())
        more.setMenu(more_menu)
        action_row.addWidget(more)
        action_row.addStretch(1)
        self.table = FileTable()
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.itemSelectionChanged.connect(self._update_details)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        details = self._build_details_panel()
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.table, 1)
        body.addWidget(details)
        root.addLayout(header)
        root.addLayout(path_row)
        root.addLayout(action_row)
        root.addLayout(body, 1)
        self.refresh()

    def _build_details_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Surface")
        panel.setFixedWidth(270)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title = QLabel("文件详情")
        title.setObjectName("SectionTitle")
        self.detail_name = QLabel("未选择文件")
        self.detail_name.setObjectName("MetricValue")
        self.detail_type = QLabel("请选择列表中的文件或文件夹。")
        self.detail_type.setObjectName("MutedText")
        self.detail_size = QLabel("")
        self.detail_size.setObjectName("MutedText")
        self.detail_path = QLabel("")
        self.detail_path.setObjectName("MutedText")
        self.detail_status = QLabel("状态：-")
        self.detail_status.setObjectName("SuccessText")
        download = QPushButton("下载到本地")
        download.clicked.connect(self.download_selected)
        copy_path = QPushButton("复制路径")
        copy_path.setObjectName("GhostButton")
        copy_path.clicked.connect(lambda: QApplication.clipboard().setText((self.table.selected_item().path or self.table.selected_item().name) if self.table.selected_item() else ""))
        layout.addWidget(title)
        layout.addWidget(self.detail_name)
        layout.addWidget(self.detail_type)
        layout.addWidget(self.detail_size)
        layout.addWidget(self.detail_path)
        layout.addWidget(self.detail_status)
        layout.addSpacing(8)
        layout.addWidget(download)
        layout.addWidget(copy_path)
        layout.addStretch(1)
        return panel

    def _update_details(self) -> None:
        item = self.table.selected_item()
        if not item:
            self.detail_name.setText("未选择文件")
            self.detail_type.setText("请选择列表中的文件或文件夹。")
            self.detail_size.setText("")
            self.detail_path.setText("")
            self.detail_status.setText("状态：-")
            return
        self.detail_name.setText(item.name)
        self.detail_type.setText("文件夹" if item.is_dir else "文件")
        self.detail_size.setText("大小：-" if item.is_dir else f"大小：{human_size(item.size)}")
        self.detail_path.setText(f"路径：{item.path or self.current_path}")
        self.detail_status.setText("状态：云端文件" if item.is_dir else "状态：已同步")

    def refresh(self, previous_state: tuple[str, str | None] | None = None) -> None:
        self.breadcrumb.setText(self.current_path)
        request_hint = f"{self.current_path}" + (f" | id={self.current_parent_id}" if self.current_parent_id else "")
        self.status.setText(f"加载中... {request_hint}")
        # previous_state 用于导航失败时回滚面包屑和当前目录，
        # 避免用户双击一个不可访问目录后页面停留在错误路径。
        worker = ListDirWorker(self.client, self.current_path, self.current_parent_id, previous_state)
        worker.loaded.connect(lambda items, current=worker: self._items_loaded(items, current))
        worker.failed.connect(lambda msg, current=worker: self._load_failed(msg, current))
        self._start_worker(worker)

    def _items_loaded(self, items: list[CloudItem], worker: ListDirWorker | None = None) -> None:
        if worker is not None and worker is not self.worker:
            # 忽略旧请求的过期结果，避免较晚返回的旧导航覆盖当前页面。
            return
        self.table.set_items(items)
        self._update_details()
        self.status.setText(f"就绪，共 {len(items)} 项")

    def _load_failed(self, msg: str, worker: ListDirWorker | None = None) -> None:
        if worker is not None and worker is not self.worker:
            # 旧请求产生的错误不应替换当前页面状态。
            return
        if worker is not None and worker.previous_state is not None:
            if self.history and self.history[-1] == worker.previous_state:
                self.history.pop()
            self.current_path, self.current_parent_id = worker.previous_state
            self.breadcrumb.setText(self.current_path)
        if self._looks_like_auth_expired(msg):
            self.status.setText("登录已过期")
            QMessageBox.warning(
                self,
                "登录已过期",
                f"{msg}\n\n请点击右上角“已登录” > “切换用户”，在浏览器中重新登录后再访问云端文件。",
            )
            return
        self.status.setText("加载失败")
        QMessageBox.warning(self, "云端文件加载失败", msg)

    def _worker_finished(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if worker is not self.worker:
            worker.deleteLater()

    def _start_worker(self, worker: QThread) -> None:
        old_worker = self.worker
        if old_worker is not None and not old_worker.isRunning() and old_worker not in self._workers:
            old_worker.deleteLater()
        self.worker = worker
        self._workers.append(worker)
        # 保留引用直到线程结束，避免 Python 垃圾回收提前回收仍在运行的 QThread。
        # 这是 PySide 常见坑：如果 QThread 没有 Python 侧引用，可能出现线程运行中对象被销毁。
        worker.finished.connect(lambda current=worker: self._worker_finished(current))
        worker.start()

    def do_search(self) -> None:
        keyword = self.search.text().strip()
        if not keyword:
            self.refresh()
            return
        self.status.setText(f"搜索中... {keyword}")
        worker = SearchWorker(self.client, keyword)
        worker.loaded.connect(lambda items, current=worker: self._search_loaded(keyword, items, current))
        worker.failed.connect(lambda msg, current=worker: self._search_failed(msg, current))
        self._start_worker(worker)

    def search_cloud(self, keyword: str) -> None:
        self.search.setText(keyword)
        if keyword.strip():
            self.do_search()
        else:
            self.search.setFocus()

    def _search_loaded(self, keyword: str, items: list[CloudItem], worker: SearchWorker | None = None) -> None:
        if worker is not None and worker is not self.worker:
            # 搜索和目录导航共用当前 worker 保护，防止旧结果覆盖新结果。
            return
        self.table.set_items(items)
        self._update_details()
        self.status.setText(f"搜索完成：{keyword}，共 {len(items)} 项")

    def _search_failed(self, msg: str, worker: SearchWorker | None = None) -> None:
        if worker is not None and worker is not self.worker:
            return
        if self._looks_like_auth_expired(msg):
            self.status.setText("登录已过期")
            QMessageBox.warning(
                self,
                "登录已过期",
                f"{msg}\n\n请点击右上角“已登录” > “切换用户”，在浏览器中重新登录后再搜索云端文件。",
            )
            return
        self.status.setText("搜索失败")
        QMessageBox.warning(self, "搜索失败", msg)

    @staticmethod
    def _looks_like_auth_expired(message: str) -> bool:
        lowered = message.lower()
        return "http 401" in lowered or "access token" in lowered or "token" in lowered and "过期" in message

    def go_parent(self) -> None:
        if not self.history:
            return
        self.current_path, self.current_parent_id = self.history.pop()
        self.refresh()

    def open_selected(self) -> None:
        self._open_item(self.table.selected_item())

    def mkdir(self) -> None:
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称")
        if not ok or not name:
            return
        remote_path = f"{self.current_path.rstrip('/')}/{name}" if self.current_path != "/" else f"/{name}"
        self._run_action(lambda: self.client.mkdir(remote_path), "创建中...", "创建失败")

    def upload_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择要上传的文件")
        if not path:
            return
        self.status.setText("上传中 0%")
        worker = UploadWorker(self.client, Path(path), self.current_path, self.current_parent_id)
        worker.progress.connect(lambda value: self.status.setText(f"上传中 {value}%"))
        worker.finished_ok.connect(lambda: (self.status.setText("上传完成"), self.refresh()))
        worker.failed.connect(lambda msg: QMessageBox.warning(self, "上传失败", msg))
        self._start_worker(worker)

    def download_selected(self) -> None:
        item = self.table.selected_item()
        if not item:
            return
        target, _ = QFileDialog.getSaveFileName(self, "保存文件", item.name)
        if not target:
            return
        self.status.setText("下载中 0%")
        worker = DownloadWorker(self.client, item.id, Path(target))
        worker.progress.connect(lambda value: self.status.setText(f"下载中 {value}%"))
        worker.finished_ok.connect(lambda: self.status.setText("下载完成"))
        worker.failed.connect(lambda msg: QMessageBox.warning(self, "下载失败", msg))
        self._start_worker(worker)

    def delete_selected(self) -> None:
        item = self.table.selected_item()
        if not item:
            return
        if QMessageBox.question(self, "确认删除", f"删除 {item.name}？") != QMessageBox.Yes:
            return
        self._run_action(lambda: self.client.delete(item.id), "删除中...", "删除失败")

    def rename_selected(self) -> None:
        item = self.table.selected_item()
        if not item:
            return
        name, ok = QInputDialog.getText(self, "重命名", "新名称", text=item.name)
        if not ok or not name:
            return
        self._run_action(lambda: self.client.rename(item.id, name), "重命名中...", "重命名失败")

    def move_selected(self) -> None:
        item = self.table.selected_item()
        if not item:
            return
        target_id = self._ask_target_dir("移动到")
        if not target_id:
            return
        self._run_action(lambda: self.client.move(item.id, target_id), "移动中...", "移动失败")

    def copy_selected(self) -> None:
        item = self.table.selected_item()
        if not item:
            return
        target_id = self._ask_target_dir("复制到")
        if not target_id:
            return
        self._run_action(lambda: self.client.copy(item.id, target_id), "复制中...", "复制失败")

    def _double_clicked(self, row: int, column: int) -> None:
        item: CloudItem | None = self.table.items[row] if row < len(self.table.items) else None
        self._open_item(item)

    def _open_item(self, item: CloudItem | None) -> None:
        if item and item.is_dir:
            target_path, target_id = self._directory_target(item)
            if not target_path and not target_id:
                QMessageBox.warning(self, "无法进入文件夹", f"{item.name} 缺少可用的目录 ID 或路径。")
                return
            previous_state = (self.current_path, self.current_parent_id)
            self.history.append(previous_state)
            self.current_path = target_path or target_id or item.name
            self.current_parent_id = target_id
            self.search.clear()
            self.refresh(previous_state=previous_state)
        elif item:
            QMessageBox.information(self, "文件信息", f"{item.name}\nID: {item.id}")

    def _directory_target(self, item: CloudItem) -> tuple[str | None, str | None]:
        raw = item.raw or {}
        # 不同 RESTful API 返回的目录字段名不完全一致。
        # 这里同时兼容 docid、docId、gns、itemId、path 等字段，保证公共文档库也能进入。
        target_id = item.id or self._first_raw_str(raw, "docid", "docId", "doc_id", "gns", "itemId", "id")
        target_path = item.path or self._first_raw_str(raw, "path", "fullPath", "full_path", "itemPath", "item_path", "docid", "docId", "doc_id", "gns")
        fallback_path = f"{self.current_path.rstrip('/')}/{item.name}" if self.current_path != "/" else f"/{item.name}"
        if target_path == self.current_path and target_id and target_id != self.current_parent_id:
            # 有些接口把 path 回成父目录，但 id 已经是子目录 id；
            # 此时优先用 id 继续请求，否则会反复加载当前目录。
            target_path = target_id
        elif item.name and target_path in (None, "", self.current_path) and target_id in (None, "", self.current_parent_id):
            # 如果后端没有给可用路径或 id，就退化为根据当前路径拼接目录名。
            # 这不是最理想，但比直接无法导航更友好。
            target_path = fallback_path
            target_id = target_path
        elif target_path and not target_id:
            target_id = target_path
        return target_path, target_id

    @staticmethod
    def _first_raw_str(raw: dict, *keys: str) -> str | None:
        for key in keys:
            value = raw.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    def _show_context_menu(self, pos) -> None:
        item = self.table.selected_item()
        if not item:
            return
        menu = QMenu(self)
        open_action = menu.addAction("打开")
        download = menu.addAction("下载")
        rename = menu.addAction("重命名")
        move = menu.addAction("移动")
        copy = menu.addAction("复制")
        delete = menu.addAction("删除")
        copy_path = menu.addAction("复制路径")
        detail = menu.addAction("查看详情")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == open_action:
            self._open_item(item)
        elif action == download:
            self.download_selected()
        elif action == rename:
            self.rename_selected()
        elif action == move:
            self.move_selected()
        elif action == copy:
            self.copy_selected()
        elif action == delete:
            self.delete_selected()
        elif action == copy_path:
            QApplication.clipboard().setText(item.path or item.name)
        elif action == detail:
            QMessageBox.information(self, "文件详情", f"名称: {item.name}\nID: {item.id}\n路径: {item.path or '-'}")

    def _run_action(self, action: Callable[[], None], status: str, failure_title: str) -> None:
        self.status.setText(status)
        worker = ActionWorker(action)
        worker.finished_ok.connect(lambda: (self.status.setText("操作完成"), self.refresh()))
        worker.failed.connect(lambda msg: QMessageBox.warning(self, failure_title, msg))
        self._start_worker(worker)

    def _ask_target_dir(self, title: str) -> str | None:
        default = self.current_parent_id or "root"
        value, ok = QInputDialog.getText(self, title, "目标目录 ID 或路径", text=default)
        if not ok or not value.strip():
            return None
        target = value.strip()
        if target in ("/", "root"):
            return "root"
        if target.startswith("/"):
            item = self.client.get_item_by_path(target)
            if not item:
                QMessageBox.warning(self, "目标目录不存在", f"找不到云端目录：{target}")
                return None
            return item.id
        return target
