# -*- coding: utf-8 -*-
import os
import requests
import json
from xml.dom import minidom
import xml.etree.ElementTree as ET

import sys

reload(sys)
sys.setdefaultencoding('utf8')


def get_specification_info():
    url = "http://sdc.specification.huawei.com/get_table_data_api/"
    body = {"table_outer_id": "specification_info", "filter": {"state": 1, "type_name": {"$in": ["M6741-10-Z40-E2"]}}}
    # body = {"table_outer_id": "specification_info", "filter": {"state": 1, "type_name": {"$in": ["M6741-10-Z40", "M6741-10-Z40-E2"]}}}
    # body = {"table_outer_id": "specification_info", "filter": {"state": 1}}

    r = requests.post(url, json=body)
    data = json.loads(r.text)

    items = data['data']
    for each_item in items:
        print('-------------------------------')
        column_name = json.loads('"%s"' % data['col_info']['type_name']['column_name'])
        type_name = json.loads('"%s"' % each_item['type_name'])
        print column_name, type_name

        audio_existence_detection_column_name = json.loads('"%s"' % data['col_info']['audio_existence_detection']['column_name'])
        audio_existence_detection_ability = json.loads('"%s"' % each_item['audio_existence_detection'])
        print audio_existence_detection_column_name, audio_existence_detection_ability

        # write
        filepath = "specification" + "_" + type_name + ".json"
        with open(filepath, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
            print 'write %s success' % filepath


class IntellAbility:
    def __init__(self):
        self.filenameOfxml_ = "ability.xml"
        self.iball_detect_ = "0"
        self.totalAbilityFile = 'totalAbilityInfo.txt'
        self.unique_id = 1
        self.chainAttrInfoList = {}
        self.intellInfoList = {}
        self.ytnInfo = {}

    # 写入xml文档的方法
    def create_intell_xml_ability(self):
        # 新建xml文档对象
        xml = minidom.Document()

        # /message/IntelligentInfo/ChainAttrInfo
        # 创建message根节点
        root = xml.createElement('message')

        # 写入属性version
        root.setAttribute('version', "1.0")

        # 添加根节点到文档中
        xml.appendChild(root)

        # IntelligentInfo
        intell_node = xml.createElement('IntelligentInfo')
        root.appendChild(intell_node)

        # ChainAttrInfo
        chain_node = xml.createElement('ChainAttrInfo')
        intell_node.appendChild(chain_node)

        # 添加IBALL属性
        tag = xml.createElement('IBALL')
        tag.setAttribute('Enable', self.iball_detect_)
        chain_node.appendChild(tag)

        # 保存文档
        with open(self.filenameOfxml_, 'wb') as f:
            f.write(xml.toprettyxml(encoding='utf-8'))

    def walkData(self, root_node, tag, level, result_list):
        temp_list = [self.unique_id, level, tag, root_node.tag, root_node.attrib]
        result_list.append(temp_list)

        # print temp_list
        if tag == 'ChainAttrInfo' and level == 4:
            self.chainAttrInfoList[root_node.tag] = root_node.attrib
        if tag == 'IntelligentInfo' and level == 3:
            self.intellInfoList[root_node.tag] = root_node.attrib
        if tag == 'ITGT_SUPPORT_MODE_LIST' and level == 4:
            print root_node.tag, root_node.text
            if root_node.tag not in self.intellInfoList[tag]:
                self.intellInfoList[tag][root_node.tag] = []
            self.intellInfoList[tag][root_node.tag].append(root_node.text)
        if tag == 'message' and root_node.tag == 'YTNInfo' and level == 2:
            self.ytnInfo[root_node.tag] = root_node.attrib

        self.unique_id += 1
        # 遍历每个子节点
        children_node = root_node.getchildren()
        if len(children_node) == 0:
            return
        for child in children_node:
            self.walkData(child, root_node.tag, level + 1, result_list)
        return

    def getXmlData(self, root):
        level = 1  # 节点的深度从1开始
        result_list = []
        self.walkData(root, root.tag, level, result_list)
        return result_list

    def showallAbility(self, path):
        for dirpath, dirnames, filenames in os.walk(path):
            for filepath in filenames:
                if filepath != 'ability.xml':
                    continue
                ab_file = os.path.join(dirpath, filepath)
                print ab_file

                root = ET.parse(ab_file).getroot()
                self.getXmlData(root)
                # for x in self.getXmlData(root):
                #     print x

        # 所有能力字段写入文件
        with open(self.totalAbilityFile, 'wb') as f:
            for key, value in self.chainAttrInfoList.items():
                print key, value
                f.write(key + '\t' + str(value) + '\n')
            f.write('=' * 80 + '\n')
            print '=' * 80
            for key, value in self.intellInfoList.items():
                print key, value
                f.write(key + '\t' + str(value) + '\n')
            f.write('=' * 80 + '\n')
            print '=' * 80
            for key, value in self.ytnInfo.items():
                print key, value
                f.write(key + '\t' + str(value) + '\n')


if __name__ == '__main__':
    ability = IntellAbility()
    # ability.create_intell_xml_ability()
    path = 'D:/code/HoloSens_SDC/os/board/config/all_model_config'
    ability.showallAbility(path)

    # get_specification_info()
