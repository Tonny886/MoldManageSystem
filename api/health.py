from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "success", "message": "健康检查应用运行正常"})

@app.route('/health')
def health():
    return "OK"

application = app

if __name__ == '__main__':
    app.run(debug=True)