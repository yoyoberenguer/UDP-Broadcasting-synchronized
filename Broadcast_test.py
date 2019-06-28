

import socket
import threading
import _pickle as cpickle
import time


class GLL:
    STOP = threading.Event()


class Control(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        try:
            self.ss = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # self.ss.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except socket.error as e:
            print('\n[-]ERROR - Control socket not connected.. : %s ' % e)
            GLL.STOP.set()

    def run(self):

        while not GLL.STOP.isSet():
            try:

                self.ss.sendto(cpickle.dumps('helo client'), ('192.168.1.112', 59000))

            except Exception as e:
                print('\n[-] Error - Control %s ' % e)

        print('\n[+]INFO - Control : thread is now terminated.')
        self.ss.close()


if __name__ == '__main__':
    Control().start()
    while 1:
        time.sleep(0.0001)