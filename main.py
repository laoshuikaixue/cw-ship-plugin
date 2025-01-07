import time
import requests
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QWidget, QVBoxLayout, QScrollBar
from loguru import logger
from qfluentwidgets import isDarkTheme

WIDGET_CODE = 'widget_ship.ui'
WIDGET_NAME = '船班信息 | LaoShui'
WIDGET_WIDTH = 360
API_URL = "https://zyb.ziubao.com/api/v1/getShipDynamics?area=%E5%85%AD%E6%A8%AA%E5%B2%9B&pageSize=4"
CACHE_DURATION = 1800  # 缓存更新周期：30分钟


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
        self.vScrollBar.scrollValue(-e.angleDelta().y())


class Plugin:
    def __init__(self, cw_contexts, method):
        # if not self.is_saturday():
        #     logger.info("今天不是周六，插件不进行初始化。")
        #     return
        self.cw_contexts = cw_contexts
        self.method = method

        self.CONFIG_PATH = f'{cw_contexts["PLUGIN_PATH"]}/config.json'
        self.PATH = cw_contexts['PLUGIN_PATH']

        self.method.register_widget(WIDGET_CODE, WIDGET_NAME, WIDGET_WIDTH)

        # 定时器：每30分钟请求一次船班信息
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ship_dynamics)
        self.timer.start(CACHE_DURATION * 1000)  # 设置定时器的间隔（毫秒）

        # 缓存数据和上次更新时间
        self.last_fetched = None
        self.cached_descriptions = []

        # 初始化执行
        self.scroll_position = 0
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.auto_scroll)
        self.scroll_timer.start(50)  # 每50毫秒执行一次滚动

    @staticmethod
    def fetch_ship_dynamics():
        """请求船班信息接口并获取数据"""
        try:
            response = requests.get(API_URL, proxies={'http': None, 'https': None})  # 禁用代理
            response.raise_for_status()  # 如果状态码不是200，则抛出异常
            data = response.json().get("data", [])
            return [item.get("description") for item in data]
        except requests.RequestException as e:
            logger.error(f"请求船班信息失败: {e}")
            return []  # 如果请求失败，返回空列表

    def update_ship_dynamics(self):
        """更新船班信息"""
        if self.should_update_cache():
            # 判断是否需要更新缓存
            descriptions = self.retry_fetch()
            if descriptions:
                self.cached_descriptions = descriptions
                self.last_fetched = time.time()
            else:
                descriptions = ["无法获取数据，请稍后再试。"]
        else:
            # 使用缓存的数据
            descriptions = self.cached_descriptions

        # 更新小组件内容
        self.update_widget_content(descriptions)

    def should_update_cache(self):
        """检查是否需要更新缓存"""
        return not self.cached_descriptions or \
            not self.last_fetched or \
            (self.last_fetched + CACHE_DURATION) < time.time()

    def update_widget_content(self, descriptions):
        """更新小组件内容"""
        self.test_widget = self.method.get_widget(WIDGET_CODE)
        if not self.test_widget:  # 如果test_widget为空
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
        scroll_area = self.create_scroll_area(descriptions)
        if scroll_area:
            content_layout.addWidget(scroll_area)
            logger.success('船班信息更新成功！')
        else:
            logger.error("滚动区域创建失败")

    @staticmethod
    def find_child_layout(widget, layout_name):
        """根据名称查找并返回布局"""
        return widget.findChild(QHBoxLayout, layout_name)

    def create_scroll_area(self, descriptions):
        """创建并返回一个包含船班描述信息的滚动区域"""
        scroll_area = SmoothScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollBar:vertical { width: 0px; }")  # 隐藏滚动条

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout()
        scroll_content.setLayout(scroll_content_layout)

        for description in descriptions:
            description_label = self.create_description_label(description)
            scroll_content_layout.addWidget(description_label)

            # 添加分割线
            line = QLabel()
            line.setFixedHeight(1)
            line.setStyleSheet("background-color: #E0E0E0;" if not isDarkTheme() else "background-color: #3A3A3A;")
            scroll_content_layout.addWidget(line)

        scroll_area.setWidget(scroll_content)
        return scroll_area

    @staticmethod
    def create_description_label(description):
        """创建一个描述标签并返回"""
        description_label = QLabel(description)
        description_label.setAlignment(Qt.AlignLeft)
        description_label.setWordWrap(True)  # 自动换行

        # 根据主题设置样式
        if isDarkTheme():
            description_label.setStyleSheet(
                "font-size: 14px; color: #FAF9F6; font-weight: bold;"
            )
        else:
            description_label.setStyleSheet(
                "font-size: 14px; color: #2E2E2E; font-weight: bold;"
            )

        return description_label

    @staticmethod
    def clear_existing_content(content_layout):
        """清除布局中的旧内容"""
        while content_layout.count() > 0:
            child = content_layout.takeAt(0).widget()
            if child:
                child.deleteLater()  # 确保子组件被正确销毁

    @staticmethod
    def is_saturday():
        """判断今天是否是周六"""
        return time.localtime().tm_wday == 5

    def auto_scroll(self):
        """自动滚动功能"""
        if not self.test_widget:  # 检查小组件是否存在
            # logger.warning("自动滚动失败，小组件未初始化或已被销毁") 不能加log不然没启用的话日志就被刷爆了
            return

        scroll_area = self.test_widget.findChild(SmoothScrollArea)
        if not scroll_area:  # 检查滚动区域是否存在
            logger.warning("滚动区域未找到或已被销毁")
            return

        vertical_scrollbar = scroll_area.verticalScrollBar()
        if not vertical_scrollbar:  # 检查滚动条是否存在
            logger.warning("滚动条未找到")
            return

        max_value = vertical_scrollbar.maximum()
        if self.scroll_position >= max_value:
            self.scroll_position = 0  # 滚动回顶部
        else:
            self.scroll_position += 1
        vertical_scrollbar.setValue(self.scroll_position)

    def retry_fetch(self):
        """请求失败后重试获取数据"""
        retries = 3
        for attempt in range(retries):
            descriptions = self.fetch_ship_dynamics()
            if descriptions:
                return descriptions
            logger.warning(f"获取船班信息失败，正在重试 ({attempt + 1}/{retries})...")
            time.sleep(1)  # 重试间隔1秒
        return []

    def execute(self):
        # if not self.is_saturday():
        #     logger.info("今天不是周六，插件不进行初始化。")
        #     return
        """首次执行，加载船班信息"""
        self.update_ship_dynamics()
