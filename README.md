## UDP-Broadcasting-synchronized
Video/sound broadcasting with UDP socket and datagram synchronized

This project show how to send UDP datagrams throughout the network **as long as your firewall or the distant firewall
does not block the traffic. **

**Start the receiver first (e.g machine with IP 192.168.1.110)**
```
C:\>UDP_Receiver.exe -l 192.168.1.110 -d 192.168.1.112 -p 59000

[+]INFO - Control socket broadcasting to 192.168.1.112 58997 
[+]INFO - Sound socket listening to 192.168.1.110 58999 
[+]INFO - Video socket listening to 192.168.1.110 59000 
```
**On the other machine (e.g machine with ip 192.168.1.112)**
```
C:\>UDP_Broadcast.exe -l 192.168.1.112 -d 192.168.1.110 -p 59000

[+]INFO - Control socket listening to 192.168.1.112 58997 
[+]INFO - Video socket broadcasting to 192.168.1.110 59000 
[+]INFO - Sound socket broadcasting to 192.168.1.110 58999 

```
