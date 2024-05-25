# !/usr/bin/python
# -*- coding: utf-8 -*-

import json
import re
import sys
from datetime import datetime
from time import sleep

# import paramiko
# import time
import requests
import urllib3
from requests.auth import HTTPDigestAuth

reload(sys)
sys.setdefaultencoding('utf8')

urllib3.disable_warnings()

username = 'ApiAdmin'
passwd = 'HuaWei123'


def demo(ip):
    appurl = 'https://%s/SDCAPI/V1.0/ItsApp/Tgateway/LaneParam?ChannelId=101' % ip
    appur2 = 'https://%s/SDCAPI/V1.0/ItsApp/Epolice/LaneParam?ChannelId=101' % ip

    try:
        for i in range(100):
            print("-----START Tgateway ： %s-------" % (ip))
            r = requests.get(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            data = r.text
            print("第【%s】次GET：状态[%s]" % (i, r.status_code))
            sleep(1)
            print("第【%s】次SET：状态[%s], 时间 %s" % (i, r.status_code, datetime.now()))
            r = requests.put(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data)
            sleep(30)

            print("-----START Epolice : %s-------" % (ip))
            r = requests.get(appur2, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            data = r.text
            print("第【%s】次GET：状态[%s]" % (i, r.status_code))
            sleep(1)
            print("第【%s】次SET：状态[%s], 时间 %s" % (i, r.status_code, datetime.now()))
            r = requests.put(appur2, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data)
            sleep(30)
            # create_memout()
            # print("-----END-------")
    except:
        raise "FAIL!!"


def testCallOSD(ip):
    appurl = 'https://%s/SDCAPI/V1.0/ItsApp/FrameOSD?ChannelId=101&OverlayPicType=0' % ip

    try:
        data = ''
        i = 0
        while True:
            print("-----START OSD ： %s-------" % (ip))
            if not data:
                r = requests.get(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
                data = r.text
                print("第【%s】次GET：状态[%s]" % (i, r.status_code))
                sleep(1)

            print("第【%s】次SET：状态[%s], 时间 %s" % (i, r.status_code, datetime.now()))
            r = requests.put(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False,
                             data=data.encode('utf-8'))
            sleep(0.1)
            i += 1
    except:
        raise "FAIL!!"


def testTDome(ip):
    appurl1 = 'https://%s/SDCAPI/V1.0/TrafficDomeApp/AlgParam?channelId=101' % ip
    appurl2 = 'https://%s/SDCAPI/V1.0/TrafficDomeApp/SceneAppParam?channelId=101&index=1' % ip

    try:
        data = ''
        i = 0
        while True:
            print("-----START ： %s-------" % (ip))
            r = requests.get(appurl1, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            data = r.text
            print("[%s] 第【%s】次GET：状态[%s]" % (datetime.now(), i, r.status_code))

            json_str = json.loads(r.text)
            if json_str['enable'] == 1:
                json_str['enable'] = 0
                print('enable -> 0')
            else:
                json_str['enable'] = 1
                print('enable -> 1')

            data2 = json.dumps(json_str)
            r = requests.put(appurl1, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data2)
            print("[%s] 第【%s】次SET：状态[%s]" % (datetime.now(), i, r.status_code))

            # r = requests.get(appur2, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            # data = r.text
            # print("[%s] 第【%s】次GET：状态[%s]" % (datetime.now(), i, r.status_code))
            sleep(10)
            i += 1
    except Exception as e:
        print e


def testvhdParam(ip):
    appurl = 'https://%s/SDCAPI/V1.0/VhdApp/VhdParam?UUID=29dfda17-5b93-a8cc-ea14-dff686912f8f' % ip

    try:
        data = ''
        i = 0
        while True:
            r = requests.get(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            print("[%s] 第【%s】次GET：状态[%s]" % (datetime.now(), i, r.status_code))
            json_str = json.loads(r.text)
            if json_str['enable'] == 1:
                json_str['enable'] = 0
                print('enable -> 0')
            else:
                json_str['enable'] = 1
                print('enable -> 1')

            data2 = json.dumps(json_str)
            r = requests.put(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data2)
            print("[%s] 第【%s】次SET：状态[%s]" % (datetime.now(), i, r.status_code))
            # sleep(10)
    except:
        raise "FAIL!!"


def testMultiTask(ip):
    appurl = 'https://%s/SDCAPI/V1.0/MultiTaskApp/TaskLists?UUID=b9dbcb63-0d58-3f29-cb95-ffd6a554b363' % ip
    data1 = {"taskList": [
        {"uuid": "b9dbcb63-0d58-3f29-cb95-ffd6a554b363", "algMode": 7, "bussinessStatus": {"behaviorDetect": 0}}]}
    data2 = {"taskList": [
        {"uuid": "b9dbcb63-0d58-3f29-cb95-ffd6a554b363", "algMode": 7, "bussinessStatus": {"behaviorDetect": 1}}]}

    try:
        i = 0
        while True:
            print("-----START ： %s-------" % (ip))
            r = requests.get(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            print("第【%s】次GET：状态[%s]" % (i, r.status_code))
            sleep(3)

            i += 1

            if i % 100 == 0:
                r = requests.put(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data1)
                print("第【%s】次SET：状态[%s]" % (i, r.status_code))
                sleep(3)
            elif i % 120 == 0:
                r = requests.put(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data1)
                print("第【%s】次SET：状态[%s]" % (i, r.status_code))
                sleep(3)
    except:
        raise "FAIL!!"


def testLight(ip):
    appurl = 'https://%s/SDCAPI/V1.0/ItsApp/ManualSnap' % ip
    data = '{"UUID":"4dbbe6ed-06af-2bb7-55d4-bb454662ac2c","snapNum":1,"snapInterval":[0,0,0,0]}'
    appurl2 = 'https://%s/SDCAPI/V1.0/IspIaas/DN?UUID=4dbbe6ed-06af-2bb7-55d4-bb454662ac2c&AlgMode=0' % ip
    try:
        i = 0
        while True:
            r = requests.get(appurl2, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            print("第【%s】次GET：状态[%s]" % (i, r.status_code))
            # print(r.text)
            json_str = json.loads(r.text)
            # print(json_str)
            if json_str['polarizerMode'] == 1:
                json_str['polarizerMode'] = 0
                print('polarizerMode -> 0')
            else:
                json_str['polarizerMode'] = 1
                print('polarizerMode -> 1')
            # print(json_str)

            data2 = json.dumps(json_str)
            # print(data2)

            r = requests.put(appurl2, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data2)
            print("第【%s】次GET：状态[%s]" % (i, r.status_code))
            sleep(3)

            # r = requests.get(appurl2, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data='')
            # print("第【%s】次GET：状态[%s]" % (i, r.status_code))
            # print(r.text)

            j = 0
            while j < 10:
                r = requests.put(appurl, auth=HTTPDigestAuth('%s' % username, passwd), verify=False, data=data)
                print("第【%s】次SET：状态[%s]" % (j, r.status_code))
                sleep(1.5)
                j += 1
            i += 1
    except:
        raise "FAIL!!"


def getSpecification():
    url = "http://sdc.specification.huawei.com/get_table_data_api/"
    body = {"table_outer_id": "specification_info", "filter": {"state": 1, "type_name": {"$in": ["M6741-10-Z40"]}}}
    # body = { "table_outer_id" : "specification_info", "filter" : { "state": 1 } }
    try:
        r = requests.post(url, json=body)
        # print(len(r.text))
        # print(r.text[0:100])

        data = json.loads(r.text)
        # print('data: %s' % data)
    except:
        raise "FAIL!!"


'''
cnt = 1
def create_memout():
    global cnt

    #登录，返回ssh
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('90.85.95.124', username='admin', password='HuaWei123')

    chan=ssh.invoke_shell()#新函数
    chan.send('Y\n')
    time.sleep(1)
    chan.send('su\n')
    time.sleep(1)
    chan.send('HuaWei123\n')
    time.sleep(1)
    chan.send('cd /nfsroot\n')
    time.sleep(1)
    chan.recv(1024)

#    ssh.exec_command('ls -l')
    chan.send('./meminfo.sh' + ' ' + str(cnt) + '\n')
    time.sleep(25)
    cnt = cnt +1
 #   res=chan.recv(1024)#非必须，接受返回消息
 #   print(res)
    chan.close()
    ssh.close()
'''


def usage():
    print(
        """
Usage:sys.args[0] [option]
-h or --help：显示帮助信息
-i or --ip：设备IP
"""
    )


def check_ip(ip):
    compile_ip = re.compile(
        '^(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|[1-9])\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)$')
    if compile_ip.match(ip):
        return True
    else:
        return False


def main():
    # try:
    #     opts,args=getopt.getopt(sys.argv[1:],'hi:',['help','ip='])
    # except getopt.GetoptError:
    #     usage()
    #     sys.exit(2)

    # if not opts:
    #     usage()
    #     sys.exit()

    # ip=None
    # for o,a in opts:
    #     if o in ('-h','--help'):
    #         usage()
    #         sys.exit()
    #     elif o in ('-i','--ip'):
    #         ip = a
    #     else:
    #         print("%s ==> %s"%(o, a));
    #         sys.exit()

    # if not check_ip(ip):
    #     print("ip: %s not valid"%ip)
    #     sys.exit()

    ip = '90.85.45.29'
    # demo(ip)
    # testCallOSD(ip)
    testTDome(ip)

    # getSpecification()

    # testMultiTask(ip)

    # testLight(ip)

    # testvhdParam(ip)


if __name__ == '__main__':
    main()
