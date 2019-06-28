import socket
import threading
import time
import _pickle as cpickle


class GL:
    STOP = threading.Event()
    

class ControlReceiver(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(('192.168.1.112', 59000))
        except socket.error as error:
            print('\n[-]Error : %s ' % error)

        while not GL.STOP.isSet():

            try:
                data_, addr = sock.recvfrom(1024)
                data = cpickle.loads(data_)
                print(data)
            except Exception as e:
                print('\n[-]Error : %s ' % e)
        sock.close()


if __name__ == '__main__':

    import socket

    ControlReceiver().start()
    while 1:
        time.sleep(0.0001)

        
