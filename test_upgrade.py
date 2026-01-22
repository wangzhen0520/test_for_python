import wx
import wx.lib.newevent
import wx.adv
import subprocess
import threading
import queue
import re
import os
import sys
import serial
import serial.tools.list_ports
import time
from pathlib import Path
from typing import List, Dict, Tuple

# 定义自定义事件
(ProgressUpdateEvent, EVT_PROGRESS_UPDATE) = wx.lib.newevent.NewEvent()
(OutputUpdateEvent, EVT_OUTPUT_UPDATE) = wx.lib.newevent.NewEvent()
(ProcessCompletedEvent, EVT_PROCESS_COMPLETED) = wx.lib.newevent.NewEvent()
(SerialPortsUpdateEvent, EVT_SERIAL_PORTS_UPDATE) = wx.lib.newevent.NewEvent()
(FlashFileAddedEvent, EVT_FLASH_FILE_ADDED) = wx.lib.newevent.NewEvent()
(FlashFileRemovedEvent, EVT_FLASH_FILE_REMOVED) = wx.lib.newevent.NewEvent()

class SerialPortMonitor(threading.Thread):
    """串口监控线程，检测热插拔"""
    def __init__(self, update_callback, interval=2):
        super().__init__()
        self.update_callback = update_callback
        self.interval = interval
        self._stop_event = threading.Event()
        self.last_ports = set()
        self.daemon = True
    
    def stop(self):
        self._stop_event.set()
    
    def run(self):
        while not self._stop_event.is_set():
            try:
                current_ports = set([p.device for p in serial.tools.list_ports.comports()])
                
                # 检测串口变化
                if current_ports != self.last_ports:
                    self.last_ports = current_ports
                    port_list = list(current_ports)
                    port_list.sort()
                    wx.CallAfter(self.update_callback, port_list)
                
                time.sleep(self.interval)
            except Exception as e:
                print(f"串口监控错误: {e}")
                time.sleep(self.interval)

class FlashFileItem(wx.Panel):
    """烧录文件条目"""
    def __init__(self, parent, index, on_remove_callback):
        super().__init__(parent)
        self.index = index
        self.on_remove_callback = on_remove_callback
        self.init_ui()
    
    def init_ui(self):
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # 文件选择
        hbox.Add(wx.StaticText(self, label=f"文件{self.index+1}:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.file_path = wx.TextCtrl(self, style=wx.TE_READONLY)
        hbox.Add(self.file_path, 1, wx.EXPAND | wx.RIGHT, 5)
        
        browse_btn = wx.Button(self, label="选择文件")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_file)
        hbox.Add(browse_btn, 0, wx.RIGHT, 5)
        
        # 地址输入
        hbox.Add(wx.StaticText(self, label="地址:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.address = wx.TextCtrl(self, value="0x1000", size=(100, -1))
        hbox.Add(self.address, 0, wx.RIGHT, 5)
        
        # 删除按钮
        remove_btn = wx.Button(self, label="×")
        remove_btn.SetMinSize((30, 25))
        remove_btn.SetForegroundColour(wx.RED)
        remove_btn.Bind(wx.EVT_BUTTON, lambda evt: self.on_remove_callback(self.index))
        hbox.Add(remove_btn, 0)
        
        self.SetSizer(hbox)
    
    def on_browse_file(self, event):
        """选择文件"""
        wildcard = "二进制文件 (*.bin)|*.bin|所有文件 (*.*)|*.*"
        dialog = wx.FileDialog(self, "选择烧录文件", 
                              wildcard=wildcard, 
                              style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        
        if dialog.ShowModal() == wx.ID_OK:
            self.file_path.SetValue(dialog.GetPath())
        
        dialog.Destroy()
    
    def get_file_info(self):
        """获取文件信息"""
        path = self.file_path.GetValue().strip()
        addr = self.address.GetValue().strip()
        
        if not path or not addr:
            return None
        
        return {
            'path': path,
            'address': addr
        }

class CommandExecutor(threading.Thread):
    """执行命令的线程类"""
    def __init__(self, cmd, output_queue, progress_queue):
        super().__init__()
        self.cmd = cmd
        self.output_queue = output_queue
        self.progress_queue = progress_queue
        self._stop_event = threading.Event()
        self.daemon = True
        
    def stop(self):
        self._stop_event.set()
        
    def run(self):
        try:
            process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                universal_newlines=True,
                shell=True
            )
            
            while True:
                if self._stop_event.is_set():
                    process.terminate()
                    break
                    
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                    
                if line:
                    self.output_queue.put(line)
                    
                    # 解析烧录进度
                    progress = self.parse_flash_progress(line)
                    if progress is not None:
                        self.progress_queue.put(progress)
            
            return_code = process.wait()
            self.output_queue.put(f"\n进程执行完成，退出码: {return_code}")
            self.progress_queue.put(("completed", return_code))
            
        except Exception as e:
            self.output_queue.put(f"执行错误: {str(e)}")
            self.progress_queue.put(("error", str(e)))
    
    @staticmethod
    def parse_flash_progress(text):
        """解析烧录进度"""
        text = text.strip()
        
        # 匹配擦除进度
        if "EraseFlash" in text:
            return 20
        elif "End 4K Erase" in text:
            return 30
        elif "End 64K Erase" in text:
            return 40
        elif "EraseFlash ->pass" in text:
            return 50
        
        # 匹配写入进度
        if "Begin write to flash" in text:
            return 60
        elif "WriteFlash ->pass" in text:
            return 90
        
        # 匹配文件大小进度
        file_write_pattern = r'file_length : 0x[0-9a-f]+ \((\d+) KB\)'
        match = re.search(file_write_pattern, text)
        if match:
            file_size_kb = int(match.group(1))
            if file_size_kb > 0:
                # 这里可以根据实际写入进度动态计算
                return 70
        
        # 匹配完成
        if "Writing Flash OK" in text:
            return 100
        elif "All Finished Successfully" in text:
            return 100
        
        return None

class ProgressPanel(wx.Panel):
    """进度条面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 标题
        title = wx.StaticText(self, label="烧录进度")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL, 5)
        
        # 进度条
        self.progress_bar = wx.Gauge(self, range=100, size=(-1, 30))
        vbox.Add(self.progress_bar, 0, wx.EXPAND | wx.ALL, 5)
        
        # 进度标签和时间
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.progress_label = wx.StaticText(self, label="准备就绪")
        hbox.Add(self.progress_label, 1, wx.ALIGN_CENTER_VERTICAL)
        
        self.time_label = wx.StaticText(self, label="耗时: --")
        hbox.Add(self.time_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(vbox)
        self.start_time = None
    
    def update_progress(self, value, status=None):
        self.progress_bar.SetValue(value)
        
        if self.start_time is None and value > 0:
            self.start_time = time.time()
        
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.time_label.SetLabel(f"耗时: {elapsed:.1f}s")
        
        if status:
            self.progress_label.SetLabel(status)
        else:
            self.progress_label.SetLabel(f"进度: {value}%")
        
        if value == 100:
            self.start_time = None

class SerialPortPanel(wx.Panel):
    """串口配置面板"""
    def __init__(self, parent, on_port_change_callback):
        super().__init__(parent)
        self.on_port_change_callback = on_port_change_callback
        self.init_ui()
        
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 标题
        title = wx.StaticText(self, label="串口配置")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL, 5)
        
        # 串口选择
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        hbox1.Add(wx.StaticText(self, label="串口:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.port_combo = wx.ComboBox(self, style=wx.CB_READONLY)
        hbox1.Add(self.port_combo, 1, wx.EXPAND | wx.RIGHT, 5)
        
        self.refresh_btn = wx.Button(self, label="刷新")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh_ports)
        hbox1.Add(self.refresh_btn, 0)
        
        vbox.Add(hbox1, 0, wx.EXPAND | wx.ALL, 5)
        
        # 波特率选择
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        hbox2.Add(wx.StaticText(self, label="波特率:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.baudrate_combo = wx.ComboBox(self, value="2000000", 
                                         choices=["115200", "230400", "460800", "921600", "2000000"])
        hbox2.Add(self.baudrate_combo, 0, wx.RIGHT, 5)
        
        vbox.Add(hbox2, 0, wx.EXPAND | wx.ALL, 5)
        
        # UART类型
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.Add(wx.StaticText(self, label="UART类型:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.uart_combo = wx.ComboBox(self, value="CH340", 
                                     choices=["CH340"])
        hbox3.Add(self.uart_combo, 0, wx.RIGHT, 5)
        
        vbox.Add(hbox3, 0, wx.EXPAND | wx.ALL, 5)
        
        # 快速连接选项
        self.fast_link_check = wx.CheckBox(self, label="快速连接 (--fast-link)")
        self.fast_link_check.SetValue(True)
        vbox.Add(self.fast_link_check, 0, wx.ALL, 5)
        
        self.SetSizer(vbox)
        self.refresh_ports()
    
    def on_refresh_ports(self, event):
        """刷新串口列表"""
        self.refresh_ports()
    
    def refresh_ports(self):
        """刷新串口列表"""
        current_selection = self.port_combo.GetValue()
        self.port_combo.Clear()
        
        try:
            ports = serial.tools.list_ports.comports()
            port_names = sorted([port.device for port in ports])
            
            for port in port_names:
                self.port_combo.Append(port)
            
            # 尝试恢复之前的选择
            if current_selection in port_names:
                self.port_combo.SetValue(current_selection)
            elif port_names:
                self.port_combo.SetSelection(0)
        except Exception as e:
            wx.LogError(f"获取串口列表失败: {e}")
    
    def get_config(self):
        """获取串口配置"""
        return {
            'port': self.port_combo.GetValue(),
            'baudrate': self.baudrate_combo.GetValue(),
            'uart_type': self.uart_combo.GetValue(),
            'fast_link': self.fast_link_check.GetValue()
        }
    
    def set_port_list(self, port_list):
        """设置串口列表"""
        current_selection = self.port_combo.GetValue()
        self.port_combo.Clear()
        
        for port in port_list:
            self.port_combo.Append(port)
        
        # 如果当前选择的串口还在列表中，保持选择
        if current_selection in port_list:
            self.port_combo.SetValue(current_selection)
        elif port_list:
            self.port_combo.SetSelection(0)

class FlashFilesPanel(wx.Panel):
    """烧录文件配置面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.file_items = []
        self.init_ui()
    
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 标题和添加按钮
        hbox_title = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, label="烧录文件配置")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        hbox_title.Add(title, 1, wx.ALIGN_CENTER_VERTICAL)
        
        self.add_btn = wx.Button(self, label="添加文件")
        self.add_btn.Bind(wx.EVT_BUTTON, self.on_add_file)
        hbox_title.Add(self.add_btn, 0)
        
        vbox.Add(hbox_title, 0, wx.EXPAND | wx.ALL, 5)
        
        # 文件列表容器
        self.files_container = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.files_container, 1, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(vbox)
        # 默认添加一个文件
        self.add_file_item()
    
    def on_add_file(self, event):
        """添加文件条目"""
        self.add_file_item()
    
    def add_file_item(self):
        """添加文件条目"""
        index = len(self.file_items)
        item = FlashFileItem(self, index, self.on_remove_file)
        self.file_items.append(item)
        self.files_container.Add(item, 0, wx.EXPAND | wx.BOTTOM, 5)
        self.Layout()
        wx.PostEvent(self, FlashFileAddedEvent())
    
    def on_remove_file(self, index):
        """移除文件条目"""
        if 0 <= index < len(self.file_items):
            item = self.file_items.pop(index)
            item.Destroy()
            
            # 重新索引
            for i, item in enumerate(self.file_items):
                item.index = i
            
            self.Layout()
            wx.PostEvent(self, FlashFileRemovedEvent())
    
    def get_files(self):
        """获取所有文件配置"""
        files = []
        for item in self.file_items:
            file_info = item.get_file_info()
            if file_info:
                files.append(file_info)
        return files
    
    def clear_files(self):
        """清空所有文件"""
        for item in self.file_items:
            item.Destroy()
        self.file_items = []
        self.Layout()

class ControlPanel(wx.Panel):
    """控制面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # 烧录按钮
        self.flash_btn = wx.Button(self, label="开始烧录")
        self.flash_btn.SetMinSize((100, 40))
        self.flash_btn.SetBackgroundColour(wx.Colour(76, 175, 80))
        self.flash_btn.SetForegroundColour(wx.WHITE)
        self.flash_btn.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        hbox.Add(self.flash_btn, 0, wx.RIGHT, 10)
        
        # 停止按钮
        self.stop_btn = wx.Button(self, label="停止")
        self.stop_btn.SetMinSize((80, 40))
        self.stop_btn.Disable()
        hbox.Add(self.stop_btn, 0, wx.RIGHT, 10)
        
        # 清空输出按钮
        self.clear_btn = wx.Button(self, label="清空输出")
        self.clear_btn.SetMinSize((80, 40))
        hbox.Add(self.clear_btn, 0, wx.RIGHT, 10)
        
        # 清空文件按钮
        self.clear_files_btn = wx.Button(self, label="清空文件")
        self.clear_files_btn.SetMinSize((80, 40))
        hbox.Add(self.clear_files_btn, 0)
        
        self.SetSizer(hbox)

class OutputPanel(wx.Panel):
    """输出显示面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 标题
        title = wx.StaticText(self, label="输出日志")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL, 5)
        
        # 输出文本框
        self.output_text = wx.TextCtrl(
            self, 
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH | wx.TE_DONTWRAP | wx.HSCROLL
        )
        font = wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.output_text.SetFont(font)
        vbox.Add(self.output_text, 1, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(vbox)
    
    def append_text(self, text, color=None):
        """追加带颜色的文本"""
        if color:
            self.output_text.SetDefaultStyle(wx.TextAttr(color))
        self.output_text.AppendText(text)
        if color:
            self.output_text.SetDefaultStyle(wx.TextAttr(wx.NullColour))
    
    def clear(self):
        self.output_text.Clear()

class BKLoaderApp(wx.Frame):
    """BK7258 SPI Flash烧录工具主窗口"""
    def __init__(self):
        super().__init__(None, title="BK7258 SPI Flash烧录工具", size=(1000, 800))
        
        self.executor_thread = None
        self.output_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.serial_monitor = None
        
        self.init_ui()
        self.setup_timer()
        self.start_serial_monitor()
        
        self.Bind(EVT_OUTPUT_UPDATE, self.on_output_update)
        self.Bind(EVT_PROGRESS_UPDATE, self.on_progress_update)
        self.Bind(EVT_PROCESS_COMPLETED, self.on_process_completed)
        self.Bind(EVT_SERIAL_PORTS_UPDATE, self.on_serial_ports_update)
        
        self.Centre()
        self.Show()
    
    def init_ui(self):
        """初始化UI"""
        main_panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建各面板
        self.progress_panel = ProgressPanel(main_panel)
        main_sizer.Add(self.progress_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # 配置面板（使用分割窗口）
        splitter = wx.SplitterWindow(main_panel, style=wx.SP_3D)
        
        # 左面板：配置
        left_panel = wx.Panel(splitter)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.serial_panel = SerialPortPanel(left_panel, self.on_port_changed)
        left_sizer.Add(self.serial_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        self.files_panel = FlashFilesPanel(left_panel)
        left_sizer.Add(self.files_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        left_panel.SetSizer(left_sizer)
        
        # 右面板：输出
        self.output_panel = OutputPanel(splitter)
        
        splitter.SplitVertically(left_panel, self.output_panel, sashPosition=400)
        splitter.SetMinimumPaneSize(200)
        main_sizer.Add(splitter, 1, wx.EXPAND | wx.ALL, 5)
        
        # 控制面板
        self.control_panel = ControlPanel(main_panel)
        self.control_panel.flash_btn.Bind(wx.EVT_BUTTON, self.on_flash)
        self.control_panel.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        self.control_panel.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear_output)
        self.control_panel.clear_files_btn.Bind(wx.EVT_BUTTON, self.on_clear_files)
        main_sizer.Add(self.control_panel, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        main_panel.SetSizer(main_sizer)
        
        # 创建菜单栏
        self.create_menu()
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = wx.MenuBar()
        
        # 文件菜单
        file_menu = wx.Menu()
        load_config_item = file_menu.Append(wx.ID_OPEN, '加载配置', '加载配置文件')
        save_config_item = file_menu.Append(wx.ID_SAVE, '保存配置', '保存配置文件')
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, '退出', '退出程序')
        self.Bind(wx.EVT_MENU, self.on_load_config, load_config_item)
        self.Bind(wx.EVT_MENU, self.on_save_config, save_config_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        menubar.Append(file_menu, '文件')
        
        # 工具菜单
        tool_menu = wx.Menu()
        auto_detect_item = tool_menu.Append(wx.ID_ANY, '自动检测串口', '自动检测连接的设备')
        reset_item = tool_menu.Append(wx.ID_ANY, '重置设备', '发送重置信号')
        tool_menu.AppendSeparator()
        about_item = tool_menu.Append(wx.ID_ABOUT, '关于', '关于此工具')
        self.Bind(wx.EVT_MENU, self.on_auto_detect, auto_detect_item)
        self.Bind(wx.EVT_MENU, self.on_reset_device, reset_item)
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menubar.Append(tool_menu, '工具')
        
        self.SetMenuBar(menubar)
    
    def start_serial_monitor(self):
        """启动串口监控"""
        self.serial_monitor = SerialPortMonitor(self.on_serial_ports_changed)
        self.serial_monitor.start()
    
    def on_serial_ports_changed(self, port_list):
        """串口列表变化回调"""
        wx.PostEvent(self, SerialPortsUpdateEvent(ports=port_list))
    
    def on_serial_ports_update(self, event):
        """更新串口列表"""
        self.serial_panel.set_port_list(event.ports)
    
    def on_port_changed(self):
        """串口选择变化"""
        # 可以在这里添加串口测试代码
        pass
    
    def setup_timer(self):
        """设置定时器检查队列"""
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(100)
    
    def on_timer(self, event):
        """定时器事件"""
        # 检查输出队列
        while not self.output_queue.empty():
            try:
                output = self.output_queue.get_nowait()
                wx.PostEvent(self, OutputUpdateEvent(text=output))
            except queue.Empty:
                break
        
        # 检查进度队列
        while not self.progress_queue.empty():
            try:
                progress = self.progress_queue.get_nowait()
                if isinstance(progress, tuple) and len(progress) == 2:
                    wx.PostEvent(self, ProcessCompletedEvent(
                        status=progress[0], 
                        data=progress[1]
                    ))
                elif isinstance(progress, int):
                    wx.PostEvent(self, ProgressUpdateEvent(value=progress))
            except queue.Empty:
                break
    
    def on_output_update(self, event):
        """更新输出文本"""
        text = event.text
        
        # 根据内容着色
        if "error" in text.lower() or "fail" in text.lower():
            self.output_panel.append_text(text, wx.RED)
        elif "success" in text.lower() or "pass" in text.lower() or "ok" in text.lower():
            self.output_panel.append_text(text, wx.Colour(0, 128, 0))  # 绿色
        elif "warning" in text.lower():
            self.output_panel.append_text(text, wx.Colour(255, 140, 0))  # 橙色
        else:
            self.output_panel.append_text(text)
    
    def on_progress_update(self, event):
        """更新进度条"""
        progress_texts = {
            20: "开始擦除Flash...",
            30: "4K擦除完成",
            40: "64K擦除完成",
            50: "Flash擦除完成",
            60: "开始写入Flash...",
            70: "正在写入数据...",
            90: "Flash写入完成",
            100: "烧录完成"
        }
        
        status = progress_texts.get(event.value, None)
        self.progress_panel.update_progress(event.value, status)
    
    def on_process_completed(self, event):
        """进程完成事件"""
        if event.status == "completed":
            if event.data == 0:
                self.progress_panel.update_progress(100, "烧录成功完成!")
                self.output_panel.append_text("\n✓ 烧录成功完成!\n", wx.Colour(0, 128, 0))
            else:
                self.progress_panel.update_progress(0, f"烧录失败，退出码: {event.data}")
                self.output_panel.append_text(f"\n✗ 烧录失败，退出码: {event.data}\n", wx.RED)
        elif event.status == "error":
            self.progress_panel.update_progress(0, f"执行错误: {event.data}")
            self.output_panel.append_text(f"\n✗ 执行错误: {event.data}\n", wx.RED)
        
        # 恢复按钮状态
        self.control_panel.flash_btn.Enable()
        self.control_panel.stop_btn.Disable()
    
    def build_command(self):
        """构建烧录命令"""
        serial_config = self.serial_panel.get_config()
        files = self.files_panel.get_files()
        
        if not serial_config['port']:
            wx.MessageBox("请选择串口", "错误", wx.OK | wx.ICON_ERROR)
            return None
        
        if not files:
            wx.MessageBox("请至少添加一个烧录文件", "错误", wx.OK | wx.ICON_ERROR)
            return None
        
        # 构建命令
        cmd_parts = ["bk_loader_nor_ver.exe", "download"]
        
        # 添加串口参数
        port_num = serial_config['port'].replace("COM", "")
        cmd_parts.extend(["-p", port_num])
        
        # 添加波特率
        cmd_parts.extend(["-b", serial_config['baudrate']])
        
        # 添加UART类型
        cmd_parts.extend(["--uart-type", serial_config['uart_type']])
        
        # 添加文件参数
        for file_info in files:
            cmd_parts.append("--mainBin-multi")
            cmd_parts.append(f"{file_info['path']}@{file_info['address']}")
        
        # 添加快速连接参数
        if serial_config['fast_link']:
            cmd_parts.extend(["--fast-link", "1"])
        
        return " ".join(cmd_parts)
    
    def on_flash(self, event):
        """开始烧录"""
        cmd = self.build_command()
        if cmd is None:
            return
        
        # 清空输出
        self.output_panel.clear()
        
        # 重置进度
        self.progress_panel.update_progress(0, "准备烧录...")
        
        # 更新按钮状态
        self.control_panel.flash_btn.Disable()
        self.control_panel.stop_btn.Enable()
        
        # 显示执行的命令
        self.output_panel.append_text(f"执行命令: {cmd}\n", wx.Colour(0, 0, 255))
        self.output_panel.append_text("="*80 + "\n")
        
        # 创建并启动执行线程
        self.executor_thread = CommandExecutor(cmd, self.output_queue, self.progress_queue)
        self.executor_thread.start()
    
    def on_stop(self, event):
        """停止烧录"""
        if self.executor_thread and self.executor_thread.is_alive():
            self.executor_thread.stop()
            self.output_panel.append_text("\n⚠ 烧录已被用户停止\n", wx.Colour(255, 140, 0))
            self.progress_panel.update_progress(0, "烧录已停止")
            
            self.control_panel.flash_btn.Enable()
            self.control_panel.stop_btn.Disable()
    
    def on_clear_output(self, event):
        """清空输出"""
        self.output_panel.clear()
    
    def on_clear_files(self, event):
        """清空文件列表"""
        self.files_panel.clear_files()
        self.files_panel.add_file_item()  # 添加一个空文件
    
    def on_load_config(self, event):
        """加载配置文件"""
        wildcard = "配置文件 (*.json)|*.json|所有文件 (*.*)|*.*"
        dialog = wx.FileDialog(self, "加载配置", wildcard=wildcard,
                              style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        
        if dialog.ShowModal() == wx.ID_OK:
            try:
                import json
                with open(dialog.GetPath(), 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 应用配置
                # 这里可以添加配置加载逻辑
                wx.MessageBox("配置加载成功!", "提示", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"加载配置失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        dialog.Destroy()
    
    def on_save_config(self, event):
        """保存配置文件"""
        wildcard = "配置文件 (*.json)|*.json"
        dialog = wx.FileDialog(self, "保存配置", wildcard=wildcard,
                              style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        
        if dialog.ShowModal() == wx.ID_OK:
            try:
                import json
                config = {
                    'serial': self.serial_panel.get_config(),
                    'files': self.files_panel.get_files()
                }
                
                with open(dialog.GetPath(), 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                wx.MessageBox("配置保存成功!", "提示", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"保存配置失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        dialog.Destroy()
    
    def on_auto_detect(self, event):
        """自动检测设备"""
        self.serial_panel.refresh_ports()
        wx.MessageBox("串口列表已刷新", "提示", wx.OK | wx.ICON_INFORMATION)
    
    def on_reset_device(self, event):
        """重置设备"""
        serial_config = self.serial_panel.get_config()
        if not serial_config['port']:
            wx.MessageBox("请先选择串口", "错误", wx.OK | wx.ICON_ERROR)
            return
        
        # 这里可以添加发送重置信号的具体实现
        wx.MessageBox("重置功能尚未实现", "提示", wx.OK | wx.ICON_INFORMATION)
    
    def on_about(self, event):
        """关于对话框"""
        info = wx.adv.AboutDialogInfo()
        info.SetName("BK7258 SPI Flash烧录工具")
        info.SetVersion("1.0.0")
        info.SetDescription("用于BK7258芯片的Flash烧录工具\n支持多文件烧录和实时进度显示")
        info.SetCopyright("© 2026")
        info.AddDeveloper("wangzhenk@fotile.com")
        
        wx.adv.AboutBox(info)
    
    def on_exit(self, event):
        """退出程序"""
        if self.serial_monitor:
            self.serial_monitor.stop()
        
        if self.executor_thread and self.executor_thread.is_alive():
            self.executor_thread.stop()
            self.executor_thread.join(timeout=1)
        
        self.Destroy()

def main():
    """主函数"""
    app = wx.App(False)
    app.SetAppName("BK7258 SPI Flash Tool")
    BKLoaderApp()
    app.MainLoop()

if __name__ == "__main__":
    main()