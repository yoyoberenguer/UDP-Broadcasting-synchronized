import argparse
import threading
import socket
import time
import _pickle as cpickle
import hashlib
import pygame
import copyreg
import ctypes
import lz4.frame


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

class GLL:
   SCREEN = (300, 300)
   LOCAL = str(get_ip_address())
   DISTANT = '192.168.1.106'
   port = 59000
   SIZE = int((SCREEN[0]) * (SCREEN[1]) * 3)
   STOP = threading.Event()
   condition = threading.Condition()
   thread3 = threading.Condition()
   inner = threading.Event()
   event_trigger = threading.Event()


def unserialize_event(isset):
    e = threading.Event()
    if isset:
        e.set()
    return e


def serialize_event(e):
    return unserialize_event, (e.isSet(),)


copyreg.pickle(threading.Event, serialize_event)


def my_timer():
    kernel32 = ctypes.windll.kernel32
    # This sets the priority of the process to realtime--the same priority as the mouse pointer.
    kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 31)
    # This creates a timer. This only needs to be done once.
    timer = kernel32.CreateWaitableTimerA(ctypes.c_void_p(), True, ctypes.c_void_p())
    # The kernel measures in 100 nanosecond intervals, so we must multiply 1 by 10000
    delay = ctypes.c_longlong(1 * 10000)
    kernel32.SetWaitableTimer(timer, ctypes.byref(delay), 0, ctypes.c_void_p(), ctypes.c_void_p(), False)
    kernel32.WaitForSingleObject(timer, 0xffffffff)


class Control(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        try:
            self.ss = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # self.ss.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            print('\n[+]INFO - Control socket broadcasting to %s %s ' % (GLL.DISTANT, GLL.port - 3))
        except socket.error as e:
            print('\n[-]ERROR - Control socket not connected.. : %s ' % e)
            GLL.STOP.set()

    def run(self):

        while not GLL.STOP.isSet():
            try:
                while not GLL.event_trigger.isSet():
                    my_timer()
                else:
                    self.ss.sendto(cpickle.dumps(GLL.inner), (GLL.DISTANT, GLL.port - 3))

            except Exception as e:
                print('\n[-] Error - Control %s ' % e)

        print('\n[+]INFO - Control : thread is now terminated.')
        self.ss.close()


class VideoInputReceiver(threading.Thread):
    """
    Class receiving all the data frames (video UDP packets send by the video generator).
    Default address is 127.0.0.1 and port 59000
    The data flows is synchronize with threading condition and events that allows a perfect synchronization
    between receiver and transmitter (depend on system resources).
    Threading condition is controlling the start of each transfer sessions and events between threads are signaling
    to the packet generator that the receiver is ready for the next packet.

    The VideoInputReceiver class is re-ordering the UDP packets, in fact it is receiving them sequentially.
    A packet out of sync will be disregard and lost.
    This version is not designed for inventorying and processing (re-transfer) lost data frames.
    Packet received are checked with a checksum using hashlib library and synchronization is checked
    for each packet received.

    Data sent by the frame generator are bytes string like data composed with the function
    pygame.image.tostring and then pickled using the module _pickle (fast C version of pickle for python).
    All the data frames are fragmented and composed into packets with the following header

    packet = _pickle(frame number, size, data chunk, checksum)

    frame : number (integer) representing the actual frame number being sequenced
    size  : data size (integer), 1024 bytes for most packets and <1024 for the last packet.
    data chunk :  Chunk of 1024 bytes string
    checksum : md5 hash value to check data integrity

    Every packets are serialized object sent to the receiver.
    The receiver has to follow the same reverse processes in order to de-serialized packets and build
    the frame to be display to the video output.

    The frames will be disregard for the following cases:
    - out of sync data
    - Received frame size is different from the source generator
    - Checksum error

    Data flow :

        * loop until STOP signal
            * wait for condition
                * loop until all packet received
                    * wait for packet
                        process packets
                        integrity checks
            build and display frame
            signal ready

    Nota: The socket is blocking the thread until the generator is sending packets (no timeout)
          GL is the class holding all the global variable.
    """

    def __init__(self):
        threading.Thread.__init__(self)

    def sort_(self, tuple_):
        return sorted(tuple_, key=lambda x: int(x[0]), reverse=False)

    def run(self):

        width, height = GLL.SCREEN
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error as error:
            print('\n[-]Error - Receiver : %s ' % error)
            GLL.STOP.set()

        try:
            sock.bind((GLL.LOCAL, GLL.port))
            print('\n[+]INFO - Video socket listening to %s %s ' % (GLL.LOCAL, GLL.port))
        except socket.error as error:
            print('\n[-]Error - Receiver : %s ' % error)
            GLL.STOP.set()

        frame = 0

        while not GLL.STOP.isSet():
            capture = []

            try:
                buffer_ = b''
                size = GLL.SIZE
                packets = 0

                while size > 0:

                    data_, addr = sock.recvfrom(2048)
                    data = cpickle.loads(data_)
                    capture.append(data)

                    # if not data_:
                    #    break

                    # Receiver being told to abort reception
                    if data == b'quit':
                        GLL.STOP.set()
                        # Tell the generator to stop sending packets
                        GLL.inner.set()
                        GLL.event_trigger.set()
                        break

                    # if packets number is not equal to the packet number then
                    # the transfer is not synchronized, or a packet has been dropped
                    if packets != data[0]:
                        if verbose:
                            print('\n[-]ERROR - Receiver : packet not synchronised, packet %s %s.'
                                  % (packets, data[0]))
                        GLL.inner.set()
                        GLL.event_trigger.set()
                        break

                    checksum = hashlib.md5()
                    checksum.update(bytes(data[2]))
                    chk = checksum.hexdigest()

                    if chk != data[3]:
                        if verbose:
                            print('\n[-]ERROR - Receiver : checksum error. ')
                        GLL.inner.set()
                        GLL.event_trigger.set()
                        break

                    size -= data[1]
                    packets += 1

                    # Receiver is now ready for the next packet.
                    GLL.inner.set()
                    GLL.event_trigger.set()

                if not GLL.STOP.isSet():
                    # sorting out packets using the frame number index
                    # in the eventuality that packets are received asynchronously
                    # sort_capture = self.sort_(capture)
                    sort_capture = capture

                    # build the image by adding every chunks of bytes string received to
                    # compose the video buffer.
                    for element in range(len(sort_capture)):
                        buffer_ += sort_capture[element][2]

                    if len(buffer_) == GLL.SIZE:
                        global image_
                        image_ = pygame.image.frombuffer(buffer_, (width, height), 'RGB')

                    else:
                        if verbose:
                            print('\n[-]ERROR - Receiver : Video buffer is corrupted.')

            except Exception as e:
                print('\n[-]ERROR - Receiver : %s ' % e)
            finally:
                frame += 1

        print('\n[+]INFO - Receiver : thread is now terminated.')


class SoundSocketReceiver(threading.Thread):

    """
    Class receiving a pygame sound object through a TCP socket.
    The sound object is fragmented and compressed with the lz4 library by the sound generator.
    Default address is 127.0.0.1 and port 58999

    Data flow :
        * loop until STOP signal
            * wait for packet
                if no data, close connection
                if packet size=0 decompress data and play the sound object to the mixer
                else build sound object by adding remaing chunks

    """

    def __init__(self,
                 host_,  # host address
                 port_,  # port value
                 ):

        threading.Thread.__init__(self)

        """
        Create a TCP socket server to received sound data frames
        :param host_: String corresponding to the server address
        :param port_: Integer used for the port.
                      Port to listen on (non-privileged ports are > 1023) and 0 < port_ < 65535
        """

        assert isinstance(host_, str), \
            'Expecting string for argument host_, got %s instead.' % type(host_)
        assert isinstance(port_, int), \
            'Expecting integer for argument port_, got %s instead.' % type(port_)
        assert 0 < port_ < 65535, \
            'Incorrect value assign to port_, 0 < port_ < 65535, got %s ' % port_

        # Create a TCP/IP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Bind the socket to the port
            self.sock.bind((host_, port_))
        except socket.error as error:
            print('\n[-] Error : %s ' % error)

        try:
            # Listen for incoming connections
            self.sock.listen(1)
            print('\n[+]INFO - Sound socket listening to %s %s ' % (host_, port_))
        except socket.error as error:
            print('\n[-] Error : %s ' % error)

    def run(self):

        frame = 0

        while not GLL.STOP.isSet():
            try:
                # Wait for a connection
                connection, client_address = self.sock.accept()
            except Exception as e:
                print('\n[-]ERROR - Sound receiver %s ' % e)
                GLL.STOP.set()
                connection, client_address = None, None
                break
            try:
                buffer = b''
                # Receive the data in small chunks
                while not GLL.STOP.isSet():
                    data = connection.recv(4096)
                    # build the sound by adding data chunks
                    if len(data) > 0:
                        buffer += data
                    else:
                        # Decompress the data frame
                        decompress_data = lz4.frame.decompress(buffer)
                        if decompress_data == b'quit':
                            GLL.STOP.set()
                            break
                        sound = pygame.mixer.Sound(decompress_data)
                        sound.play()
                        break
            except Exception as e:
                print('\n[-]ERROR - Sound receiver %s ' % e)
                GLL.STOP.set()
            finally:
                if connection is not None:
                    connection.close()
                frame += 1
        print('\n[+]INFO - Sound receiver thread is now terminated.')


if __name__ == '__main__':
    width_, height_ = (300, 300)
    SCREENRECT = pygame.Rect(0, 0, width_, height_)
    pygame.display.init()
    SCREEN = pygame.display.set_mode(SCREENRECT.size, pygame.RESIZABLE, 32)
    SCREEN.set_alpha(None)
    pygame.display.set_caption('UDP Receiver')
    pygame.mixer.pre_init(44100, 16, 2, 4095)
    pygame.init()
    image_ = pygame.Surface((300, 300))
    ap = argparse.ArgumentParser()
    ap.add_argument("-a", "--address", required=False, default=GLL.DISTANT, help="distant server")
    ap.add_argument("-p", "--port", required=False, default=GLL.port, help="Port to use")
    ap.add_argument("-v", "--verbose", required=False, default=False, help="verbose")

    args = vars(ap.parse_args())
    DISTANT = args['address']
    verbose = bool(args['verbose'])

    Control().start()

    STOP_GAME = False
    clock = pygame.time.Clock()
    VideoInputReceiver().start()
    SoundSocketReceiver(GLL.LOCAL, int(args['port']) - 1).start()

    while not GLL.STOP.isSet():
        keys = pygame.key.get_pressed()

        if keys[pygame.K_ESCAPE]:
            GLL.STOP.set()
            break

        pygame.event.pump()
        SCREEN.blit(image_, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()