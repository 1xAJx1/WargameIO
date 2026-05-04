import socketio
import random
import os
import json
import requests
from PIL import Image
import io as pyio
from aiohttp import web

sio = socketio.AsyncServer(cors_allowed_origins="*")
app = web.Application()
sio.attach(app)

app.router.add_static("/static", path=os.path.join(os.path.dirname(__file__), "static"))

def generate_world_data():
    cache_file = 'world_data.json'
    if os.path.exists(cache_file):
        print("Loading cached world map...")
        with open(cache_file) as f:
            return json.load(f)

    print("Downloading world map...")

    urls = [
        "https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x2048x1024.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Whole_world_-_land_and_oceans.jpg/1280px-Whole_world_-_land_and_oceans.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/80/World_map_-_low_resolution.svg/1280px-World_map_-_low_resolution.svg.png",
    ]

    img = None
    for url in urls:
        try:
            print(f"Trying {url}...")
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            img = Image.open(pyio.BytesIO(response.content))
            print("Success!")
            break
        except Exception as e:
            print(f"Failed: {e}")
            continue

    if img is None:
        print("All URLs failed, generating procedural map...")
        return generate_procedural_world()

    W, H = 512, 256
    img = img.resize((W, H), Image.LANCZOS).convert('RGB')

    data = []
    for y in range(H):
        for x in range(W):
            r, g, b = img.getpixel((x, y))
            if b > r + 30 and b > g + 10:
                t = 0
            elif r > 200 and g > 200 and b > 200:
                t = 5
            elif r > g + 20 and g > 100:
                t = 3
            elif g > r + 20 and g > 80:
                t = 4 if g > 130 else 1
            elif r > 120 and g > 100 and b > 80 and abs(r - g) < 30:
                t = 2
            elif b > 100 and r < 100:
                t = 0
            else:
                t = 1
            data.append(t)

    result = {'w': W, 'h': H, 'data': data}
    with open(cache_file, 'w') as f:
        json.dump(result, f)
    print("World map cached.")
    return result


def generate_procedural_world():
    print("Generating procedural world map...")
    W, H = 512, 256
    data = [0] * (W * H)

    def fill(minLat, maxLat, minLng, maxLng, t):
        x1 = int((minLng + 180) / 360 * W)
        x2 = int((maxLng + 180) / 360 * W)
        y1 = int((90 - maxLat) / 180 * H)
        y2 = int((90 - minLat) / 180 * H)
        for y in range(max(0, y1), min(H, y2)):
            for x in range(max(0, x1), min(W, x2)):
                data[y * W + x] = t

    fill(25, 72, -168, -52, 1)
    fill(-56, 12, -82, -34, 1)
    fill(36, 71, -10, 40, 1)
    fill(-35, 37, -18, 52, 1)
    fill(1, 77, 26, 180, 1)
    fill(-39, -10, 113, 154, 1)
    fill(-90, -66, -180, 180, 5)
    fill(60, 83, -55, -18, 5)
    fill(25, 72, -50, -10, 0)
    fill(8, 25, -92, -58, 0)
    fill(30, 60, -125, -105, 2)
    fill(-55, 10, -80, -70, 2)
    fill(44, 48, 5, 16, 2)
    fill(28, 35, 72, 100, 2)
    fill(50, 68, 58, 62, 2)
    fill(14, 30, -18, 36, 3)
    fill(16, 26, 44, 58, 3)
    fill(38, 48, 90, 120, 3)
    fill(-10, 5, -78, -48, 4)
    fill(-5, 5, 16, 30, 4)
    fill(55, 70, 60, 140, 4)
    fill(50, 65, -130, -60, 4)

    result = {'w': W, 'h': H, 'data': data}
    with open('world_data.json', 'w') as f:
        json.dump(result, f)
    print("Procedural world map cached.")
    return result


world_map_data = generate_world_data()
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
async def start_game(sid, data):
    code = data.get("code")
    map_key = data.get("map", "world")
    if code in lobbies:
        host = lobbies[code]["players"][0]
        if host["sid"] == sid:
            await sio.emit("game_started", {"map": map_key}, room=code)


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


async def index(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), "static/index.html"))


async def get_map_data(request):
    return web.json_response(world_map_data)


app.router.add_get("/", index)
app.router.add_get("/mapdata", get_map_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    web.run_app(app, host="0.0.0.0", port=port)