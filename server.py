import socketio
import random
import os
from aiohttp import web

sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="aiohttp")
app = web.Application()
sio.attach(app)

app.router.add_static("/static", path=os.path.join(os.path.dirname(__file__), "static"))

lobbies = {}

MAPS = {
    "europe": {
        "name": "Europe",
        "spawn_range": 20
    },
    "world": {
        "name": "World",
        "spawn_range": 40
    }
}

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

    lobbies[code] = {
        "host": sid,
        "players": [{"sid": sid, "name": name}]
    }

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

    if any(p["sid"] == sid for p in lobby["players"]):
        return

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
async def start_game(sid, data):
    code = data.get("code")
    map_key = data.get("map", "europe")

    if code not in lobbies:
        return

    lobby = lobbies[code]

    # only host can start
    if lobby["host"] != sid:
        return

    map_data = MAPS.get(map_key, MAPS["europe"])

    await sio.emit("game_started", {
        "map": map_key,
        "map_data": map_data
    }, room=code)


@sio.event
async def disconnect(sid):
    code, lobby = find_lobby_by_sid(sid)

    if not lobby:
        return

    lobby["players"] = [p for p in lobby["players"] if p["sid"] != sid]

    # host reassignment
    if lobby.get("host") == sid and lobby["players"]:
        lobby["host"] = lobby["players"][0]["sid"]

    if not lobby["players"]:
        del lobbies[code]
    else:
        await sio.emit("lobby_update", {
            "code": code,
            "players": [p["name"] for p in lobby["players"]]
        }, room=code)


async def index(request):
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return web.FileResponse(path)


app.router.add_get("/", index)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    web.run_app(app, host="0.0.0.0", port=port)