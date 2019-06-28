## UDP-Broadcasting-synchronized
Video/sound broadcasting with UDP socket and datagram synchronized

This project show how to send UDP datagrams throughout the network as long as your firewall or the distant firewall
does not block the traffic. 

Start the receiver first (option -a represent the machine sending the packets, -p the port to listen to) 
```
machine with IP 192.168.1.110
C:\>UDP_Receiver.exe -a 192.168.1.112 -p 59000

[+]INFO - Control socket broadcasting to 192.168.1.112 58997 
[+]INFO - Sound socket listening to 192.168.1.110 58999 
[+]INFO - Video socket listening to 192.168.1.110 59000 
```
On the other machine (same, specify the address of the listener, here 192.168.1.110)
```
machine with ip 192.168.1.112
C:\>UDP_Broadcast.exe -a 192.168.1.110 -p 59000
[+]INFO - Control socket listening to 192.168.1.112 58997 
[+]INFO - Video socket broadcasting to 192.168.1.110 59000 
[+]INFO - Sound socket broadcasting to 192.168.1.110 58999 

```

the following also works on the same machine (the program will find the correct ip to talk to):
```
C:\>UDP_Receiver.exe
```
```
C:\>UDP_Broadcast.exe
```
