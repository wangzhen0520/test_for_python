# !/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import string


def convert_bin_to_hex():
    # 将bin文件转换为hex文件, 并保存到指定路径, 并按照16进制格式输出
    bin_file_path = 'E:\\share\\ota\\app.bin'
    hex_file_path = 'E:\\share\\ota\\app.txt'

    with open(bin_file_path, 'rb') as bin_file:
        bin_data = bin_file.read()

    with open(hex_file_path, 'w') as hex_file:
        i = 0
        for byte in bin_data:
            i += 1
            
            # if i > 3615 :
            #     while i <= 4096:
            #         hex_file.write('{:02x}'.format(255))
                    
            #         if i % 16 == 0:
            #             hex_file.write(' \n')
            #         else:
            #             hex_file.write(' ')
                        
            #         i += 1
                
            hex_file.write('{:02x}'.format(byte))

            if i % 16 == 0:
                hex_file.write(' \n')
            else:
                hex_file.write(' ')

    print(f'Bin file {bin_file_path} has been converted to Hex file {hex_file_path}')


if __name__ == '__main__':
    convert_bin_to_hex()
