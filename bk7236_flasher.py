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
import signal
import psutil
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# 定义自定义事件
(ProgressUpdateEvent, EVT_PROGRESS_UPDATE) = wx.lib.newevent.NewEvent()
(OutputUpdateEvent, EVT_OUTPUT_UPDATE) = wx.lib.newevent.NewEvent()
(ProcessCompletedEvent, EVT_PROCESS_COMPLETED) = wx.lib.newevent.NewEvent()
(SerialPortsUpdateEvent, EVT_SERIAL_PORTS_UPDATE) = wx.lib.newevent.NewEvent()
(FlashFileAddedEvent, EVT_FLASH_FILE_ADDED) = wx.lib.newevent.NewEvent()
(FlashFileRemovedEvent, EVT_FLASH_FILE_REMOVED) = wx.lib.newevent.NewEvent()

def resource_path(relative_path):
    """获取资源文件的路径"""
    if getattr(sys, 'frozen', False): # 是否为打包后的环境
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class ProcessManager:
    """进程管理类，用于快速停止进程"""
    @staticmethod
    def kill_process_tree(pid):
        """终止进程及其所有子进程"""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            
            try:
                parent.terminate()
            except psutil.NoSuchProcess:
                pass
            
            gone, alive = psutil.wait_procs([parent] + children, timeout=3)
            
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
                    
        except (psutil.NoSuchProcess, ProcessLookupError):
            pass
    
    @staticmethod
    def find_processes_by_name(name):
        """根据进程名查找进程"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and name in proc.info['name']:
                    processes.append(proc.info['pid'])
                elif proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if name in cmdline:
                        processes.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return processes

class SerialPortMonitor(threading.Thread):
    """串口监控线程，检测热插拔"""
    def __init__(self, update_callback, interval=2):
        super().__init__()
        self.update_callback = update_callback
        self.interval = interval
        self._stop_event = threading.Event()
        self.last_ports = []
        self.daemon = True
    
    def stop(self):
        self._stop_event.set()
    
    def run(self):
        while not self._stop_event.is_set():
            try:
                ports = []
                for port in serial.tools.list_ports.comports():
                    port_info = {
                        'device': port.device,
                        'description': port.description if port.description else '未知设备',
                        'hwid': port.hwid if port.hwid else '未知ID',
                        'manufacturer': port.manufacturer if port.manufacturer else '未知厂商',
                        'product': port.product if port.product else '未知产品'
                    }
                    ports.append(port_info)
                
                # 按设备名排序
                ports.sort(key=lambda x: x['device'])
                
                if ports != self.last_ports:
                    self.last_ports = ports
                    try:
                        wx.CallAfter(self.update_callback, ports)
                    except wx.PyDeadObjectError:
                        break
                
                time.sleep(self.interval)
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"串口监控错误: {e}")
                time.sleep(self.interval)

class FlashFileItem(wx.Panel):
    """烧录文件条目 - 增加勾选和内部/外部Flash选项"""
    def __init__(self, parent, index, on_remove_callback, on_check_callback):
        super().__init__(parent)
        self.index = index
        self.on_remove_callback = on_remove_callback
        self.on_check_callback = on_check_callback
        self.init_ui()
    
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 第一行：文件选择和地址
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        
        # 是否启用烧录复选框
        self.enable_check = wx.CheckBox(self, label="")
        self.enable_check.SetValue(True)  # 默认勾选
        self.enable_check.Bind(wx.EVT_CHECKBOX, self.on_enable_changed)
        hbox1.Add(self.enable_check, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.file_path = wx.TextCtrl(self, style=wx.TE_READONLY)
        hbox1.Add(self.file_path, 1, wx.EXPAND | wx.RIGHT, 5)
        
        browse_btn = wx.Button(self, label="浏览")
        browse_btn.SetMinSize((50, 25))
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_file)
        hbox1.Add(browse_btn, 0, wx.RIGHT, 2)
        
        hbox1.Add(wx.StaticText(self, label="地址:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        
        self.address = wx.TextCtrl(self, value="", size=(70, -1))
        hbox1.Add(self.address, 0, wx.RIGHT, 5)
        
        self.internal_check = wx.CheckBox(self, label="内部")
        self.internal_check.SetValue(True)  # 默认勾选
        hbox1.Add(self.internal_check, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 0)
        
        # 删除按钮
        remove_btn = wx.Button(self, label="删除")
        remove_btn.SetMinSize((50, 25))
        remove_btn.SetForegroundColour(wx.RED)
        remove_btn.Bind(wx.EVT_BUTTON, lambda evt: self.on_remove_callback(self.index))
        hbox1.Add(remove_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        
        vbox.Add(hbox1, 0, wx.EXPAND | wx.BOTTOM, 5)
        
        self.SetSizer(vbox)
    
    def on_browse_file(self, event):
        wildcard = "二进制文件 (*.bin)|*.bin|所有文件 (*.*)|*.*"
        dialog = wx.FileDialog(self, "选择烧录文件", 
                              wildcard=wildcard, 
                              style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        
        if dialog.ShowModal() == wx.ID_OK:
            self.file_path.SetValue(dialog.GetPath())
        
        dialog.Destroy()
    
    def on_enable_changed(self, event):
        # 当启用状态改变时，通知父组件
        if self.on_check_callback:
            self.on_check_callback(self.index, self.enable_check.GetValue())
    
    def get_file_info(self):
        path = self.file_path.GetValue().strip()
        addr = self.address.GetValue().strip()
        
        if not path or not addr:
            return None
        
        return {
            'path': path,
            'address': addr,
            'enabled': self.enable_check.GetValue(),
            'internal': self.internal_check.GetValue()
        }
    
    def set_file_info(self, file_info):
        """设置文件信息"""
        if 'path' in file_info:
            self.file_path.SetValue(file_info['path'])
        if 'address' in file_info:
            self.address.SetValue(file_info['address'])
        if 'enabled' in file_info:
            self.enable_check.SetValue(file_info['enabled'])
        if 'internal' in file_info:
            self.internal_check.SetValue(file_info['internal'])

class CommandExecutor(threading.Thread):
    """执行命令的线程类"""
    def __init__(self, cmd, output_queue, progress_queue, tool_type="internal", progress_offset=0, callback=None):
        super().__init__()
        self.cmd = cmd
        self.output_queue = output_queue
        self.progress_queue = progress_queue
        self.tool_type = tool_type  # "internal" 或 "external"
        self.progress_offset = progress_offset  # 进度偏移量，用于多个烧录过程的进度合并
        self.callback = callback  # 回调函数
        self._stop_event = threading.Event()
        self._user_stopped = False
        self._current_progress = 0
        self._last_progress_update = 0
        self._has_failure = False
        self._failure_message = ""
        self.process = None
        self.process_pid = None
        self.daemon = True
        
        # 阶段跟踪
        self._current_phase = "idle"
        self._erase_percent = 0
        self._write_percent = 0
        
    def stop(self):
        self._stop_event.set()
        self._user_stopped = True
        
        if self.process and self.process.poll() is None:
            try:
                if self.process_pid:
                    ProcessManager.kill_process_tree(self.process_pid)
                else:
                    self.process.terminate()
                    
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                    
            except Exception:
                pass
        
    def run(self):
        try:
            # 根据工具类型添加前缀
            tool_prefix = "[内部]" if self.tool_type == "internal" else "[外部]"
            
            self.process = subprocess.Popen(
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
            
            self.process_pid = self.process.pid
            
            # 发送初始状态
            try:
                tool_name = "内部Flash" if self.tool_type == "internal" else "外部SPI Flash"
                self.progress_queue.put((self.progress_offset, f"准备{tool_name}烧录..."))
                self.output_queue.put(f"{tool_prefix} 执行命令: {self.cmd}\n")
            except:
                pass
            
            while True:
                if self._stop_event.is_set():
                    if self.process and self.process.poll() is None:
                        try:
                            self.process.terminate()
                            try:
                                self.process.wait(timeout=0.5)
                            except subprocess.TimeoutExpired:
                                self.process.kill()
                                self.process.wait()
                        except Exception:
                            pass
                    
                    try:
                        tool_name = "内部Flash" if self.tool_type == "internal" else "外部SPI Flash"
                        self.progress_queue.put((self.progress_offset, f"用户停止{tool_name}烧录"))
                    except:
                        pass
                    
                    # 调用回调函数，表示烧录被停止
                    if self.callback:
                        wx.CallAfter(self.callback, False, True)  # False表示失败，True表示用户停止
                    break
                    
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None:
                    break
                    
                if line:
                    # 添加工具类型前缀
                    prefixed_line = f"{tool_prefix} {line}"
                    try:
                        self.output_queue.put(prefixed_line)
                    except:
                        break
                    
                    # 检查失败信息
                    failure_detected = self.check_for_failure(line)
                    if failure_detected:
                        self._has_failure = True
                        self._failure_message = failure_detected
                        try:
                            self.output_queue.put(f"{tool_prefix} 检测到失败信息: {failure_detected}\n")
                        except:
                            pass
                    
                    # 解析进度和状态
                    progress_info = self.parse_progress_and_status(line)
                    if progress_info:
                        progress, status = progress_info
                        # 调整进度，考虑偏移量
                        adjusted_progress = self.progress_offset + progress * (100 - self.progress_offset) / 100.0
                        if adjusted_progress > self._current_progress:
                            self._current_progress = adjusted_progress
                            try:
                                self.progress_queue.put((adjusted_progress, status))
                            except:
                                pass
                        
                        self._last_progress_update = time.time()
                        
            # 等待进程完全结束
            return_code = self.process.wait()
            
            if self._user_stopped:
                return
            
            # 根据烧录进度、返回码和失败信息判断结果
            tool_name = "内部Flash" if self.tool_type == "internal" else "外部SPI Flash"
            if self._has_failure:
                try:
                    self.output_queue.put(f"{tool_prefix} 烧录失败: {self._failure_message}，退出码: {return_code}\n")
                    self.progress_queue.put((self.progress_offset, f"{tool_name}烧录失败: {self._failure_message}"))
                except:
                    pass
                # 调用回调函数，表示烧录失败
                if self.callback:
                    wx.CallAfter(self.callback, False, False)  # False表示失败，False表示不是用户停止
            elif self._current_progress >= self.progress_offset + 95:  # 接近完成
                try:
                    self.output_queue.put(f"{tool_prefix} 烧录成功完成，退出码: {return_code}\n")
                    self.progress_queue.put((self.progress_offset + 100, f"{tool_name}烧录成功完成!"))
                except:
                    pass
                # 调用回调函数，表示烧录成功
                if self.callback:
                    wx.CallAfter(self.callback, True, False)  # True表示成功，False表示不是用户停止
            elif self._current_progress > self.progress_offset:
                try:
                    self.output_queue.put(f"{tool_prefix} 烧录未完成，进度: {int(self._current_progress - self.progress_offset)}%，退出码: {return_code}\n")
                    self.progress_queue.put((self.progress_offset, f"{tool_name}烧录未完成，进度: {int(self._current_progress - self.progress_offset)}%"))
                except:
                    pass
                # 调用回调函数，表示烧录部分完成
                if self.callback:
                    wx.CallAfter(self.callback, False, False)  # False表示失败，False表示不是用户停止
            else:
                try:
                    self.output_queue.put(f"{tool_prefix} 烧录失败，退出码: {return_code}\n")
                    self.progress_queue.put((self.progress_offset, f"{tool_name}烧录失败，退出码: {return_code}"))
                except:
                    pass
                # 调用回调函数，表示烧录失败
                if self.callback:
                    wx.CallAfter(self.callback, False, False)  # False表示失败，False表示不是用户停止
            
        except Exception:
            # 异常情况下也调用回调函数
            if self.callback:
                wx.CallAfter(self.callback, False, False)  # False表示失败，False表示不是用户停止
    
    @staticmethod
    def check_for_failure(text):
        text = text.strip()
        
        failure_patterns = [
            (r'connect failed', "串口连接失败"),
            (r'Connect device fail!', "设备连接失败"),
            (r'Writing Flash Failed', "Flash写入失败"),
            (r'EraseFlash ->fail', "Flash擦除失败"),
            (r'WriteFlash ->fail', "Flash写入失败"),
            (r'Timeout', "操作超时"),
            (r'Not found', "未找到设备或文件"),
            (r'Error:', "错误信息"),
            (r'error:', "错误信息"),
            (r'Failed', "失败"),
            (r'failed', "失败"),
            (r'无效', "无效操作或参数"),
            (r'不支持', "不支持的操作"),
        ]
        
        for pattern, message in failure_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                lines = text.split('\n')
                for line in lines:
                    if re.search(pattern, line, re.IGNORECASE):
                        return line.strip()
        
        return None
    
    def parse_progress_and_status(self, text):
        """解析进度和状态信息"""
        text = text.strip()
        
        # 如果包含失败信息，返回失败状态
        if self.check_for_failure(text):
            return (0, "检测到失败信息")
        
        # 连接成功
        if "connect success" in text:
            return (5, "串口连接成功")
        
        # 获取总线
        if "Gotten Bus" in text:
            return (7, "获取设备总线")
        
        # 识别芯片
        if "Current Chip is" in text:
            chip_match = re.search(r'Current Chip is : (\w+)', text)
            if chip_match:
                chip = chip_match.group(1)
                return (10, f"识别到芯片: {chip}")
        
        # 波特率切换成功
        if "Current baudrate" in text and "success" in text:
            return (12, "波特率切换成功")
        
        # Flash解除保护
        if "Unprotecting Flash" in text:
            return (15, "解除Flash保护")
        if "Unprotected Flash ->pass" in text:
            return (20, "Flash保护已解除")
        
        # 文件信息
        if "file_length" in text:
            file_match = re.search(r'file_length : 0x[0-9a-f]+ \((\d+) KB\)', text)
            if file_match:
                size_kb = file_match.group(1)
                return (25, f"文件大小: {size_kb} KB")
        
        # 开始擦除Flash
        if "Begin EraseFlash" in text:
            self._current_phase = "erasing"
            self._erase_percent = 0
            return (30, "开始擦除Flash...")
        
        # 4K擦除
        if "Start 4K Erase" in text:
            return (35, "4K擦除...")
        if "End 4K Erase" in text:
            return (40, "4K擦除完成")
        
        # 64K擦除
        if "Start 64K Erase" in text:
            return (45, "64K擦除...")
        
        # 擦除百分比
        erase_match = re.search(r'Erasing Flash \.\.\. (\d+)%', text)
        if erase_match:
            self._erase_percent = int(erase_match.group(1))
            progress = 45 + (self._erase_percent * 0.15)
            return (int(progress), f"擦除Flash: {self._erase_percent}%")
        
        if "End 64K Erase" in text:
            return (60, "64K擦除完成")
        if "EraseFlash ->pass" in text:
            self._current_phase = "writing"
            self._write_percent = 0
            return (65, "Flash擦除完成")
        
        # 开始写入
        if "Begin write to flash" in text:
            return (70, "开始写入Flash...")
        
        # 写入百分比
        write_match = re.search(r'Writing Flash \.\.\. (\d+)%', text)
        if write_match:
            self._write_percent = int(write_match.group(1))
            progress = 70 + (self._write_percent * 0.20)
            return (int(progress), f"写入Flash: {self._write_percent}%")
        
        # 写入完成
        if "WriteFlash ->pass" in text:
            self._current_phase = "protecting"
            return (90, "Flash写入完成")
        
        # 保护Flash
        if "Enprotect pass" in text:
            self._current_phase = "rebooting"
            return (95, "Flash保护完成")
        
        # 重启
        if "Boot_Reboot" in text:
            return (97, "设备重启中...")
        
        # 烧录完成
        if "Writing Flash OK" in text or "All Finished Successfully" in text:
            return (100, "烧录完成")
        
        # 总耗时
        time_match = re.search(r'Total Test Time : (\d+\.\d+) s', text)
        if time_match:
            time_sec = time_match.group(1)
            return (100, f"烧录完成，耗时: {time_sec}秒")
        
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
        
        # 状态标签和时间
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # 统一的状态标签
        self.status_label = wx.StaticText(self, label="准备就绪")
        self.status_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        hbox.Add(self.status_label, 6, wx.ALIGN_CENTER_VERTICAL)
        
        # 时间标签
        self.time_label = wx.StaticText(self, label="耗时: --")
        self.time_label.SetForegroundColour(wx.Colour(100, 100, 100))
        hbox.Add(self.time_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        
        vbox.Add(hbox, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(vbox)
        self.start_time = None
    
    def update_progress(self, value, status=None):
        try:
            self.progress_bar.SetValue(int(value))
            
            # 启动计时器
            if self.start_time is None and value > 0:
                self.start_time = time.time()
            
            # 更新耗时显示
            if self.start_time:
                elapsed = time.time() - self.start_time
                self.time_label.SetLabel(f"耗时: {elapsed:.3f}s")
            
            # 更新状态显示
            if status:
                self.status_label.SetLabel(status)
            else:
                if value == 0:
                    self.status_label.SetLabel("准备就绪")
                elif value == 100:
                    self.status_label.SetLabel("烧录完成")
                else:
                    self.status_label.SetLabel(f"烧录中... {value}%")
                
        except wx.PyDeadObjectError:
            pass
    
    def reset(self):
        try:
            self.progress_bar.SetValue(0)
            self.status_label.SetLabel("准备就绪")
            self.time_label.SetLabel("耗时: --")
            self.start_time = None
        except wx.PyDeadObjectError:
            pass

class SerialPortPanel(wx.Panel):
    """串口配置面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.port_info_dict = {}  # 存储端口设备名到详细信息的映射
        self.init_ui()
        
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 标题
        title = wx.StaticText(self, label="串口配置")
        title.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL, 5)
        
        # 串口选择
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        hbox1.Add(wx.StaticText(self, label="串   口:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.port_combo = wx.ComboBox(self, style=wx.CB_READONLY)
        self.port_combo.SetToolTip("显示格式: 串口号 - 描述信息")
        hbox1.Add(self.port_combo, 1, wx.EXPAND | wx.RIGHT, 5)
        
        self.refresh_btn = wx.Button(self, label="刷新")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh_ports)
        hbox1.Add(self.refresh_btn, 0)
        
        vbox.Add(hbox1, 0, wx.EXPAND | wx.ALL, 5)
        
        # 波特率选择
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        hbox2.Add(wx.StaticText(self, label="波特率:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.baudrate_combo = wx.ComboBox(self, value="2000000", 
                                         choices=["115200", "512000", "921600", "1000000", "1500000", "2000000", "3000000", "4000000", "5000000", "6000000"])
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
        
        # 大端模式选项（仅内部Flash使用）
        self.big_endian_check = wx.CheckBox(self, label="大端模式 (--big-endian) [仅内部Flash]")
        self.big_endian_check.SetValue(True)
        vbox.Add(self.big_endian_check, 0, wx.ALL, 5)
        
        self.SetSizer(vbox)
        self.refresh_ports()
    
    def on_refresh_ports(self, event):
        self.refresh_ports()
    
    def refresh_ports(self):
        try:
            current_selection = self.port_combo.GetValue()
            self.port_combo.Clear()
            self.port_info_dict.clear()
            
            try:
                ports = serial.tools.list_ports.comports()
                port_info_list = []
                
                for port in ports:
                    # 构建显示文本
                    description = port.description if port.description else "未知设备"
                    display_text = f"{port.device} - {description}"
                    
                    # 存储端口信息
                    self.port_info_dict[display_text] = {
                        'device': port.device,
                        'description': port.description if port.description else '未知设备',
                        'hwid': port.hwid if port.hwid else '未知ID',
                        'manufacturer': port.manufacturer if port.manufacturer else '未知厂商',
                        'product': port.product if port.product else '未知产品'
                    }
                    
                    port_info_list.append(display_text)
                
                # 按设备名排序
                port_info_list.sort()
                
                for display_text in port_info_list:
                    self.port_combo.Append(display_text)
                
                # 尝试恢复之前的选择
                if current_selection in port_info_list:
                    self.port_combo.SetValue(current_selection)
                elif port_info_list:
                    self.port_combo.SetSelection(0)
            except Exception as e:
                print(f"获取串口列表失败: {e}")
        except wx.PyDeadObjectError:
            pass
    
    def get_config(self):
        try:
            selected_text = self.port_combo.GetValue()
            port_device = ""
            
            if selected_text and selected_text in self.port_info_dict:
                port_device = self.port_info_dict[selected_text]['device']
            elif selected_text:
                # 如果没有在字典中找到，尝试解析设备名
                # 格式: COMx - 描述信息
                if " - " in selected_text:
                    port_device = selected_text.split(" - ")[0]
                else:
                    port_device = selected_text
            
            return {
                'port': port_device,
                'baudrate': self.baudrate_combo.GetValue(),
                'uart_type': self.uart_combo.GetValue(),
                'fast_link': self.fast_link_check.GetValue(),
                'big_endian': self.big_endian_check.GetValue()
            }
        except wx.PyDeadObjectError:
            return {}
    
    def set_config(self, config):
        """设置串口配置"""
        try:
            if 'port' in config:
                port_device = config['port']
                # 查找对应的显示文本
                display_text = None
                for text, info in self.port_info_dict.items():
                    if info['device'] == port_device:
                        display_text = text
                        break
                
                if display_text:
                    self.port_combo.SetValue(display_text)
                else:
                    # 如果找不到，尝试直接设置
                    self.port_combo.SetValue(port_device)
            
            if 'baudrate' in config:
                self.baudrate_combo.SetValue(config['baudrate'])
            if 'uart_type' in config:
                self.uart_combo.SetValue(config['uart_type'])
            if 'fast_link' in config:
                self.fast_link_check.SetValue(config['fast_link'])
            if 'big_endian' in config:
                self.big_endian_check.SetValue(config['big_endian'])
        except wx.PyDeadObjectError:
            pass
    
    def set_port_list(self, port_info_list):
        """设置串口列表（用于串口监控更新）"""
        try:
            current_selection = self.port_combo.GetValue()
            self.port_combo.Clear()
            self.port_info_dict.clear()
            
            # 构建显示文本列表
            display_texts = []
            for port_info in port_info_list:
                device = port_info['device']
                description = port_info['description']
                display_text = f"{device} - {description}"
                
                self.port_info_dict[display_text] = port_info
                display_texts.append(display_text)
            
            # 排序
            display_texts.sort()
            
            for display_text in display_texts:
                self.port_combo.Append(display_text)
            
            # 尝试恢复之前的选择
            if current_selection in display_texts:
                self.port_combo.SetValue(current_selection)
            elif display_texts:
                # 如果没有找到完全匹配的，尝试部分匹配
                found = False
                for display_text in display_texts:
                    if current_selection and current_selection.split(" - ")[0] in display_text:
                        self.port_combo.SetValue(display_text)
                        found = True
                        break
                
                if not found:
                    self.port_combo.SetSelection(0)
        except wx.PyDeadObjectError:
            pass

class FlashFilesPanel(wx.Panel):
    """烧录文件配置面板 - 支持滚动显示"""
    def __init__(self, parent):
        super().__init__(parent)
        self.file_items = []
        self.max_files = 10  # 最大文件数量
        self.init_ui()
    
    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 标题和添加按钮
        hbox_title = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(self, label="烧录文件配置")
        title.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        hbox_title.Add(title, 1, wx.ALIGN_CENTER_VERTICAL)
        
        # 添加内部文件按钮
        self.add_internal_btn = wx.Button(self, label="添加内部文件")
        self.add_internal_btn.Bind(wx.EVT_BUTTON, lambda e: self.add_file_item(internal=True))
        hbox_title.Add(self.add_internal_btn, 0, wx.RIGHT, 5)
        
        # 添加外部文件按钮
        self.add_external_btn = wx.Button(self, label="添加外部文件")
        self.add_external_btn.Bind(wx.EVT_BUTTON, lambda e: self.add_file_item(internal=False))
        hbox_title.Add(self.add_external_btn, 0)
        
        vbox.Add(hbox_title, 0, wx.EXPAND | wx.ALL, 5)
        
        # 文件列表容器 - 使用ScrolledWindow支持滚动
        self.scrolled_window = wx.ScrolledWindow(self)
        self.scrolled_window.SetScrollRate(10, 10)
        self.scrolled_window.SetMinSize((-1, 200))  # 设置最小高度
        
        self.files_container = wx.BoxSizer(wx.VERTICAL)
        self.scrolled_window.SetSizer(self.files_container)
        
        vbox.Add(self.scrolled_window, 1, wx.EXPAND | wx.ALL, 5)
        
        # 文件计数标签
        self.file_count_label = wx.StaticText(self, label="文件数: 0/10")
        vbox.Add(self.file_count_label, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 5)
        
        self.SetSizer(vbox)
        # 默认添加一个内部文件
        self.add_file_item(internal=True)
        self.update_file_count()
    
    def add_file_item(self, internal=True):
        # 检查是否达到最大文件数
        if len(self.file_items) >= self.max_files:
            wx.MessageBox(f"最多只能添加{self.max_files}个文件", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        
        index = len(self.file_items)
        item = FlashFileItem(self.scrolled_window, index, self.on_remove_file, self.on_file_check_changed)
        if not internal:
            item.internal_check.SetValue(False)
        self.file_items.append(item)
        self.files_container.Add(item, 0, wx.EXPAND | wx.BOTTOM, 5)
        
        # 调整滚动窗口大小
        self.scrolled_window.SetVirtualSize(self.scrolled_window.GetBestVirtualSize())
        self.scrolled_window.Layout()
        
        wx.PostEvent(self, FlashFileAddedEvent())
        self.update_file_count()
    
    def on_remove_file(self, index):
        if 0 <= index < len(self.file_items):
            item = self.file_items.pop(index)
            item.Destroy()
            
            # 重新索引
            for i, item in enumerate(self.file_items):
                item.index = i
            
            # 调整滚动窗口大小
            self.scrolled_window.SetVirtualSize(self.scrolled_window.GetBestVirtualSize())
            self.scrolled_window.Layout()
            self.scrolled_window.Refresh()
            
            wx.PostEvent(self, FlashFileRemovedEvent())
            self.update_file_count()
    
    def on_file_check_changed(self, index, enabled):
        """当文件勾选状态改变时的回调"""
        # 这里可以添加额外的处理逻辑
        pass
    
    def update_file_count(self):
        """更新文件计数显示"""
        count = len(self.file_items)
        self.file_count_label.SetLabel(f"文件数: {count}/{self.max_files}")
    
    def get_files(self):
        files = []
        for item in self.file_items:
            file_info = item.get_file_info()
            if file_info:
                files.append(file_info)
        return files
    
    def get_internal_files(self):
        """获取内部Flash文件列表（已启用）"""
        internal_files = []
        for item in self.file_items:
            file_info = item.get_file_info()
            if file_info and file_info['enabled'] and file_info['internal']:
                internal_files.append(file_info)
        return internal_files
    
    def get_external_files(self):
        """获取外部SPI Flash文件列表（已启用）"""
        external_files = []
        for item in self.file_items:
            file_info = item.get_file_info()
            if file_info and file_info['enabled'] and not file_info['internal']:
                external_files.append(file_info)
        return external_files
    
    def set_files(self, files):
        """设置文件列表"""
        # 清空现有文件
        self.clear_files()
        
        # 添加新的文件项
        for file_info in files:
            internal = file_info.get('internal', True)
            self.add_file_item(internal=internal)
            # 设置最后一个添加的文件项的信息
            if self.file_items:
                self.file_items[-1].set_file_info(file_info)
        
        # 如果没有文件，添加一个空文件项
        if not files:
            self.add_file_item(internal=True)
        
        self.scrolled_window.SetVirtualSize(self.scrolled_window.GetBestVirtualSize())
        self.scrolled_window.Layout()
        self.update_file_count()
    
    def clear_files(self):
        for item in self.file_items:
            item.Destroy()
        self.file_items = []
        self.scrolled_window.SetVirtualSize(self.scrolled_window.GetBestVirtualSize())
        self.scrolled_window.Layout()
        self.update_file_count()

class ControlPanel(wx.Panel):
    """控制面板 - 现在放在进度面板下面"""
    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        # 使用水平BoxSizer，让按钮在一行中
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # 烧录按钮
        self.flash_btn = wx.Button(self, label="开始烧录")
        self.flash_btn.SetMinSize((100, 40))
        self.flash_btn.SetBackgroundColour(wx.Colour(76, 175, 80))
        self.flash_btn.SetForegroundColour(wx.WHITE)
        self.flash_btn.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        hbox.Add(self.flash_btn, 0, wx.RIGHT, 10)
        
        # 停止按钮（原来的强制停止按钮）
        self.stop_btn = wx.Button(self, label="停止")
        self.stop_btn.SetMinSize((80, 40))
        self.stop_btn.Disable()
        hbox.Add(self.stop_btn, 0, wx.RIGHT, 10)
        
        # 添加一个可拉伸的空间，让后面的按钮靠右
        hbox.AddStretchSpacer(1)
        
        # 清空输出按钮
        self.clear_btn = wx.Button(self, label="清空输出")
        self.clear_btn.SetMinSize((90, 40))
        hbox.Add(self.clear_btn, 0, wx.RIGHT, 10)
        
        # 清空文件按钮
        self.clear_files_btn = wx.Button(self, label="清空文件")
        self.clear_files_btn.SetMinSize((90, 40))
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
        title.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
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
        if color:
            self.output_text.SetDefaultStyle(wx.TextAttr(color))
        self.output_text.AppendText(text)
        if color:
            self.output_text.SetDefaultStyle(wx.TextAttr(wx.NullColour))
    
    def clear(self):
        self.output_text.Clear()

class BKLoaderApp(wx.Frame):
    """BK7236烧录工具主窗口"""
    def __init__(self):
        super().__init__(None, title="BK7236 Flash烧录工具", size=(1000, 700))
        
        self.internal_executor = None
        self.external_executor = None
        self.output_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.serial_monitor = None
        self._closing = False
        self.current_flash_stage = None  # 当前烧录阶段: None, "internal", "external"
        self.waiting_for_reboot = False  # 是否正在等待重启
        
        # 配置文件路径
        self.config_file = os.path.join(os.path.expanduser("./"), ".bk7236_flasher_config.json")
        
        self.init_ui()
        self.setup_timer()
        self.start_serial_monitor()
        
        self.Bind(EVT_OUTPUT_UPDATE, self.on_output_update)
        self.Bind(EVT_PROGRESS_UPDATE, self.on_progress_update)
        self.Bind(EVT_PROCESS_COMPLETED, self.on_process_completed)
        self.Bind(EVT_SERIAL_PORTS_UPDATE, self.on_serial_ports_update)
        
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        self.Centre()
        self.Show()
        
        # 加载上次的配置
        wx.CallLater(500, self.load_last_config)
    
    def init_ui(self):
        main_panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 第一行：进度面板
        self.progress_panel = ProgressPanel(main_panel)
        main_sizer.Add(self.progress_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # 第二行：按钮面板（在进度面板下面）
        self.control_panel = ControlPanel(main_panel)
        main_sizer.Add(self.control_panel, 0, wx.EXPAND | wx.ALL, 10)
        
        # 第三行：配置面板和输出面板
        hbox_middle = wx.BoxSizer(wx.HORIZONTAL)
        
        # 左侧：配置面板容器
        config_container = wx.Panel(main_panel)
        config_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 配置面板标题
        config_title = wx.StaticText(config_container, label="烧录配置")
        config_title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        config_sizer.Add(config_title, 0, wx.ALL, 5)
        
        # 串口配置面板
        self.serial_panel = SerialPortPanel(config_container)
        config_sizer.Add(self.serial_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # 文件配置面板
        self.files_panel = FlashFilesPanel(config_container)
        config_sizer.Add(self.files_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        config_container.SetSizer(config_sizer)
        hbox_middle.Add(config_container, 1, wx.EXPAND | wx.RIGHT, 5)
        
        # 右侧：输出面板
        self.output_panel = OutputPanel(main_panel)
        hbox_middle.Add(self.output_panel, 1, wx.EXPAND)
        
        main_sizer.Add(hbox_middle, 1, wx.EXPAND | wx.ALL, 5)
        
        # 绑定按钮事件
        self.control_panel.flash_btn.Bind(wx.EVT_BUTTON, self.on_flash)
        self.control_panel.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        self.control_panel.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear_output)
        self.control_panel.clear_files_btn.Bind(wx.EVT_BUTTON, self.on_clear_files)
        
        main_panel.SetSizer(main_sizer)
        
        self.create_menu()
    
    def create_menu(self):
        menubar = wx.MenuBar()
        
        # 文件菜单
        file_menu = wx.Menu()
        load_config_item = file_menu.Append(wx.ID_OPEN, '加载配置\tCtrl+O', '加载配置文件')
        save_config_item = file_menu.Append(wx.ID_SAVE, '保存配置\tCtrl+S', '保存配置文件')
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, '退出\tCtrl+Q', '退出程序')
        self.Bind(wx.EVT_MENU, self.on_load_config, load_config_item)
        self.Bind(wx.EVT_MENU, self.on_save_config, save_config_item)
        self.Bind(wx.EVT_MENU, self.on_close_menu, exit_item)
        menubar.Append(file_menu, '文件')
        
        # 工具菜单
        tool_menu = wx.Menu()
        about_item = tool_menu.Append(wx.ID_ABOUT, '关于', '关于此工具')
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menubar.Append(tool_menu, '工具')
        
        self.SetMenuBar(menubar)
    
    def load_last_config(self):
        """加载上次的配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 加载上次的配置
                if 'last_config' in config_data:
                    config = config_data['last_config']
                    self.apply_config(config)
                    
                    # 检查文件是否存在
                    files = config.get('files', [])
                    valid_files = []
                    for file_info in files:
                        if 'path' in file_info and os.path.exists(file_info['path']):
                            valid_files.append(file_info)
                    
                    if len(valid_files) < len(files):
                        wx.MessageBox("部分文件不存在，已从配置中移除", "提示", wx.OK | wx.ICON_INFORMATION)
                        config['files'] = valid_files
                    
        except Exception as e:
            print(f"加载上次配置失败: {e}")
    
    def save_last_config(self):
        """保存当前配置到上次配置"""
        try:
            config = self.get_current_config()
            
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
            else:
                config_data = {}
            
            config_data['last_config'] = config
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存上次配置失败: {e}")
    
    def get_current_config(self):
        """获取当前配置"""
        return {
            'serial': self.serial_panel.get_config(),
            'files': self.files_panel.get_files()
        }
    
    def apply_config(self, config):
        """应用配置"""
        try:
            if 'serial' in config:
                self.serial_panel.set_config(config['serial'])
            
            if 'files' in config:
                self.files_panel.set_files(config['files'])
        except Exception as e:
            wx.MessageBox(f"应用配置失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
    
    def on_close(self, event):
        if self._closing:
            event.Skip()
            return
            
        self._closing = True
        
        # 保存当前配置
        self.save_last_config()
        
        # 停止定时器
        if hasattr(self, 'timer') and self.timer:
            self.timer.Stop()
            self.timer = None
        
        # 停止串口监控线程
        if self.serial_monitor:
            self.serial_monitor.stop()
            self.serial_monitor.join(timeout=0.5)
            self.serial_monitor = None
        
        # 停止烧录线程
        for executor in [self.internal_executor, self.external_executor]:
            if executor and executor.is_alive():
                executor.stop()
                executor.join(timeout=0.5)
                
                if executor.is_alive():
                    try:
                        bk_pids = ProcessManager.find_processes_by_name("bk_loader")
                        for pid in bk_pids:
                            try:
                                ProcessManager.kill_process_tree(pid)
                            except Exception:
                                pass
                    except Exception:
                        pass
        
        # 清空队列
        try:
            while not self.output_queue.empty():
                self.output_queue.get_nowait()
            while not self.progress_queue.empty():
                self.progress_queue.get_nowait()
        except:
            pass
        
        self.Destroy()
    
    def on_close_menu(self, event):
        self.Close()
    
    def start_serial_monitor(self):
        self.serial_monitor = SerialPortMonitor(self.on_serial_ports_changed)
        self.serial_monitor.start()
    
    def on_serial_ports_changed(self, port_info_list):
        if not self._closing:
            try:
                wx.PostEvent(self, SerialPortsUpdateEvent(ports=port_info_list))
            except wx.PyDeadObjectError:
                pass
    
    def on_serial_ports_update(self, event):
        if not self._closing:
            self.serial_panel.set_port_list(event.ports)
    
    def setup_timer(self):
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(100)
    
    def on_timer(self, event):
        if self._closing:
            return
        
        try:
            # 检查输出队列
            while not self.output_queue.empty():
                try:
                    output = self.output_queue.get_nowait()
                    wx.PostEvent(self, OutputUpdateEvent(text=output))
                except queue.Empty:
                    break
                except wx.PyDeadObjectError:
                    self.timer.Stop()
                    return
            
            # 检查进度队列
            while not self.progress_queue.empty():
                try:
                    item = self.progress_queue.get_nowait()
                    if isinstance(item, tuple) and len(item) == 2:
                        progress, status = item
                        wx.PostEvent(self, ProgressUpdateEvent(value=progress, status=status))
                    elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], (str, int)):
                        status, data = item
                        wx.PostEvent(self, ProcessCompletedEvent(status=status, data=data))
                except queue.Empty:
                    break
                except wx.PyDeadObjectError:
                    self.timer.Stop()
                    return
        except Exception:
            pass
    
    def on_output_update(self, event):
        if self._closing:
            return
            
        try:
            text = event.text
            
            text_lower = text.lower()
            if "error" in text_lower or "fail" in text_lower or "failed" in text_lower:
                self.output_panel.append_text(text, wx.RED)
            elif "success" in text_lower or "pass" in text_lower or "ok" in text_lower or "finished successfully" in text_lower:
                self.output_panel.append_text(text, wx.Colour(0, 128, 0))
            elif "warning" in text_lower or "stopped" in text_lower or "停止" in text_lower:
                self.output_panel.append_text(text, wx.Colour(255, 140, 0))
            elif "正在停止" in text_lower:
                self.output_panel.append_text(text, wx.Colour(255, 87, 34))
            elif "[内部]" in text:
                self.output_panel.append_text(text, wx.Colour(0, 0, 180))  # 蓝色
            elif "[外部]" in text:
                self.output_panel.append_text(text, wx.Colour(180, 0, 180))  # 紫色
            else:
                self.output_panel.append_text(text)
        except wx.PyDeadObjectError:
            pass
    
    def on_progress_update(self, event):
        if self._closing:
            return
            
        try:
            if hasattr(event, 'status'):
                self.progress_panel.update_progress(event.value, event.status)
            else:
                self.progress_panel.update_progress(event.value)
        except AttributeError:
            self.progress_panel.update_progress(event.value)
        except wx.PyDeadObjectError:
            pass
    
    def on_process_completed(self, event):
        if self._closing:
            return
            
        try:
            if event.status == "completed" and event.data == 0:
                self.progress_panel.update_progress(100, "烧录成功!")
                self.output_panel.append_text("\n✓ 烧录成功!\n", wx.Colour(0, 128, 0))
                
            elif event.status == "failure":
                self.progress_panel.update_progress(0, "烧录失败")
                self.output_panel.append_text(f"\n✗ 烧录失败，请检查设备连接和配置\n", wx.RED)
                
            elif event.status == "partial":
                self.progress_panel.update_progress(0, f"烧录未完成，进度: {event.data}%")
                self.output_panel.append_text(f"\n⚠ 烧录未完成，进度: {event.data}%\n", wx.Colour(255, 140, 0))
                
            elif event.status == "stopped":
                self.progress_panel.update_progress(0, "用户停止烧录")
                self.output_panel.append_text("\n⚠ 烧录已被用户停止\n", wx.Colour(255, 140, 0))
                
            elif event.status == "error":
                self.progress_panel.update_progress(0, f"烧录错误，返回码: {event.data}")
                self.output_panel.append_text(f"\n✗ 烧录错误，返回码: {event.data}\n", wx.RED)
            
            self.reset_buttons()
        except wx.PyDeadObjectError:
            pass
    
    def reset_buttons(self):
        """重置按钮状态到正常状态"""
        try:
            self.control_panel.flash_btn.Enable()
            self.control_panel.stop_btn.Disable()
            self.current_flash_stage = None
            self.waiting_for_reboot = False
        except wx.PyDeadObjectError:
            pass
    
    def build_internal_command(self):
        """构建内部Flash烧录命令"""
        if self._closing:
            return None
            
        try:
            serial_config = self.serial_panel.get_config()
            internal_files = self.files_panel.get_internal_files()
            
            if not serial_config.get('port'):
                wx.MessageBox("请选择串口", "错误", wx.OK | wx.ICON_ERROR)
                return None
            
            if not internal_files:
                return None  # 没有内部文件需要烧录
            
            cmd_parts = []
            cmd = resource_path(os.path.join("res", "bk_loader.exe"))
            cmd_parts.append(cmd)
            cmd_parts.append("download")
            
            port_num = serial_config['port'].replace("COM", "")
            cmd_parts.extend(["-p", port_num])
            
            cmd_parts.extend(["-b", serial_config['baudrate']])
            
            cmd_parts.extend(["--uart-type", serial_config['uart_type']])
            
            cmd_parts.append("--mainBin-multi")
            
            # 构建文件地址列表
            file_parts = []
            for file_info in internal_files:
                file_parts.append(f"{file_info['path']}@{file_info['address']}")
            
            cmd_parts.append(",".join(file_parts))
            
            if serial_config['big_endian']:
                cmd_parts.append("--big-endian")
            
            if serial_config['fast_link']:
                cmd_parts.extend(["--fast-link", "1"])
            
            return " ".join(cmd_parts)
        except wx.PyDeadObjectError:
            return None
    
    def build_external_command(self):
        """构建外部SPI Flash烧录命令"""
        if self._closing:
            return None
            
        try:
            serial_config = self.serial_panel.get_config()
            external_files = self.files_panel.get_external_files()
            
            if not serial_config.get('port'):
                wx.MessageBox("请选择串口", "错误", wx.OK | wx.ICON_ERROR)
                return None
            
            if not external_files:
                return None  # 没有外部文件需要烧录
            
            cmd_parts = []
            cmd = resource_path(os.path.join("res", "bk_loader_nor_ver.exe"))
            cmd_parts.append(cmd)
            cmd_parts.append("download")
            
            port_num = serial_config['port'].replace("COM", "")
            cmd_parts.extend(["-p", port_num])
            
            cmd_parts.extend(["-b", serial_config['baudrate']])
            
            cmd_parts.extend(["--uart-type", serial_config['uart_type']])
            
            cmd_parts.append("--mainBin-multi")
            
            # 构建文件地址列表
            for file_info in external_files:
                cmd_parts.append(f"{file_info['path']}@{file_info['address']}")
            
            if serial_config['fast_link']:
                cmd_parts.extend(["--fast-link", "1"])
            
            return " ".join(cmd_parts)
        except wx.PyDeadObjectError:
            return None
    
    def on_flash(self, event):
        if self._closing:
            return
            
        # 获取内部和外部文件
        internal_files = self.files_panel.get_internal_files()
        external_files = self.files_panel.get_external_files()
        
        if not internal_files and not external_files:
            wx.MessageBox("请至少勾选一个文件进行烧录", "错误", wx.OK | wx.ICON_ERROR)
            return
        
        try:
            self.output_panel.clear()
            self.progress_panel.reset()
            
            self.control_panel.flash_btn.Disable()
            self.control_panel.stop_btn.Enable()
            
            self.output_panel.append_text("="*80 + "\n")
            self.output_panel.append_text("开始烧录流程...\n", wx.Colour(0, 0, 255))
            self.output_panel.append_text(f"内部Flash文件数: {len(internal_files)}\n")
            self.output_panel.append_text(f"外部SPI Flash文件数: {len(external_files)}\n")
            self.output_panel.append_text("="*80 + "\n")
            
            self.start_time = None
            
            # 先烧录内部Flash
            if internal_files:
                self.current_flash_stage = "internal"
                internal_cmd = self.build_internal_command()
                if internal_cmd:
                    self.internal_executor = CommandExecutor(
                        internal_cmd, 
                        self.output_queue, 
                        self.progress_queue,
                        tool_type="internal",
                        progress_offset=0,
                        callback=self.on_internal_completed  # 设置回调函数
                    )
                    self.internal_executor.start()
                else:
                    self.on_internal_completed(False, False)
            else:
                self.on_internal_completed(True, False)  # 没有内部文件，直接开始外部烧录
            
        except wx.PyDeadObjectError:
            pass
    
    def on_internal_completed(self, success=True, user_stopped=False):
        """内部Flash烧录完成回调"""
        if user_stopped:
            # 用户停止了烧录
            self.output_panel.append_text("\n内部Flash烧录已停止\n", wx.Colour(255, 87, 34))
            self.reset_buttons()
            return
        
        if not success:
            # 内部烧录失败，停止整个流程
            self.output_panel.append_text("\n内部Flash烧录失败，停止外部Flash烧录\n", wx.RED)
            self.reset_buttons()
            return
        
        # 检查是否有外部文件需要烧录
        external_files = self.files_panel.get_external_files()
        
        if external_files:
            # 如果有内部文件和外部文件都需要烧录，等待5秒让设备重启
            internal_files = self.files_panel.get_internal_files()
            if internal_files and external_files:
                self.output_panel.append_text("\n" + "="*80 + "\n", wx.Colour(0, 0, 180))
                self.output_panel.append_text("内部Flash烧录完成，等待5秒设备重启...\n", wx.Colour(0, 0, 180))
                self.output_panel.append_text("="*80 + "\n", wx.Colour(0, 0, 180))
                
                self.waiting_for_reboot = True
                wx.CallLater(5000, self.start_external_flash)
            else:
                # 只有外部文件，直接开始
                self.start_external_flash()
        else:
            # 没有外部文件，完成整个流程
            self.output_panel.append_text("\n✓ 所有烧录任务完成!\n", wx.Colour(0, 128, 0))
            self.reset_buttons()
    
    def start_external_flash(self):
        """开始外部Flash烧录"""
        self.waiting_for_reboot = False
        self.output_panel.append_text("\n" + "="*80 + "\n", wx.Colour(180, 0, 180))
        self.output_panel.append_text("开始外部SPI Flash烧录...\n", wx.Colour(180, 0, 180))
        self.output_panel.append_text("="*80 + "\n", wx.Colour(180, 0, 180))
        
        self.current_flash_stage = "external"
        external_cmd = self.build_external_command()
        if external_cmd:
            self.external_executor = CommandExecutor(
                external_cmd, 
                self.output_queue, 
                self.progress_queue,
                tool_type="external",
                progress_offset=0,
                callback=self.on_external_completed  # 设置回调函数
            )
            self.external_executor.start()
        else:
            self.on_external_completed(False, False)
    
    def on_external_completed(self, success=True, user_stopped=False):
        """外部SPI Flash烧录完成回调"""
        if user_stopped:
            # 用户停止了烧录
            self.output_panel.append_text("\n外部SPI Flash烧录已停止\n", wx.Colour(255, 87, 34))
            self.reset_buttons()
            return
        
        if success:
            self.output_panel.append_text("\n✓ 外部SPI Flash烧录完成!\n", wx.Colour(0, 128, 0))
        else:
            self.output_panel.append_text("\n✗ 外部SPI Flash烧录失败\n", wx.RED)
        
        self.output_panel.append_text("\n" + "="*80 + "\n")
        self.output_panel.append_text("烧录流程结束\n")
        self.output_panel.append_text("="*80 + "\n")
        
        self.reset_buttons()
    
    def on_stop(self, event):
        if self._closing:
            return
            
        try:
            self.output_panel.append_text("\n正在停止烧录...\n", wx.Colour(255, 87, 34))
            self.progress_panel.status_label.SetLabel("停止中...")
            
            # 停止当前烧录阶段的线程
            if self.current_flash_stage == "internal" and self.internal_executor and self.internal_executor.is_alive():
                self.internal_executor.stop()
            elif self.current_flash_stage == "external" and self.external_executor and self.external_executor.is_alive():
                self.external_executor.stop()
            elif self.waiting_for_reboot:
                # 如果在等待重启阶段，直接停止
                self.output_panel.append_text("已取消等待重启\n", wx.Colour(255, 87, 34))
                self.waiting_for_reboot = False
                self.reset_buttons()
            
            # 强制停止所有相关进程
            try:
                bk_pids = ProcessManager.find_processes_by_name("bk_loader")
                for pid in bk_pids:
                    try:
                        ProcessManager.kill_process_tree(pid)
                        self.output_panel.append_text(f"已终止进程 PID: {pid}\n", wx.Colour(255, 87, 34))
                    except Exception:
                        pass
            except Exception:
                pass
            
            wx.CallLater(1000, self.on_stop_completed)
        except wx.PyDeadObjectError:
            pass
    
    def on_stop_completed(self):
        if self._closing:
            return
            
        try:
            self.progress_panel.update_progress(0, "已停止")
            self.output_panel.append_text("\n⚠ 已停止烧录\n", wx.Colour(255, 87, 34))
        except wx.PyDeadObjectError:
            pass
    
    def on_clear_output(self, event):
        if not self._closing:
            self.output_panel.clear()
    
    def on_clear_files(self, event):
        if not self._closing:
            self.files_panel.clear_files()
            self.files_panel.add_file_item(internal=True)
    
    def on_load_config(self, event):
        wildcard = "配置文件 (*.json)|*.json|所有文件 (*.*)|*.*"
        dialog = wx.FileDialog(self, "加载配置", wildcard=wildcard,
                              style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        
        if dialog.ShowModal() == wx.ID_OK:
            file_path = dialog.GetPath()
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.apply_config(config)
                
                wx.MessageBox(f"配置加载成功!\n文件: {os.path.basename(file_path)}", "提示", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"加载配置失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        dialog.Destroy()
    
    def on_save_config(self, event):
        wildcard = "配置文件 (*.json)|*.json"
        dialog = wx.FileDialog(self, "保存配置", wildcard=wildcard,
                              style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        
        if dialog.ShowModal() == wx.ID_OK:
            file_path = dialog.GetPath()
            
            # 确保文件扩展名是.json
            if not file_path.endswith('.json'):
                file_path += '.json'
            
            try:
                config = self.get_current_config()
                
                # 检查文件是否存在
                files = config.get('files', [])
                missing_files = []
                for file_info in files:
                    if 'path' in file_info and not os.path.exists(file_info['path']):
                        missing_files.append(file_info['path'])
                
                if missing_files:
                    response = wx.MessageBox(
                        f"以下文件不存在，是否继续保存配置？\n\n" + "\n".join(missing_files[:3]) + 
                        ("\n..." if len(missing_files) > 3 else ""),
                        "警告", wx.YES_NO | wx.ICON_WARNING
                    )
                    if response != wx.YES:
                        dialog.Destroy()
                        return
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                wx.MessageBox(f"配置保存成功!\n文件: {os.path.basename(file_path)}", "提示", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"保存配置失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        dialog.Destroy()
    
    def on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("BK7236 Flash烧录工具")
        info.SetVersion("1.2.0")
        info.SetDescription("用于BK7236芯片的Flash烧录工具\n支持内部Flash和外部SPI Flash烧录\n支持多文件烧录和实时进度显示")
        info.SetCopyright("© 2024")
        info.AddDeveloper("开发者")
        
        wx.adv.AboutBox(info)

def main():
    import traceback
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: (
        print("Uncaught exception:", exc_type, exc_value),
        traceback.print_tb(exc_traceback)
    )
    
    app = wx.App(False)
    app.SetAppName("BK7236FlashTool")
    
    try:
        frame = BKLoaderApp()
        app.MainLoop()
    except Exception as e:
        print(f"程序异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()