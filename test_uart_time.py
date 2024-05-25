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
# file_handler = logging.FileHandler(filename)
# file_handler.setLevel(logging.DEBUG)
# file_handler.setFormatter(format_option)

# 将处理器添加到logger对象中
logger.addHandler(console_handler)
# logger.addHandler(file_handler)

# 定义队列类
class MyQueue(object):
    def __init__(self, size):
        self.size = size  # 定义队列长度
        self.queue = []  # 存储队列 列表

    def __str__(self):
        # 返回对象的字符串表达式，方便查看
        return str(self.queue)

    def inQueue(self, n):
        # 入队
        if self.isFull():
            return -1
        self.queue.append(n)  # 列表末尾添加新的对象

    def outQueue(self):
        # 出队
        if self.isEmpty():
            return -1
        firstelement = self.queue[0]   # 删除队头元素
        self.queue.remove(firstelement)  # 删除队操作
        return firstelement

    def delete(self, n):
        # 删除某元素
        element = self.queue[n]
        self.queue.remove(element)

    def inPut(self, n, m):
        # 插入某元素 n代表列表当前的第n位元素 m代表传入的值
        self.queue[n] = m

    def getSize(self):
        # 获取当前长度
        return len(self.queue)

    def getnumber(self, n):
        # 获取某个元素
        element = self.queue[n]
        return element

    def isEmpty(self):
        # 判断是否为空
        if len(self.queue) == 0:
            return True
        return False

    def isFull(self):
        # 判断队列是否满
        if len(self.queue) == self.size:
            return True
        return False


class SerialCommunication:
    def __init__(self):
        self.serial_port = self.select_serial_port()
        self.baud_rate = 9600
        self.ser = None
        try:
            self.ser = serial.Serial(self.serial_port, self.baud_rate)
        except serial.serialutil.SerialException:
            logging.error("PermissionError: Please check the permission of the serial port.")
            return None
        self.recv_queue = queue.Queue()
        self.recv_queue2 = MyQueue(1024)

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
            if cnt > 0:
                received_data = self.ser.read_all()
                # logging.info("cnt:%d %d", cnt, received_data[0])
                if (received_data is None) or (len(received_data) == 0):
                    continue
                for i in range(0, len(received_data)):
                    self.recv_queue2.inQueue(received_data[i])

                if (self.recv_queue2.getSize() < 2):
                    continue

                while (self.recv_queue2.getSize() > 1 and self.recv_queue2.getnumber(0) != 0xf4 and self.recv_queue2.getnumber(1) != 0xf5):
                    self.recv_queue2.outQueue()

                if (self.recv_queue2.getSize() < 4):
                    continue

                f_size = (self.recv_queue2.getnumber(2) << 8 | self.recv_queue2.getnumber(3)) + 4
                # logging.info("f_size: %d que:%d", f_size, self.recv_queue2.getSize())
                hex_str = ""
                if f_size > 0 and self.recv_queue2.getSize() >= f_size:
                    while (f_size > 0):
                        f_size -= 1
                        hex_val = self.recv_queue2.outQueue()
                        hex_str += hex(int(hex_val))[2:].zfill(2) + " "
                        self.recv_queue.put(hex_val)

                    logging.info("recv: [%d] %s", (len(hex_str) + 1) / 3, hex_str)
                    logging.info("remain: [%d]", self.recv_queue2.getSize())

    def send_str_data(self, data):
        self.ser.write((data + "\n").encode("utf-8"))
        logging.info(f"Sent: {data}")

    def send_byte_data(self, data):
        if len(data) == 0:
            return
        self.ser.write(bytearray.fromhex(data))

        # queue_size = self.recv_queue.qsize()
        # if queue_size != 0:
        #     logging.info("recv_queue size: %d", queue_size)

        logging.info("send: [%d] %s", (len(data) + 1) / 3, data)

    def start_serial_threads(self):
        receive_thread = threading.Thread(target=self.receive_data)
        receive_thread.daemon = True
        receive_thread.start()


    def test_send_recv(self):
        data = "f4 f5 00 61 02 02 09 09 1C 25 01 00 03 00 00 00 F1 00 00 00 00 00 00 00 ff ff ff ff 01 00 0a 00 04 00 5f 00 01 01 00 00 09 5c 00 00 00 0a 00 0a 00 0a 00 0a 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ED 79"
        self.send_byte_data(data)
        self.send_cnt += 1

        t1 = time.perf_counter_ns()
        while True:
            queue_size = self.recv_queue.qsize()
            if queue_size < 81:
                if time.perf_counter_ns() - t1 > 400000000:
                    break
                time.sleep(0.01)
                continue
            else:
                while not self.recv_queue.empty():
                    try:
                        self.recv_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.recv_cnt+=1
                break
        logging.info("recv_queue size: %d", queue_size)

    def test(self):
        self.start_serial_threads()

        self.ser.set_buffer_size(rx_size=100,tx_size=120)

        self.send_cnt = 0
        self.recv_cnt = 0
        log_cnt = 0
        try:
            time1 = time.perf_counter_ns()
            while True:
                if (time.perf_counter_ns() - time1 >= 500000000):
                    time1 = time.perf_counter_ns()
                    time_send_start = time.perf_counter_ns()
                    self.test_send_recv()
                    time_send_end = time.perf_counter_ns()
                    logging.info("total cost: %f", (time_send_end - time_send_start) / 1000000)

                    if (log_cnt % 10 == 0):
                        logging.info("~~~~~~~ send: %d recv: %d ~~~~~~~~~~", self.send_cnt, self.recv_cnt)
                        log_cnt = 0
                    log_cnt += 1

        except KeyboardInterrupt:
            pass

        finally:
            self.ser.close()


if __name__ == "__main__":
    main_serial_cm = SerialCommunication()
    if main_serial_cm.ser is None:
        exit()

    # try:
    #     while True:
    #         data_to_send = input("Enter 'Y' to start (or 'N' to quit): ")
    #         if data_to_send.lower() == "n":
    #             exit()
    #         elif data_to_send.lower() == "y":
    #             break
    # except KeyboardInterrupt:
    #     exit()
    
    main_serial_cm.test()
    # main_serial_cm.ser.close()

