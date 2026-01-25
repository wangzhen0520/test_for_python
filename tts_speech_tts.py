import wx
import wx.lib.newevent
import wx.adv
import os
import uuid
import json
import requests
import time
import hmac
import hashlib
import datetime
from threading import Thread
import wx.lib.newevent
import wx.grid

# 自定义事件，用于线程与主线程通信
TtsProgressEvent, EVT_TTS_PROGRESS = wx.lib.newevent.NewEvent()
TtsCompleteEvent, EVT_TTS_COMPLETE = wx.lib.newevent.NewEvent()

def hmac_sha1(key: bytes, message: bytes) -> str:
    """计算 HMAC-SHA1 签名"""
    hmac_obj = hmac.new(key, message, hashlib.sha1)
    return hmac_obj.hexdigest()

class TTSWorker(Thread):
    """后台工作线程，处理TTS请求"""
    def __init__(self, parent, params):
        Thread.__init__(self)
        self.parent = parent
        self.params = params
        self.running = True
        self.create_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def run(self):
        try:
            # 注册设备
            device_secret = self.reg_device()
            if not device_secret:
                wx.PostEvent(self.parent, TtsCompleteEvent(
                    success=False,
                    message="设备注册失败"
                ))
                return
                
            # 处理文本
            texts = self.params['texts']
            voice_ids = self.params['voice_ids']
            output_dir = self.params.get('output_dir', 'output')
            
            total = len(texts) * len(voice_ids)
            processed = 0
            
            for voice_id in voice_ids:
                if not self.running:
                    break
                    
                for text_content, filename in texts:
                    if not self.running:
                        break
                        
                    processed += 1
                    
                    # 如果文件名为空，使用文本内容作为文件名
                    if not filename or filename.strip() == '':
                        # 取前30个字符作为文件名，移除非法字符
                        safe_text = ''.join(c for c in text_content if c.isalnum() or c in (' ', '-', '_'))[:30]
                        filename = f"{safe_text.strip()}.mp3"
                    elif not filename.endswith('.mp3'):
                        filename = f"{filename}.mp3"
                    
                    wx.PostEvent(self.parent, TtsProgressEvent(
                        current=processed,
                        total=total,
                        text_name=filename,
                        voice_id=voice_id,
                        status=f"正在处理: {filename} - {voice_id}"
                    ))
                    
                    success = self.submit_tts(
                        self.create_time, voice_id, device_secret, 
                        filename, text_content, output_dir
                    )
                    
                    if not success:
                        wx.PostEvent(self.parent, TtsCompleteEvent(
                            success=False,
                            message=f"处理失败: {filename} - {voice_id}"
                        ))
                        return
                        
            wx.PostEvent(self.parent, TtsCompleteEvent(
                success=True,
                message=f"全部完成！共处理 {processed} 个音频文件",
                output_dir=output_dir,
                create_time=self.create_time
            ))
            
        except Exception as e:
            wx.PostEvent(self.parent, TtsCompleteEvent(
                success=False,
                message=f"发生错误: {str(e)}"
            ))
    
    def reg_device(self):
        """注册设备"""
        product_id = self.params['product_id']
        product_key = self.params['product_key']
        product_secret = self.params['product_secret']
        device_name = self.params['device_name']
        formate = "plain"
        
        nonce = str(uuid.uuid4()).replace("-", "")
        timestamp = int(round(time.time() * 1000))
        sig_data = f"{product_key}{formate}{nonce}{product_id}{timestamp}"
        signature = hmac_sha1(product_secret.encode("utf-8"), sig_data.encode("utf-8"))
        
        url = f'{self.params["api_reg_url"]}?productKey={product_key}&format={formate}&productId={product_id}&timestamp={timestamp}&nonce={nonce}&sig={signature}'
        
        body = {
            "platform": "linux",
            "deviceName": device_name
        }
        payload_body = str.encode(json.dumps(body))
        
        try:
            response = requests.post(url, data=payload_body, headers={'Content-Type': 'application/json'})
            rsp_str = json.loads(response.text)
            return rsp_str['deviceSecret']
        except Exception as e:
            print(f"注册设备失败: {e}")
            return None
    
    def submit_tts(self, create_time, voice_id, device_secret, filename, text, output_dir):
        """提交TTS请求"""
        product_id = self.params['product_id']
        device_name = self.params['device_name']
        
        nonce = str(uuid.uuid4()).replace("-", "")
        timestamp = int(round(time.time() * 1000))
        sig_data = f"{device_name}{nonce}{product_id}{timestamp}"
        signature = hmac_sha1(device_secret.encode("utf-8"), sig_data.encode("utf-8"))
        
        body = {
            "context": {
                "productId": product_id,
            },
            "request": {
                "requestId": nonce,
                "audio": {
                    "audioType": "mp3",
                    "sampleRate": 16000
                },
                "tts": {
                    "text": text,
                    "textType": "text",
                    "voiceId": voice_id,
                    "speed": self.params.get('speed', '1.0'),
                    "volume": self.params.get('volume', 100)
                }
            }
        }
        
        url = f'{self.params["api_tts_url"]}?voiceId={voice_id}&deviceName={device_name}&nonce={nonce}&productId={product_id}&timestamp={timestamp}&sig={signature}'
        
        payload_body = str.encode(json.dumps(body))
        
        try:
            response = requests.post(url, data=payload_body, headers={'Content-Type': 'application/json'}, timeout=30)
            
            # 创建输出目录结构：output_dir/时间/音色/
            time_dir = os.path.join(output_dir, create_time)
            if not os.path.exists(time_dir):
                os.makedirs(time_dir)
                
            voice_dir = os.path.join(time_dir, voice_id)
            if not os.path.exists(voice_dir):
                os.makedirs(voice_dir)
            
            # 保存文件
            file_path = os.path.join(voice_dir, filename)
            with open(file_path, "wb") as f:
                f.write(response.content)
            
            return True
        except Exception as e:
            print(f"TTS请求失败: {e}")
            return False
    
    def stop(self):
        self.running = False

class TextGrid(wx.grid.Grid):
    """文本输入表格"""
    def __init__(self, parent):
        wx.grid.Grid.__init__(self, parent, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, 0)
        
        # 创建表格
        self.CreateGrid(10, 2)
        self.SetRowLabelSize(30)
        self.SetColLabelSize(25)
        
        # 设置列标题
        self.SetColLabelValue(0, "文本内容")
        self.SetColLabelValue(1, "文件名")
        
        # 设置列宽
        self.SetColSize(0, 400)
        self.SetColSize(1, 200)
        
        # 设置初始行数
        self.default_rows = 10
        self.current_rows = 10
        
        # 设置默认值提示
        self.SetCellValue(0, 0, "欢迎使用语音助手")
        self.SetCellValue(0, 1, "欢迎语.mp3")
        self.SetCellValue(1, 0, "操作已完成")
        self.SetCellValue(1, 1, "完成提示.mp3")
        
        # 设置字体
        font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False)
        self.SetDefaultCellFont(font)
        
        # 设置表格样式
        self.SetGridLineColour(wx.Colour(200, 200, 200))
        
        # 绑定事件
        self.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.on_cell_changed)
    
    def on_cell_changed(self, event):
        """单元格内容变化事件"""
        row = event.GetRow()
        col = event.GetCol()
        
        # 如果是最后一行有内容，添加新行
        if row == self.current_rows - 1 and self.GetCellValue(row, 0).strip():
            self.AppendRows(1)
            self.current_rows += 1
            
            # 滚动到最后一行（使用GoToCell方法）
            wx.CallAfter(self.GoToCell, row + 1, 0)

class ConfigDialog(wx.Dialog):
    """API配置对话框"""
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, id=wx.ID_ANY, title="API配置", 
                          pos=wx.DefaultPosition, size=wx.Size(500, 300))
        
        self.parent = parent
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        """初始化UI"""
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建配置面板
        config_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "API配置"), wx.VERTICAL)
        
        grid_sizer = wx.FlexGridSizer(4, 2, 10, 15)
        grid_sizer.AddGrowableCol(1)
        
        # Product ID
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "Product ID:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.product_id = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0)
        grid_sizer.Add(self.product_id, 0, wx.EXPAND | wx.ALL, 5)
        
        # Product Key
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "Product Key:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.product_key = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0)
        grid_sizer.Add(self.product_key, 0, wx.EXPAND | wx.ALL, 5)
        
        # Product Secret
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "Product Secret:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.product_secret = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, wx.TE_PASSWORD)
        grid_sizer.Add(self.product_secret, 0, wx.EXPAND | wx.ALL, 5)
        
        # Device Name
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "Device Name:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.device_name = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0)
        grid_sizer.Add(self.device_name, 0, wx.EXPAND | wx.ALL, 5)
        
        config_sizer.Add(grid_sizer, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(config_sizer, 1, wx.EXPAND | wx.ALL, 10)
        
        # 按钮
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Layout()
    
    def load_config(self):
        """加载配置"""
        # 从父窗口获取当前配置
        self.product_id.SetValue(self.parent.product_id.GetValue())
        self.product_key.SetValue(self.parent.product_key.GetValue())
        self.product_secret.SetValue(self.parent.product_secret.GetValue())
        self.device_name.SetValue(self.parent.device_name.GetValue())
    
    def get_config(self):
        """获取配置"""
        return {
            'product_id': self.product_id.GetValue(),
            'product_key': self.product_key.GetValue(),
            'product_secret': self.product_secret.GetValue(),
            'device_name': self.device_name.GetValue()
        }

class SynthesisParamDialog(wx.Dialog):
    """合成参数对话框"""
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, id=wx.ID_ANY, title="合成参数配置", 
                          pos=wx.DefaultPosition, size=wx.Size(400, 300))
        
        self.parent = parent
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        """初始化UI"""
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建参数面板
        param_sizer = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "合成参数"), wx.VERTICAL)
        
        grid_sizer = wx.FlexGridSizer(4, 2, 10, 15)
        grid_sizer.AddGrowableCol(1)
        
        # 语速
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "语速(0.5-2.0):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.speed = wx.TextCtrl(self, wx.ID_ANY, "1.0", wx.DefaultPosition, wx.Size(100, -1), 0)
        grid_sizer.Add(self.speed, 0, wx.ALL, 5)
        
        # 音量
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "音量(0-100):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.volume = wx.TextCtrl(self, wx.ID_ANY, "100", wx.DefaultPosition, wx.Size(100, -1), 0)
        grid_sizer.Add(self.volume, 0, wx.ALL, 5)
        
        # 采样率
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "采样率:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.sample_rate = wx.ComboBox(self, wx.ID_ANY, "16000", choices=["8000", "16000", "24000", "32000", "44100", "48000"], 
                                      style=wx.CB_READONLY, size=(100, -1))
        grid_sizer.Add(self.sample_rate, 0, wx.ALL, 5)
        
        # 音频格式
        grid_sizer.Add(wx.StaticText(self, wx.ID_ANY, "音频格式:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.audio_format = wx.ComboBox(self, wx.ID_ANY, "mp3", choices=["mp3", "wav", "pcm"], 
                                       style=wx.CB_READONLY, size=(100, -1))
        grid_sizer.Add(self.audio_format, 0, wx.ALL, 5)
        
        param_sizer.Add(grid_sizer, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(param_sizer, 1, wx.EXPAND | wx.ALL, 10)
        
        # 提示信息
        hint_sizer = wx.BoxSizer(wx.HORIZONTAL)
        hint_text = wx.StaticText(self, wx.ID_ANY, 
                                 "提示：语速范围为0.5-2.0，音量范围为0-100")
        hint_text.SetForegroundColour(wx.Colour(128, 128, 128))
        hint_sizer.Add(hint_text, 0, wx.ALL, 5)
        sizer.Add(hint_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 按钮
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Layout()
    
    def load_config(self):
        """加载配置"""
        # 从父窗口获取当前配置
        self.speed.SetValue(self.parent.speed.GetValue())
        self.volume.SetValue(self.parent.volume.GetValue())
        self.sample_rate.SetValue(self.parent.sample_rate.GetValue())
        self.audio_format.SetValue(self.parent.audio_format.GetValue())
    
    def get_config(self):
        """获取配置"""
        return {
            'speed': self.speed.GetValue(),
            'volume': self.volume.GetValue(),
            'sample_rate': self.sample_rate.GetValue(),
            'audio_format': self.audio_format.GetValue()
        }

class TTSFrame(wx.Frame):
    """主窗口"""
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title="文字转语音工具", 
                         pos=wx.DefaultPosition, size=wx.Size(1000, 800),
                         style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)
        
        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        
        # 初始化变量
        self.worker = None
        
        # 创建菜单栏
        self.init_menu()
        
        # 初始化主界面
        self.init_ui()
        self.load_default_config()
        
        # 绑定事件
        self.Bind(EVT_TTS_PROGRESS, self.on_progress_update)
        self.Bind(EVT_TTS_COMPLETE, self.on_complete)
    
    def init_menu(self):
        """初始化菜单栏"""
        menubar = wx.MenuBar()
        
        # 文件菜单
        file_menu = wx.Menu()
        m_exit = file_menu.Append(wx.ID_EXIT, "退出(&X)", "退出程序")
        menubar.Append(file_menu, "文件(&F)")
        
        # 配置菜单
        config_menu = wx.Menu()
        m_api_config = config_menu.Append(wx.ID_ANY, "API配置(&A)...", "设置API参数")
        m_synth_config = config_menu.Append(wx.ID_ANY, "合成参数(&S)...", "设置合成参数")
        m_save_config = config_menu.Append(wx.ID_ANY, "保存配置(&S)", "保存当前配置")
        m_load_config = config_menu.Append(wx.ID_ANY, "加载配置(&L)...", "加载配置")
        config_menu.AppendSeparator()
        m_reset_config = config_menu.Append(wx.ID_ANY, "重置配置(&R)", "恢复默认配置")
        menubar.Append(config_menu, "配置(&C)")
        
        # 工具菜单
        tools_menu = wx.Menu()
        m_clear_log = tools_menu.Append(wx.ID_ANY, "清空日志(&C)", "清空日志窗口")
        m_open_output = tools_menu.Append(wx.ID_ANY, "打开输出目录(&O)", "打开输出文件夹")
        tools_menu.AppendSeparator()
        m_clear_table = tools_menu.Append(wx.ID_ANY, "清空表格(&T)", "清空文本表格")
        menubar.Append(tools_menu, "工具(&T)")
        
        # 帮助菜单
        help_menu = wx.Menu()
        m_about = help_menu.Append(wx.ID_ABOUT, "关于(&A)...", "关于本程序")
        m_user_guide = help_menu.Append(wx.ID_HELP, "使用指南(&G)", "查看使用说明")
        menubar.Append(help_menu, "帮助(&H)")
        
        self.SetMenuBar(menubar)
        
        # 绑定菜单事件
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)
        self.Bind(wx.EVT_MENU, self.on_api_config, m_api_config)
        self.Bind(wx.EVT_MENU, self.on_synth_config, m_synth_config)
        self.Bind(wx.EVT_MENU, self.on_save_config, m_save_config)
        self.Bind(wx.EVT_MENU, self.on_load_config, m_load_config)
        self.Bind(wx.EVT_MENU, self.on_reset_config, m_reset_config)
        self.Bind(wx.EVT_MENU, self.on_clear_log, m_clear_log)
        self.Bind(wx.EVT_MENU, self.on_open_output, m_open_output)
        self.Bind(wx.EVT_MENU, self.on_clear_table, m_clear_table)
        self.Bind(wx.EVT_MENU, self.on_about, m_about)
        self.Bind(wx.EVT_MENU, self.on_user_guide, m_user_guide)
    
    def init_ui(self):
        """初始化UI"""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 音色选择
        voice_panel = self.create_voice_panel()
        main_sizer.Add(voice_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # 文本输入表格
        text_panel = self.create_text_panel()
        main_sizer.Add(text_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        # 按钮面板
        button_panel = self.create_button_panel()
        main_sizer.Add(button_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # 进度面板
        progress_panel = self.create_progress_panel()
        main_sizer.Add(progress_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(main_sizer)
        self.Layout()
    
    def create_voice_panel(self):
        """创建音色选择面板"""
        panel = wx.Panel(self, wx.ID_ANY, style=wx.TAB_TRAVERSAL)
        sizer = wx.StaticBoxSizer(wx.StaticBox(panel, wx.ID_ANY, "选择音色（可多选）"), wx.VERTICAL)
        
        # 音色列表
        self.voice_list = [
            ("gdfanfp", "国语-女声-芳平"),
            ("gqlanfp", "国语-男声-芳平"),
            ("gdfanf_natong", "国语-女声-娜彤"),
            ("xbekef", "粤语-男声"),
            ("jlshimp", "津鲁声-男声"),
            ("xijunma", "西骏马-男声"),
            ("xmguof", "小芒果-女声")
        ]
        
        # 操作按钮
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_select_all = wx.Button(panel, wx.ID_ANY, "全选", wx.DefaultPosition, wx.DefaultSize, 0)
        btn_select_none = wx.Button(panel, wx.ID_ANY, "取消全选", wx.DefaultPosition, wx.DefaultSize, 0)
        btn_invert = wx.Button(panel, wx.ID_ANY, "反选", wx.DefaultPosition, wx.DefaultSize, 0)
        
        btn_sizer.Add(btn_select_all, 0, wx.ALL, 3)
        btn_sizer.Add(btn_select_none, 0, wx.ALL, 3)
        btn_sizer.Add(btn_invert, 0, wx.ALL, 3)
        btn_sizer.AddStretchSpacer()
        
        # 显示选中数量
        self.selected_count = wx.StaticText(panel, wx.ID_ANY, "已选择: 1/7")
        btn_sizer.Add(self.selected_count, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 创建复选框列表
        grid_sizer = wx.GridSizer(2, 4, 5, 15)
        self.voice_checkboxes = []
        
        for voice_id, voice_desc in self.voice_list:
            cb = wx.CheckBox(panel, wx.ID_ANY, voice_desc)
            cb.voice_id = voice_id  # 将voice_id存储在checkbox对象中
            cb.Bind(wx.EVT_CHECKBOX, self.update_selected_count)
            grid_sizer.Add(cb, 0, wx.ALL, 3)
            self.voice_checkboxes.append(cb)
        
        # 默认选中第一个
        if self.voice_checkboxes:
            self.voice_checkboxes[0].SetValue(True)
        
        sizer.Add(grid_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        
        # 绑定按钮事件
        btn_select_all.Bind(wx.EVT_BUTTON, self.on_select_all)
        btn_select_none.Bind(wx.EVT_BUTTON, self.on_select_none)
        btn_invert.Bind(wx.EVT_BUTTON, self.on_invert_selection)
        
        return panel
    
    def create_text_panel(self):
        """创建文本输入面板"""
        panel = wx.Panel(self, wx.ID_ANY, style=wx.TAB_TRAVERSAL)
        sizer = wx.StaticBoxSizer(wx.StaticBox(panel, wx.ID_ANY, "文本输入（批量模式）"), wx.VERTICAL)
        
        # 提示信息
        hint_sizer = wx.BoxSizer(wx.HORIZONTAL)
        hint_text = wx.StaticText(panel, wx.ID_ANY, 
                                 "提示：第一列为文本内容，第二列为文件名（可选，如为空则使用文本内容作为文件名）")
        hint_text.SetForegroundColour(wx.Colour(128, 128, 128))
        hint_sizer.Add(hint_text, 0, wx.ALL, 5)
        sizer.Add(hint_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 操作按钮
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        btn_add = wx.Button(panel, wx.ID_ANY, "添加行", wx.DefaultPosition, wx.DefaultSize, 0)
        btn_clear = wx.Button(panel, wx.ID_ANY, "清空表格", wx.DefaultPosition, wx.DefaultSize, 0)
        btn_load = wx.Button(panel, wx.ID_ANY, "导入文本", wx.DefaultPosition, wx.DefaultSize, 0)
        btn_export = wx.Button(panel, wx.ID_ANY, "导出表格", wx.DefaultPosition, wx.DefaultSize, 0)
        
        btn_sizer.Add(btn_add, 0, wx.ALL, 3)
        btn_sizer.Add(btn_clear, 0, wx.ALL, 3)
        btn_sizer.Add(btn_load, 0, wx.ALL, 3)
        btn_sizer.Add(btn_export, 0, wx.ALL, 3)
        btn_sizer.AddStretchSpacer()
        
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # 创建表格（表格自带滚动功能）
        self.text_grid = TextGrid(panel)
        self.text_grid.SetMinSize(wx.Size(-1, 250))
        sizer.Add(self.text_grid, 1, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        
        # 绑定事件
        btn_add.Bind(wx.EVT_BUTTON, self.on_add_row)
        btn_clear.Bind(wx.EVT_BUTTON, self.on_clear_grid)
        btn_load.Bind(wx.EVT_BUTTON, self.on_load_text)
        btn_export.Bind(wx.EVT_BUTTON, self.on_export_grid)
        
        return panel
    
    def create_button_panel(self):
        """创建按钮面板"""
        panel = wx.Panel(self, wx.ID_ANY, style=wx.TAB_TRAVERSAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 输出目录选择
        sizer.Add(wx.StaticText(panel, wx.ID_ANY, "输出目录:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.output_dir = wx.TextCtrl(panel, wx.ID_ANY, "output", wx.DefaultPosition, wx.Size(250, -1), 0)
        sizer.Add(self.output_dir, 0, wx.ALL, 5)
        
        btn_browse = wx.Button(panel, wx.ID_ANY, "浏览...", wx.DefaultPosition, wx.DefaultSize, 0)
        sizer.Add(btn_browse, 0, wx.ALL, 5)
        
        sizer.AddStretchSpacer()
        
        # 操作按钮
        self.btn_start = wx.Button(panel, wx.ID_ANY, "开始转换", wx.DefaultPosition, wx.DefaultSize, 0)
        self.btn_stop = wx.Button(panel, wx.ID_ANY, "停止", wx.DefaultPosition, wx.DefaultSize, 0)
        self.btn_stop.Disable()
        
        sizer.Add(self.btn_start, 0, wx.ALL, 5)
        sizer.Add(self.btn_stop, 0, wx.ALL, 5)
        
        # 绑定事件
        btn_browse.Bind(wx.EVT_BUTTON, self.on_browse)
        self.btn_start.Bind(wx.EVT_BUTTON, self.on_start)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop)
        
        panel.SetSizer(sizer)
        return panel
    
    def create_progress_panel(self):
        """创建进度面板"""
        panel = wx.Panel(self, wx.ID_ANY, style=wx.TAB_TRAVERSAL)
        sizer = wx.StaticBoxSizer(wx.StaticBox(panel, wx.ID_ANY, "进度和日志"), wx.VERTICAL)
        
        # 进度条
        self.progress_bar = wx.Gauge(panel, wx.ID_ANY, 100, wx.DefaultPosition, wx.DefaultSize, wx.GA_HORIZONTAL)
        self.progress_bar.SetValue(0)
        sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.ALL, 5)
        
        # 状态文本
        self.status_text = wx.StaticText(panel, wx.ID_ANY, "准备就绪", wx.DefaultPosition, wx.DefaultSize, 0)
        sizer.Add(self.status_text, 0, wx.EXPAND | wx.ALL, 5)
        
        # 日志文本框（带滚动条）
        self.log_text = wx.TextCtrl(panel, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 
                                   wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL | wx.TE_RICH2)
        self.log_text.SetMinSize(wx.Size(-1, 120))
        
        # 设置日志文本框的字体
        font = wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False)
        self.log_text.SetFont(font)
        
        sizer.Add(self.log_text, 1, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        return panel
    
    def load_default_config(self):
        """加载默认配置"""
        # API配置控件
        self.product_id = wx.TextCtrl(self, wx.ID_ANY, "279630209", style=wx.TE_READONLY)
        self.product_key = wx.TextCtrl(self, wx.ID_ANY, "085757baadb96edbffcdc2f09ab68ab7", style=wx.TE_READONLY)
        self.product_secret = wx.TextCtrl(self, wx.ID_ANY, "ef59258308d5691c39e07626e0e7a983", style=wx.TE_READONLY)
        self.device_name = wx.TextCtrl(self, wx.ID_ANY, "1C:79:2D:2F:B2:98", style=wx.TE_READONLY)
        
        # 合成参数控件（隐藏，仅用于存储值）
        self.speed = wx.TextCtrl(self, wx.ID_ANY, "1.0", style=wx.TE_READONLY)
        self.volume = wx.TextCtrl(self, wx.ID_ANY, "100", style=wx.TE_READONLY)
        self.sample_rate = wx.ComboBox(self, wx.ID_ANY, "16000", choices=["8000", "16000", "24000", "32000", "44100", "48000"], 
                                      style=wx.CB_READONLY)
        self.audio_format = wx.ComboBox(self, wx.ID_ANY, "mp3", choices=["mp3", "wav", "pcm"], style=wx.CB_READONLY)
        
        # 隐藏这些控件
        self.product_id.Hide()
        self.product_key.Hide()
        self.product_secret.Hide()
        self.device_name.Hide()
        self.speed.Hide()
        self.volume.Hide()
        self.sample_rate.Hide()
        self.audio_format.Hide()
        
        # API URL（固定值）
        self.api_reg_url = "https://auth.dui.ai/auth/device/register"
        self.api_tts_url = "https://tts.dui.ai/runtime/v2/synthesize"
        
        # 默认输出目录
        if not os.path.exists("output"):
            os.makedirs("output")
        
        # 更新选中音色计数
        self.update_selected_count()
    
    def on_select_all(self, event):
        """全选音色"""
        for cb in self.voice_checkboxes:
            cb.SetValue(True)
        self.update_selected_count()
        self.add_log("已选择所有音色")
    
    def on_select_none(self, event):
        """取消全选音色"""
        for cb in self.voice_checkboxes:
            cb.SetValue(False)
        self.update_selected_count()
        self.add_log("已取消所有音色选择")
    
    def on_invert_selection(self, event):
        """反选音色"""
        for cb in self.voice_checkboxes:
            cb.SetValue(not cb.GetValue())
        self.update_selected_count()
        self.add_log("已反选音色")
    
    def update_selected_count(self, event=None):
        """更新选中音色计数"""
        selected = sum(1 for cb in self.voice_checkboxes if cb.GetValue())
        total = len(self.voice_checkboxes)
        self.selected_count.SetLabel(f"已选择: {selected}/{total}")
    
    def on_api_config(self, event):
        """API配置"""
        dlg = ConfigDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            config = dlg.get_config()
            
            # 更新配置
            self.product_id.SetValue(config['product_id'])
            self.product_key.SetValue(config['product_key'])
            self.product_secret.SetValue(config['product_secret'])
            self.device_name.SetValue(config['device_name'])
            
            self.add_log("API配置已更新")
        
        dlg.Destroy()
    
    def on_synth_config(self, event):
        """合成参数配置"""
        dlg = SynthesisParamDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            config = dlg.get_config()
            
            # 更新配置
            self.speed.SetValue(config['speed'])
            self.volume.SetValue(config['volume'])
            self.sample_rate.SetValue(config['sample_rate'])
            self.audio_format.SetValue(config['audio_format'])
            
            self.add_log("合成参数已更新")
        
        dlg.Destroy()
    
    def on_save_config(self, event):
        """保存配置"""
        dlg = wx.FileDialog(self, "保存配置", wildcard="配置文件 (*.json)|*.json|所有文件 (*.*)|*.*",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            try:
                config = {
                    'product_id': self.product_id.GetValue(),
                    'product_key': self.product_key.GetValue(),
                    'product_secret': self.product_secret.GetValue(),
                    'device_name': self.device_name.GetValue(),
                    'speed': self.speed.GetValue(),
                    'volume': self.volume.GetValue(),
                    'sample_rate': self.sample_rate.GetValue(),
                    'audio_format': self.audio_format.GetValue(),
                    'output_dir': self.output_dir.GetValue(),
                    'voices': [cb.voice_id for cb in self.voice_checkboxes if cb.GetValue()]
                }
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                wx.MessageBox(f"配置已保存到 {filename}", "提示", wx.OK | wx.ICON_INFORMATION)
                self.add_log(f"配置已保存: {filename}")
                
            except Exception as e:
                wx.MessageBox(f"保存配置失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
        
        dlg.Destroy()
    
    def on_load_config(self, event):
        """加载配置"""
        dlg = wx.FileDialog(self, "加载配置", wildcard="配置文件 (*.json)|*.json|所有文件 (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 更新配置
                if 'product_id' in config:
                    self.product_id.SetValue(config['product_id'])
                if 'product_key' in config:
                    self.product_key.SetValue(config['product_key'])
                if 'product_secret' in config:
                    self.product_secret.SetValue(config['product_secret'])
                if 'device_name' in config:
                    self.device_name.SetValue(config['device_name'])
                if 'speed' in config:
                    self.speed.SetValue(config['speed'])
                if 'volume' in config:
                    self.volume.SetValue(config['volume'])
                if 'sample_rate' in config:
                    self.sample_rate.SetValue(config['sample_rate'])
                if 'audio_format' in config:
                    self.audio_format.SetValue(config['audio_format'])
                if 'output_dir' in config:
                    self.output_dir.SetValue(config['output_dir'])
                
                # 更新音色选择
                if 'voices' in config:
                    for cb in self.voice_checkboxes:
                        cb.SetValue(cb.voice_id in config['voices'])
                
                # 更新选中计数
                self.update_selected_count()
                
                wx.MessageBox(f"配置已从 {filename} 加载", "提示", wx.OK | wx.ICON_INFORMATION)
                self.add_log(f"配置已加载: {filename}")
                
            except Exception as e:
                wx.MessageBox(f"加载配置失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
        
        dlg.Destroy()
    
    def on_reset_config(self, event):
        """重置配置"""
        dlg = wx.MessageDialog(self, "确定要重置所有配置为默认值吗？", "确认重置", 
                              wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            self.load_default_config()
            
            # 重置输出目录
            self.output_dir.SetValue("output")
            
            # 重置表格
            self.reset_table()
            
            wx.MessageBox("配置已重置为默认值", "提示", wx.OK | wx.ICON_INFORMATION)
            self.add_log("配置已重置为默认值")
        
        dlg.Destroy()
    
    def on_clear_log(self, event):
        """清空日志"""
        self.log_text.SetValue("")
        self.add_log("日志已清空")
    
    def on_open_output(self, event):
        """打开输出目录"""
        output_dir = self.output_dir.GetValue()
        if os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            wx.MessageBox(f"输出目录不存在: {output_dir}", "错误", wx.OK | wx.ICON_ERROR)
    
    def on_clear_table(self, event):
        """清空表格（菜单）"""
        self.on_clear_grid(event)
    
    def on_about(self, event):
        """关于"""
        about_info = wx.adv.AboutDialogInfo()
        about_info.SetName("文字转语音工具")
        about_info.SetVersion("1.0.0")
        about_info.SetDescription("批量文字转语音合成工具\n支持多种音色和参数配置\n\n主要功能：\n1. 批量文字转语音\n2. 多音色同时合成\n3. 自定义合成参数\n4. 配置导入导出\n5. 智能文件管理")
        about_info.SetCopyright("(C) 2026")
        about_info.AddDeveloper("wz")
        # about_info.SetWebSite("https://github.com/example/tts-tool")
        # about_info.SetLicence("MIT License")
        
        # 添加开发者信息
        # about_info.SetDevelopers(["开发团队"])
        
        wx.adv.AboutBox(about_info)
    
    def on_user_guide(self, event):
        """使用指南"""
        guide_text = """使用指南：

1. 配置设置：
   - 通过菜单栏【配置】→【API配置】设置API参数
   - 通过菜单栏【配置】→【合成参数】设置语速、音量等参数
   - 可以保存和加载配置，方便重复使用

2. 音色选择：
   - 支持多选音色，每个文本会生成所有选中音色的音频
   - 使用【全选】、【取消全选】、【反选】按钮快速选择

3. 文本输入：
   - 支持批量输入，每行一个文本
   - 第一列：文本内容（必填）
   - 第二列：文件名（可选，为空时自动生成）
   - 支持导入/导出文本文件

4. 文件输出：
   - 音频文件按【时间/音色】目录结构保存
   - 每次转换生成唯一的时间目录（格式：年月日时分秒）
   - 每个音色在时间目录下有独立的子目录
   - 支持自定义输出目录

5. 注意事项：
   - 确保网络连接正常
   - 单个文件处理需要一定时间，批量处理请耐心等待
   - 建议先测试单个文件，确认无误后再进行批量处理

如有问题，请查看日志窗口获取详细信息。"""
        
        dlg = wx.Dialog(self, wx.ID_ANY, "使用指南", size=(600, 500))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建带滚动条的文本控件
        text_ctrl = wx.TextCtrl(dlg, wx.ID_ANY, guide_text, 
                               style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL | wx.VSCROLL)
        
        # 设置字体
        font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False)
        text_ctrl.SetFont(font)
        
        sizer.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        
        # 关闭按钮
        btn_close = wx.Button(dlg, wx.ID_CLOSE, "关闭")
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM, 10)
        
        dlg.SetSizer(sizer)
        
        # 绑定关闭事件
        btn_close.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CLOSE))
        
        dlg.ShowModal()
        dlg.Destroy()
    
    def on_exit(self, event):
        """退出程序"""
        self.Close()
    
    def on_add_row(self, event):
        """添加行"""
        self.text_grid.AppendRows(1)
        # 滚动到最后一行
        rows = self.text_grid.GetNumberRows()
        wx.CallAfter(self.text_grid.GoToCell, rows - 1, 0)
    
    def reset_table(self):
        """重置表格为初始状态（10行）"""
        # 获取当前行数
        current_rows = self.text_grid.GetNumberRows()
        
        # 如果当前行数不等于10，先删除所有行
        if current_rows > 0:
            self.text_grid.DeleteRows(0, current_rows)
        
        # 添加10行
        self.text_grid.AppendRows(10)
        
        # 重置表格行计数器
        if hasattr(self.text_grid, 'current_rows'):
            self.text_grid.current_rows = 10
        
        # 设置默认值
        self.text_grid.SetCellValue(0, 0, "欢迎使用语音助手")
        self.text_grid.SetCellValue(0, 1, "欢迎语.mp3")
        self.text_grid.SetCellValue(1, 0, "操作已完成")
        self.text_grid.SetCellValue(1, 1, "完成提示.mp3")
        
        # 滚动到第一行
        wx.CallAfter(self.text_grid.GoToCell, 0, 0)
    
    def on_clear_grid(self, event):
        """清空表格"""
        dlg = wx.MessageDialog(self, "确定要清空所有内容吗？", "确认", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            self.reset_table()
            self.add_log("表格已清空并重置为10行")
        dlg.Destroy()
    
    def on_load_text(self, event):
        """导入文本文件"""
        dlg = wx.FileDialog(self, "选择文本文件", wildcard="文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 清空表格并重置为10行
                self.reset_table()
                
                # 添加数据
                for i, line in enumerate(lines):
                    # 如果行数不够，添加行
                    if i >= self.text_grid.GetNumberRows():
                        self.text_grid.AppendRows(1)
                        if hasattr(self.text_grid, 'current_rows'):
                            self.text_grid.current_rows += 1
                    
                    line = line.strip()
                    if '|' in line:
                        parts = line.split('|', 1)
                        self.text_grid.SetCellValue(i, 0, parts[1].strip())
                        self.text_grid.SetCellValue(i, 1, parts[0].strip())
                    else:
                        self.text_grid.SetCellValue(i, 0, line)
                
                wx.MessageBox(f"成功导入 {len(lines)} 行文本", "提示", wx.OK | wx.ICON_INFORMATION)
                self.add_log(f"已从 {filename} 导入 {len(lines)} 行文本")
                
                # 滚动到最后一行
                if lines:
                    last_row = min(len(lines) - 1, self.text_grid.GetNumberRows() - 1)
                    wx.CallAfter(self.text_grid.GoToCell, last_row, 0)
                
            except Exception as e:
                wx.MessageBox(f"导入失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
        
        dlg.Destroy()
    
    def on_export_grid(self, event):
        """导出表格到文件"""
        dlg = wx.FileDialog(self, "保存文件", wildcard="文本文件 (*.txt)|*.txt|CSV文件 (*.csv)|*.csv",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    rows = self.text_grid.GetNumberRows()
                    for i in range(rows):
                        text = self.text_grid.GetCellValue(i, 0).strip()
                        filename_cell = self.text_grid.GetCellValue(i, 1).strip()
                        
                        if text:  # 只导出有文本内容的行
                            if filename_cell:
                                f.write(f"{filename_cell}|{text}\n")
                            else:
                                f.write(f"{text}\n")
                
                wx.MessageBox(f"成功导出到 {filename}", "提示", wx.OK | wx.ICON_INFORMATION)
                self.add_log(f"表格已导出到 {filename}")
                
            except Exception as e:
                wx.MessageBox(f"导出失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
        
        dlg.Destroy()
    
    def on_browse(self, event):
        """选择输出目录"""
        dlg = wx.DirDialog(self, "选择输出目录", style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.output_dir.SetValue(dlg.GetPath())
        dlg.Destroy()
    
    def on_start(self, event):
        """开始转换"""
        # 验证输入
        if not self.validate_input():
            return
        
        # 获取参数
        params = self.get_params()
        
        # 准备文本数据
        texts = self.prepare_texts()
        if not texts:
            wx.MessageBox("没有有效的文本输入！", "错误", wx.OK | wx.ICON_ERROR)
            return
        
        params['texts'] = texts
        
        # 检查是否选择了音色
        if not params['voice_ids']:
            wx.MessageBox("请至少选择一个音色！", "错误", wx.OK | wx.ICON_ERROR)
            return
        
        # 计算总任务数
        total_tasks = len(texts) * len(params['voice_ids'])
        if total_tasks > 100:
            dlg = wx.MessageDialog(self, f"总共要生成 {total_tasks} 个音频文件，可能需要较长时间，确定继续吗？", 
                                  "确认", wx.YES_NO | wx.ICON_QUESTION)
            if dlg.ShowModal() != wx.ID_YES:
                dlg.Destroy()
                return
            dlg.Destroy()
        
        # 禁用开始按钮，启用停止按钮
        self.btn_start.Disable()
        self.btn_stop.Enable()
        
        # 清空日志
        self.log_text.SetValue("")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.add_log(f"开始转换时间: {current_time}")
        self.add_log(f"共 {len(texts)} 个文本 × {len(params['voice_ids'])} 个音色 = {total_tasks} 个文件")
        self.add_log(f"输出目录结构: {self.output_dir.GetValue()}/时间目录/音色目录/音频文件")
        
        # 启动工作线程
        self.worker = TTSWorker(self, params)
        self.worker.start()
    
    def on_stop(self, event):
        """停止转换"""
        if self.worker:
            self.worker.stop()
            self.add_log("正在停止...")
    
    def on_progress_update(self, event):
        """更新进度"""
        current = event.current
        total = event.total
        text_name = event.text_name
        voice_id = getattr(event, 'voice_id', '')
        
        # 更新进度条
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.SetValue(progress)
        
        # 更新状态
        status_msg = f"{text_name}"
        if voice_id:
            status_msg = f"{voice_id} - {status_msg}"
        status_msg = f"正在处理: {status_msg} ({current}/{total})"
        self.status_text.SetLabel(status_msg)
        
        # 添加日志
        log_msg = f"✓ [{voice_id}] {text_name}"
        self.add_log(log_msg)
    
    def on_complete(self, event):
        """转换完成"""
        self.btn_start.Enable()
        self.btn_stop.Disable()
        self.progress_bar.SetValue(100)
        
        if event.success:
            self.status_text.SetLabel(f"完成！{event.message}")
            self.add_log(f"✓ {event.message}")
            if hasattr(event, 'output_dir') and hasattr(event, 'create_time'):
                output_path = os.path.join(event.output_dir, event.create_time)
                self.add_log(f"✓ 文件保存在: {output_path}")
                # 打开输出目录
                if wx.MessageBox(f"转换完成！文件保存在：{output_path}\n\n是否打开输出目录？", 
                               "完成", wx.YES_NO | wx.ICON_INFORMATION) == wx.YES:
                    if os.path.exists(output_path):
                        os.startfile(output_path)
                    else:
                        os.startfile(event.output_dir)
        else:
            self.status_text.SetLabel(f"失败：{event.message}")
            self.add_log(f"✗ {event.message}")
        
        self.worker = None
    
    def validate_input(self):
        """验证输入"""
        if not self.product_id.GetValue():
            wx.MessageBox("请输入 Product ID！", "错误", wx.OK | wx.ICON_ERROR)
            return False
        
        if not self.product_key.GetValue():
            wx.MessageBox("请输入 Product Key！", "错误", wx.OK | wx.ICON_ERROR)
            return False
        
        if not self.product_secret.GetValue():
            wx.MessageBox("请输入 Product Secret！", "错误", wx.OK | wx.ICON_ERROR)
            return False
        
        if not self.device_name.GetValue():
            wx.MessageBox("请输入 Device Name！", "错误", wx.OK | wx.ICON_ERROR)
            return False
        
        # 验证语速
        try:
            speed = float(self.speed.GetValue())
            if speed < 0.5 or speed > 2.0:
                wx.MessageBox("语速必须在0.5到2.0之间！", "错误", wx.OK | wx.ICON_ERROR)
                return False
        except:
            wx.MessageBox("语速必须是数字！", "错误", wx.OK | wx.ICON_ERROR)
            return False
        
        # 验证音量
        try:
            volume = int(self.volume.GetValue())
            if volume < 0 or volume > 100:
                wx.MessageBox("音量必须在0到100之间！", "错误", wx.OK | wx.ICON_ERROR)
                return False
        except:
            wx.MessageBox("音量必须是整数！", "错误", wx.OK | wx.ICON_ERROR)
            return False
        
        return True
    
    def get_params(self):
        """获取所有参数"""
        # 获取选中的音色
        voice_ids = []
        for cb in self.voice_checkboxes:
            if cb.GetValue():
                voice_ids.append(cb.voice_id)
        
        return {
            'product_id': self.product_id.GetValue(),
            'product_key': self.product_key.GetValue(),
            'product_secret': self.product_secret.GetValue(),
            'device_name': self.device_name.GetValue(),
            'voice_ids': voice_ids,
            'speed': self.speed.GetValue(),
            'volume': self.volume.GetValue(),
            'sample_rate': self.sample_rate.GetValue(),
            'audio_format': self.audio_format.GetValue(),
            'api_reg_url': self.api_reg_url,
            'api_tts_url': self.api_tts_url,
            'output_dir': self.output_dir.GetValue()
        }
    
    def prepare_texts(self):
        """准备文本数据"""
        texts = []
        rows = self.text_grid.GetNumberRows()
        
        for i in range(rows):
            text_content = self.text_grid.GetCellValue(i, 0).strip()
            filename = self.text_grid.GetCellValue(i, 1).strip()
            
            if text_content:  # 只要有文本内容就处理
                texts.append((text_content, filename))
        
        return texts
    
    def add_log(self, message):
        """添加日志"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        # 添加到日志文本框
        self.log_text.AppendText(log_line)
        
        # 滚动到最后
        self.log_text.ShowPosition(self.log_text.GetLastPosition())

class TTSApp(wx.App):
    """应用程序类"""
    def OnInit(self):
        self.frame = TTSFrame(None)
        self.frame.Show()
        return True

if __name__ == "__main__":
    app = TTSApp(False)
    app.MainLoop()