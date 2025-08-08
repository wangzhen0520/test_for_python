# !/usr/bin/python
# -*- coding: utf-8 -*-

import imageio
import os
import sys
# import pygifsicle


def create_gif(source, name, duration):
    '''
    生成gif的函数, 原始图片仅支持png
    source: 为png图片列表(排好序)
    name: 生成的文件名称
    fps: 帧率，也就是画面每秒传输帧数，值越大，gif动图的播放速度越大
    loop: 循环次数, 0为无限循环
    '''
    # 读取PNG文件并创建GIF
    with imageio.get_writer(name, mode='I', fps=duration, loop=0) as writer:  # duration为每帧间隔时间（秒）
        for image_path in source:
            image = imageio.imread(image_path)
            writer.append_data(image)
    # pygifsicle.optimize(name, name+'-min.gif')
    print("%s 处理完成" % name)


def gen_gif(or_path, output, fps=10):
    '''
    or_path: 目标的文件夹
    '''
    pic_list = sorted([os.path.join(or_path, f) for f in os.listdir(or_path) if f.endswith('.png')])
    gif_name = output  # 生成gif文件的名称
    duration_time = fps  # (1/fps) 每秒帧数
    # print(duration_time)
    # 生成gif
    create_gif(pic_list, gif_name, duration_time)


if __name__ == '__main__':
    path = 'E:\\zzk_ota\\2.8寸屏\\自动'
    gen_gif(path, "auto.gif", 12)

    path = 'E:\\zzk_ota\\2.8寸屏\\开机动画'
    gen_gif(path, "bootanim.gif", 12)

    path = 'E:\\zzk_ota\\2.8寸屏\\强档'
    gen_gif(path, "strong.gif", 12)

    path = 'E:\\zzk_ota\\2.8寸屏\\波动'
    gen_gif(path, "wave.gif", 12)

    path = 'E:\\zzk_ota\\2.8寸屏\\弱档'
    gen_gif(path, "weak.gif", 12)
