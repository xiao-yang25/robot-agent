"""CI-only deterministic candidate peer using the pinned private skill transport."""
import socket
import sys
import time
from robot_harness._transport import Channel


def main():
    channel = Channel(socket.socket(fileno=int(sys.argv[1])), binary=True)
    channel.queue({'kind': 'ready'})
    try:
        while True:
            for request in channel.pump():
                if request['kind'] == 'close':
                    return
                start = request['observation']['sequence']
                channel.queue({'kind': 'prediction', 'identity': request['identity'],
                               'actions': [[float(start + i + 1)] * 14
                                           for i in range(request['count'])]})
            time.sleep(.002)
    except (EOFError, BrokenPipeError, ConnectionResetError):
        pass
    finally:
        channel.close()


if __name__ == '__main__':
    main()
