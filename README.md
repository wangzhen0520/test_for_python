# test_for_python

use python 2.7


# lora_interference_simulation.py
use python 3.8.10
# 进入虚拟环境

# 虚拟环境中安装以下库
pip install serial
pip install pyserial
pip install pillow
# 打包exe
pyinstaller -F lora_interference_simulation.py --hidden-import serial -p E:\\share\\code\\python_work\\test_for_python\\.venv\\Lib\\site-packages

# cat1_iqc_detect.py
# 虚拟环境中安装以下库
pip install wxPython  
pyinstaller -F cat1_iqc_detect.py --noconsole --hidden-import serial --hidden-import wx -p E:\\share\\code\\python_work\\test_for_python\\.venv\\Lib\\site-packages

bk7236_flasher.py
# 虚拟环境中安装以下库
pip install psutil
# 打包exe
pyinstaller -F bk7236_flasher.py --noconsole --hidden-import serial --hidden-import wx -p E:\\share\\code\\python_work\\test_for_python\\.venv\\Lib\\site-packages -i res\\bk7236_flasher.ico
# 手动修改spec文件 将datas=[], 修改为 datas=[('res', 'res')]
pyinstaller bk7236_flasher.spec

test_speech_tts.py
# 虚拟环境中安装以下库
pip install requests
# 打包exe
pyinstaller -F test_speech_tts.py --noconsole --hidden-import wx -p E:\\share\\code\\python_work\\test_for_python\\.venv\\Lib\\site-packages