"""Start the web server:  python run.py   then open http://127.0.0.1:8000"""
import uvicorn

from app.main import create_app
from config.settings import Settings

if __name__ == "__main__":
    settings = Settings.from_env()
    print(f"Open http://{settings.host}:{settings.port} in your browser (Ctrl+C to stop).")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
