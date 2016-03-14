#!/usr/bin/env python3
from argparse import ArgumentParser
from aiohttp import web
import aiohttp, asyncio, json, logging.handlers, os,random, re, \
    ssl, sys, time, uuid
import requests
import threading

FISHROOM_TOKEN_ID = ""
FISHROOM_TOKEN_KEY = ""
FISHROOM_MY_TAG = ""

FISHROOM_ADDR = "https://fishroom.tuna.moe/api/messages"
FISHROOM_POST_ADDR = "https://fishroom.tuna.moe/api/messages/{room}/"
BINDING = []

try:
    from config import (
        FISHROOM_TOKEN_ID, FISHROOM_TOKEN_KEY, FISHROOM_MY_TAG, BINDING
    )
except ImportError:
    pass

logger = logging.getLogger('wechatircd')
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.WARNING)


def debug(msg, *args):
    logger.debug(msg, *args)


def info(msg, *args):
    logger.info(msg, *args)


def warning(msg, *args):
    logger.warning(msg, *args)


def error(msg, *args):
    logger.error(msg, *args)


try:
    import pygments, pygments.lexers, pygments.formatters
    __use_pygments = True
    print("Using pygments")
except ImportError:
    print("Not using pygments")
    __use_pygments = False


class ExceptionHook(object):
    instance = None

    def __call__(self, *args, **kwargs):
        if self.instance is None:
            from IPython.core import ultratb
            self.instance = ultratb.VerboseTB(call_pdb=True)
        return self.instance(*args, **kwargs)


def pprint_json(data):
    if not isinstance(data, str):
        fjson = json.dumps(data, sort_keys=True, indent=2)
    else:
        fjson = data
    if __use_pygments:
        fjson = pygments.highlight(
            fjson, pygments.lexers.JsonLexer(),
            pygments.formatters.TerminalFormatter()
        )
    print(fjson)


### HTTP serving webwxapp.js & WebSocket server

class Web(object):
    instance = None

    def __init__(self):
        self.token2ws = {}
        self.ws2token = {}
        assert not Web.instance
        Web.instance = self

    def remove_ws(self, ws, peername):
        token = self.ws2token.pop(ws)
        del self.token2ws[token]
        # Server.instance.on_wechat_close(token, peername)

    def remove_token(self, token, peername):
        del self.ws2token[self.token2ws[token]]
        del self.token2ws[token]
        # Server.instance.on_wechat_close(token, peername)

    async def handle_webwxapp_js(self, request):
        with open(os.path.join(os.path.dirname(__file__), 'webwxapp.js'), 'rb') as f:
            return web.Response(body=f.read(),
                                headers={'Content-Type': 'application/javascript; charset=UTF-8',
                                         'Access-Control-Allow-Origin': '*'})

    async def handle_web_socket(self, request):
        ws = web.WebSocketResponse()
        peername = request.transport.get_extra_info('peername')
        info('WebSocket connected to %r', peername)
        await ws.prepare(request)
        async for msg in ws:
            if msg.tp == web.MsgType.text:
                try:
                    data = json.loads(msg.data)
                    token = data['token']
                    assert isinstance(token, str) and re.match(
                        r'^[0-9a-f]{32}$', token)
                    if ws in self.ws2token:
                        if self.ws2token[ws] != token:
                            self.remove_ws(ws, peername)
                    if ws not in self.ws2token:
                        if token in self.token2ws:
                            self.remove_token(token, peername)
                        self.ws2token[ws] = token
                        self.token2ws[token] = ws
                    #     Server.instance.on_wechat_open(token, peername)
                    # Server.instance.on_wechat(data)
                    Fishwechat.instance.on_wechat(data)
                except AssertionError as e:
                    # info('WebSocket %r', e)
                    raise
                    break
                except:
                    raise
            elif msg.tp == web.MsgType.ping:
                try:
                    ws.pong()
                except:
                    break
            elif msg.tp == web.MsgType.close:
                break
        info('WebSocket disconnected from %r', peername)
        if ws in self.ws2token:
            self.remove_ws(ws, peername)
        return ws

    def start(self, host, port, tls, loop):
        self.loop = loop
        self.app = aiohttp.web.Application()
        self.app.router.add_route('GET', '/', self.handle_web_socket)
        self.app.router.add_route(
            'GET', '/webwxapp.js', self.handle_webwxapp_js)
        self.handler = self.app.make_handler()
        self.srv = loop.run_until_complete(
            loop.create_server(self.handler, host, port, ssl=tls))

    def stop(self):
        self.srv.close()
        self.loop.run_until_complete(self.srv.wait_closed())
        self.loop.run_until_complete(self.app.shutdown())
        self.loop.run_until_complete(self.handler.finish_connections(0))
        self.loop.run_until_complete(self.app.cleanup())

    def send_text_message(self, token, receiver, msg):
        if token in self.token2ws:
            ws = self.token2ws[token]
            try:
                ws.send_str(json.dumps({
                    'command': 'send_text_message',
                    'receiver': receiver,
                    'message': msg,
                    # @ webwxapp.js /e.ClientMsgId = e.LocalID = e.MsgId = (utilFactory.now() + Math.random().toFixed(3)).replace(".", ""),
                    'local_id': '{}0{:03}'.format(int(time.time()*1000), random.randint(0, 999)),
                }))
            except:
                pass

    def add_member(self, token, roomname, username):
        if token in self.token2ws:
            ws = self.token2ws[token]
            try:
                ws.send_str(json.dumps({
                    'command': 'add_member',
                    'room': roomname,
                    'user': username,
                }))
            except:
                pass

    def del_member(self, token, roomname, username):
        if token in self.token2ws:
            ws = self.token2ws[token]
            try:
                ws.send_str(json.dumps({
                    'command': 'del_member',
                    'room': roomname,
                    'user': username,
                }))
            except:
                pass

    def mod_topic(self, token, roomname, topic):
        if token in self.token2ws:
            ws = self.token2ws[token]
            try:
                ws.send_str(json.dumps({
                    'command': 'mod_topic',
                    'room': roomname,
                    'topic': topic,
                }))
            except:
                pass


class WeChatCommands:
    @staticmethod
    def friend(client, data):
        pass

    @staticmethod
    def non_friend(client, data):
        pass

    @staticmethod
    def room(client, data):
        debug("Room")
        debug({k: v for k, v in data['record'].items() if k in ['UserName', 'DisplayName', 'NickName', 'IsSelf', 'EncryChatRoomId']})
        record = data['record']
        client.ensure_wechat_room(record)

    @staticmethod
    def message(client, data):
        # receiver is a WeChat chatroom
        if data.get('room', None):
            client.ensure_wechat_room(data['room']) \
                .on_wechat_msg(data)
        # receiver is a WeChat user
        else:
            pass

    @staticmethod
    def send_text_message_fail(client, data):
        print('failed: {}'.format(data['message']))
        # client.write(':{} NOTICE {} :{}'.format(client.server.name, '+status', 'failed: {}'.format(data['message'])))


class WeChatRoom(object):

    def __init__(self, channel, record):
        self.username = record['UserName']
        self.name = record['DisplayName']
        self.channel = channel
        self.record = record

    def on_wechat_msg(self, msg):
        # pprint_json(msg)
        if msg['sender']["UserName"] == self.username:
            info(msg["message"])
            self.name = msg["sender"]["DisplayName"]
        else:
            info("[%s] %s (%s)", msg["sender"]["NickName"],
                 msg["message"], msg["type"])
            self.channel.on_wechat_msg(
                self.name, msg["sender"]["NickName"], msg["message"])

    def update(self, record):
        self.username = record['UserName']
        self.name = record['DisplayName']
        self.record = record

    def send_text_msg(self, token, sender, content):
        msg = "[{sender}] {content}".format(sender=sender, content=content)
        Web.instance.send_text_message(token, self.username, msg)


class Fishwechat(object):

    instance = None

    def __init__(self, fish_token_id, fish_token_key):
        assert not Fishwechat.instance
        Fishwechat.instance = self

        self.channels = {}              # joined, name -> channel
        self.wcunamerooms = {}
        self.wcnamerooms = {}
        self.token = None

        self.fish_token_id = fish_token_id
        self.fish_token_key = fish_token_key

        self.fishchan2wcroom = {}
        self.wcroom2fishchan = {}

        for fishchan, wcroom in BINDING:
            self.fishchan2wcroom[fishchan] = wcroom
            self.wcroom2fishchan[wcroom] = fishchan

    def change_token(self, token):
        info("Token: %s", token)
        self.token = token

    def on_wechat(self, data):
        command = data['command']
        if type(WeChatCommands.__dict__.get(command)) == staticmethod:
            getattr(WeChatCommands, command)(self, data)

    def ensure_wechat_room(self, record):
        assert isinstance(record['UserName'], str)
        assert isinstance(record['DisplayName'], str)
        assert isinstance(record.get('OwnerUin', -1), int)
        # self.channels[]
        if record['UserName'] in self.wcunamerooms:
            room = self.wcunamerooms[record['UserName']]
            del self.wcnamerooms[room.name]
            room.update(record)
        else:
            room = WeChatRoom(self, record)
            self.wcunamerooms[record['UserName']] = room
        self.wcnamerooms[room.name] = room

        return room

    def on_fishroom_msg(self, msg):
        info("<fishroom> [%s] %s (%s)", msg["sender"],
             msg["content"], msg["room"])
        fishchan = msg["room"]
        if fishchan not in self.fishchan2wcroom:
            return
        roomname = self.fishchan2wcroom[fishchan]
        if roomname not in self.wcnamerooms:
            return
        room = self.wcnamerooms[roomname]
        room.send_text_msg(self.token, msg["sender"], msg["content"])

    def on_wechat_msg(self, wcroom, sender, content):
        if wcroom not in self.wcroom2fishchan:
            return
        fishchan = self.wcroom2fishchan[wcroom]

        content = re.sub(r'<[^>]*>', '', content)  # remove emoji
        # remove unsupported links
        content = re.sub(r'\[.+\] (https://wx.qq.com/.*)?', '', content)
        if not content:
            return

        self.send_fishroom_msg(fishchan, sender, content)

    def listen_fishroom(self):
        info("Starting listening to fishroom")
        while 1:
            try:
                debug("Fetching fishroom")
                r = requests.get(
                    FISHROOM_ADDR,
                    params={
                        'id': self.fish_token_id, 'key': self.fish_token_key
                    }
                )
            except requests.exceptions.ConnectionError:
                print("Connection Error")
                time.sleep(2)

            if r.status_code == 200:
                try:
                    j = r.json()
                except:
                    continue
                msgs = j['messages']
                for m in msgs:
                    if m['channel'] == FISHROOM_MY_TAG:
                        continue
                    self.on_fishroom_msg(m)

    def send_fishroom_msg(self, room, sender, content):
        url = FISHROOM_POST_ADDR.format(room=room)
        try:
            r = requests.post(
                url,
                params={
                    'id': self.fish_token_id, 'key': self.fish_token_key,
                },
                json={
                    'sender': sender, 'content': content,
                }
            )
        except requests.exceptions.ConnectionError:
            print("Connection Error")

        if r.status_code != 200:
            warning("failed to post fishroom message")



def fishroom_thread():
    Fishwechat.instance.listen_fishroom()


def main():
    ap = ArgumentParser(description='wechatircd brings wx.qq.com to IRC clients')
    ap.add_argument('-d', '--debug', action='store_true', help='run ipdb on uncaught exception')
    ap.add_argument('-l', '--listen', default='127.0.0.1', help='IRC/HTTP/WebSocket listen address')
    ap.add_argument('-q', '--quiet', action='store_const', const=logging.WARN, dest='loglevel')
    ap.add_argument('-v', '--verbose', action='store_const', const=logging.DEBUG, dest='loglevel')
    ap.add_argument('--web-port', type=int, default=9000, help='HTTP/WebSocket listen port')
    ap.add_argument('--tls-cert', help='HTTP/WebSocket listen port')
    ap.add_argument('--tls-key', help='HTTP/WebSocket listen port')
    options = ap.parse_args()

    # send to syslog if run as a daemon (no controlling terminal)
    try:
        with open('/dev/tty'):
            pass
        logging.basicConfig(format='%(asctime)s:%(levelname)s: %(message)s')
    except OSError:
        logging.root.addHandler(logging.handlers.SysLogHandler('/dev/log'))
    logging.root.setLevel(options.loglevel or logging.INFO)

    if options.tls_cert:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        tls.load_cert_chain(options.tls_cert, options.tls_key)
    else:
        tls = None

    loop = asyncio.get_event_loop()
    if options.debug:
        sys.excepthook = ExceptionHook()
    web = Web()
    fish = Fishwechat(FISHROOM_TOKEN_ID, FISHROOM_TOKEN_KEY)
    fish.change_token(uuid.uuid1().hex)

    web.start(options.listen, options.web_port, tls, loop)

    t = threading.Thread(target=fishroom_thread)
    t.setDaemon(True)
    t.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        web.stop()
        loop.stop()


if __name__ == '__main__':
    sys.exit(main())

# vim: ts=4 sw=4 sts=4 expandtab
