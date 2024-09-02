# coding=utf-8

import os
import json


class packinfo:
    def __init__(self):
        self.url = ""
        self.name = ""
        self.md5 = ""
        self.size = ""

    def print_info(self):
        print("url:", self.url)
        print("name:", self.name)
        print("md5:", self.md5)
        print("size:", self.size)

    def to_json(self):
        return {
            "url": self.url,
            "name": self.name,
            "md5": self.md5,
            "size": self.size
        }

    def set_url(self, url):
        self.url = url

    def get_url(self):
        return self.url

    def set_name(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def set_md5(self, md5):
        self.md5 = md5

    def get_md5(self):
        return self.md5

    def set_size(self, size):
        self.size = size

    def get_size(self):
        return self.size


def test_json():
    # 读取json文件
    with open('ota_config.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        print(data)

        packinfo_list = []

        # 遍历json文件中的数据
        for key, value in data.items():
            if isinstance(value, list):
                for item in value:
                    pkinfo = packinfo()
                    pkinfo.set_url(item['url'])
                    pkinfo.set_name(item['name'])
                    pkinfo.set_md5(item['md5'])
                    pkinfo.set_size(item['size'])
                    packinfo_list.append(pkinfo)

    packet_info = []
    for pkinfo in packinfo_list:
        # 读取文件
        file_path = pkinfo.get_name() + '.md5'
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                buf = f.readline().lower()
                pkinfo.set_md5(buf)
                print("file: %s md5: %s" % (file_path, pkinfo.get_md5()))
        except FileNotFoundError:
            print("file: %s not exist" % file_path)

        packet_info.append(pkinfo.to_json())
        print(pkinfo.to_json())

    data["packet"] = packet_info

    # 写入json文件
    with open('ota_config_bak.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        print("json file write success")


class ota_packet():
    def __init__(self, base_path="", cfg_path="ota_config.json", file_list=[]):
        self.base_path = base_path
        self.cfg_path = cfg_path
        self.partion_file_list = file_list

    def get_partion_file_md5(self, file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                buf = f.readline().rstrip()
                if buf.strip() != "":
                    return buf.upper()
                else:
                    return None
        except FileNotFoundError:
            print("file: %s not exist" % file_name)
            return None

    def get_partion_file_size(self, file_name):
        if os.path.exists(file_name):
            file_size = os.stat(file_name).st_size
            return file_size
        else:
            print("file: %s not exist" % file_name)
            return None

    def build_packet_info(self):
        packet_info = []
        for partion in self.partion_file_list:
            pkinfo = packinfo()
            pkinfo.set_name(partion)
            md5 = self.get_partion_file_md5(self.base_path + '/md5_pkg/' + partion + '.md5')
            if md5 is not None:
                pkinfo.set_md5(md5)
            else:
                print("file: %s md5 not exist" % partion)
                continue

            size = self.get_partion_file_size(self.base_path + '/' + partion)
            if size is not None:
                pkinfo.set_size(size)
            else:
                print("file: %s size not exist" % partion)
                continue

            packet_info.append(pkinfo.to_json())

        return packet_info

    def build_ota_default_config(self):
        '''
        生成默认的ota配置文件信息
        flash_threshold: 设置升级包存放在flash的阈值 (单位:字节)
        download_type: 升级数据包下载缓存类型 0-flash优先 1-内存优先
        packet: 分区信息
        '''
        data = {}
        data["flash_threshold"] = 82837504  # 79M
        data["download_type"] = "0"  # 0-flash优先 1-内存优先
        data["packet"] = []  # 分区信息

        return data

    def build_ota_config(self):
        pakcet = self.build_packet_info()
        if pakcet is None:
            print("build packet info failed")
            return

        data = self.build_ota_default_config()

        # 读取json文件
        try:
            with open(self.cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print("file: %s not exist!!! userd default config" % self.cfg_path)

        data["packet"] = pakcet

        # 写入json文件
        with open(self.cfg_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            print("write ota json config success")


if __name__ == '__main__':
    ota = ota_packet("ota", "ota_config.json", ["recovery.img", "bootlogo.img", "rootfs.img"])
    ota.build_ota_config()
