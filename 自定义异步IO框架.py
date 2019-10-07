import socket
import select
import re
import time


class Future(object):

    def __init__(self, time_out=0):
        self.result = None
        self.start_time = time.time()
        self.time_out = time_out


class HttpRequest(object):

    def __init__(self, content):
        self.content = content
        self.header_bytes = bytes()
        self.body_bytes = bytes()
        self.method = ''
        self.url = ''
        self.protocal = ''
        self.headers_dict = {}
        self.initialize()
        self.initialize_header()

    def initialize(self):
        temp_list = self.content.split(b'\r\n\r\n', 1)
        # 类似于GET请求，只有请求头
        if len(temp_list) == 1:
            self.header_bytes += temp_list[0]
        else:
            # 类似于POST请求既有请求头又有请求体
            h, b = temp_list
            self.header_bytes += h
            self.body_bytes += b

    # 将请求头的字节类型转成字符串类型
    def header_str(self):
        return str(self.header_bytes, encoding='utf-8')

    # 处理请求头、请求体
    def initialize_header(self):
        headers = self.header_str().split('\r\n')
        # 处理请求首行 GET /index HTTP/1.0
        first_line_list = headers[0].split(' ')
        if len(first_line_list) == 3:
            self.method, self.url, self.protocal = first_line_list
        # 处理请求头，变成字典形式
        for line in headers:
            headers_list = line.split(':')
            if len(headers_list) == 2:
                headers_title, headers_body = headers_list
                self.headers_dict[headers_title] = headers_body


# 视图函数
def login(request):
    return 'login'


def index(request):
    """
    非正常的请求，返回future对象
    """
    future = Future(5)
    return future

# 路由系统
routers = [
    ('/login/', login),
    ('/index/', index),
]


def run():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 如果要已经处于连接状态的soket在调用closesocket后强制关闭，不经历TIME_WAIT的过程：
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 8888), )
    sock.setblocking(False)
    sock.listen(128)

    inputs = []
    inputs.append(sock)
    asyn_request_dic = {
        # 'sock':future
    }
    while True:
        rlist, wlist, elist = select.select(inputs, [], [], 0.005)

        # 客户端发送的正常请求
        for r in rlist:
            if r == sock:
                # 有客户端来进行连接
                conn, addr = sock.accept()
                conn.setblocking(False)
                inputs.append(conn)
            else:
                # 客户端发来数据
                data = b""
                while True:
                    # 防止数据接收完毕报错，进行异常处理
                    try:
                        chunk = r.recv(1024)
                        data = data + chunk
                    except Exception as e:
                        chunk = None
                    if not chunk:
                        break
                    # 将请求信息封装到HttpRequest类中处理
                request = HttpRequest(data)
                func = None
                flag = False
                # 路由匹配，匹配请求的url,执行对应的视图函数
                for route in routers:
                    if re.match(route[0], request.url):
                        flag = True
                        func = route[1]
                        break
                    # 匹配成功
                if flag:
                    # 获取对应请求url视图函数执行结果
                    result = func(request)
                    # 判断返回的是否是future对象，如果是非正常请求，将conn添加到字典，后面单独处理
                    if isinstance(result, Future):
                        asyn_request_dic[r] = result
                    # 正常请求就正常返回，注意返回后需要从监视的列表中移除conn,并且断开连接，因为HTTP是短链接
                    else:
                        r.sendall(bytes(result, encoding='utf-8'))
                        inputs.remove(r)
                        r.close()
                    # 匹配没成功
                else:
                    r.sendall(b'404')
                    inputs.remove(r)
                    r.close()

            # 客户端发送非正常请求，比如在视图函数中阻塞了，判断非正常请求是否超时，如果超时就设置 future.result="请求超时"，
            # 此时future.result就有值了，直接返回
        for conn in list(asyn_request_dic.keys()):
            future = asyn_request_dic[conn]
            start_time = future.start_time
            time_out = future.time_out
            finall_time = time.time()
            if future.result:
                # 此处有sendall(),需要将字符串转为字节类型
                conn.sendall(bytes(future.result, encoding='utf-8'))
                conn.close()
                # 字典在循环时是不能进行修改、删除等操作的，所以转换为列表即可
                del asyn_request_dic[conn]
                inputs.remove(conn)

            if start_time + time_out <= finall_time:
                future.result = "请求超时"


if __name__ == '__main__':
    run()

