from flask import Flask, jsonify

app = Flask(__name__)
app.json.ensure_ascii = False

@app.get("/api/hello")
def hello():
    return jsonify({"code": 0, "data": "你好，后端", "msg": "ok"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)