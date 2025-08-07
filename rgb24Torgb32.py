# !/usr/bin/python
# -*- coding: utf-8 -*-
import os
from PIL import Image

def rgb24Torgb32():
    path  = "E:\\test"
    for filename in os.listdir(path):
        file = path + "\\" + filename
        img = Image.open(file)
        if (img.mode == 'RGBA'):
            continue;  

        print("[%s] mode: %s" % (filename, img.mode))
        if (img.mode == 'RGB' or img.mode == 'P'):        
            new_img = Image.new('RGBA', img.size)
            new_img.paste(img, (0, 0))
            new_img.save(file)
            print("change [%s] to RGBA success" % filename)

 

if __name__ == '__main__':
    rgb24Torgb32()
