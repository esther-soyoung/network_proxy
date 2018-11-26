from socket import *
from urllib.parse import urlparse
import threading
import sys
import datetime
import select
import math


BUFSIZE = 16384
TIMEOUT = 5
CRLF = '\r\n'

# Dissect HTTP header into line(first line), header(second line to end), body
def parseHTTP(data):
    line = data.split(b'\r\n')[0].decode()
    header = dict()
    header_line = data.split(b'\r\n\r\n')[0].decode().split('\r\n')[1:]
    for h in header_line:
        hl = h.split(': ')
        field = hl[0]
        if len(hl) <= 1:
            value = ''
        else:
            value = hl[1]
        header[field] = value
    #body = data.split(b'\r\n\r\n')[1]
    n = data.find( b'\r\n\r\n' )
    body = data [n+4:]
    return HTTPPacket(line, header, body)

# Receive HTTP packet with socket
# It support seperated packet receive
def recvData(conn, cli_svr):
    try:
        if cli_svr == "server":
            # Set time out for error or persistent connection end
            conn.settimeout(TIMEOUT)
            data = conn.recv(BUFSIZE)
        else:
            conn.settimeout(None)
            data = conn.recv(BUFSIZE)
            if 0 == len(data):
                return HTTPPacket("", "", "")
    except OSError as e2:
        return HTTPPacket("", "", "")
    except socket.error as e0:
        return HTTPPacket("", "", "")
    except socket.timeout as e1:
        return HTTPPacket("", "", "")

    while b'\r\n\r\n' not in data:  # receive up to Header
        data += conn.recv(BUFSIZE)
    packet = parseHTTP(data)  # packet with empty Body
    body = packet.body  # can be 0, partial, or whole
    #print('received packet')
    
    # Receive Body
    # Chunked-Encoding
    if packet.isChunked():
        #print('Chunked packet')
        readed = 0
        while True:
            while b'\r\n' not in body[readed:len(body)]:  # receive chunk size info
                d = conn.recv(BUFSIZE)
                body += d
            #print('received chunk size info')
            size_str = body[readed:len(body)].split(b'\r\n')[0]  # chunk size info
            size = int(size_str, 16)  # size of chunk
            readed += len(size_str) + 2  # chunk size info and CRLF
            while len(body) - readed < size + 2:  # receive a chunk
                d = conn.recv(BUFSIZE)
                body += d
            #print('received chunk')
            readed += size + 2  # mark up to current chunk as readed
            if size == 0: break
        #print('received all the chunks, to the end of the Body')
    
    # Content-Length
    elif packet.getHeader('Content-Length'):
        #print('Not a chunked packet')
        received = 0
        expected = packet.getHeader('Content-Length')
        if expected == None:
            expected = '0'
        expected = int(expected)
        received += len(body)
        #print('expected: %d, received: %d' %(expected, received))
        
        while received < expected:  # receive total Body
            #print('more left to receive')
            d = conn.recv(BUFSIZE)
            #print('additional reception')
            received += len(d)
            body += d
            #print('content length: received %d, now %d received' %(len(d), received))
        #print('Received total Body as a whole, size of %d' %len(body))

    conn.settimeout(None)
    packet.body = body
    return packet


# HTTP packet class
# Manage packet data and provide related functions
class HTTPPacket:
    # Constructer
    def __init__(self, line, header, body):
        self.line = line  # Packet first line(String)
        self.header = header  # Headers(Dict.{Field:Value})
        self.body = body  # Body(Bytes)
    
    # Make encoded packet data
    def pack(self):
        ret = self.line + CRLF
        for field in self.header:
            ret += field + ': ' + str(self.header[field]) + CRLF
        ret += CRLF
        ret = ret.encode()
        ret += self.body
        return ret
    
    # Get HTTP header value
    # If not exist, return empty string
    def getHeader(self, field):
        if field not in self.header:
            return ''
        return self.header[field]
    
    # Set HTTP header value
    # If not exist, add new field
    # If value is empty string, remove field
    def setHeader(self, field, value):
        if value == '':
            del self.header[field]
        else:
            self.header[field] = value 

    def delHeader(self, field):
        if field in self.header:
            del self.header[field]
    
    # Get URL from request packet line
    def getURL(self):
        return self.line.split(' ')[1]
    
    def isChunked(self):
        return 'chunked' in self.getHeader('Transfer-Encoding')


class ProxyThread_mt_pc(threading.Thread):
    def __init__(self, conn_sock, cli_addr, pc):
        super().__init__()
        self.conn = conn_sock  # Connection socket
        self.addr = cli_addr  # Client address
        self.pc = pc # Persistent Connection flag

    # Thread Routine
    # Override
    def run(self):
        global conn_no

        if self.conn.fileno() < 0:
            return
        while True:
            try:
                try:
                    sr,sw,se = select.select( [self.conn], [], [] )
                except ValueError:
                    print('ProxyThread_mt_pc() ValueError in select()')
                    return
                except OSError:
                    print('ProxyThread_mt_pc() OSError in select()')
                    return

                req = recvData(self.conn, "client" )
                if len(req.line) == 0 or len(req.header) == 0:
                    self.conn.close()
                    return 

                # increase connection number for each reqeust
                conn_no += 1
                this_conn_no = conn_no
                url = urlparse(req.getURL())
            
                print('[%d]' %this_conn_no, end = ' ')
                print(datetime.datetime.now().strftime('%d/%b/%Y %H:%M:%S'))
                print('[%d] > Connection from %s' %(this_conn_no, self.addr[0]+':'+str(self.addr[1])))
                print('[%d] > %s' %(this_conn_no, req.line))
            
                # What to do if it is not persistent connection?
                req.setHeader('Connection', 'keep-alive')

                # Remove proxy infomation
                req.setHeader('Proxy-Connection', '')
    
                # Get hostname
                hostname = req.getHeader('Host')
                if len(hostname) == 0:
                    hostname = url.hostname
                if hostname == None:
                    pass

                # Connect to Server
                sock2 = socket(AF_INET, SOCK_STREAM)  # Client side socket to connect with server
                sock2.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

                try:
                    sock2.connect((hostname, 80))  # Connect with server                
                except gaierror as gai:
                    print( "Invalid server name: %s" % hostname ) 
                    self.conn.close()
                    return
            
                #print('connected to server: %s' %hostname)
                # Send all the client's requests to the server
                sock2.sendall(req.pack())
                #print('sent request packet') 
                # receive data from the server
                res = recvData(sock2, "server")
                #print('received response data')
                #res = parseHTTP(data)
                #print('created response packet')
                res.setHeader('Connection', 'keep-alive')
    
                # Set connection header
                res.setHeader('Connection', 'keep-alive')

                # Print out
                info = res.getHeader('Content-Type') + ' ' + str(res.getHeader('Content-Length'))+'bytes'
                print('[%d] < %s' %(this_conn_no, res.line))
                print('[%d] < %s' %(this_conn_no, info))
                print()

                # Send response to client
                self.conn.send(res.pack()) 

                sock2.close()
                
            except Exception as e:
                print('exception: ', e.message)
                sys.exit()

            except KeyboardInterrupt:
                # print('KeyboardInterrupt')
                self.conn.close()
                sock2.close()


# Proxy handler thread class
class ProxyThread(threading.Thread):
    def __init__(self, conn_sock, cli_addr, pc):
        super().__init__()
        self.conn = conn_sock  # Connection socket
        self.addr = cli_addr  # Client address
        self.pc = pc # Persistent Connection flag

    # Thread Routine
    # Override
    def run(self):
        global conn_no
        global connections
        global util

        if self.conn.fileno() < 0:
            return
        try:
            req = recvData(self.conn, "client")
            if len(req.line) == 0 or len(req.header) == 0:
                self.conn.close()
                if self.conn in connections:
                    connections.remove(self.conn)
                    del util[self.conn]
                return 

            #req = parseHTTP(data)  # Request packet from client
            # increase connection number for each reqeust
            conn_no += 1
            this_conn_no = conn_no
            url = urlparse(req.getURL())
            
            print('[%d]' %this_conn_no, end = ' ')
            print(datetime.datetime.now().strftime('%d/%b/%Y %H:%M:%S'))
            print('[%d] > Connection from %s' %(this_conn_no, self.addr[0]+':'+str(self.addr[1])))
            print('[%d] > %s' %(this_conn_no, req.line))
            
            # What to do if it is not persistent connection?
            if self.pc:
                req.setHeader('Connection', 'keep-alive')
            else:
                req.setHeader('Connection', 'close')

            # Remove proxy infomation
            req.setHeader('Proxy-Connection', '')
    
            # Get hostname
            hostname = req.getHeader('Host')
            if len(hostname) == 0:
                hostname = url.hostname
            if hostname == None:
                pass
            #print('debug: host name=[%s]' % hostname  )
            # Connect to Server
            sock2 = socket(AF_INET, SOCK_STREAM)  # Client side socket to connect with server
            sock2.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

            try:
                sock2.connect((hostname, 80))  # Connect with server                
            except gaierror as gai:
                print( "Invalid server name: %s" % hostname ) 
                self.conn.close()
                if self.conn in connections:
                    connections.remove(self.conn)
                    del util[self.conn]
                return
            
            #print('connected to server: %s' %hostname)
            # Send all the client's requests to the server
            sock2.sendall(req.pack())
            #print('sent request packet') 
            # receive data from the server
            res = recvData(sock2, "server")
            #print('received response data')
            #res = parseHTTP(data)
            #print('created response packet')
            if self.pc:
                res.setHeader('Connection', 'keep-alive')
            else:
                res.setHeader('Connection', 'close')
    
            # Set connection header
            if self.pc:
                res.setHeader('Connection', 'keep-alive')
            else:
                res.setHeader('Connection', 'close')

            # Print out
            info = res.getHeader('Content-Type') + ' ' + str(res.getHeader('Content-Length'))+'bytes'
            print('[%d] < %s' %(this_conn_no, res.line))
            print('[%d] < %s' %(this_conn_no, info))
            print()

            # Send response to client
            self.conn.send(res.pack()) 
            #print('Sent response back to client')
            # If support pc, how to do socket and keep-alivei?
            if self.pc:
                sock2.close()
            else: 
                self.conn.close()
                sock2.close()

        except Exception as e:
            print('exception: ', e.message)
            sys.exit()

        except KeyboardInterrupt:
            # print('KeyboardInterrupt')
            self.conn.close()
            sock2.close()
            sys.exit()
    
def main():
    try:
        sock1 = socket(AF_INET, SOCK_STREAM)  # Server side welcome socket
        sock1.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        port = int(sys.argv[1])
        sock1.bind(('0.0.0.0', port))
        sock1.listen(20)
        print('Proxy Server started on port %d at' % port, end = ' ')
        print(datetime.datetime.now().strftime('%d/%b/%Y %H:%M:%S') + '.')

        mt = False
        pc = False
        if '-mt' in sys.argv:
            mt = True
            print('* Multithreading - [ON]')
        else:
            print('* Multithreading - [OFF]')
        if '-pc' in sys.argv:
            pc = True
            print('* Persistent Connection - [ON]')
        else:
            print('* Persistent Connection - [OFF]')
        print() 
        
        # conn No.
        global conn_no
        conn_no = 0
       
        if mt: # Multithreading
            threads = []
            while True:
                #Connect with Client
                conn_sock, cli_addr = sock1.accept()  # Server side connection socket
                #Start Handling
                if pc:
                    pt = ProxyThread_mt_pc(conn_sock, cli_addr, pc)
                else:
                    pt = ProxyThread(conn_sock, cli_addr, pc)
                pt.start()
                threads.append(pt)

        else: # Singlethreading
            global connections
            global util
            connections = [sock1]
            util = dict()
            while connections:
                for s in connections:
                    if s.fileno() < 0:
                        connections.remove(s)
                        del util[s]
                try:       
                    sr, sw, se = select.select(connections, [], [])
                except ValueError:
                    print( 'Value Error in select()' )
                except OSError as eos:
                    print( 'OS Error' )

                for s in sr:
                    if s == sock1:
                        conn_sock, cli_addr = sock1.accept()
                        if 0 <= conn_sock.fileno():
                            connections.append(conn_sock)
                            util[conn_sock] = cli_addr
                    elif 0 <= s.fileno():
                        pt = ProxyThread(s, util[s], pc)
                        pt.start() 
                        if not pc and s in connections:
                            connections.remove(s)
                            del util[s]
                    elif s in connections:
                        connections.remove(s)
                        del util[s]
 
    except KeyboardInterrupt:
        print('KeyboardInterrupt')
        sock1.close()
        sys.exit()

    sock1.close()

if __name__ == '__main__':
    main()

