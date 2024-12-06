from fastapi import FastAPI, Request
from voice_handler import handle_media_stream, handle_incoming_call, make_call
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# Define a root endpoint
@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

# 路由配置
app.add_api_route("/incoming-call", handle_incoming_call, methods=["POST"])
app.websocket("/media-stream")(handle_media_stream)
app.add_api_route("/make-call", make_call, methods=["POST"])

# Add these lines after creating the FastAPI app
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6060)
