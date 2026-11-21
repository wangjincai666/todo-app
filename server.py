import json
import os
import sqlite3
from datetime import datetime

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, stream_with_context

load_dotenv()

app = Flask(__name__)
MODEL_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-4-flash"
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return resp
app.json.ensure_ascii = False


def get_db():
    con = sqlite3.connect("data.db")
    con.row_factory = sqlite3.Row
    return con


def ok(data=None, msg="ok"):
    return jsonify({"code": 0, "data": data, "msg": msg})


def init_db():
    con = get_db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


@app.get("/api/items")
def list_items():
    con = get_db()
    rows = con.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    con.close()
    return ok([dict(r) for r in rows])


@app.post("/api/items")
def add_item():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"code": 400, "data": None, "msg": "title 不能为空"}), 400

    con = get_db()
    cur = con.execute(
        "INSERT INTO items (title, created_at) VALUES (?, ?)",
        (title, datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return jsonify({"code": 0, "data": {"id": new_id}, "msg": "created"}), 201


@app.delete("/api/items/<int:item_id>")
def delete_item(item_id):
    con = get_db()
    cur = con.execute("DELETE FROM items WHERE id = ?", (item_id,))
    con.commit()
    deleted = cur.rowcount
    con.close()
    if deleted == 0:
        return jsonify({"code": 404, "data": None, "msg": "没有这条"}), 404
    return ok({"id": item_id})


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    messages = body.get("messages") or []
    if not messages:
        return jsonify({"code": 400, "data": None, "msg": "messages 不能为空"}), 400

    payload = {"model": MODEL_NAME, "messages": messages[-10:], "stream": True}
    headers = {"Authorization": f"Bearer {os.environ['ZHIPU_API_KEY']}"}

    def gen():
        with requests.post(MODEL_URL, json=payload, headers=headers, stream=True, timeout=60) as r:
            for line in r.iter_lines():
                if not line or not line.startswith(b"data: "):
                    continue
                data = line[6:]
                if data == b"[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except Exception:
                    continue
                text = delta.get("content")
                if text:
                    yield "data: " + json.dumps({"t": text}, ensure_ascii=False) + "\n\n"

    return Response(stream_with_context(gen()), mimetype="text/event-stream")
@app.errorhandler(Exception)
def on_error(e):
    code = getattr(e, "code", 500)
    return jsonify({"code": code, "data": None, "msg": str(e)}), code


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)