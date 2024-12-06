import asyncio
from http import HTTPStatus
import ssl

from websockets.asyncio.server import serve

file1_path = "../local/asv"
file2_path = "../local/vep"

throw_429 = True


def toggle(connection, request):
    global throw_429
    if request.path == "/toggle":
        throw_429 = not throw_429
        if throw_429:
            return connection.respond(HTTPStatus.OK, f"OK {throw_429}\n")
        else:
            return connection.respond(HTTPStatus.IM_A_TEAPOT, f"\n")

    if throw_429:
        return connection.respond(HTTPStatus.TOO_MANY_REQUESTS, "\n")


async def send_files(websocket):
    try:
        async for message in websocket:
            print(message)
            return

        # Datei 1 lesen
        with open(file1_path, "rb") as file1:
            file1_content = file1.read()

        # Datei 2 lesen
        with open(file2_path, "rb") as file2:
            file2_content = file2.read()

        # Nachricht an den Client senden
        await websocket.send(file1_content)
        print("file 1 sent")
        asyncio.sleep(2)
        await websocket.send(file2_content)
        print("file 2 sent")

    except FileNotFoundError as e:
        error_message = f"Fehler: Datei nicht gefunden - {e.filename}"
        print(error_message)
        await websocket.send(error_message)

    except Exception as e:
        error_message = f"Ein Fehler ist aufgetreten: {e}"
        print(error_message)
        await websocket.send(error_message)


async def main():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="../local/selfsigned.crt", keyfile="../local/selfsigned.key")
    context.check_hostname = False
    async with serve(send_files, "localhost", 8001, process_request=toggle, ssl=context):
        await asyncio.get_running_loop().create_future()  # run forever


asyncio.run(main())
