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
    for i in range(len(ports)):
        comport = list(ports[i])
        ports_list.append([i, comport[0], comport[1]])
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

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(format_option)

        # 创建文件处理器
        file_handler = TimedRotatingFileHandler(filename=LOG_PATH + '/' +
                                                file_name,
                                                when='MIDNIGHT',
                                                interval=1,
                                                backupCount=7,
                                                encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(format_option)

        # 统计日志文件名
        count_file_name = 'count-' + time.strftime(
            '%Y-%m-%d', time.localtime(time.time())) + '.log'
        # 统计文件格式
        count_log_formatter = logging.Formatter('%(message)s')
        # 统计日志处理器
        count_handler = TimedRotatingFileHandler(filename='logs/' +
                                                 count_file_name,
                                                 when='MIDNIGHT',
                                                 interval=1,
                                                 backupCount=7,
                                                 encoding='utf-8')
        count_handler.setFormatter(count_log_formatter)
        count_handler.setLevel(logging.FATAL)

        # 将处理器添加到logger对象中
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(count_handler)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self.logger.warn(msg, *args, **kwargs)

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

        if self.recv_queue.empty() == False:
            self.recv_queue.get_nowait()

        if ser.isOpen() == True:
            ser.close()
            logger.info("close serial port: %s success" % ser.port)

        ser = None

    def send_str_data(self, ser, data):
        if ser is None:
            return

        if ser.isOpen() == False:
            return

        logger.info(f"Sent: {data}")
        try:
            ser.write((data + "\n").encode("utf-8"))
        except serial.serialutil.SerialException:
            logger.error("WriteFile failed")

    def send_byte_data(self, ser, data):
        if len(data) == 0:
            return

        if ser is None:
            return

        if ser.isOpen() == False:
            return

        logger.info("send: [%d] %s" % ((len(data) + 1) / 3, data))
        try:
            ser.write(bytearray.fromhex(data))
        except serial.serialutil.SerialException:
            logger.error("WriteFile failed")

    def crc16(self, data: bytes) -> int:
        # 初始化crc为0xFFFF
        crc = 0xFFFF
        # 循环处理每个数据字节
        for byte in data:
            # 将每个数据字节与crc进行异或操作
            crc ^= byte
            # 对crc的每一位进行处理
            for _ in range(8):
                # 如果最低位为1，则右移一位并执行异或0xA001操作(即0x8005按位颠倒后的结果)
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                # 如果最低位为0，则仅将crc右移一位
                else:
                    crc = crc >> 1
        # 返回最终的crc值
        return crc

    def receive_data(self):
        received_data = ""
        while self.recv_thread_enable:
            time.sleep(0.3)
            if self.ser_receive_flag == False:
                continue

            if self.ser is None:
                continue

            if self.ser.isOpen() == False:
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
                # time.sleep(1)
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

                # crc 校验
                crc = self.crc16(received_data[0:cnt - 2]).to_bytes(2, 'big')
                if not (crc[0] == received_data[cnt - 2]
                        and crc[1] == received_data[cnt - 1]):
                    logger.warn("crc check fail")

                self.recv_queue.put(received_data)
            else:
                try:
                    if isinstance(received_data.decode('utf-8'), str):
                        recv_data = received_data.decode()
                        logger.info(recv_data)
                        self.recv_queue.put(recv_data)
                    else:
                        logger.warn("not str")
                except UnicodeDecodeError:
                    logger.warn("UnicodeDecodeError")
                    logger.info(received_data)

    def start_serial_threads(self, ser):
        self.ser = ser
        self.ser_receive_flag = True

        if self.recv_thread_enable == False:
            self.recv_thread_enable = True
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.daemon = True
            self.receive_thread.start()

    def pause_recv_data(self):
        if self.recv_queue.empty() == False:
            self.recv_queue.get_nowait()

        self.ser_receive_flag = False

    def resume_recv_data(self):
        self.ser_receive_flag = True

    def stop_serial_threads(self):
        # self.recv_thread_enable = False
        self.ser_receive_flag = False
        self.ser = None
        # self.receive_thread.join()


class MyFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(MyFrame, self).__init__(*args, **kw)

        self.cat1_ver   = ""  # cat1 软件版本号
        self.csq        = ""  # cat1 信号强度
        self.cat1_imei  = ""  # cat1 IMEI号码
        self.cat1_iccid = ""  # cat1 ICCID号码

        self.auto_detect_flag = False  # 自动检测使能标志
        self.task_run_flag = False  # 检测线程运行检测标志
        self.task_run_enable = False  # 检测线程运行总开关
        self.com1_name = ""  # 串口1 名称
        self.com2_name = ""  # 串口2 名称
        self.ser1 = None  # 串口1 对象句柄
        self.ser2 = None  # 串口2 对象句柄

        self.success_count = 0  # 成功次数统计
        self.fail_count = 0  # 失败次数统计

        self.InitUI()

    def InitUI(self):
        Label_Location_X = 50
        Label_Location_Y = 80

        self.SetTitle('FT_CAT1_IQC_AutoDetect')
        self.SetSize((800, 480))
        self.SetWindowStyle(self.GetWindowStyle() & ~wx.RESIZE_BORDER)
        self.SetWindowStyle(self.GetWindowStyle() & ~wx.MAXIMIZE_BOX)

        panel = wx.Panel(self)

        font_1 = wx.Font(24, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_2 = wx.Font(16, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_3 = wx.Font(16, wx.DECORATIVE, wx.NORMAL, wx.NORMAL)
        font_4 = wx.Font(18, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_5 = wx.Font(18, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_6 = wx.Font(12, wx.DECORATIVE, wx.NORMAL, wx.BOLD)

        self.label_title = wx.StaticText(panel, label="CAT1模块IQC检测程序", style=wx.ALIGN_CENTER)
        self.label_title.SetFont(font_1)
        self.label_title.SetForegroundColour((255, 0, 0))

        # 设置标签的尺寸，使其居中
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.label_title, 0, wx.ALL | wx.CENTER, 25)  # 5是边距
        panel.SetSizer(sizer)

        self.label_sw_vertion = wx.StaticText(panel, label="软件版本号：", pos=(Label_Location_X, Label_Location_Y), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_sw_vertion.SetFont(font_2)
        self.label_sw_vertion_text = wx.StaticText(panel, label="", pos=((Label_Location_X+220), Label_Location_Y))
        self.label_sw_vertion_text.SetFont(font_3)

        self.label_csq = wx.StaticText(panel, label="信号强度：", pos=(Label_Location_X, (Label_Location_Y+50)), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_csq.SetFont(font_2)
        self.label_csq_text = wx.StaticText(panel, label="", pos=((Label_Location_X+220), (Label_Location_Y+50)))
        self.label_csq_text.SetFont(font_3)

        self.label_imei = wx.StaticText(panel, label="IMEI号码：", pos=(Label_Location_X, (Label_Location_Y+100)), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_imei.SetFont(font_2)
        self.label_imei_text = wx.StaticText(panel, label="", pos=((Label_Location_X+220), (Label_Location_Y+100)))
        self.label_imei_text.SetFont(font_3)

        self.label_iccid = wx.StaticText(panel, label="ICCID号码：", pos=(Label_Location_X, (Label_Location_Y+150)), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_iccid.SetFont(font_2)
        self.label_iccid_text = wx.StaticText(panel, label="", pos=((Label_Location_X+220), (Label_Location_Y+150)))
        self.label_iccid_text.SetFont(font_3)

        self.label_result = wx.StaticText(panel, label="检测结果：", pos=((Label_Location_X+50), (Label_Location_Y+210)), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_result.SetFont(font_4)
        self.label_result_text = wx.StaticText(panel, label="", pos=((Label_Location_X+320), (Label_Location_Y+210)))
        self.label_result_text.SetFont(font_5)
        self.label_result_text.SetForegroundColour((0, 255, 0))

        #异常因素显示
        # self.label_except = wx.StaticText(panel, label="异常原因：", pos=((Label_Location_X-30), (Label_Location_Y+250)), size=(30, 30), style=wx.ALIGN_LEFT)
        # self.label_except.SetFont(font_6)
        # self.label_except.SetForegroundColour((240, 240, 240, 0.5))
        self.label_except_text = wx.StaticText(panel, label="", pos=((Label_Location_X+10), (Label_Location_Y+260)), size=(600, 30), style=wx.ALIGN_CENTRE)
        self.label_except_text.SetFont(font_6)
        self.label_except_text.SetForegroundColour((250, 0, 0))

        self.button = wx.Button(panel, label="开始检测", pos=((Label_Location_X+430), (Label_Location_Y+300)), size=(120, 30))
        self.button.Bind(wx.EVT_BUTTON, self.on_button_click)

        # self.statusbar = self.CreateStatusBar()  # 创建状态栏
        # self.statusbar.SetFieldsCount(3)
        # self.statusbar.SetStatusWidths([-1, -1, -2])
        self.statusbar = self.CreateStatusBar()  # 创建状态栏
        self.statusbar.SetFieldsCount(2)
        self.statusbar.SetStatusWidths([-1, -2])        

        self.sc1 = SerialCommunication()
        self.sc2 = SerialCommunication()
        self.ser_ports = get_available_ports()
        show_available_ports(self.ser_ports)

        # 创建串口下拉列表
        # self.serial_list1 = wx.StaticText(panel, label="串口1：", pos=(10, 395), size=(60, 30), style=wx.ALIGN_LEFT)
        # self.cb1 = wx.ComboBox(panel, pos=(70, 390), choices=[], style=wx.CB_READONLY)
        # self.cb1.Clear()
        # for item in self.ser_ports:
        #     if item[2].startswith("ASR"):
        #         self.cb1.Append(item[1] + "  " + item[2])

        # if self.cb1.GetCount() > 0:
        #     self.cb1.SetSelection(0)
        #     self.com1_name = self.cb1.GetStringSelection().split(' ')[0]
        #     self.statusbar.SetStatusText(self.com1_name + " 未连接", 0)
        # else:
        #     self.statusbar.SetStatusText("串口1未识别, 请检查！", 0)

        # self.cb1.Bind(wx.EVT_COMBOBOX, self.OnSelect1)

        # self.serial_list2 = wx.StaticText(panel, label="串口2：", pos=(210, 395), size=(60, 30), style=wx.ALIGN_LEFT)
        self.serial_list2 = wx.StaticText(panel, label="串口：", pos=((Label_Location_X-15), (Label_Location_Y+300)), size=(40, 30), style=wx.ALIGN_LEFT)        
        self.cb2 = wx.ComboBox(panel, pos=((Label_Location_X+30), (Label_Location_Y+300)), size=(150, 30), style=wx.CB_READONLY)
        self.cb2.Clear()
        for item in self.ser_ports:
            if not item[2].startswith("ASR"):
                self.cb2.Append(item[1] + "  " + item[2])

        if self.cb2.GetCount() > 0:
            self.cb2.SetSelection(0)
            self.com2_name = self.cb2.GetStringSelection().split(' ')[0]
            # self.statusbar.SetStatusText(self.com2_name + " 未连接", 1)
            self.statusbar.SetStatusText(self.com2_name + " 未连接", 0)
        else:
            # self.statusbar.SetStatusText("未找到串口2, 请检查！", 1)
            self.statusbar.SetStatusText("未找到串口, 请检查！", 0)

        # self.statusbar.SetStatusText("   成功: " + str(self.success_count) + "       失败: " + str(self.fail_count), 2)
        self.statusbar.SetStatusText("   成功: " + str(self.success_count) + "       失败: " + str(self.fail_count), 1)

        self.cb2.Bind(wx.EVT_COMBOBOX, self.OnSelect2)
        self.Bind(wx.EVT_CLOSE, self.CloseWindow)  # 判断窗口关闭

        # logger.info("当前选择：%s\n com1_name: %s" % (self.cb1.GetStringSelection(), self.com1_name))
        logger.info("当前选择：%s\n com2_name: %s" % (self.cb2.GetStringSelection(), self.com2_name))

        self.load_config()

        # 自动检测串口线程
        auto_detect_thread = threading.Thread(target=self.auto_detect_serial)
        auto_detect_thread.daemon = True
        auto_detect_thread.start()

    def OnSelect1(self, e):
        str = e.GetString()
        self.com1_name = str.split(' ')[0]
        logger.info("当前选择：%s\n com1_name: %s" % (str, self.com1_name))

    def OnSelect2(self, e):
        str = e.GetString()
        self.com2_name = str.split(' ')[0]
        logger.info("当前选择：%s\n com2_name: %s" % (str, self.com2_name))

    def CloseWindow(self, event):
        # 弹出确认对话框
        result = wx.MessageBox("确定要退出吗？", "确认", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        if result == wx.YES:
            self.Destroy()  # 确认则关闭窗口
        else:
            event.Veto()  # 否则取消关闭

    def load_config(self):
        try:
            with open("config.json", 'r', encoding='UTF-8') as f:
                buf = json.load(f)
                self.target_version = buf.get('target_version')
                logger.info("target_version: %s" % self.target_version)
        except FileNotFoundError:
            logger.error("config.json not found")
            wx.MessageBox("配置文件加载失败，请检查！", "错误", wx.OK | wx.ICON_ERROR)
            return None

    def get_cat1_imei(self):
        if self.ser1 is not None:
            while self.sc1.recv_queue.empty() == False:
                self.sc1.recv_queue.get_nowait()

            self.sc1.send_str_data(self.ser1, "AT+GSN=1\r\n")

            try:
                data_str = self.sc1.recv_queue.get(timeout=1)
            except queue.Empty:
                return

            if data_str.find("+GSN:"):
                data_str = data_str.split("\r\n")
                if len(data_str) > 3:
                    result = data_str[3]
                    imei = data_str[1]
                else:
                    result = ""
                    imei = ""

            if (result == "OK"):
                logger.info("imei %s" % imei)
                if imei.find("+GSN:") != -1:
                    imei = imei.split("+GSN:")
                    if len(imei) > 1:
                        imei = imei[1].strip()
                    logger.info("get imei is {0}".format(imei))
                    self.cat1_imei = imei.strip()
            else:
                logger.info("get data is {0}".format(data_str))
                return

    def get_cat1_iccid(self):
        if self.ser1 is not None:
            while self.sc1.recv_queue.empty() == False:
                self.sc1.recv_queue.get_nowait()

            self.sc1.send_str_data(self.ser1, "AT+ICCID\r\n")

            try:
                data_str = self.sc1.recv_queue.get(timeout=1)
            except queue.Empty:
                return

            if data_str.find("+ICCID:"):
                data_str = data_str.split("\r\n")
                if len(data_str) > 3:
                    result = data_str[3]
                    iccid = data_str[1]
                else:
                    result = ""
                    iccid = ""

            if (result == "OK"):
                iccid = iccid.split("+ICCID:")[1]
                logger.info("get iccid is {0}".format(iccid))
                self.cat1_iccid = iccid.strip()
            else:
                logger.error("get data is {0}".format(data_str))
                return

    def get_cat1_version(self):
        if self.ser2 is not None:
            while self.sc2.recv_queue.empty() == False:
                self.sc2.recv_queue.get_nowait()

            data = "F4 F5 00 0A 02 03 09 00 00 00 00 00 E3 08"
            self.sc2.send_byte_data(self.ser2, data)

            try:
                data_str = self.sc2.recv_queue.get(timeout=1)
            except queue.Empty:
                return ""

            self.cat1_ver   = ""
            self.cat1_imei  = ""
            self.cat1_iccid = ""
            if (data_str[0] == 0xF4 and data_str[1] == 0xF5):
                try:
                    self.cat1_ver   = data_str[8:23].decode('utf-8')
                    self.cat1_imei  = data_str[25:40].decode('utf-8')
                    self.cat1_iccid = data_str[40:60].decode('utf-8')
                except Exception as e:
                    logger.error("decode error is {0}".format(e))

                self.csq = data_str[24] - 256
            
            logger.info("cat1_ver is {0}".format(self.cat1_ver))
            logger.info("csq is {0}".format(self.csq))
            logger.info("cat1_imei is {0}".format(self.cat1_imei))
            logger.info("cat1_iccid is {0}".format(self.cat1_iccid))


    def detect_task(self):
        cnt = 3
        while self.task_run_enable:
            if self.task_run_flag == False:
                time.sleep(1)
                cnt = 3
                continue

            if cnt != 0:
                # # 查询IMEI号
                # self.get_cat1_imei()
                # if self.task_run_flag:
                #     self.label_imei_text.SetLabelText(self.cat1_imei)

                # # 查询ICCID
                # self.get_cat1_iccid()
                # if self.task_run_flag:
                #     self.label_iccid_text.SetLabelText(self.cat1_iccid)

                # 查询版本号
                self.get_cat1_version()
                if self.task_run_flag and self.cat1_ver != "":
                    self.label_sw_vertion_text.SetLabelText(self.cat1_ver)
                    self.label_csq_text.SetLabelText(str(self.csq) + " dBm")
                    self.label_imei_text.SetLabelText(self.cat1_imei)
                    self.label_iccid_text.SetLabelText(self.cat1_iccid)

                cnt -= 1

                if cnt == 0:
                    if self.target_version == self.cat1_ver:
                        self.label_result_text.SetLabelText("PASS")
                        self.label_result_text.SetForegroundColour((0, 255, 0))
                        self.success_count += 1
                        logger.count_log(self.cat1_imei + "   PASS")
                    else:
                        self.label_result_text.SetLabelText("FAIL")
                        self.label_result_text.SetForegroundColour((255, 0, 0))

                        self.label_except_text.SetLabelText('软件版本号错误，请检查配置文件或确认模块版本号！')
                        self.label_except_text.SetForegroundColour((255, 0, 0))

                        self.fail_count += 1
                        logger.count_log(self.cat1_imei + "   FAIL")

                    # self.statusbar.SetStatusText("   成功: " + str(self.success_count) + "       失败: " + str(self.fail_count), 2)
                    self.statusbar.SetStatusText("   成功: " + str(self.success_count) + "       失败: " + str(self.fail_count), 1)
                    
                    
            time.sleep(1)

    def on_button_click(self, event):
        if (self.com1_name == self.com2_name):
            wx.MessageBox("串口不能相同", "错误", wx.OK | wx.ICON_ERROR)
            return

        # 清空界面文本显示内容
        self.label_csq_text.SetLabelText("")
        self.label_imei_text.SetLabelText("")
        self.label_iccid_text.SetLabelText("")
        self.label_sw_vertion_text.SetLabelText("")
        self.label_result_text.SetLabelText("")
        self.label_except_text.SetLabelText("")

        if self.button.GetLabelText() == "停止检测":
            self.button.SetLabelText("开始检测")

            self.auto_detect_flag = False
            self.task_run_flag = False
            self.sc1.stop_serial_threads()
            self.sc2.stop_serial_threads()
            self.sc1.close_serial_port(self.ser1)
            self.sc2.close_serial_port(self.ser2)
            # self.statusbar.SetStatusText(self.com1_name + " 未连接", 0)
            # self.statusbar.SetStatusText(self.com2_name + " 未连接", 1)
            self.statusbar.SetStatusText(self.com2_name + " 未连接", 0)
            return

        # self.ser1 = self.sc1.open_serial_port(self.com1_name, 115200)
        # self.ser2 = self.sc2.open_serial_port(self.com2_name, 9600)

        # if not (self.ser1 and self.ser2):
        #     self.sc1.close_serial_port(self.ser1)
        #     self.sc2.close_serial_port(self.ser2)
        #     if not self.ser1:
        #         wx.MessageBox("串口1 " + self.com1_name + " 打开失败", "错误", wx.OK | wx.ICON_ERROR)
        #     else:
        #         wx.MessageBox("串口2 " + self.com2_name + " 打开失败", "错误", wx.OK | wx.ICON_ERROR)
        #     return
        self.ser2 = self.sc2.open_serial_port(self.com2_name, 9600)

        if not (self.ser2):
            self.sc2.close_serial_port(self.ser2)
            wx.MessageBox("串口 " + self.com2_name + " 打开失败", "错误", wx.OK | wx.ICON_ERROR)
            return        

        # if self.ser1 is not None:
        #     self.statusbar.SetStatusText(self.com1_name + " 已连接", 0)
        #     self.sc1.start_serial_threads(self.ser1)
        # else:
        #     self.statusbar.SetStatusText(self.com1_name + " 连接失败", 0)

        # if self.ser2 is not None:
        #     self.statusbar.SetStatusText(self.com2_name + " 已连接", 1)
        #     self.sc2.start_serial_threads(self.ser2)
        # else:
        #     self.statusbar.SetStatusText(self.com2_name + " 连接失败", 1)
        if self.ser2 is not None:
            self.statusbar.SetStatusText(self.com2_name + " 已连接", 0)
            self.sc2.start_serial_threads(self.ser2)
        else:
            self.statusbar.SetStatusText(self.com2_name + " 连接失败", 0)        

        # 启动检测线程
        self.button.SetLabelText("停止检测")
        self.task_run_flag = True
        self.auto_detect_flag = True
        if self.task_run_enable == False:
            self.task_run_enable = True
            self.task_thread = threading.Thread(target=self.detect_task)
            self.task_thread.daemon = True
            self.task_thread.start()

    # 恢复自动检测
    def resume_auto_detect(self):
        self.label_csq_text.SetLabelText("")
        self.label_imei_text.SetLabelText("")
        self.label_iccid_text.SetLabelText("")
        self.label_sw_vertion_text.SetLabelText("")
        self.label_result_text.SetLabelText("")
        self.label_except_text.SetLabelText("")

        # if self.ser1 and self.ser2:
        #     self.sc1.resume_recv_data()
        #     self.sc2.resume_recv_data()
        #     self.task_run_flag = True
        if self.ser2:
            self.sc2.resume_recv_data()
            self.task_run_flag = True        

    # 串口自动检测线程
    def auto_detect_serial(self):
        removeList = []
        addList = []

        while True:
            current_ports = get_available_ports()
            if self.ser_ports != current_ports:
                removeList = [port for port in self.ser_ports if port not in current_ports]
                if len(removeList) > 0:
                    for port in removeList:
                        logger.info("detect serial remove: %s" % port)
                        remove_index = []
                        # for i in range(self.cb1.GetCount()):
                        #     if port[1] == self.cb1.GetString(i).split(" ")[0]:
                        #         self.task_run_flag = False
                        #         self.sc1.pause_recv_data()  # 任意一个串口插拔所有的都不接收数据
                        #         self.sc2.pause_recv_data()  # 任意一个串口插拔所有的都不接收数据
                        #         if port[1] == self.com1_name:
                        #             self.sc1.stop_serial_threads()
                        #             self.sc1.close_serial_port(self.ser1)
                        #         remove_index.append(i)
                        #         self.statusbar.SetStatusText("", 0)

                        # 统一删除更新列表
                        # for index in remove_index:
                        #     self.cb1.Delete(index)
                        # self.cb1.Refresh()

                        remove_index = []
                        for i in range(self.cb2.GetCount()):
                            if port[1] == self.cb2.GetString(i).split(" ")[0]:
                                self.task_run_flag = False
                                self.sc1.pause_recv_data()  # 任意一个串口插拔所有的都不接收数据
                                self.sc2.pause_recv_data()  # 任意一个串口插拔所有的都不接收数据
                                if port[1] == self.com2_name:
                                    self.sc2.stop_serial_threads()
                                    self.sc2.close_serial_port(self.ser2)
                                remove_index.append(i)
                                self.statusbar.SetStatusText("", 0)

                        # 统一删除更新列表
                        for index in remove_index:
                            self.cb2.Delete(index)
                        self.cb2.Refresh()

                addList = [port for port in current_ports if port not in self.ser_ports]
                if len(addList) > 0:
                    for port in addList:
                        logger.info("detect serial plug: %s" % port)
                        # if port[2].startswith("ASR"):
                        #     if self.cb1.GetCount() == 0:
                        #         self.statusbar.SetStatusText(self.com1_name + " 未连接", 0)

                        #     self.cb1.Append(port[1] + "  " + port[2])
                        #     self.cb1.SetSelection(0)

                        #     if self.com1_name == "":
                        #         self.com1_name = self.cb1.GetStringSelection().split(' ')[0]
                        #         logger.info("当前选择：%s\n com1_name: %s" % (self.cb1.GetStringSelection(), self.com1_name))

                        #     for i in range(self.cb1.GetCount()):
                        #         if self.com1_name == self.cb1.GetString(i).split(" ")[0] and self.com1_name == port[1]:
                        #             self.cb1.SetSelection(i)

                        #             if self.task_run_enable and self.auto_detect_flag:
                        #                 self.ser1 = self.sc1.open_serial_port(self.com1_name, 115200)
                        #                 self.statusbar.SetStatusText(self.com1_name + " 已连接", 0)
                        #                 self.resume_auto_detect()
                        #             else:
                        #                 self.statusbar.SetStatusText(self.com1_name + " 未连接", 0)

                        #     self.cb1.Refresh()
                        # else:
                        if self.cb2.GetCount() == 0:
                            self.statusbar.SetStatusText(self.com2_name + " 未连接", 0)

                        self.cb2.Append(port[1] + "  " + port[2])
                        self.cb2.SetSelection(0)

                        if self.com2_name == "":
                            self.com2_name = self.cb2.GetStringSelection().split(' ')[0]
                            logger.info("当前选择：%s\n com2_name: %s" % (self.cb2.GetStringSelection(), self.com2_name))

                        for i in range(self.cb2.GetCount()):
                            if self.com2_name == self.cb2.GetString(i).split(" ")[0] and self.com2_name == port[1]:
                                self.cb2.SetSelection(i)

                                if self.task_run_enable and self.auto_detect_flag:
                                    self.ser2 = self.sc2.open_serial_port(self.com2_name, 9600)
                                    self.statusbar.SetStatusText(self.com2_name + " 已连接", 0)
                                    self.resume_auto_detect()
                                else:
                                    self.statusbar.SetStatusText(self.com2_name + " 未连接", 0)

                        self.cb2.Refresh()

            # 更新当前列表缓存
            self.ser_ports = current_ports

            time.sleep(2)


def main():
    app = wx.App()
    ex = MyFrame(None)
    ex.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
