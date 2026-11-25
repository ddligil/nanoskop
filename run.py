"""Quick start: python run.py [port]"""
import sys, uvicorn
port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8000
host = "0.0.0.0" if "--ag" in sys.argv else "127.0.0.1"
print(f"Nanoskop: http://localhost:{port}  (admin: /admin)")
uvicorn.run("app.main:app", host=host, port=port)
