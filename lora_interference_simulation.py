import serial
import serial.tools.list_ports
import threading
import queue, time, json
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

format_option = logging.Formatter('%(asctime)s.%(msecs)03d | %(levelname)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
filename = f'AutoTest_{now}.log'

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(format_option)

# 创建文件处理器
file_handler = logging.FileHandler(filename)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(format_option)

# 将处理器添加到logger对象中
logger.addHandler(console_handler)
logger.addHandler(file_handler)

class SerialCommunication:
    def __init__(self):
        self.serial_port = self.select_serial_port()
        self.baud_rate = 115200
        self.ser = None
        try:
            self.ser = serial.Serial(self.serial_port, self.baud_rate)
        except serial.serialutil.SerialException:
            logging.error("PermissionError: Please check the permission of the serial port.")
            return None
        self.recv_queue = queue.Queue()

    def get_available_ports(self):
        ports = serial.tools.list_ports.comports()
        ports_list = []
        for i in range(len(ports)):
            comport = list(ports[i])
            ports_list.append([i, comport[0], comport[1]])
        return ports_list

    def print_available_ports(self):
        ports = self.get_available_ports()
        if ports:
            logging.info("%-10s %-10s %-50s", "num", "number", "name")
            for port in ports:
                logging.info("%-10s %-10s %-50s", port[0], port[1], port[2])
        else:
            logging.warning("No available ports found.")

    def select_serial_port(self):
        self.print_available_ports()
        while True:
            selected_port = input("Enter the serial port (e.g., COM1) or 'exit' to quit: ")
            if selected_port.lower() == 'exit':
                exit()

            ports = self.get_available_ports()
            for port in ports:
                if str(port[0]) == selected_port:
                    logging.info("Selected port: %s" % port[1])
                    return port[1]

            logging.warning("Invalid serial port. Please try again.")

    def crc16(self, data: bytes) -> int:
        # 初始化crc为0xFFFF
        crc = 0xFFFF
        # 循环处理每个数据字节
        for byte in data:
            # 将每个数据字节与crc进行异或操作
            crc ^= byte
            # 对crc的每一位进行处理
            for _ in range(8):
                # 如果最低位为1，则右移一位并执行异或0xA001操作(即0x8005按位颠倒后的结果)
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                # 如果最低位为0，则仅将crc右移一位
                else:
                    crc = crc >> 1
        # 返回最终的crc值
        return crc

    def receive_data(self):
        while True:
            cnt = self.ser.in_waiting
            if cnt <= 0:
                time.sleep(0.01)
                continue
            
            received_data = self.ser.read(cnt)
            if received_data[0] == 0xff:
                hex_str = ""
                recv_hex_str = received_data.hex()
                for i in range(0, len(recv_hex_str), 2):
                    hex_str += recv_hex_str[i:i+2].upper() + " "
                logging.info("recv: [%d] %s", len(hex_str) / 3, hex_str)

                # crc 校验
                crc = self.crc16(received_data[0:cnt - 2]).to_bytes(2, 'little')
                if not (crc[0] == received_data[cnt - 2]
                        and crc[1] == received_data[cnt - 1]):
                    logging.error("crc check fail")
                    break
                self.recv_queue.put(received_data)
            else:
                pass
                # print(received_data.decode())

    def get_lora_freq(self):
        data = "FF 03 00 D3 00 01 60 2D"
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取当前信道
                if (hex_str[2] == 0x02) and (hex_str[3] == 0x00):
                    logging.info("get freq: %d", hex_str[4])
                    self.freq = hex_str[4]
                else:
                    logging.error("get freq fail")
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue
            

    def set_lora_freq(self, freq):
        hex_str = hex(int(freq))[2:].zfill(2)
        data = "FF 10 00 D3 00 01 02 00 " + str(hex_str).upper() + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 扫描信道设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x00) and (hex_str[3] == 0xD3):
                    logging.info("set freq success: %s", freq)
                else:
                    logging.error("set freq failed: %s", freq)
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def get_lora_netwk_id(self):
        data = "FF 03 00 D8 00 02 51 EE"
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取网络标识
                if (hex_str[2] == 0x04) and (hex_str[3] == 0x00):
                    self.netwk_id = hex_str[5] << 8 | hex_str[6]
                    logging.info("get netwk_id: %d", self.netwk_id)
                else:
                    logging.error("set netwk_id fail")
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue    

    def set_lora_netwk_id(self, net_id):
        hex_str = hex(int(net_id))[2:].zfill(2)
        net_id_str = str(hex_str).upper()
        data = "FF 10 00 D8 00 02 04 00 00 " + net_id_str[0:2] + " " + net_id_str[2:4] + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 网络标识设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x00) and (hex_str[3] == 0xD8):
                    logging.info("set netwk_id success: %s", net_id)
                else:
                    logging.error("set netwk_id failed: %s", net_id)
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def get_lora_interference_duration(self):
        data = "FF 03 ED 2A 00 01 85 70"
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取干扰评估时长
                if (hex_str[1] == 0x03) and (hex_str[2] == 0x02):
                    self.interf_dura = hex_str[3] << 8 | hex_str[4]
                    logging.info("get interf_dura: %d", self.interf_dura)
                else:
                    logging.error("get interf_dura fail")
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def set_lora_interference_duration(self, duration):
        hex_str = hex(int(duration))[2:].zfill(4)
        duration_str = str(hex_str).upper()
        data = "FF 10 ED 2A 00 01 02 " + duration_str[0:2] + " " + duration_str[2:4] + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 设置干扰评估时长
                if (hex_str[1] == 0x10) and (hex_str[2] == 0xED) and (hex_str[3] == 0x2A):
                    logging.info("set interf_dura success: %s", duration)
                else:
                    logging.error("set interf_dura failed: %s", duration)
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def get_lora_netwk_addr(self):
        data = "FF 03 01 2D 00 02 40 20"
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取网络地址
                if (hex_str[1] == 0x03) and (hex_str[2] == 0x04):                    
                    self.netwk_addr = hex_str[3] << 24 | hex_str[4] << 16 | hex_str[5] << 8 | hex_str[6]
                    logging.info("get netwk_addr: %d", self.netwk_addr)
                else:
                    logging.error("get netwk_addr fail")
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def set_lora_netwk_addr(self, addr):
        hex_str = hex(int(addr))[2:].zfill(2)
        addr_str = str(hex_str).upper()
        data = "FF 10 EB 3C 00 04 08 A5 AD A5 AD " + addr_str[0:2] + " " + addr_str[2:4] + " " + addr_str[4:6] + " " + addr_str[6:8] + " "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 网络标识设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0xEB) and (hex_str[3] == 0x3C):
                    logging.info("set netwk_addr success: %s", addr)
                else:
                    logging.error("set netwk_addr failed: %s", addr)
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def get_lora_rf_speed(self):
        data = "FF 03 00 D4 00 01 D1 EC"
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取无线速率
                if (hex_str[2] == 0x02) and (hex_str[3] == 0x00):
                    logging.info("get rf speed id: %d", hex_str[4])
                    self.rf_speed_id = hex_str[4]
                else:
                    logging.error("get rf speed failed")
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def get_lora_scan_channel(self):
        data = "FF 03 01 CD 00 07 81 D5"
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 获取扫描信道
                if (hex_str[1] == 0x03) and (hex_str[2] == 0x0e):
                    logging.info("get start scan ch: %d", hex_str[3])
                    self.start_freq = hex_str[3]
                else:
                    logging.error("get start scan ch failed")
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def set_lora_scan_channel(self, ch):
        hex_str = hex(int(ch))[2:].zfill(2)
        data = "FF 10 01 CD 00 07 0E " + str(hex_str).upper() + " 00 FF FF FF FF FF FF FF FF FF FF 00 00 "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 扫描信道设置结果
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x01) and (hex_str[3] == 0xCD):
                    logging.info("set scan ch success: %s", ch)
                else:
                    logging.error("set scan ch failed: %s", ch)
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue

    def set_interference_addr(self, addr):
        hex_str = hex(int(addr))[2:].zfill(2)
        addr_str = str(hex_str).upper()
        data = "FF 10 01 F4 00 03 06 " + addr_str[0:2] + " " + addr_str[2:4] + " " + addr_str[4:6] + " " + addr_str[6:8] + " 00 00 "
        data_byte = bytearray.fromhex(data)
        crc = self.crc16(data_byte).to_bytes(2, byteorder='little')
        data += hex(crc[0])[2:].upper().zfill(2) + " "
        data += hex(crc[1])[2:].upper().zfill(2)
        # 设置干扰目的地址
        self.send_byte_data(data)

        retry_cnt = 0
        while True:
            try:
                hex_str = self.recv_queue.get(timeout=5)
                # 设置干扰目的地址
                if (hex_str[1] == 0x10) and (hex_str[2] == 0x01):
                    logging.info("set interfer addr:%d success", addr)
                else:
                    logging.info("set interfer addr:%d fail or not support", addr)
                break
            except:
                logging.warning("timeout")
                time.sleep(1)
                self.send_byte_data(data)
                retry_cnt += 1
                if retry_cnt > 3:
                    break
                continue
        
    def lora_interference_simulation(self):
        # 触发跳频指令
        self.send_byte_data("FF 03 02 26 00 05 70 64")
        logging.info("simulation success")

    def send_str_data(self, data):
        self.ser.write((data + "\n").encode("utf-8"))
        logging.info(f"Sent: {data}")

    def send_byte_data(self, data):
        if len(data) == 0:
            return
        
        queue_size = self.recv_queue.qsize()
        if queue_size != 0:
            logging.info("recv_queue size: %d", queue_size)
        logging.info("send: [%d] %s", (len(data) + 1) / 3, data)
        self.ser.write(bytearray.fromhex(data))

    def start_serial_threads(self):
        receive_thread = threading.Thread(target=self.receive_data)
        receive_thread.daemon = True
        receive_thread.start()

    def test(self):
        self.start_serial_threads()

        try:
            while True:
                data_to_send = input("Enter data to send (or 'exit' to quit): ")
                if data_to_send.lower() == "exit":
                    break
                # self.send_byte_data(data_to_send)
                if data_to_send == '1':
                    self.get_lora_freq()
                elif data_to_send == '2':
                    self.get_lora_netwk_id()
                elif data_to_send == '3':
                    self.get_lora_rf_speed()
                elif data_to_send == '4':
                    self.get_lora_scan_channel()
                elif data_to_send == '5':
                    ch = input("Enter start ch: ")
                    self.set_lora_scan_channel(ch)
                elif data_to_send == '6':
                    addr = input("Enter dest addr: ")
                    self.lora_interference_simulation(addr)
                elif data_to_send == '7':
                    net_id = input("Enter net id: ")
                    self.set_lora_netwk_id(net_id)

        except KeyboardInterrupt:
            pass

        finally:
            self.ser.close()


class LocConfig:
    def __init__(self):
        self.interference_duration = 60 # 干扰评估时长
        self.interference_num = 0 # 干扰次数, 0:一直干扰 >0:干扰多少次后结束
        self.time_interval = 200 # 毫秒
        self.next_interference_interval = 60 # 下次干扰触发间隔 秒

        try:
            with open("config.json", 'r', encoding='UTF-8') as f:
                buf = json.load(f)
                self.interference_duration = buf.get('interference_duration')
                self.time_interval = buf.get('time_interval')
                self.interference_num = buf.get('interference_num')
                self.next_interference_interval = buf.get('next_interference_interval')
                logging.info("interference_duration: %d", self.interference_duration)
                logging.info("interference_num: %d", self.interference_num)
                logging.info("time_interval: %d", self.time_interval)
                logging.info("next_interference_interval: %d", self.next_interference_interval)
        except FileNotFoundError:
            logging.warning("config.json not found")
            return None

    def get_interference_duration(self):
        return self.interference_duration
    
    def get_interference_num(self):
        return self.interference_num

    def get_time_interval(self):
        return self.time_interval
    
    def get_next_interference_interval(self):
        return self.next_interference_interval


if __name__ == "__main__":
    #读取当前配置, 读取不到使用默认配置
    cfg = LocConfig()

    main_serial_cm = SerialCommunication()
    if main_serial_cm.ser is None:
        exit()
    # serial_communication.test()

    sub_serial_cm = SerialCommunication()
    if main_serial_cm.ser is None:
        exit()

    try:
        while True:
            data_to_send = input("Enter 'Y' to start (or 'N' to quit): ")
            if data_to_send.lower() == "n":
                exit()
            elif data_to_send.lower() == "y":
                break
    except KeyboardInterrupt:
        exit()

    main_serial_cm.start_serial_threads()
    sub_serial_cm.start_serial_threads()

    try:
        main_serial_cm.get_lora_freq()
        main_serial_cm.get_lora_netwk_id()
        main_serial_cm.get_lora_netwk_addr()
        main_serial_cm.get_lora_interference_duration()
        main_serial_cm.set_lora_interference_duration(cfg.get_interference_duration())

        sub_serial_cm.get_lora_freq()
        sub_serial_cm.set_lora_netwk_id(main_serial_cm.netwk_id - 1)
        sub_serial_cm.set_lora_freq(main_serial_cm.freq)
        sub_serial_cm.set_interference_addr(main_serial_cm.netwk_addr)

        start_time = time.time()
        interference_start_time = start_time
        interference_cnt = 0
        while True:
            if (time.time() - start_time) > 10:
                main_serial_cm.get_lora_freq()
                sub_serial_cm.get_lora_freq()
                if (main_serial_cm.freq != sub_serial_cm.freq):
                    interference_cnt += 1
                    logging.info("interference cnt: %d cost: %ds", interference_cnt, time.time() - interference_start_time)
                    if cfg.get_interference_num() > 0 and interference_cnt > cfg.get_interference_num():
                        break

                    logging.info("next interference interval will wait: %ds", cfg.get_next_interference_interval())
                    time.sleep(cfg.get_next_interference_interval())
                    sub_serial_cm.set_lora_freq(main_serial_cm.freq)
                    sub_serial_cm.set_interference_addr(main_serial_cm.netwk_addr)
                start_time = time.time()
                interference_start_time = start_time

            sub_serial_cm.lora_interference_simulation()
            time.sleep(cfg.get_time_interval() / 1000.0)
    except KeyboardInterrupt:
        pass
    finally:
        main_serial_cm.ser.close()
        sub_serial_cm.ser.close()

