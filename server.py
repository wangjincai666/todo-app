import json
import re
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
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
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
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "把一条待办写进数据库。用户说“记一下/帮我加/别忘了”时调用。title 只填要做的事本身，去掉“帮我加一条”这类指令词。例如用户说“帮我加一条明天交实验报告”，title 只填“明天交实验报告”。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "待办内容，保留用户原话，不要改写"}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_items",
            "description": "查询待办列表。用户问“还有哪些/有哪些没做完”时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "only_todo": {"type": "boolean", "description": "是否只看未完成的"}
                },
                "required": [],
            },
        },
    },
]


def run_tool(name, args):
    def clean_title(raw):
        t = (raw or "").strip()
        t = re.sub(r"^(帮我|请|麻烦|给我|给|再)?\s*(添加|加|记一下|记|记录|新增|新建)\s*(一条|一个|一下)?\s*", "", t)
        return t.strip(" ，,。.!！") or (raw or "").strip()

    con = get_db()
    try:
        if name == "add_item":
            title = clean_title(args.get("title") or "")
            if not title:
                return {"ok": False, "error": "title 为空"}
            cur = con.execute(
                "INSERT INTO items (title, created_at) VALUES (?, ?)",
                (title, datetime.now().isoformat(timespec="seconds")),
            )
            con.commit()
            return {"ok": True, "id": cur.lastrowid}

        if name == "query_items":
            sql = "SELECT id, title, done FROM items"
            if args.get("only_todo"):
                sql += " WHERE done = 0"
            rows = con.execute(sql + " ORDER BY id DESC").fetchall()
            return {"ok": True, "items": [dict(r) for r in rows]}

        return {"ok": False, "error": f"未知工具 {name}"}
    finally:
        con.close()


@app.post("/api/agent")
def agent():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"code": 400, "data": None, "msg": "text 不能为空"}), 400

    messages = [
        {"role": "system", "content": "你是待办助手。用户让你记事情就调用 add_item；问有哪些待办就调用 query_items。回答用中文，简短。"},
        {"role": "user", "content": text},
    ]
    logs = []
    headers = {"Authorization": f"Bearer {os.environ['ZHIPU_API_KEY']}"}

    for _ in range(3):
        r = requests.post(
            MODEL_URL,
            headers=headers,
            json={"model": MODEL_NAME, "messages": messages, "tools": TOOLS},
            timeout=60,
        )
        msg = r.json()["choices"][0]["message"]

        if not msg.get("tool_calls"):
            return ok({"reply": msg.get("content", ""), "logs": logs})

        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg["tool_calls"]})
        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                args = {}
            result = run_tool(name, args)
            logs.append({"tool": name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    return ok({"reply": "（工具调用超过 3 轮，已停止）", "logs": logs})
@app.put("/api/items/<int:item_id>")
def update_item(item_id):
    data = request.get_json(silent=True) or {}
    con = get_db()
    try:
        row = con.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return jsonify({"code": 404, "data": None, "msg": "没有这条"}), 404

        title = (data.get("title", row["title"]) or "").strip()
        if not title:
            return jsonify({"code": 400, "data": None, "msg": "title 不能为空"}), 400

        done = data.get("done", row["done"])
        done = 1 if str(done) in ("1", "true", "True") else 0

        con.execute("UPDATE items SET title = ?, done = ? WHERE id = ?", (title, done, item_id))
        con.commit()
        new_row = con.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return ok(dict(new_row))
    finally:
        con.close()
@app.errorhandler(Exception)
def on_error(e):
    code = getattr(e, "code", 500)
    return jsonify({"code": code, "data": None, "msg": str(e)}), code


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)