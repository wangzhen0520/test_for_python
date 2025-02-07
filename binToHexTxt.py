# !/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import string

import struct


def get_file_size(file_path):
    try:
        # 获取文件大小
        size = os.path.getsize(file_path)
        return size
    except FileNotFoundError:
        return "文件未找到"
    except Exception as e:
        return f"发生错误: {e}"

def add_header_to_bin_file(input_file, output_file, header_data):
    # 定义头部结构
    HEADER_FORMAT = '8sI'  # I: unsigned int (4 bytes), h: short (2 bytes), 10s: string of 10 bytes
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    print("HEADER_SIZE: %d" % HEADER_SIZE)

    # 打开输入文件和输出文件
    with open(input_file, 'rb') as infile, open(output_file, 'wb') as outfile:
        # 打包头部数据
        header = struct.pack(HEADER_FORMAT, *header_data)
        
        # 写入头部
        outfile.write(header)
        
        # 读取原始文件内容并写入输出文件
        outfile.write(infile.read())

def change_fonts_to_bin():
    input_file = 'E:\\share\\code\\fotile_project\\rtos_app_touch\\main\\app\\res_spi\\font\OPPOSanSR-sim.ttf'
    output_file = 'E:\\share\\code\\fotile_project\\rtos_app_touch\\main\\app\\res_spi\\font\\font.bin'
    input_file_size = get_file_size(input_file)
    
    print("input_file_size: %d" % input_file_size)
    
    # 示例头部数据
    header_data = (b'font', input_file_size)  # 整数、短整数和字符数组

    # 调用函数
    add_header_to_bin_file(input_file, output_file, header_data)


def convert_bin_to_hex():
    # 将bin文件转换为hex文件, 并保存到指定路径, 并按照16进制格式输出
    bin_file_path = 'E:\\zzk_ota\\ota\\all-test.bin'
    hex_file_path = 'E:\\zzk_ota\\ota\\all-test.txt'

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
                if (i % 1024) == 0:
                    hex_file.write('\n')
            else:
                hex_file.write(' ')

    print(f'Bin file {bin_file_path} has been converted to Hex file {hex_file_path}')


if __name__ == '__main__':
    convert_bin_to_hex()
    # change_fonts_to_bin()
