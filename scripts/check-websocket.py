import argparse
import json
import sys
import time
from pathlib import Path

import websocket

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pok.conn import Conn
from pok.contract import QUERIES
from pok.cookies import load_cookie_file
from pok.stream import StreamConnection, StreamProtocolError, parse_frame


def subscription_variables(client):
    variables = {
        "chatUpdated": {"filter": {"userId": client.id}, "showForbiddenImage": True},
        "chatMarkedAsRead": {"filter": {"userId": client.id}, "showForbiddenImage": True},
        "userUpdated": {"userId": client.id},
    }
    chats = client.load_chats(count=1)
    if chats.chats:
        variables["chatMessageCreated"] = {
            "filter": {"chatId": chats.chats[0].id}, "showForbiddenImage": True,
        }
    return variables


def observe_subscriptions(stream, duration):
    deadline = time.monotonic() + duration
    pong = False
    stream.send({"type": "ping", "payload": {"probe": True}})
    while time.monotonic() < deadline:
        stream.socket.settimeout(max(0.1, deadline - time.monotonic()))
        try:
            frame = parse_frame(stream.socket.recv())
        except websocket.WebSocketTimeoutException:
            break
        if frame["type"] == "error":
            raise StreamProtocolError("Subscription rejected")
        if frame["type"] == "next" and frame.get("payload", {}).get("errors"):
            raise StreamProtocolError("Subscription returned errors")
        pong = pong or frame["type"] == "pong"
        stream.handle_control(frame)
    return pong


def check_connection(client, variables):
    stream = StreamConnection(client)
    try:
        stream.connect()
        for name, values in variables.items():
            stream.send({"id": name, "type": "subscribe", "payload": {
                "operationName": name, "query": QUERIES[name], "variables": values,
            }})
        pong = observe_subscriptions(stream, duration=4)
        for name in variables:
            stream.send({"id": name, "type": "complete"})
        return {"acknowledged": True, "subscriptions": len(variables), "pong": pong}
    finally:
        stream.close()


def main():
    parser = argparse.ArgumentParser(description="Проверка WebSocket Playerok: подключение, подписки, ping/pong")
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument("--user-agent", default="", help="User-Agent браузера, из которого экспортированы Cookie")
    parser.add_argument("--proxy", default=None, help="прокси в формате conf/config.json")
    args = parser.parse_args()
    with Conn(cookies=load_cookie_file(args.cookies), user_agent=args.user_agent, proxy=args.proxy) as client:
        client.get()
        variables = subscription_variables(client)
        for cycle in range(2):
            result = check_connection(client, variables)
            print(json.dumps({"cycle": cycle + 1, **result}), flush=True)


if __name__ == "__main__":
    main()
