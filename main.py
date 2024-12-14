import time
import requests
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QWidget, QVBoxLayout
from loguru import logger

WIDGET_CODE = 'widget_test.ui'
WIDGET_NAME = '船班信息 | LaoShui'
WIDGET_WIDTH = 360
API_URL = "https://zyb.ziubao.com/api/v1/getShipDynamics?area=%E5%85%AD%E6%A8%AA%E5%B2%9B&pageSize=5"
CACHE_DURATION = 300  # 缓存更新周期：5分钟


class Plugin:
    def __init__(self, cw_contexts, method):
        self.cw_contexts = cw_contexts
        self.method = method

        self.CONFIG_PATH = f'{cw_contexts["PLUGIN_PATH"]}/config.json'
        self.PATH = cw_contexts['PLUGIN_PATH']

        self.method.register_widget(WIDGET_CODE, WIDGET_NAME, WIDGET_WIDTH)

        # 定时器：每5分钟请求一次船班信息
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

        # 初始数据加载
        self.execute()

    @staticmethod
    def fetch_ship_dynamics():
        """请求船班信息接口并获取数据"""
        try:
            response = requests.get(API_URL)
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
            descriptions = self.fetch_ship_dynamics()
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
        if self.test_widget:
            content_layout = self.find_child_layout(self.test_widget, 'contentLayout')
            content_layout.setSpacing(5)

            # 修改标题
            self.method.change_widget_content(WIDGET_CODE, WIDGET_NAME, WIDGET_NAME)
            # 清除旧内容
            self.clear_existing_content(content_layout)

            # 创建滚动区域并设置内容
            scroll_area = self.create_scroll_area(descriptions)
            content_layout.addWidget(scroll_area)

        logger.success('船班信息更新成功！')

    @staticmethod
    def find_child_layout(widget, layout_name):
        """根据名称查找并返回布局"""
        return widget.findChild(QHBoxLayout, layout_name)

    def create_scroll_area(self, descriptions):
        """创建并返回一个包含船班描述信息的滚动区域"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout()
        scroll_content.setLayout(scroll_content_layout)

        for description in descriptions:
            description_label = self.create_description_label(description)
            scroll_content_layout.addWidget(description_label)

        scroll_area.setWidget(scroll_content)
        return scroll_area

    @staticmethod
    def create_description_label(description):
        """创建一个描述标签并返回"""
        description_label = QLabel(description)
        description_label.setAlignment(Qt.AlignLeft)
        description_label.setWordWrap(True)  # 自动换行
        description_label.setStyleSheet("font-size: 14px; color: #FAF9F6;")
        return description_label

    @staticmethod
    def clear_existing_content(content_layout):
        """清除布局中的旧内容"""
        for i in range(content_layout.count()):
            child_widget = content_layout.itemAt(i).widget()
            if child_widget:
                child_widget.deleteLater()

    def auto_scroll(self):
        """自动滚动功能"""
        scroll_area = self.test_widget.findChild(QScrollArea)
        if scroll_area:
            vertical_scrollbar = scroll_area.verticalScrollBar()
            if vertical_scrollbar:
                max_value = vertical_scrollbar.maximum()
                if self.scroll_position >= max_value:
                    vertical_scrollbar.setValue(0)  # 滚动到顶部
                    self.scroll_position = 0
                else:
                    self.scroll_position += 1
                    vertical_scrollbar.setValue(self.scroll_position)

    def execute(self):
        """首次执行，加载船班信息"""
        self.update_ship_dynamics()

    def update(self, cw_contexts):
        """每秒执行的更新方法"""
        self.cw_contexts = cw_contexts
        logger.debug("更新方法执行。执行轻量级操作。")
