import socketio
import random
from aiohttp import web

sio = socketio.AsyncServer(cors_allowed_origins="*")
app = web.Application()
sio.attach(app)

app.router.add_static("/", path="static/", show_index=True)

lobbies = {}

def find_lobby_by_sid(sid):
    for code, lobby in lobbies.items():
        for p in lobby["players"]:
            if p["sid"] == sid:
                return code, lobby
    return None, None

@sio.event
async def create_lobby(sid, data):
    name = data.get("name", "Player")
    code = str(random.randint(1000, 9999))
    while code in lobbies:
        code = str(random.randint(1000, 9999))

    lobbies[code] = {"players": [{"sid": sid, "name": name}]}
    await sio.enter_room(sid, code)
    await sio.emit("lobby_update", {
        "code": code,
        "players": [p["name"] for p in lobbies[code]["players"]]
    }, room=code)

@sio.event
async def join_lobby(sid, data):
    code = data.get("code")
    name = data.get("name", "Player")

    if code not in lobbies:
        await sio.emit("error", {"msg": "Lobby not found"}, to=sid)
        return

    lobby = lobbies[code]
    if len(lobby["players"]) >= 4:
        await sio.emit("error", {"msg": "Lobby is full"}, to=sid)
        return

    lobby["players"].append({"sid": sid, "name": name})
    await sio.enter_room(sid, code)
    await sio.emit("lobby_update", {
        "code": code,
        "players": [p["name"] for p in lobby["players"]]
    }, room=code)

@sio.event
async def disconnect(sid):
    code, lobby = find_lobby_by_sid(sid)
    if lobby:
        lobby["players"] = [p for p in lobby["players"] if p["sid"] != sid]
        if not lobby["players"]:
            del lobbies[code]
        else:
            await sio.emit("lobby_update", {
                "code": code,
                "players": [p["name"] for p in lobby["players"]]
            }, room=code)

if __name__ == "__main__":
    web.run_app(app, port=5000)