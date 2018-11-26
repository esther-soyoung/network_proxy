import socket, sys, select

cli_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv_host = sys.argv[1]
srv_port = int(sys.argv[2])

# connect to the server
cli_sock.connect((srv_host, srv_port))

while True:
  try:
    sr, sw, se = select.select([sys.stdin, cli_sock], [], [])
    for s in sr:
      # receive data from server
      if s == cli_sock:
        data = s.recv(1024).decode()
        if data:
          print(data)
        else:
          cli_sock.close()
          print('Server closed the connection.')
          sys.exit()

      # send user input to server
      else:
        cli_chat = input()
        # disconnect if input is empty string
        if cli_chat == '':
          cli_sock.close()
          print('You have been disconnected.')
          sys.exit()
        else:
          cli_sock.send(cli_chat.encode())
        print('[You] ' + cli_chat)

  except KeyboardInterrupt:
    print('KeyboardInterrupt')
    cli_sock.close()
    sys.exit()

  except InterruptedError as e:
    print('InterruptedError: ', e.message)
    cli_sock.close()
    sys.exit()

