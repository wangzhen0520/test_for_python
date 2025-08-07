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
# voice_id = "gdfanfp"
voice_id = "jlshimp"
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

    signature = hmac_sha1(product_secret.encode(
        "utf-8"), sig_data.encode("utf-8"))
    print("signature: %s" % signature)

    url = f'{api_reg_url}?productKey={product_key}&format={formate}&productId={product_id}&timestamp={timestamp}&nonce={nonce}&sig={signature}'
    print("url: %s" % url)

    body = {
        "platform": "linux",
        "deviceName": device_name
    }
    payload_body = str.encode(json.dumps(body))

    response = requests.post(url, data=payload_body, headers={
        'Content-Type': 'application/json'})
    print(response.text)
    rsp_str = json.loads(response.text)
    device_secret = rsp_str['deviceSecret']
    print("device_secret: %s" % device_secret)
    return device_secret


def submit_tts(device_secret, text):
    nonce = str(uuid.uuid4()).replace("-", "")
    timestamp = int(round(time.time() * 1000))
    sig_data = f"{device_name}{nonce}{product_id}{timestamp}"
    signature = hmac_sha1(device_secret.encode(
        "utf-8"), sig_data.encode("utf-8"))

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
    path = f"{voice_id}"
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"文件夹 {path} 创建成功")

    file_path = os.path.join(path, f"{text}.mp3")
    with open(file_path, "wb") as f:
        f.write(response.content)
        print(f"write file {file_path} success")


async def test_submit():
    req_device_secret = reg_device()
    # text_list = ['网络不稳定,请稍后重试', '授权失败了,请重新授权', '网络离线了,我听不懂你说什么',
    #              '鉴权失败了,请重新授权', '响应超时了,暂时不能为您服务', '抱歉帮不了您, 有需要再叫我哦',
    #              '抱歉没听懂你说什么, 有需要再叫我哦']
    # text_list = ['语音资源初始化失败了, 请稍后重试']
    text_list = ['我在呢']

    for text in text_list:
        submit_tts(req_device_secret, text)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_submit())
