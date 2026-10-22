"""Start the web server:  python run.py   then open http://127.0.0.1:8000

Options: --port 8010 (another port), --host 0.0.0.0 (allow other devices on the network),
         --data-dir PATH (use a different folder for the databases).
"""
import argparse
import os

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ShopAgents web server.")
    parser.add_argument("--host", help="Address to listen on (default from .env or 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Port to listen on (default from .env or 8000)")
    parser.add_argument("--data-dir", help="Folder for the databases (default: data/)")
    args = parser.parse_args()
    if args.host:
        os.environ["HOST"] = args.host
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.data_dir:
        os.environ["DATA_DIR"] = args.data_dir

    from app.main import create_app
    from config.settings import Settings

    settings = Settings.from_env()
    print(f"Open http://{settings.host}:{settings.port} in your browser (Ctrl+C to stop).")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
