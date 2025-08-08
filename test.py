# coding=utf-8

import wx
import os
import serial
import serial.tools.list_ports
import threading
import time
import queue


class SerialCommunication:
    def __init__(self):
        self.recv_queue = queue.Queue()

    def get_available_ports(self):
        ports = serial.tools.list_ports.comports()
        ports_list = []
        for i in range(len(ports)):
            comport = list(ports[i])
            ports_list.append([i, comport[0], comport[1]])

            print("%-10s %-10s %-50s" % (i, comport[0], comport[1]))
        return ports_list

    def detect_serial_port(self, ser):
        return ser.isOpen()

    def open_serial_port(self, port_name, baud_rate):
        try:
            ser = serial.Serial(port_name, baud_rate)
            print("open serial port: %s success" % port_name)
            return ser
        except serial.serialutil.SerialException:
            print("PermissionError: Please check the permission of the serial port.")
            return None

    def close_serial_port(self, ser):
        ser.close()

    def send_str_data(self, ser, data):
        ser.write((data + "\n").encode("utf-8"))
        print(f"Sent: {data}")

    def send_byte_data(self, ser, data):
        if len(data) == 0:
            return

        print("send: [%d] %s" % ((len(data) + 1) / 3, data))
        ser.write(bytearray.fromhex(data))

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
        while True:
            time.sleep(0.3)
            cnt = self.ser.in_waiting
            if cnt <= 0:
                time.sleep(0.1)
                continue

            received_data = self.ser.read(cnt)
            if received_data[0] == 0xF4:
                hex_str = ""
                recv_hex_str = received_data.hex()
                for i in range(0, len(recv_hex_str), 2):
                    hex_str += recv_hex_str[i:i + 2].upper() + " "
                print("recv: [%d] %s" % (len(hex_str) / 3, hex_str))

                # crc 校验
                crc = self.crc16(received_data[0:cnt - 2]).to_bytes(2, 'big')
                if not (crc[0] == received_data[cnt - 2]
                        and crc[1] == received_data[cnt - 1]):
                    print("crc check fail")

                self.recv_queue.put(received_data)
            else:
                try:
                    if isinstance(received_data.decode('utf-8'), str):
                        recv_data = received_data.decode()
                        print(recv_data)
                        self.recv_queue.put(recv_data)
                    else:
                        print("not str")
                except UnicodeDecodeError:
                    print("UnicodeDecodeError")
                    print(received_data)

    def start_serial_threads(self, ser):
        self.ser = ser
        receive_thread = threading.Thread(target=self.receive_data)
        receive_thread.daemon = True
        receive_thread.start()


class MyFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(MyFrame, self).__init__(*args, **kw)
        self.InitUI()

    def InitUI(self):
        self.SetTitle('')
        self.SetSize((800, 480))
        self.SetWindowStyle(self.GetWindowStyle() & ~wx.RESIZE_BORDER)
        self.SetWindowStyle(self.GetWindowStyle() & ~wx.MAXIMIZE_BOX)

        panel = wx.Panel(self)

        font_1 = wx.Font(24, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_2 = wx.Font(16, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_3 = wx.Font(16, wx.DECORATIVE, wx.NORMAL, wx.NORMAL)
        font_4 = wx.Font(18, wx.DECORATIVE, wx.NORMAL, wx.BOLD)
        font_5 = wx.Font(18, wx.DECORATIVE, wx.NORMAL, wx.BOLD)

        self.label_title = wx.StaticText(panel, label="CAT1模块IQC检测程序", style=wx.ALIGN_CENTER)
        self.label_title.SetFont(font_1)
        self.label_title.SetForegroundColour((255, 0, 0))

        # 设置标签的尺寸，使其居中
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.label_title, 0, wx.ALL | wx.CENTER, 25)  # 5是边距
        panel.SetSizer(sizer)

        self.label_sw_vertion = wx.StaticText(
            panel, label="软件版本号：", pos=(
                50, 100), size=(
                200, 30), style=wx.ALIGN_RIGHT)
        self.label_sw_vertion.SetFont(font_2)
        self.label_sw_vertion_text = wx.StaticText(panel, label="FIKS-CAT1-CR010", pos=(270, 100))
        self.label_sw_vertion_text.SetFont(font_3)

        self.label_csq = wx.StaticText(panel, label="信号强度：", pos=(50, 150), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_csq.SetFont(font_2)
        self.label_csq_text = wx.StaticText(panel, label="-88 dBm", pos=(270, 150))
        self.label_csq_text.SetFont(font_3)

        self.label_imei = wx.StaticText(panel, label="IMEI号码：", pos=(50, 200), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_imei.SetFont(font_2)
        self.label_imei_text = wx.StaticText(panel, label="864606062075386", pos=(270, 200))
        self.label_imei_text.SetFont(font_3)

        self.label_iccid = wx.StaticText(panel, label="ICCID号码：", pos=(50, 250), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_iccid.SetFont(font_2)
        self.label_iccid_text = wx.StaticText(panel, label="898608121923C0996921", pos=(270, 250))
        self.label_iccid_text.SetFont(font_3)

        self.label_result = wx.StaticText(panel, label="检测结果：", pos=(130, 320), size=(200, 30), style=wx.ALIGN_RIGHT)
        self.label_result.SetFont(font_4)
        self.label_result_text = wx.StaticText(panel, label="PASS", pos=(370, 320))
        self.label_result_text.SetFont(font_5)
        self.label_result_text.SetForegroundColour((0, 255, 0))

        button = wx.Button(panel, label="开始检测", pos=(390, 390))
        button.Bind(wx.EVT_BUTTON, self.on_button_click)

        self.statusbar = self.CreateStatusBar()  # 创建状态栏
        self.statusbar.SetFieldsCount(3)
        self.statusbar.SetStatusWidths([-1, -2, -3])

        self.sc1 = SerialCommunication()
        self.sc2 = SerialCommunication()
        self.ser_ports = self.sc1.get_available_ports()

        # 创建一个只读下拉列表，可选择Linux的各种发行版本
        self.serial_list1 = wx.StaticText(panel, label="串口1：", pos=(10, 395), size=(50, 20), style=wx.ALIGN_LEFT)
        self.cb1 = wx.ComboBox(panel, pos=(60, 390), choices=[], style=wx.CB_READONLY)
        self.cb1.Clear()
        for item in self.ser_ports:
            self.cb1.Append(item[1] + "  " + item[2])
        self.cb1.SetSelection(0)
        self.com1_name = self.cb1.GetStringSelection().split(' ')[0]
        self.statusbar.SetStatusText(self.com1_name + " 未连接", 0)
        self.cb1.Bind(wx.EVT_COMBOBOX, self.OnSelect1)

        self.serial_list2 = wx.StaticText(panel, label="串口2：", pos=(200, 395), size=(50, 20), style=wx.ALIGN_LEFT)
        self.cb2 = wx.ComboBox(panel, pos=(250, 390), choices=[], style=wx.CB_READONLY)
        self.cb2.Clear()
        if len(self.ser_ports) > 1:
            for item in self.ser_ports:
                self.cb2.Append(item[1] + "  " + item[2])
            self.cb2.SetSelection(1)
            self.com2_name = self.cb2.GetStringSelection().split(' ')[0]
            self.statusbar.SetStatusText(self.com2_name + " 未连接", 1)
        self.cb2.Bind(wx.EVT_COMBOBOX, self.OnSelect2)

        print("当前选择：%s\n com1_name: %s" % (self.cb1.GetStringSelection(), self.com1_name))
        print("当前选择：%s\n com2_name: %s" % (self.cb2.GetStringSelection(), self.com2_name))

        # menubar = wx.MenuBar()
        # fileMenu = wx.Menu()
        # fileItem = fileMenu.Append(wx.ID_ANY, '串口配置(&U)', '串口配置')
        # menubar.Append(fileMenu, '设置(&S)')
        # self.SetMenuBar(menubar)

        # #绑定菜单项的行为
        # self.Bind(wx.EVT_MENU, self.OnQuit, fileItem)

    def OnSelect1(self, e):
        str = e.GetString()
        self.com1_name = str.split(' ')[0]
        print("当前选择：%s\n com1_name: %s" % (str, self.com1_name))

    def OnSelect2(self, e):
        str = e.GetString()
        self.com2_name = str.split(' ')[0]
        print("当前选择：%s\n com2_name: %s" % (str, self.com2_name))

    def OnQuit(self, e):
        AnotherFrame(parent=self, id=-1, title="另一个窗口")

    def get_cat1_imei(self):
        if self.ser1 is not None:
            while self.sc1.recv_queue.empty() == False:
                self.sc1.recv_queue.get_nowait()

            self.sc1.send_str_data(self.ser1, "AT+GSN=1\r\n")

            data_str = self.sc1.recv_queue.get(timeout=1)

            if data_str.find("+GSN:"):
                data_str = data_str.split("\r\n")
                if len(data_str) > 3:
                    result = data_str[3]
                    imei = data_str[1]
                else:
                    result = ""
                    imei = ""

            if (result == "OK"):
                print("imei %s" % imei)
                imei = imei.split("+GSN:")[1]
                print("get imei is {0}".format(imei))
                return imei.strip()
            else:
                print("get data is {0}".format(data_str))
                return ""

    def get_cat1_iccid(self):
        if self.ser1 is not None:
            while self.sc1.recv_queue.empty() == False:
                self.sc1.recv_queue.get_nowait()

            self.sc1.send_str_data(self.ser1, "AT+ICCID\r\n")

            data_str = self.sc1.recv_queue.get(timeout=1)

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
                print("get iccid is {0}".format(iccid))
                return iccid.strip()
            else:
                print("get data is {0}".format(data_str))
                return ""

    def get_cat1_version(self):
        if self.ser2 is not None:
            while self.sc2.recv_queue.empty() == False:
                self.sc2.recv_queue.get_nowait()

            data = "F4 F5 00 0A 02 03 09 00 00 00 00 00 E3 08"
            self.sc2.send_byte_data(self.ser2, data)

            data_str = self.sc2.recv_queue.get(timeout=1)
            print("get version is {0}".format(data_str))

            if (data_str[0] == 0xF4 and data_str[1] == 0xF5):
                try:
                    self.cat1_ver = data_str[8:23].decode('utf-8')
                except Exception as e:
                    print("decode error is {0}".format(e))
                    self.cat1_ver = ""

                self.csq = data_str[24] - 256

            print("cat1_ver is {0}".format(self.cat1_ver))
            print("csq is {0}".format(self.csq))

    def task(self):
        while True:
            # 查询IMEI号
            imei = self.get_cat1_imei()
            self.label_imei_text.SetLabelText(imei)

            # 查询ICCID
            iccid = self.get_cat1_iccid()
            self.label_iccid_text.SetLabelText(iccid)

            # 查询版本号
            self.get_cat1_version()
            if self.cat1_ver:
                self.label_sw_vertion_text.SetLabelText(self.cat1_ver)

            self.label_csq_text.SetLabelText(str(self.csq))

            time.sleep(3)

    def on_button_click(self, event):
        if (self.com1_name == self.com2_name):
            wx.MessageBox("串口不能相同", "错误", wx.OK | wx.ICON_ERROR)
            return

        self.ser1 = self.sc1.open_serial_port(self.com1_name, 115200)
        if self.ser1 is not None:
            self.statusbar.SetStatusText(self.com1_name + " 已连接", 0)
            self.sc1.start_serial_threads(self.ser1)
        else:
            self.statusbar.SetStatusText(self.com1_name + " 连接失败", 0)

        self.ser2 = self.sc2.open_serial_port(self.com2_name, 9600)
        if self.ser2 is not None:
            self.statusbar.SetStatusText(self.com2_name + " 已连接", 1)
            self.sc2.start_serial_threads(self.ser2)
        else:
            self.statusbar.SetStatusText(self.com2_name + " 连接失败", 1)

        task_thread = threading.Thread(target=self.task)
        task_thread.daemon = True
        task_thread.start()


class AnotherFrame(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title)
        self.Show()


def main():
    app = wx.App()
    ex = MyFrame(None)
    ex.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()

'''
from PIL import Image
import numpy as np

def palette_compress_16bit(
    img_path, palette_path, number_of_colors_from_img=16, save_path="output.png"
):
    # 读取图片和调色板
    img = Image.open(img_path)
    palette = Image.open(palette_path)

    # 转换为numpy数组
    img_array = np.array(img)
    palette_array = np.array(palette)

    # 确保调色板是正确的形状
    palette_array = palette_array.reshape((-1, 3))

    # 计算每种颜色的出现次数
    colors, count = np.unique(img_array.reshape(-1, 3), axis=0, return_counts=True)

    # 获取出现次数最多的前n种颜色的索引
    top_colors_idx = count.argsort()[-number_of_colors_from_img:]

    # 获取对应的颜色
    top_colors = colors[top_colors_idx]

    # 将这些颜色加入到调色板中
    palette_array = np.concatenate((palette_array, top_colors))

    # print(palette_array)

    # 如果调色板的颜色不足256种，用黑色填充
    if len(palette_array) < 256:
        palette_array = np.concatenate(
            (palette_array, np.zeros((256 - len(palette_array), 3)))
        )

    # print(palette_array)

    # 遍历图片中的每一行
    for i in range(img_array.shape[0]):
        row_colors = img_array[i, :].astype(np.int32) # 必须转换否则效果不佳，疑似和结果溢出有关

        print("--------------11------------------- %d %d" % (i, len(palette_array)))
        print(palette_array.shape)
        print("---------------22------------------ %d %d" % (i, len(row_colors)))
        print(row_colors.shape)
        print("----------------33----------------- %d %d" % (i, len(row_colors)))
        print(row_colors[:, None])

        # 计算与调色板中所有颜色的距离
        distances = np.sum(np.absolute(row_colors[:, None] - palette_array[:, None]), axis=-1) # 性能改进！

        # 找到距离最小的颜色
        min_indices = np.argmin(distances, axis=-1)

        # 替换颜色
        img_array[i, :] = palette_array[min_indices]

    # 创建一个掩码数组并将掩码数组重塑为(1, 1, 3)
    mask = np.array([0xF8, 0xFC, 0xF8], dtype=np.uint8).reshape((1, 1, 3))

    # 压缩为16位
    img_array = img_array & mask

    # 将numpy数组转换回Image对象
    img_array = Image.fromarray(img_array)

    # 保存图片
    img_array.save(save_path)

def _16bit_palette_gen():
    xterm_lut = [0, 96, 136, 176, 216, 252]  # 6bit r/g/b
    xterm_lut_grayscale = [
        8,
        20,
        32,
        40,
        52,
        60,
        72,
        80,
        92,
        100,
        112,
        120,
        132,
        140,
        152,
        160,
        172,
        180,
        192,
        200,
        212,
        220,
        232,
        240,
    ]  # 6bit grayscale

    img_palette = Image.new(mode="RGB", size=(16, 15), color="black")

    x = 0
    y = 0

    for r in xterm_lut:
        for g in xterm_lut:
            for b in xterm_lut:
                img_palette.putpixel((x, y), (r, g, b))
                x = x + 1
                if x == 16:
                    x = 0
                    y = y + 1

    for i in xterm_lut_grayscale:
        img_palette.putpixel((x, y), (i, i, i))
        x = x + 1
        if x == 16:
            x = 0
            y = y + 1
        if y == 15:
            break

    img_palette.save("xterm_palette.bmp")


if __name__ == "__main__":
    _16bit_palette_gen()
    palette_compress_16bit("Web1x _蒸.png", "xterm_palette.bmp")
'''

'''
import sys, struct
from PIL import Image

# 图片(jpg/png)转ARGB1555
def pic_to_argb():
	infile = "fod.png"
	outfile = "food1_1.png"
	im=Image.open(infile)
	# im.show()
	print("read %s\nImage Width:%d Height:%d mode: %s" % (infile, im.size[0], im.size[1], im.mode))
	f = open(outfile, "wb")
	pix = im.load()  #load pixel array
	for h in range(im.size[1]):
		for w in range(im.size[0]):
			R = pix[w, h][0] >> 3
			G = pix[w, h][1] >> 3
			B = pix[w, h][2] >> 3
			# argb第一位要是1，才是不透明，是0则是全透明
			argb = (1 << 15) | (R << 10) | (G << 5) | B
			# 转换的图是小端的，所以先后半字节，再前半字节
			f.write(struct.pack('B', argb & 255))
			f.write(struct.pack('B', (argb >> 8) & 255))
	f.close()
	print("write to %s" % outfile)

# 图片(jpg/png)转RGB565
def pic_to_rgb565():
	infile = "food1.png"
	outfile = "res.bin"
	im=Image.open(infile)
	# im.show()
	print("read %s\nImage Width:%d Height:%d mode: %s" % (infile, im.size[0], im.size[1], im.mode))

	f = open(outfile, "wb")
	pix = im.load()  #load pixel array
	for h in range(im.size[1]):
		for w in range(im.size[0]):
			R = pix[w, h][0] >> 3
			G = pix[w, h][1] >> 2
			B = pix[w, h][2] >> 3
			rgb = (R << 11) | (G << 5) | B
			# 转换的图是小端的，所以先后半字节，再前半字节
			f.write(struct.pack('B', rgb & 255))
			f.write(struct.pack('B', (rgb >> 8) & 255))

	f.close()
	print("write to %s" % outfile)

if __name__ == "__main__":
	pic_to_rgb565()
'''

'''
import wx
from PIL import Image

class Myframe(wx.Frame):
    def __init__(self, filename):
        wx.Frame.__init__(self, None, -1, u'图片显示', size=(640, 640))
        self.filename = filename
        self.Bind(wx.EVT_SIZE, self.change)
        self.p = wx.Panel(self, -1)
        self.SetBackgroundColour('white')

    def start(self):
        self.p.DestroyChildren()  # 抹掉原先显示的图片
        self.width, self.height = self.GetSize()
        print(self.width, self.height)

        # image = Image.open(self.filename)
        # self.x, self.y = image.size
        # self.x = self.width / 2 - self.x / 2
        # self.y = self.height / 2 - self.y / 2
        # img = wx.Image(self.filename, wx.BITMAP_TYPE_ANY)
        # # img = img.Scale(self.width, self.height)
        # self.pic = img.ConvertToBitmap()
        # # 通过计算获得图片的存放位置
        # print(self.x, self.y)

        image = wx.Image(self.filename, wx.BITMAP_TYPE_JPEG)
        self.x = 10
        self.y = 10
        self.pic = image.Scale(self.width, self.height).ConvertToBitmap()
        self.SetSize([self.width, self.height])
        self.button = wx.BitmapButton(self.p, -1, self.pic, pos=(self.x, self.y))
        self.p.Fit()

    def change(self, size):  # 如果检测到框架大小的变化，及时改变图片的位置
        if self.filename != "":
            self.start()
        else:
            pass


def main():
    app = wx.App()
    frame = Myframe('1.jpg')
    frame.start()
    frame.Center()
    frame.Show()
    app.MainLoop()

if __name__ == '__main__':
    main()
'''

'''
import hashlib
import os

def cal_file_sha256(filt_path):
    with open(filt_path, "rb") as f:
        file_hash = hashlib.sha256()
        while chunk := f.read(1024 * 1024):
            file_hash.update(chunk)
    return file_hash.hexdigest()


def cal_folder_hash(folder):
    if not os.path.exists(folder):
        print("Folder doesn't exist %s" % folder)
        return

    file_hash = hashlib.md5()
    for file in os.listdir(folder):
        path = os.path.join(folder, file)
        if os.path.isdir(path):
            cal_folder_hash(path)
        else:
            print("File: %s" % path)
            # sha256 = cal_file_sha256(path)
            with open(path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    file_hash.update(chunk)
    sha256 = file_hash.hexdigest()
    print("SHA256: %s\n" % sha256)


if __name__ == "__main__":
    cal_folder_hash("E:\\share\\code\\armino_fotile\\components\\bk_libs\\bk7256_lvgl\\fotile\\libs")

'''
