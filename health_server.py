from flask import Flask
import threading
from main import run_bot   # your bot loop

app = Flask(__name__)

@app.route("/")
def health():
    return {"status": "running"}, 200


def start_bot():
    run_bot()


if __name__ == "__main__":
    t = threading.Thread(target=start_bot)
    t.start()
    app.run(host="0.0.0.0", port=8080)
