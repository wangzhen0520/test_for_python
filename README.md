# test_for_python

use python 2.7


# lora_interference_simulation.py
use python 3.8.10
pip install serial
pip install pyserial
pip install pillow
# 打包exe
pyinstaller -F lora_interference_simulation.py --hidden-import serial

# cat1_iqc_detect.py
pip install wxPython