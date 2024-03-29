# encoding: utf-8
"""
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software,and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 """


import threading
import pygame
import math
import socket
import argparse
import _pickle as cpickle
import hashlib
import lz4.frame
import time
import ctypes
import copyreg

__author__ = "Yoann Berenguer"
__copyright__ = "Copyright 2007, UDP Project"
__credits__ = ["Yoann Berenguer"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Yoann Berenguer"
__email__ = "yoyoberenguer@hotmail.com"
__status__ = "Video broadcast through UDP socket"

"""
This project demonstrate how to transfer video frames and sound object through UDP socket.  
The transfer is implemented on the loopback internet protocol (localhost).
A subclass MasterSync is synchronising data between two threads : the receiver and the generator (sender). 

TODO 
In the next version, I will use the same code to synchronize the receiver and generator using threads.Event 
through a designated socket from a local machine to a remote PC.
Pickling a threading.Event can be pickle using the methods describe in the following demonstration (refer 
to the link below)
http://code.activestate.com/recipes/473863-a-threadingevent-you-can-pickle/

import copyreg

    def unserialize_event(isset):
        e = threading.Event()
        if isset:
            e.set()
        return e
    
    def serialize_event(e):
        return unserialize_event, (e.isSet(),)
        
    copyreg.pickle(threading.Event, serialize_event)


"""


def unserialize_event(isset):
    e = threading.Event()
    if isset:
        e.set()
    return e


def serialize_event(e):
    return unserialize_event, (e.isSet(),)


copyreg.pickle(threading.Event, serialize_event)


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


class GL:
    """
    Class holding all the global variables
    """
    DISTANT = None                              # distant host
    LOCAL = None                                # local host
    PORT = 59000                                # default PORT
    SCREEN = (300, 300)                         # screen sizes width and height
    BUFFER = 1024                               # Video data chunk byte size
    SIZE = int((SCREEN[0]) * (SCREEN[1]) * 3)   # Frame size
    STOP = threading.Event()                    # Termination signal
    FRAME = -1                                  # Frame counter
    condition = threading.Condition()           # Synchronisation condition for video receiver and video generator
    thread4 = threading.Condition()             # Generator ready event condition
    TIMER = 0                                   # Master Sync timestamp
    inner = threading.Event()                   # Inner loop event, signal between threads
    gen_stop = threading.Event()                # Generator stop event


class ControlReceiver(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        print('\n[+]INFO - Control socket listening to %s %s ' % (GL.LOCAL, GL.PORT - 3))

    def run(self):

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((GL.LOCAL, GL.PORT - 3))
        except socket.error as error:
            print('\n[-]Error : %s ' % error)

        while not GL.STOP.isSet():

            try:
                data_, addr = sock.recvfrom(1024)
                data = cpickle.loads(data_)
                if data.isSet():
                    GL.inner.set()
                else:
                    GL.inner.clear()
            except Exception as e:
                print('\n[-]Error : %s ' % e)
        sock.close()


# Function generating wave effects (both directions x, y) on static surface
def wave_xy(texture_, rad1_, amplitude_) -> pygame.Surface:
    w, h = texture_.get_size()
    xblocks = range(0, w, amplitude_)
    yblocks = range(0, h, amplitude_)
    waves = pygame.Surface((w, h), pygame.SRCALPHA)
    waves.fill((0, 0, 0, 0))
    for x in xblocks:
        xpos = (x + (math.sin(rad1_ + x * 1 / (amplitude_ ** 2)) * amplitude_)) + amplitude_
        for y in yblocks:
            ypos = (y + (math.sin(rad1_ + y * 1 / (amplitude_ ** 2)) * amplitude_)) + amplitude_
            waves.blit(texture_, (0 + x, 0 + y), (xpos, ypos, amplitude_, amplitude_))
    return waves.convert()


def sound_socket_emitter(host_, port_, data_) -> None:
    """
    Open a TCP socket and send a pygame sound object (byte string format) compress wit lz4 algorithm
    default 127.0.0.1 PORT 58999
    :param host_:  host address (string)
    :param port_:  PORT value (integer)
    :param data_:  byte string copy of the Sound samples.
    :return: None
    """
    assert isinstance(host_, str), \
        'Expecting string for argument host_, got %s instead.' % type(host_)
    assert isinstance(port_, int), \
        'Expecting integer for argument port_, got %s instead.' % type(port_)
    assert 0 < port_ < 65535, \
        'Incorrect value assign to port_, 0 < port_ < 65535, got %s ' % port_
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host_, port_))
            compress_data = lz4.frame.compress(data_, compression_level=lz4.frame.COMPRESSIONLEVEL_MINHC)
            sock.send(compress_data)
    except socket.error as error:
        print('\n[-] Error - Sound socket emitter: %s ' % error)
    finally:
        sock.close()
        

class MasterSync(threading.Thread):
    """
    MasterSync control and provide a real time synchronisation between the receiving thread and the
    video frame generator.
    The master sync duty is to provide a regular timing (based on the given FPS timing)
    and control signals between threads.
    The thread will hang until it has received the confirmation from both threads (receiver and generator) that
    they are ready to process the next data transfer (this is done by thread3.notify() and thread4.notify())
    After confirmations, the thread will wait during a definite time given by self.dt e.g (self.dt = 16.6ms for
    60 fps or 33.3ms @ 30 fps).
    After the elapsed time(self.dt), the thread will send a signal to both receiver and generator
    in order to start processing the next video frame.

    The real fps value will be given by the threads response time, if the threads cannot complete the transfer
    in the allowed time, the Master sync will wait both threads to be ready and thus the fps time will be
    capped to the global processing time.

    """

    def __init__(self):
        threading.Thread.__init__(self)
        # Desire FPS.Real value will be achieve with
        # the synchronisation between receiver and video frames generator
        self.fps = 100
        self.dt = 1 / self.fps  # time constant (delay between frames to achieve the desire FPS)

    def run(self):
        while not GL.STOP.isSet():
            with GL.thread4:
                GL.thread4.wait()           # wait until video frame generator is ready
                GL.FRAME += 1
                time.sleep(self.dt)
                GL.TIMER = time.time()
                if VERBOSE:
                    print('\n[+]INFO - MasterSync timer : %f frame %s ' % (GL.TIMER, GL.FRAME))
                # Send notification to receiver and video frame
                # generator to start UDP packets transfer
                with GL.condition:
                    GL.condition.notify()
        print('[+]INFO - MasterSync thread is not terminated.')


def mytimer():

    kernel32 = ctypes.windll.kernel32
    # This sets the priority of the process to realtime--the same priority as the mouse pointer.
    kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 31)
    # This creates a timer. This only needs to be done once.
    timer = kernel32.CreateWaitableTimerA(ctypes.c_void_p(), True, ctypes.c_void_p())
    # The kernel measures in 100 nanosecond intervals, so we must multiply 1 by 10000
    delay = ctypes.c_longlong(1 * 10000)
    kernel32.SetWaitableTimer(timer, ctypes.byref(delay), 0, ctypes.c_void_p(), ctypes.c_void_p(), False)
    kernel32.WaitForSingleObject(timer, 0xffffffff)


def video_output_generator(host_, port_):

    swoosh = pygame.mixer.Sound("Assets\\swoosh.ogg")
    impact = pygame.mixer.Sound("Assets\\Impact.ogg")
    gunshot = pygame.mixer.Sound("Assets\\GunShot.ogg")
    gunshot.set_volume(0.2)

    screen_impact1 = pygame.image.load('Assets\\Broken glass.png').convert_alpha()
    screen_impact1 = pygame.transform.scale(screen_impact1, (128, 128))

    screen_impact = pygame.image.load('Assets\\broken_screen_overlay.png').convert_alpha()
    screen_impact = pygame.transform.scale(screen_impact, (128, 128))

    surface_org = pygame.image.load("Assets\\Cobra1.png").convert()
    surface_org = pygame.transform.smoothscale(surface_org, SCREEN.get_size()).convert()
    surface_org_x2 = pygame.transform.smoothscale(surface_org, (width_ * 2, height_ * 2)).convert()

    stop_game = False
    angle = 0
    scale = 1
    min_s = 400
    angle_inc = 20
    stop = False
    angle1 = 0
    frame = 0
    # Start the Master thread controlling the synchronisation between
    # thread receiver and video frame generator.
    # This is a subclassing thread
    MasterSync().start()

    # threading conditions initialisation (allow Master Sync to start cycling)
    # GL.thread4 (emitter/generator) send ready signal
    with GL.thread4:
        GL.thread4.notify()

    try:
        ss = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # ss.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        print('\n[+]INFO - Video socket broadcasting to %s %s ' % (host_, port_))
        print('\n[+]INFO - Sound socket broadcasting to %s %s ' % (host_, port_ - 1))
    except socket.error as e:
        print('\n[-]ERROR - Generator socket not connected.. : %s ' % e)
        stop_game = True
        GL.STOP.set()
        ss = None


    while not stop_game:

        try:
            with GL.condition:
                GL.condition.wait()
            if VERBOSE:
                print('\n[+]INFO - Generator starting condition delay %s msecs timestamp %s frame %s' %
                      (round(time.time() - GL.TIMER, 2) * 1000, time.time(), frame))

            pygame.event.pump()
            keys = pygame.key.get_pressed()

            if keys[pygame.K_ESCAPE]:
                GL.STOP.set()
                stop_game = True
                stop = True
                with GL.thread4:
                    GL.thread4.notify()
                sound_socket_emitter(host_, port_ - 1, bytes('quit', 'UTF-8'))
                if ss:
                    ss.sendto(cpickle.dumps(bytes('quit', 'UTF-8')), (host_, port_))
                break

            if not stop:
                surface = pygame.transform.rotozoom(surface_org_x2.copy(), angle, scale)
            else:
                surface = wave_xy(surface_org.copy(), angle1, 10)

            rect = surface.get_rect(center=SCREENRECT.center)
            SCREEN.blit(surface, (SCREENRECT.centerx - int(rect.w / 2),
                                  SCREENRECT.centery - int(rect.h / 2)))
            if not stop:
                if surface.get_width() > min_s:
                    angle += angle_inc
                    if angle % 80 == 0:
                        sound_socket_emitter(host_, port_ - 1, swoosh.get_raw())
                        swoosh.play()
                else:
                    if angle != 0:
                        angle += angle_inc
                    else:
                        sound_socket_emitter(host_, port_ - 1, impact.get_raw())
                        impact.play()
                        stop = True
            else:
                if not stop_game:
                    if frame == 80:
                        sound_socket_emitter(host_, port_ - 1, gunshot.get_raw())
                        gunshot.play()
                        v1 = pygame.math.Vector2(300, 400)
                        surface_org.blit(screen_impact1, (v1.x * width_ / 800, v1.y * height_ / 1024))

                    elif frame == 120:
                        sound_socket_emitter(host_, port_ - 1, gunshot.get_raw())
                        gunshot.play()
                        v1 = pygame.math.Vector2(390, 250)
                        surface_org.blit(screen_impact, (v1.x * width_ / 800, v1.y * height_ / 1024))
                    elif frame == 140:
                        v1 = pygame.math.Vector2(300, 170)
                        sound_socket_emitter(host_, port_ - 1, gunshot.get_raw())
                        gunshot.play()
                        surface_org.blit(screen_impact, (v1.x * width_ / 800, v1.y * height_ / 1024))

            angle %= 360
            angle1 += 0.1
            scale -= 0.05 if surface.get_width() > min_s else 0

            SCREEN.blit(surface, (0, 0))
            pygame.display.flip()

            # Transform image into bytes string data
            data = pygame.image.tostring(
                pygame.transform.scale(SCREEN, (width_, height_)), 'RGB', False)

            # ***********************************************************************
            # Video frame generator
            # send packets via UDP socket
            size = len(data)
            buffer = GL.BUFFER
            pos = 0
            packet = 0

            if not GL.STOP.isSet():
                while size > 0 and not GL.gen_stop.isSet():

                    if size >= buffer:
                        # create a packet
                        block = data[pos * buffer: pos * buffer + buffer]
                        lblock = len(block)

                        # Determine checksum
                        checksum = hashlib.md5()
                        checksum.update(bytes(block))
                        chk = checksum.hexdigest()

                        # Serialized packet before sending it through the socket
                        d = cpickle.dumps((packet, lblock, block, chk))
                        size -= lblock
                        ss.sendto(d, (host_, port_))
                    else:
                        # send remaining bytes
                        block = data[pos * buffer: pos * buffer + size]
                        checksum = hashlib.md5()
                        checksum.update(bytes(block))
                        chk = checksum.hexdigest()
                        d = cpickle.dumps((packet, len(block), block, chk))
                        ss.sendto(d, (host_, port_))
                        size = 0
                        break
                    # Small stop to give to the receiver the time to process the packet.
                    # This can be removed, but it is a safe method for removing extra overhead
                    # on the receiver
                    mytimer()

                    pos += 1
                    packet += 1

                    # ! very important, Generator is now waiting a signal from
                    # the receiver before processing the next packet.
                    # The generator is sending a large amount of data throughout the socket
                    # Without this synchronisation, the receiver will received only a fraction of the
                    # data frames.
                    GL.inner.wait()
                    GL.inner.clear()
            # ***********************************************************************
            pygame.event.clear()

            clock.tick(60)

        except Exception as e:
            print('\n [-] Error - video frame generator %s ' % e)
            stop_game = True

        finally:
            GL.gen_stop.clear()
            if VERBOSE:
                print('\n[+]SERVER FINISHED delay %s msecs timestamp %s frame %s'
                      % (round(time.time() - GL.TIMER, 2) * 1000, time.time(), frame))
            frame += 1
            with GL.thread4:
                GL.thread4.notify()

    ss.shutdown(socket.SHUT_WR)
    ss.close()
    print('\n[+]INFO - Video output generator is now terminated.')


if __name__ == '__main__':

    width_, height_ = GL.SCREEN
    SCREENRECT = pygame.Rect(0, 0, width_, height_)

    # socket.setdefaulttimeout(0.01)

    pygame.display.init()
    SCREEN = pygame.display.set_mode(SCREENRECT.size, pygame.RESIZABLE, 32)
    SCREEN.set_alpha(None)
    pygame.display.set_caption('UDP Generator')
    pygame.mixer.pre_init(44100, 16, 2, 4095)
    pygame.init()
    image_ = pygame.Surface((300, 300))

    ap = argparse.ArgumentParser()
    ap.add_argument("-l", "--local", required=True, default=GL.LOCAL, help="local ip e.g '192.168.1.108'")
    ap.add_argument("-d", "--distant", required=True, default=GL.DISTANT, help="distant ip e.g '192.168.1.100'")
    ap.add_argument("-p", "--port", required=False, default=int(GL.PORT), help="port to use (choose a port > 1027")
    ap.add_argument("-v", "--verbose", required=False, default=False, help="Verbose True | False")

    args = vars(ap.parse_args())
    LOCAL = args['local']
    DISTANT = args['distant']
    VERBOSE = args['verbose']
    PORT = args['port']

    if isinstance(DISTANT, str):
        GL.DISTANT = DISTANT
    else:
        raise AssertionError('-d, --distant. Expecting string, got %s ' % type(DISTANT))

    if isinstance(LOCAL, str):
        GL.LOCAL = LOCAL
    else:
        raise AssertionError('-l, --local. Expecting string got %s ' % type(LOCAL))

    if isinstance(VERBOSE, bool):
        GL.VERBOSE = VERBOSE
    else:
        raise AssertionError('-v, --verbose. Expecting boolean True | False, got %s ' % type(VERBOSE))

    try:
        GL.PORT = int(PORT)
    except ValueError:
        raise AssertionError('-p, --port. Expecting integer got %s ' % type(PORT))

    assert 1027 < GL.PORT < 65535, \
        'Incorrect value for port, 1027 < port < 65535, got %s ' % GL.PORT

    STOP_GAME = False
    clock = pygame.time.Clock()

    # Start the synchronisation
    # listen on the distant IP
    ControlReceiver().start()

    # Start video broadcasting on distant IP
    video_output_generator(GL.DISTANT, GL.PORT)

