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
pip install pyserial wxPython psutil pyinstaller
# 打包 exe（onedir 目录模式，避免 onefile 运行时解压到 TEMP/_MEI...）
# 图标已内嵌到代码和 spec 中，res 目录只需要保留两个 loader exe
pyinstaller -y bk7236_flasher.spec
# 输出目录: dist\bk7236_flasher\bk7236_flasher.exe

test_speech_tts.py
# 虚拟环境中安装以下库
pip install requests
# 打包exe
pyinstaller -F test_speech_tts.py --noconsole --hidden-import wx -p E:\\share\\code\\python_work\\test_for_python\\.venv\\Lib\\site-packages

## TTS 音色配置

`test_speech_tts.py` 已内置常用音色，没有 `voices.json` 时也能正常运行。
如需新增、改名或停用音色，可在 Python 文件（或打包后的 EXE）的同一目录放置
`voices.json`。程序启动时会把该文件与内置音色合并，因此不需要重新编译。

完整示例：

```json
{
  "voices": [
    { "id": "new_voice_id", "name": "新增音色名称" },
    { "id": "xmguof", "name": "修改后的显示名称" },
    { "id": "yezi1f_csh", "enabled": false }
  ]
}
```

- 新增音色：填写新的 `id` 和 `name`，`enabled` 可省略，默认是 `true`。
- 修改内置音色名称：填写已有 `id` 和新的 `name`。
- 停用音色：设置 `"enabled": false`；内置音色可省略 `name`，新增音色应保留 `name`。
- 重新启用音色：设置 `"enabled": true`；删除内置音色的配置项会恢复其默认状态，删除新增音色的配置项会移除它。
- `id` 在外部配置中不能重复，且至少要保留一个启用的音色。
- JSON 不支持 `//` 注释，最后一项末尾也不能有多余逗号。

可复制 `voices.example.json` 为 `voices.json` 后再按实际音色修改。
