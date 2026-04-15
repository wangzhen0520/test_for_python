# coding=utf-8

import wx
import serial
import serial.tools.list_ports
import threading
import time
import queue
import json
import os
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


def get_available_ports():
    ports = serial.tools.list_ports.comports()
    ports_list = []
    for i, port in enumerate(ports):
        ports_list.append([i, port.device, port.description])
    return ports_list


def show_available_ports(ports):
    for item in ports:
        logger.info("%-10s %-10s %-50s" % (item[0], item[1], item[2]))


LOG_PATH = "logs"


class Mylogger:
    def __init__(self) -> None:
        self.logger = None
        self.init_log()

    def init_log(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)

        if not os.path.exists(LOG_PATH):
            os.mkdir(LOG_PATH)

        format_option = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')

        now = datetime.now().strftime("%Y-%m-%d")
        file_name = f'AutoTest_{now}.log'

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(format_option)

        # 文件处理器
        file_handler = TimedRotatingFileHandler(filename=LOG_PATH + '/' + file_name,
                                                when='MIDNIGHT',
                                                interval=1,
                                                backupCount=7,
                                                encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(format_option)

        # 统计日志处理器
        count_file_name = 'count-' + time.strftime('%Y-%m-%d', time.localtime(time.time())) + '.log'
        count_log_formatter = logging.Formatter('%(message)s')
        count_handler = TimedRotatingFileHandler(filename='logs/' + count_file_name,
                                                 when='MIDNIGHT',
                                                 interval=1,
                                                 backupCount=7,
                                                 encoding='utf-8')
        count_handler.setFormatter(count_log_formatter)
        count_handler.setLevel(logging.FATAL)

        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(count_handler)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def count_log(self, msg, *args, **kwargs):
        self.logger.fatal(msg, *args, **kwargs)


logger = Mylogger()


class SerialCommunication:
    def __init__(self):
        self.recv_queue = queue.Queue()
        self.ser_receive_flag = False
        self.recv_thread_enable = False

    def open_serial_port(self, port_name, baud_rate):
        try:
            ser = serial.Serial(port_name, baud_rate)
            logger.info("open serial port: %s success" % port_name)
            return ser
        except serial.serialutil.SerialException:
            logger.error("PermissionError: Please check the permission of the serial port.")
            return None

    def close_serial_port(self, ser):
        if ser is None:
            return
        if not self.recv_queue.empty():
            self.recv_queue.get_nowait()
        if ser.isOpen():
            ser.close()
            logger.info("close serial port: %s success" % ser.port)
        ser = None

    def send_str_data(self, ser, data):
        if ser is None or not ser.isOpen():
            return
        logger.info(f"Sent: {data}")
        try:
            ser.write((data + "\n").encode("utf-8"))
        except serial.serialutil.SerialException:
            logger.error("WriteFile failed")

    def send_byte_data(self, ser, data):
        if len(data) == 0 or ser is None or not ser.isOpen():
            return
        logger.info("send: [%d] %s" % ((len(data) + 1) / 3, data))
        try:
            ser.write(bytearray.fromhex(data))
        except serial.serialutil.SerialException:
            logger.error("WriteFile failed")

    def crc16(self, data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc = crc >> 1
        return crc

    def receive_data(self):
        while self.recv_thread_enable:
            time.sleep(0.3)
            if not self.ser_receive_flag or self.ser is None or not self.ser.isOpen():
                continue

            try:
                cnt = self.ser.in_waiting
                if cnt <= 0:
                    time.sleep(1)
                    continue
                received_data = self.ser.read(cnt)
            except serial.serialutil.SerialException:
                logger.error("receive data SerialException")
                self.ser_receive_flag = False
                continue

            if len(received_data) == 0:
                continue

            if self.recv_queue.qsize() > 2048:
                self.recv_queue.get_nowait()

            if received_data[0] == 0xF4:
                hex_str = ""
                recv_hex_str = received_data.hex()
                for i in range(0, len(recv_hex_str), 2):
                    hex_str += recv_hex_str[i:i + 2].upper() + " "
                logger.info("recv: [%d] %s" % (len(hex_str) / 3, hex_str))

                crc = self.crc16(received_data[0:cnt - 2]).to_bytes(2, 'big')
                if not (crc[0] == received_data[cnt - 2] and crc[1] == received_data[cnt - 1]):
                    logger.warn("crc check fail")

                self.recv_queue.put(received_data)
            else:
                try:
                    recv_data = received_data.decode('utf-8')
                    logger.info(recv_data)
                    self.recv_queue.put(recv_data)
                except UnicodeDecodeError:
                    logger.warn("UnicodeDecodeError")
                    logger.info(received_data)

    def start_serial_threads(self, ser):
        self.ser = ser
        self.ser_receive_flag = True
        if not self.recv_thread_enable:
            self.recv_thread_enable = True
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.daemon = True
            self.receive_thread.start()

    def pause_recv_data(self):
        if not self.recv_queue.empty():
            self.recv_queue.get_nowait()
        self.ser_receive_flag = False

    def resume_recv_data(self):
        self.ser_receive_flag = True

    def stop_serial_threads(self):
        self.ser_receive_flag = False
        self.ser = None
        
class MyFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(MyFrame, self).__init__(*args, **kw)

        self.cat1_ver = ""
        self.csq = ""
        self.cat1_imei = ""
        self.cat1_iccid = ""
        self.target_version = ""
        self.saved_serial = ""
        self.last_imei = ""

        self.auto_detect_flag = False
        self.task_run_flag = False
        self.task_run_enable = False
        self.com_name = ""
        self.ser = None
        self.baud_rate = 9600   # 固定波特率

        self.success_count = 0
        self.fail_count = 0

        self.InitUI()

    def InitUI(self):
        self.SetTitle('方太CAT1模块IQC检测程序')
        self.SetSize((750, 500))
        self.SetMinSize((700, 400))

        panel = wx.Panel(self)
        panel.SetBackgroundColour('#F5F7FA')          # 整体背景色
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------- 标题 ----------
        title = wx.StaticText(panel, label="CAT1模块检测结果")
        title_font = wx.Font(18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        title.SetForegroundColour('#1E3A8A')
        main_sizer.Add(title, 0, wx.ALIGN_CENTER | wx.ALL, 15)

        # 分隔线（自定义颜色）
        line1 = wx.StaticLine(panel)
        line1.SetBackgroundColour('#CBD5E1')
        main_sizer.Add(line1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        # ---------- 信息面板（GridBagSizer）----------
        grid = wx.GridBagSizer(20, 30)

        # 增大字体：标签字体 16 磅加粗，结果字体 20 磅正常
        label_font = wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        value_font = wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        label_color = '#334155'
        value_color = '#0F172A'
    
        style_label = wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL | wx.RIGHT
        style_value = wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL | wx.EXPAND

        # 软件版本
        sw_version_label = wx.StaticText(panel, label="软件版本号：")
        sw_version_label.SetFont(label_font)
        sw_version_label.SetForegroundColour(label_color)
        grid.Add(sw_version_label, pos=(0, 0), flag=style_label, border=20)
        self.label_sw_version = wx.StaticText(panel, label="")
        self.label_sw_version.SetFont(value_font)
        self.label_sw_version.SetForegroundColour(value_color)
        grid.Add(self.label_sw_version, pos=(0, 1), flag=style_value)
        grid.Add(wx.StaticText(panel, label=""), pos=(0, 2))

        # 信号强度（数值 + 图标放在同一格内）
        csq_label = wx.StaticText(panel, label="信号强度：")
        csq_label.SetFont(label_font)
        csq_label.SetForegroundColour(label_color)
        grid.Add(csq_label, pos=(1, 0), flag=style_label, border=20)

        csq_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.label_csq = wx.StaticText(panel, label="")
        self.label_csq.SetFont(value_font)
        self.label_csq.SetForegroundColour(value_color)
        self.label_csq.SetMinSize((80, -1))  # 设定最小宽度，防止被挤压
        csq_sizer.Add(self.label_csq, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 15) # 增加间距

        self.label_signal_icon = wx.StaticText(panel, label="")
        self.label_signal_icon.SetFont(value_font)
        self.label_signal_icon.SetMinSize((40, -1))  # 确保有最小宽度
        csq_sizer.Add(self.label_signal_icon, 0, wx.ALIGN_CENTER_VERTICAL)

        grid.Add(csq_sizer, pos=(1, 1), flag=style_value)
        grid.Add(wx.StaticText(panel, label=""), pos=(1, 2))

        # IMEI
        imei_label = wx.StaticText(panel, label="IMEI号码：")
        imei_label.SetFont(label_font)
        imei_label.SetForegroundColour(label_color)
        grid.Add(imei_label, pos=(2, 0), flag=style_label, border=20)
        self.label_imei = wx.StaticText(panel, label="")
        self.label_imei.SetFont(value_font)
        self.label_imei.SetForegroundColour(value_color)
        grid.Add(self.label_imei, pos=(2, 1), flag=style_value)
        grid.Add(wx.StaticText(panel, label=""), pos=(2, 2))

        # ICCID
        iccid_label = wx.StaticText(panel, label="ICCID号码：")
        iccid_label.SetFont(label_font)
        iccid_label.SetForegroundColour(label_color)
        grid.Add(iccid_label, pos=(3, 0), flag=style_label, border=20)
        self.label_iccid = wx.StaticText(panel, label="")
        self.label_iccid.SetFont(value_font)
        self.label_iccid.SetForegroundColour(value_color)
        grid.Add(self.label_iccid, pos=(3, 1), flag=style_value)
        grid.Add(wx.StaticText(panel, label=""), pos=(3, 2))

        # 检测结果
        result_label = wx.StaticText(panel, label="检测结果：")
        result_label.SetFont(label_font)
        result_label.SetForegroundColour(label_color)
        grid.Add(result_label, pos=(4, 0), flag=style_label, border=20)

        self.label_result = wx.StaticText(panel, label="")
        self.label_result.SetFont(value_font)
        self.label_result.SetForegroundColour(wx.GREEN)
        grid.Add(self.label_result, pos=(4, 1), flag=style_value)
        grid.Add(wx.StaticText(panel, label=""), pos=(4, 2))

        grid.AddGrowableCol(1, 1)
        main_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 15)

        # ---------- 异常提示 ----------
        self.label_except = wx.StaticText(panel, label="")
        self.label_except.SetForegroundColour(wx.RED)
        main_sizer.Add(self.label_except, 0, wx.ALIGN_LEFT | wx.LEFT, 195)

        # 分隔线
        line2 = wx.StaticLine(panel)
        line2.SetBackgroundColour('#CBD5E1')
        main_sizer.Add(line2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ---------- 目标版本配置行（左对齐）----------
        config_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl_target = wx.StaticText(panel, label="目标版本：")
        config_sizer.Add(lbl_target, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5) 
        lbl_prefix = wx.StaticText(panel, label="FIKS-CAT1-")
        config_sizer.Add(lbl_prefix, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        version_choices = [f"CR{str(i).zfill(3)}" for i in range(10, 101)]
        self.cb_version = wx.ComboBox(panel, choices=version_choices, style=wx.CB_DROPDOWN)
        self.cb_version.SetMinSize((100, -1))
        config_sizer.Add(self.cb_version, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 350)

        # 添加灰色小号提示标签
        # hint_label = wx.StaticText(panel, label="(可下拉选择或手动填写)")
        # hint_font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL)
        # hint_label.SetFont(hint_font)
        # hint_label.SetForegroundColour(wx.Colour(128, 128, 128))  # 灰色
        # config_sizer.Add(hint_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 205)

        self.btn_save_version = wx.Button(panel, label="保存版本")
        self.btn_save_version.Hide()
        config_sizer.Add(self.btn_save_version, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 250)

        # 添加弹性空间，将后面的按钮推到最右侧
        config_sizer.AddStretchSpacer(1)

        # 开始检测按钮（加大尺寸，设置初始样式）
        self.btn_start = wx.Button(panel, label="开始检测", size=(120, 40))
        start_font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.btn_start.SetFont(start_font)
        self.btn_start.SetForegroundColour('#3CB371')
        config_sizer.Add(self.btn_start, 0, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(config_sizer, 0, wx.ALIGN_LEFT | wx.ALL, 10)

        # ---------- 串口选择行（左对齐）----------
        serial_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl_serial = wx.StaticText(panel, label="串口：")
        lbl_serial.SetForegroundColour(label_color)
        serial_sizer.Add(lbl_serial, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.cb_serial = wx.ComboBox(panel, style=wx.CB_READONLY)
        self.cb_serial.SetMinSize((400, -1))  # 缩短下拉框长度
        serial_sizer.Add(self.cb_serial, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.btn_refresh_serial = wx.Button(panel, label="刷新")
        serial_sizer.Add(self.btn_refresh_serial, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        main_sizer.Add(serial_sizer, 0, wx.ALIGN_LEFT | wx.ALL, 10)

        panel.SetSizer(main_sizer)

        # ---------- 状态栏 ----------
        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([-2, -1])
        self.statusbar.SetBackgroundColour('#E2E8F0')
        self.statusbar.SetForegroundColour('#475569')
        self.statusbar.SetStatusText("串口未连接", 0)
        self.statusbar.SetStatusText("成功: 0  失败: 0", 1)

        # 绑定事件
        self.btn_refresh_serial.Bind(wx.EVT_BUTTON, self.on_refresh_serial)
        self.btn_save_version.Bind(wx.EVT_BUTTON, self.on_save_version)
        self.btn_start.Bind(wx.EVT_BUTTON, self.on_start_stop)
        self.cb_serial.Bind(wx.EVT_COMBOBOX, self.on_serial_selected)
        self.cb_version.Bind(wx.EVT_TEXT, self.on_version_changed)
        self.Bind(wx.EVT_CLOSE, self.on_close_window)

        # 初始化串口通信对象
        self.sc = SerialCommunication()
        self.ser_ports = get_available_ports()
        show_available_ports(self.ser_ports)

        # 加载配置
        self.load_config()
        self.update_serial_list()
        self.set_default_version()

        # 启动自动检测串口线程
        self.auto_detect_thread = threading.Thread(target=self.auto_detect_serial)
        self.auto_detect_thread.daemon = True
        self.auto_detect_thread.start()

    # ---------- 串口相关 ----------
    def update_serial_list(self):
        self.cb_serial.Clear()
        ports = get_available_ports()
        self.ser_ports = ports
        for port in ports:
            if not port[2].startswith("ASR"):
                self.cb_serial.Append(port[1] + "  " + port[2])

        selected_index = -1
        for i in range(self.cb_serial.GetCount()):
            port_str = self.cb_serial.GetString(i)
            port_name = port_str.split(' ')[0]
            if port_name == self.saved_serial:
                selected_index = i
                break

        if selected_index >= 0:
            self.cb_serial.SetSelection(selected_index)
            self.com_name = self.saved_serial
        else:
            if self.cb_serial.GetCount() > 0:
                self.cb_serial.SetSelection(0)
                self.com_name = self.cb_serial.GetStringSelection().split(' ')[0]
            else:
                self.com_name = ""
        self.update_status_text()

    def update_status_text(self):
        if self.ser and self.ser.isOpen():
            text = f"{self.com_name}  已连接 波特率 {self.baud_rate} "
        else:
            text = f"{self.com_name} 未连接" if self.com_name else "未找到串口"
        self.statusbar.SetStatusText(text, 0)

    def on_refresh_serial(self, event):
        self.update_serial_list()

    def on_serial_selected(self, event):
        selected = event.GetString()
        self.com_name = selected.split(' ')[0]
        logger.info("选择串口：%s" % self.com_name)
        self.save_config()
        self.update_status_text()

    # ---------- 配置管理 ----------
    def load_config(self):
        try:
            with open("config.json", 'r', encoding='UTF-8') as f:
                config = json.load(f)
                self.target_version = config.get('target_version', "")
                self.saved_serial = config.get('serial_port', "")
                logger.info("target_version: %s, serial_port: %s" % (self.target_version, self.saved_serial))
        except FileNotFoundError:
            logger.error("config.json not found")
            self.create_default_config()
            # wx.MessageBox("配置文件加载失败，已创建默认配置！", "提示", wx.OK | wx.ICON_INFORMATION)

    def create_default_config(self):
        default_config = {
            "target_version": "FIKS-CAT1-CR020",
            "serial_port": "",
        }
        try:
            with open("config.json", 'w', encoding='UTF-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            self.target_version = "FIKS-CAT1-CR020"
            self.saved_serial = ""
            logger.info("创建默认配置文件成功")
            if hasattr(self, 'cb_version'):
                self.set_default_version()
        except Exception as e:
            logger.error("创建配置文件失败: %s" % e)

    def save_config(self):
        try:
            with open("config.json", 'r', encoding='UTF-8') as f:
                config = json.load(f)
        except:
            config = {}
        config['target_version'] = self.target_version
        config['serial_port'] = self.com_name
        with open("config.json", 'w', encoding='UTF-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logger.info("配置保存成功: target_version=%s, serial_port=%s" % (self.target_version, self.com_name))

    def set_default_version(self):
        if hasattr(self, 'cb_version') and self.target_version:
            if self.target_version.startswith("FIKS-CAT1-"):
                version_num = self.target_version.replace("FIKS-CAT1-", "")
                self.cb_version.SetValue(version_num)

    def on_version_changed(self, event):
        selected_version = self.cb_version.GetValue()
        if selected_version:
            self.target_version = "FIKS-CAT1-" + selected_version
            self.save_config()
        event.Skip()

    def on_save_version(self, event):
        selected_version = self.cb_version.GetValue()
        if not selected_version:
            wx.MessageBox("请输入或选择版本号！", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        self.target_version = "FIKS-CAT1-" + selected_version
        self.save_config()
        wx.MessageBox("版本已保存: %s" % self.target_version, "成功", wx.OK | wx.ICON_INFORMATION)

    # ---------- 信号强度图标（按档位）----------
    def update_signal_icon(self):
        if not hasattr(self, 'label_signal_icon'):
            return
        try:
            csq_value = int(self.csq)
        except (ValueError, TypeError):
            icon_text, color = "❓", (128, 128, 128)
            self.label_signal_icon.SetLabel(icon_text)
            self.label_signal_icon.SetForegroundColour(color)
            self.label_signal_icon.Refresh()
            return

        if csq_value > -85:
            icon_text, color = "📶📶", '#3CB371'
        elif -90 < csq_value <= -85:
            icon_text, color = "📶📶", (0, 200, 0)
        elif -95 < csq_value <= -90:
            icon_text, color = "📶📶", (255, 165, 0)
        elif -100 < csq_value <= -95:
            icon_text, color = "📶📶", (255, 140, 0)
        elif -105 < csq_value <= -100:
            icon_text, color = "📶📶", (255, 69, 0)
        elif -110 < csq_value <= -105:
            icon_text, color = "📶📶", wx.RED
        else:
            icon_text, color = "⚠️", wx.RED

        # logger.debug("CSQ: %d, Icon: %s, Color: %s" % (csq_value, icon_text, color))
        self.label_signal_icon.SetLabel(icon_text)
        self.label_signal_icon.SetForegroundColour(color)
        self.label_signal_icon.Refresh()

    def clear_detection_result(self):
        """清除界面上的检测结果"""
        self.label_sw_version.SetLabelText("")
        self.label_csq.SetLabelText("")
        self.label_imei.SetLabelText("")
        self.label_iccid.SetLabelText("")
        self.label_result.SetLabelText("")
        self.label_except.SetLabelText("")
        self.label_signal_icon.SetLabel("")  # 重置为默认图标
        self.csq = ""
        self.last_imei = ""  # 重要：重置IMEI记录，确保新模块能触发统计
    
    # ---------- 检测线程（持续发送指令，IMEI去重）----------
    def detect_task(self):
        self.last_imei = ""
        last_send_time = 0
        SEND_INTERVAL = 1.5
        no_response_count = 0           # 无响应计数器
        MAX_NO_RESPONSE = 30             # 最大无响应次数

        while self.task_run_enable:
            if not self.task_run_flag:
                time.sleep(0.2)
                continue

            if self.ser is None or not self.ser.isOpen():
                time.sleep(1)
                continue

            current_time = time.time()
            if current_time - last_send_time >= SEND_INTERVAL:
                data = "F4 F5 00 0A 02 03 09 00 00 00 00 00 E3 08"
                self.sc.send_byte_data(self.ser, data)
                last_send_time = current_time

            try:
                data_bytes = self.sc.recv_queue.get(timeout=0.2)
            except queue.Empty:
                # 无数据时计数器加1
                no_response_count += 1
                if no_response_count >= MAX_NO_RESPONSE:
                    logger.info("连续30次无响应，清除界面结果")
                    # 连续30次无响应，清除界面结果
                    wx.CallAfter(self.clear_detection_result)
                    no_response_count = 0  # 重置，避免反复清除
                continue

            if not (isinstance(data_bytes, (bytes, bytearray)) and len(data_bytes) >= 25
                    and data_bytes[0] == 0xF4 and data_bytes[1] == 0xF5):
                no_response_count = 0
                continue
            
            # 收到有效数据，重置计数器
            no_response_count = 0
        
            ver = imei = iccid = ""
            csq = 0
            try:
                ver   = data_bytes[8:23].decode('utf-8').strip('\x00')
                imei  = data_bytes[25:40].decode('utf-8').strip('\x00')
                iccid = data_bytes[40:60].decode('utf-8').strip('\x00')
                csq   = data_bytes[24] - 256
            except Exception as e:
                logger.error("decode error: %s" % e)
                continue

            wx.CallAfter(self.label_sw_version.SetLabelText, ver)
            wx.CallAfter(self.label_csq.SetLabelText, str(csq) + " dBm")
            wx.CallAfter(self.label_imei.SetLabelText, imei)
            wx.CallAfter(self.label_iccid.SetLabelText, iccid)
            self.csq = csq
            wx.CallAfter(self.update_signal_icon)

            if imei != self.last_imei:
                self.last_imei = imei
                if self.target_version == ver:
                    wx.CallAfter(self.label_result.SetLabelText, "PASS")
                    wx.CallAfter(self.label_result.SetForegroundColour, wx.GREEN)
                    self.success_count += 1
                    # 修改日志记录：包含目标版本和实际版本
                    logger.count_log(f"{imei}   PASS   Target:{self.target_version}   Actual:{ver}")
                else:
                    wx.CallAfter(self.label_result.SetLabelText, "FAIL")
                    wx.CallAfter(self.label_result.SetForegroundColour, wx.RED)
                    wx.CallAfter(self.label_except.SetLabelText, '检测到软件版本号和目标版本不匹配，请确认模块版本是否正确！')
                    wx.CallAfter(self.label_except.SetForegroundColour, wx.RED)
                    self.fail_count += 1
                    # 修改日志记录：包含目标版本和实际版本
                    logger.count_log(f"{imei}   FAIL   Target:{self.target_version}   Actual:{ver}")
                wx.CallAfter(self.statusbar.SetStatusText,
                            "成功: %d  失败: %d" % (self.success_count, self.fail_count), 1)
            else:
                logger.debug("重复上报，IMEI: %s，不重复统计" % imei)

    # ---------- 开始/停止检测 ----------
    def on_start_stop(self, event):
        if self.btn_start.GetLabelText() == "停止检测":
            self.btn_start.SetLabelText("开始检测")
            self.btn_start.SetForegroundColour('#3CB371')
            self.auto_detect_flag = False
            self.task_run_flag = False
            self.sc.stop_serial_threads()
            self.sc.close_serial_port(self.ser)
            self.ser = None
            self.update_status_text()
            # 恢复控件可用状态
            self.cb_serial.Enable(True)
            self.btn_refresh_serial.Enable(True)
            self.cb_version.Enable(True)          # 恢复版本下拉框
            self.btn_save_version.Enable(True)     # 恢复保存版本按钮
            return

        # 清空界面
        self.clear_detection_result()

        if not self.com_name:
            wx.MessageBox("请先选择串口", "错误", wx.OK | wx.ICON_ERROR)
            return

        self.ser = self.sc.open_serial_port(self.com_name, self.baud_rate)
        if not self.ser:
            wx.MessageBox("串口 %s 打开失败" % self.com_name, "错误", wx.OK | wx.ICON_ERROR)
            self.update_status_text()
            return

        self.sc.start_serial_threads(self.ser)
        self.update_status_text()
        self.btn_start.SetLabelText("停止检测")
        self.btn_start.SetForegroundColour(wx.RED)
        self.task_run_flag = True
        self.auto_detect_flag = True
        self.last_imei = ""

        # 禁用所有配置控件
        self.cb_serial.Enable(False)
        self.btn_refresh_serial.Enable(False)
        self.cb_version.Enable(False)          # 禁用版本下拉框
        self.btn_save_version.Enable(False)    # 禁用保存版本按钮

        if not self.sc.recv_queue.empty():
            self.sc.recv_queue.get_nowait()

        if not self.task_run_enable:
            self.task_run_enable = True
            self.task_thread = threading.Thread(target=self.detect_task)
            self.task_thread.daemon = True
            self.task_thread.start()

    # ---------- 自动检测串口插拔 ----------
    def auto_detect_serial(self):
        while True:
            time.sleep(2)
            current_ports = get_available_ports()
            if self.ser_ports != current_ports:
                removed = [p for p in self.ser_ports if p not in current_ports]
                added = [p for p in current_ports if p not in self.ser_ports]

                if removed:
                    for port in removed:
                        logger.info("detect serial remove: %s" % port)
                        if port[1] == self.com_name:
                            self.task_run_flag = False
                            self.sc.pause_recv_data()
                            self.sc.stop_serial_threads()
                            self.sc.close_serial_port(self.ser)
                            self.ser = None
                            wx.CallAfter(self.update_status_text)

                if added:
                    for port in added:
                        logger.info("detect serial plug: %s" % port)
                        if not port[2].startswith("ASR"):
                            if self.auto_detect_flag and self.com_name == port[1]:
                                self.ser = self.sc.open_serial_port(self.com_name, self.baud_rate)
                                if self.ser:
                                    self.sc.start_serial_threads(self.ser)
                                    self.sc.resume_recv_data()
                                    self.task_run_flag = True
                                    wx.CallAfter(self.update_status_text)

                wx.CallAfter(self.update_serial_list)
                self.ser_ports = current_ports

    def on_close_window(self, event):
        result = wx.MessageBox("确定要退出吗？", "确认", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        if result == wx.YES:
            self.task_run_enable = False
            self.sc.stop_serial_threads()
            self.sc.close_serial_port(self.ser)
            self.Destroy()
        else:
            event.Veto()


def main():
    app = wx.App()
    frame = MyFrame(None)
    frame.Center()          # 窗口居中显示
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()