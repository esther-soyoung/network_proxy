import socket, sys, select

welcome_sock = socket.socket()
host = sys.argv[1]
port = int(sys.argv[2])

welcome_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
welcome_sock.bind((host, port))
print('Chat Server started on port %s.' %port)

num_cli = 0
welcome_sock.listen()
conn_list = [welcome_sock]

# when there exist connection requests
while conn_list:
  try:
    sr, sw, se = select.select(conn_list, [], [])
    for s in sr:
      # create new connection
      if s == welcome_sock:
        conn_sock, cli_addr = welcome_sock.accept()
        cli_addr_format = cli_addr[0] + ':' + str(cli_addr[1])
        num_cli = num_cli +  1
        conn_list.append(conn_sock)

        if num_cli >= 2:
          conn_sock.send('> Connected to the chat server (%d users online)'.encode() %num_cli)
        else:
          conn_sock.send('> Connected to the chat server (%d user online)'.encode() %num_cli)

        if num_cli >= 2:
          msg = '> New user %s entered. (%d users online)' %(cli_addr_format, num_cli)
        else:
          msg = '> New user %s entered. (%d user online)' %(cli_addr_format, num_cli)
        print(msg)

        # send to other connected users
        for c in conn_list:
          if c != conn_sock and c != welcome_sock:
            c.send(msg.encode())

      # existing connection
      else:
        data = s.recv(1024).decode()
        s_addr = s.getpeername()[0]+':'+ str(s.getpeername()[1])
        # valid data received
        if data:
          msg = '[%s] '%s_addr + data
          print(msg)
          # send to other connected users
          for c in conn_list:
            if c != welcome_sock and c != s:
              c.send(msg.encode())

        # disconnect if blank received or keyboard interruption by client
        else:
          conn_list.remove(s)
          num_cli = num_cli - 1
          s.close()

          if num_cli >= 2:
            msg = '< The user %s left (%d users online)' %(s_addr, num_cli)
          else: 
            msg = '< The user %s left (%d user online)' %(s_addr, num_cli)
          print(msg)
          # send to other connected users
          for c in conn_list:
            if c != welcome_sock and c != s:
              c.send(msg.encode())

  # terminate the server with keyboard interruption
  except KeyboardInterrupt:
    print('KeyboardInterrupt')
    for c in conn_list:
      c.close()
    welcome_sock.close()
    sys.exit()

  except InterruptedError as e:
    print('InterruptedError: ', e.message)
    welcome_sock.close()
    sys.exit()

  except socket.error as e:
    print('Socket error: blank received. ', e.message)
