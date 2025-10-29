# coding=utf-8

'''
requires Python 3.6 or later

pip install asyncio
pip install websockets

'''
import os
import asyncio
import uuid
import json
import requests
import time
import hmac
import hashlib

product_id = "279630209"
product_key = "085757baadb96edbffcdc2f09ab68ab7"
product_secret = "ef59258308d5691c39e07626e0e7a983"
api_reg_url = "https://auth.dui.ai/auth/device/register"
api_tts_url = "https://tts.dui.ai/runtime/v2/synthesize"
formate = "plain"
device_name = "1C:79:2D:2F:B2:98"


def hmac_sha1(key: bytes, message: bytes) -> str:
    """
    计算 HMAC-SHA1 签名
    :param key: 密钥（字节类型）
    :param message: 消息（字节类型）
    :return: 十六进制格式的签名字符串
    """
    # 创建 HMAC-SHA1 对象
    hmac_obj = hmac.new(key, message, hashlib.sha1)

    # 返回十六进制字符串结果
    return hmac_obj.hexdigest()


def reg_device() -> str:
    nonce = str(uuid.uuid4()).replace("-", "")
    print("nonce: %s %d" % (nonce, len(nonce)))
    timestamp = int(round(time.time() * 1000))
    print("timestamp: %d" % timestamp)
    sig_data = f"{product_key}{formate}{nonce}{product_id}{timestamp}"
    print("sig_data: %s" % sig_data)

    signature = hmac_sha1(product_secret.encode("utf-8"), sig_data.encode("utf-8"))
    print("signature: %s" % signature)

    url = f'{api_reg_url}?productKey={product_key}&format={formate}&productId={product_id}&timestamp={timestamp}&nonce={nonce}&sig={signature}'
    print("url: %s" % url)

    body = {
        "platform": "linux",
        "deviceName": device_name
    }
    payload_body = str.encode(json.dumps(body))

    response = requests.post(url, data=payload_body, headers={'Content-Type': 'application/json'})
    print(response.text)
    rsp_str = json.loads(response.text)
    device_secret = rsp_str['deviceSecret']
    print("device_secret: %s" % device_secret)
    return device_secret


def submit_tts(voice_id, device_secret, text_name, text):
    nonce = str(uuid.uuid4()).replace("-", "")
    timestamp = int(round(time.time() * 1000))
    sig_data = f"{device_name}{nonce}{product_id}{timestamp}"
    signature = hmac_sha1(device_secret.encode("utf-8"), sig_data.encode("utf-8"))

    body = {
        "context": {
            "productId": product_id,
        },
        "request": {
            "requestId": nonce,
            "audio": {
                "audioType": "mp3",
                "sampleRate": 16000
            },
            "tts": {
                "text": text,
                "textType": "text",
                "voiceId": voice_id,
                "speed": "1.0",
                "volume": 100
            }
        }
    }
    url = f'{api_tts_url}?voiceId={voice_id}&deviceName={device_name}&nonce={nonce}&productId={product_id}&timestamp={timestamp}&sig={signature}'
    print("url: %s" % url)

    payload_body = str.encode(json.dumps(body))
    response = requests.post(url, data=payload_body, headers={
        'Content-Type': 'application/json'})
    # print(response.text)
    path = f"voiceid/{voice_id}"
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"文件夹 {path} 创建成功")

    file_path = os.path.join(path, f"{text_name}.mp3")
    with open(file_path, "wb") as f:
        f.write(response.content)
        print(f"write file {file_path} success")


async def test_submit():
    req_device_secret = reg_device()

    voice_id_list = ["gdfanfp", "gqlanfp", "gdfanf_natong", "xbekef", "jlshimp", "xijunma", "xmguof"]
    # voice_id_list = ["gdfanfp"]
    # text_list = ['网络不稳定,请稍后重试', '授权失败了,请重新授权', '网络离线了,我听不懂你说什么',
    #              '鉴权失败了,请重新授权', '响应超时了,暂时不能为您服务', '抱歉帮不了您, 有需要再叫我哦',
    #              '抱歉没听懂你说什么, 有需要再叫我哦', '语音资源初始化失败了, 请稍后重试',
    #              '欢迎使用方太语音助手，请用你好方太唤醒我', '饮品已制作完成', '消毒完成啦', '清洁完成啦',
    #              '出水完成啦', '接水盒已满，请清空和清理接水盒', '那我先去休息啦，有需要再喊我吧']
    # text_list = ['当前网络信号不好哦，请稍等一会', '进入配网模式，请按提示音操作', '网络配置失败，请重新帮我配网', '网络配置成功',
    #              '网络已连接', '网络连接失败，请重新帮我联网', '网络已断开', '好的，音量已调到40', '好的，音量已调到60',
    #              '好的，音量已调到80', '现在是最大音量', '现在是最小音量']
    # text_list = ['我在呢']
    text_list = [['INDEX_0_VOICE_OFF.mp3', '设备状态播报已关闭'],
                 ['INDEX_1_VOICE_ON.mp3', '设备状态播报已开启'],
                 ['INDEX_2_FILTER_IS_RESET.mp3', '滤芯寿命已复位'],
                 ['INDEX_7MACHINE_NOT_USED.mp3', '已连续超过七天未使用，请放水3分钟再使用'],
                 ['INDEX_10_FILTER1_ALMOST_OVER.mp3', '滤芯即将到期，请及时更换'],
                 ['INDEX_12_FILTER1_OVER.mp3', '滤芯已到期，请及时更换'],
                 ['INDEX_15_HOT_WATER_COMMING.mp3', '即将出热水，请注意防烫'],
                 ['INDEX_19_WATERPAN_NOT_INPLACE.mp3', '请将接水盒安装到位'],
                 ['INDEX_20_ABNORMAL_SEWAGE_DRAIN.mp3', '排水异常，建议手动清理接水盒'],
                 ['INDEX_21_FULL_CUP_AUTO_STOP_OFF.mp3', '满杯即停功能关闭'],
                 ['INDEX_22_FULL_CUP_AUTOSTOP_ON.mp3', '满杯即停功能开启'],
                 ['INDEX_23_COMPRESSOR_PROTECTION.mp3', '新机首次安装，请上电静置两小时后再使用净水和咖啡功能'],
                 ['INDEX_27_POWER_ON_WASHING.mp3', '上电冲洗中，请等待'],
                 ['INDEX_28_NEW_FILTER_WASHING.mp3', '冲洗调试中，请等待'],
                 ['INDEX_31_FLOW_RECOVERREMIND.mp3', '请持续放水三十秒，热水功能将自动恢复'],
                 ]

    for voice_id in voice_id_list:
        print(f"voice_id: {voice_id}")
        for text in text_list:
            submit_tts(voice_id, req_device_secret, text[0], text[1])


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_submit())
