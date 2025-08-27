import time
import requests
from datetime import datetime, date
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QThread
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QWidget, QVBoxLayout, QScrollBar
from loguru import logger
from qfluentwidgets import isDarkTheme

WIDGET_CODE = 'widget_ship.ui'
WIDGET_NAME = '船班信息 | LaoShui'
WIDGET_WIDTH = 360
API_URL = "https://zyb.ziubao.com/api/v1/getShipDynamics?area=%E5%85%AD%E6%A8%AA%E5%B2%9B&pageSize=20"
CACHE_DURATION = 1800  # 缓存更新周期：30分钟


class ShipFetchThread(QThread):
    """船班信息获取线程"""
    fetch_success = pyqtSignal(list)  # 成功信号
    fetch_failed = pyqtSignal()  # 失败信号

    def __init__(self):
        super().__init__()
        self.max_retries = 3

    def run(self):
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                response = requests.get(API_URL, headers={}, proxies={'http': None, 'https': None})
                response.raise_for_status()
                data = response.json().get("data", [])
                if data:
                    # 获取当天日期
                    today = date.today()

                    # 多重过滤条件
                    filtered_data = []
                    for item in data:
                        # 条件1: confrom 字段为"六横大岙客运中心"
                        if item.get("confrom") != "六横大岙客运中心":
                            continue

                        # 条件2: description 包含"沈家门"或"长峙"
                        description = item.get('description', '')
                        if not ('沈家门' in description or '长峙' in description):
                            continue

                        # 条件3: 只显示当天的消息
                        try:
                            item_datetime = item.get('datetime', '')
                            if item_datetime:
                                # 解析日期时间字符串，假设格式为 "YYYY-MM-DD HH:MM:SS" 或类似格式
                                item_date = datetime.strptime(item_datetime.split()[0], '%Y-%m-%d').date()
                                if item_date != today:
                                    continue
                        except (ValueError, IndexError):
                            # 如果日期解析失败，跳过该条目
                            continue

                        filtered_data.append(item)

                    # 传递完整的船班信息
                    ship_info_list = []
                    for item in filtered_data:
                        ship_info = {
                            'datetime': item.get('datetime', ''),
                            'description': item.get('description', ''),
                            'fbz': item.get('fbz', '')
                        }
                        ship_info_list.append(ship_info)
                    self.fetch_success.emit(ship_info_list)
                    return
            except Exception as e:
                logger.error(f"请求失败: {e}")

            retry_count += 1
            time.sleep(2)

        self.fetch_failed.emit()


class SmoothScrollBar(QScrollBar):
    """平滑滚动条"""
    scrollFinished = pyqtSignal()

    def __init__(self, parent=None):
        QScrollBar.__init__(self, parent)
        self.ani = QPropertyAnimation()
        self.ani.setTargetObject(self)
        self.ani.setPropertyName(b"value")
        self.ani.setEasingCurve(QEasingCurve.OutCubic)
        self.ani.setDuration(400)  # 调整动画持续时间
        self.__value = self.value()
        self.ani.finished.connect(self.scrollFinished)

    def setValue(self, value: int):
        if value == self.value():
            return

        self.ani.stop()
        self.scrollFinished.emit()

        self.ani.setStartValue(self.value())
        self.ani.setEndValue(value)
        self.ani.start()

    def wheelEvent(self, e):
        # 阻止默认的滚轮事件，使用自定义的滚动逻辑
        e.ignore()


class SmoothScrollArea(QScrollArea):
    """平滑滚动区域"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vScrollBar = SmoothScrollBar()
        self.setVerticalScrollBar(self.vScrollBar)
        self.setStyleSheet("QScrollBar:vertical { width: 0px; }")  # 隐藏原始滚动条

    def wheelEvent(self, e):
        if hasattr(self.vScrollBar, 'scrollValue'):
            self.vScrollBar.scrollValue(-e.angleDelta().y())


class Plugin:
    def __init__(self, cw_contexts, method):
        self.cw_contexts = cw_contexts
        self.method = method

        self.CONFIG_PATH = f'{cw_contexts["PLUGIN_PATH"]}/config.json'
        self.PATH = cw_contexts['PLUGIN_PATH']

        self.method.register_widget(WIDGET_CODE, WIDGET_NAME, WIDGET_WIDTH)

        # 初始化定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_update)
        self.timer.start(1000)  # 每秒检查一次是否需要更新

        # 滚动相关初始化
        self.scroll_position = 0
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.auto_scroll)
        self.scroll_timer.start(50)  # 每50毫秒执行一次滚动

        # 状态变量
        self.last_fetched = 0
        self.cached_descriptions = [{"description": "正在加载船班信息..."}]
        self.is_loading = False
        self.test_widget = None  # 初始化 test_widget 属性

    def check_update(self):
        """定时检查是否需要更新"""
        if time.time() - self.last_fetched > CACHE_DURATION and not self.is_loading:
            self.update_ship_dynamics()

    def update_ship_dynamics(self):
        """启动异步更新"""
        self.is_loading = True
        self.cached_descriptions = [{"description": "正在加载船班信息..."}]
        self._update_ui()

        self.worker_thread = ShipFetchThread()
        self.worker_thread.fetch_success.connect(self.handle_success)
        self.worker_thread.fetch_failed.connect(self.handle_failure)
        self.worker_thread.start()

    def handle_success(self, ship_info_list):
        """处理成功响应"""
        self.is_loading = False
        self.last_fetched = time.time()
        self.cached_descriptions = ship_info_list or [{"description": "暂无六横大岙客运中心船班信息"}]
        self._update_ui()

    def handle_failure(self):
        """处理失败情况"""
        self.is_loading = False
        self.cached_descriptions = [{"description": "数据获取失败，5分钟后重试"}]
        self._update_ui()
        QTimer.singleShot(300000, self.update_ship_dynamics)  # 5分钟后重试

    def _update_ui(self):
        """线程安全更新界面"""
        QTimer.singleShot(0, lambda: self.update_widget_content(self.cached_descriptions))

    def update_widget_content(self, ship_info_list):
        """更新小组件内容"""
        self.test_widget = self.method.get_widget(WIDGET_CODE)
        if not self.test_widget:
            logger.error(f"小组件未找到，WIDGET_CODE: {WIDGET_CODE}")
            return

        content_layout = self.find_child_layout(self.test_widget, 'contentLayout')
        if not content_layout:
            logger.error("未能找到小组件的'contentLayout'布局")
            return

        content_layout.setSpacing(5)
        self.method.change_widget_content(WIDGET_CODE, WIDGET_NAME, WIDGET_NAME)

        # 清除旧内容
        self.clear_existing_content(content_layout)

        # 创建滚动区域并设置内容
        scroll_area = self.create_scroll_area(ship_info_list)
        if scroll_area:
            content_layout.addWidget(scroll_area)
            logger.success('六横大岙客运中心船班信息更新成功！')
        else:
            logger.error("滚动区域创建失败")

    @staticmethod
    def find_child_layout(widget, layout_name):
        """根据名称查找并返回布局"""
        return widget.findChild(QHBoxLayout, layout_name)

    def create_scroll_area(self, ship_info_list):
        """创建并返回一个包含船班信息的滚动区域"""
        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollBar:vertical { width: 0px; }")  # 隐藏滚动条

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout()
        scroll_content_layout.setSpacing(8)  # 增加间距
        scroll_content.setLayout(scroll_content_layout)

        for ship_info in ship_info_list:
            ship_widget = self.create_ship_info_widget(ship_info)
            scroll_content_layout.addWidget(ship_widget)

        scroll_area.setWidget(scroll_content)
        return scroll_area

    @staticmethod
    def create_ship_info_widget(ship_info):
        """创建一个船班信息小部件并返回"""
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 设置容器样式 - 透明背景，只保留左侧蓝色条
        container.setStyleSheet(
            "QWidget { "
            "background-color: transparent; "
            "border-left: 4px solid #2196F3; "
            "}"
        )

        # 如果只有描述信息（加载状态或错误状态）
        if isinstance(ship_info, dict) and len(ship_info) == 1 and 'description' in ship_info:
            description_label = QLabel(ship_info['description'])
            description_label.setAlignment(Qt.AlignLeft)
            description_label.setWordWrap(True)
            if isDarkTheme():
                description_label.setStyleSheet(
                    "font-size: 16px; color: #FAF9F6; font-weight: bold; border: none; background: transparent;")
            else:
                description_label.setStyleSheet(
                    "font-size: 16px; color: #2E2E2E; font-weight: bold; border: none; background: transparent;")
            layout.addWidget(description_label)
        else:
            # 时间信息
            if ship_info.get('datetime'):
                time_label = QLabel(f"📅 {ship_info['datetime']}")
                time_label.setAlignment(Qt.AlignLeft)
                if isDarkTheme():
                    time_label.setStyleSheet(
                        "font-size: 14px; color: #B0B0B0; font-weight: normal; border: none; background: transparent;")
                else:
                    time_label.setStyleSheet(
                        "font-size: 14px; color: #666666; font-weight: normal; border: none; background: transparent;")
                layout.addWidget(time_label)

            # 描述信息
            if ship_info.get('description'):
                description_label = QLabel(ship_info['description'])
                description_label.setAlignment(Qt.AlignLeft)
                description_label.setWordWrap(True)
                if isDarkTheme():
                    description_label.setStyleSheet(
                        "font-size: 16px; color: #FAF9F6; font-weight: bold; margin: 6px 0px; border: none; background: transparent;")
                else:
                    description_label.setStyleSheet(
                        "font-size: 16px; color: #2E2E2E; font-weight: bold; margin: 6px 0px; border: none; background: transparent;")
                layout.addWidget(description_label)

        container.setLayout(layout)
        return container

    @staticmethod
    def clear_existing_content(content_layout):
        """清除布局中的旧内容"""
        while content_layout.count() > 0:
            child = content_layout.takeAt(0).widget()
            if child:
                child.deleteLater()  # 确保子组件被正确销毁

    def auto_scroll(self):
        """自动滚动功能"""
        if not self.test_widget:  # 检查小组件是否存在
            # logger.warning("自动滚动失败，小组件未初始化或已被销毁") 不能加log不然没启用的话日志就被刷爆了
            return

        scroll_area = self.test_widget.findChild(SmoothScrollArea)
        if not scroll_area:
            # logger.warning("无法找到 SmoothScrollArea，停止自动滚动") 实际使用不加log不然有错日志就被刷爆了
            return

        vertical_scrollbar = scroll_area.verticalScrollBar()
        if not vertical_scrollbar:
            # logger.warning("无法找到垂直滚动条，停止自动滚动") 实际使用不加log不然有错日志就被刷爆了
            return

        max_value = vertical_scrollbar.maximum()
        if self.scroll_position >= max_value:
            self.scroll_position = 0  # 滚动回顶部
        else:
            self.scroll_position += 1
        vertical_scrollbar.setValue(self.scroll_position)

    def execute(self):
        """首次执行"""
        self.update_ship_dynamics()
