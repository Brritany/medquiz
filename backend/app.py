from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from datetime import datetime
import os
import json
import random
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# 資料庫初始化與路徑設定（強制確保 instance 資料夾存在）
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'users.db')
os.makedirs(os.path.dirname(db_path), exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'super-secret'

db = SQLAlchemy(app)
jwt = JWTManager(app)

# 資料表定義
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class AnswerRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    question_id = db.Column(db.Integer)
    correct = db.Column(db.Boolean)
    user_answer = db.Column(db.String(5))
    question_snapshot = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime)

@app.before_request
def ensure_db():
    db.create_all()

# 註冊 API
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"msg": "使用者已存在"}), 400
    user = User(username=data['username'], password=data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({"msg": "註冊成功"})

# 登入 API
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username'], password=data['password']).first()
    if not user:
        return jsonify({"msg": "帳號或密碼錯誤"}), 401
    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token)

# 題庫資料夾設定
DATASET_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'DataSet')

@app.route('/api/list-types')
def list_types():
    files = [f for f in os.listdir(DATASET_FOLDER) if f.endswith('.json')]
    result = defaultdict(lambda: defaultdict(list))
    for f in files:
        parts = f.replace('.json', '').split('_')
        if len(parts) >= 4:
            year, level, category = parts[0], parts[1], parts[2] + '_' + parts[3]
            result[level][category].append(year)
    return jsonify(result)

@app.route('/api/load-questions', methods=['POST'])
def load_questions():
    data = request.get_json()
    level = data.get('level')
    category = data.get('category')
    year = data.get('year')
    count = data.get('count', 80)

    files = [f for f in os.listdir(DATASET_FOLDER)
             if f.endswith('.json') and level in f and category in f]

    if year and year != 'random':
        files = [f for f in files if f.startswith(year)]

    all_questions = []
    for filename in files:
        with open(os.path.join(DATASET_FOLDER, filename), encoding='utf-8') as f:
            questions = json.load(f)
            for q in questions:
                q['filename'] = filename  # 加上 filename 供紀錄使用
                all_questions.append(q)

    if year == 'random':
        random.shuffle(all_questions)
        all_questions = all_questions[:count]

    return jsonify(all_questions)

# 儲存作答
@app.route('/api/save-answers', methods=['POST'])
@jwt_required()
def save_answers():
    user_id = get_jwt_identity()
    data = request.get_json()
    results = data.get("results", [])

    try:
        for item in results:
            question_id = item['question_id']
            correct = item['correct']
            user_answer = item.get('user_answer')
            snapshot = item.get('question')

            record = AnswerRecord(
                user_id=user_id,
                question_id=question_id,
                correct=correct,
                user_answer=user_answer,
                question_snapshot=snapshot,
                timestamp=datetime.now()
            )
            db.session.add(record)

        db.session.commit()
        return jsonify({"msg": "作答紀錄已儲存"})

    except Exception as e:
        print("🔥 儲存作答錯誤：", e)
        return jsonify({"error": str(e)}), 500

# 查詢作答紀錄
@app.route('/api/history')
@jwt_required()
def get_history():
    user_id = get_jwt_identity()
    records = AnswerRecord.query.filter_by(user_id=user_id).order_by(AnswerRecord.timestamp.desc()).all()
    return jsonify([
        {
            "question_id": r.question_id,
            "correct": r.correct,
            "user_answer": r.user_answer,
            "timestamp": r.timestamp.isoformat(),
            "question": r.question_snapshot
        }
        for r in records
    ])

@app.route('/api/review')
@jwt_required()
def review_wrong_questions():
    user_id = get_jwt_identity()
    records = AnswerRecord.query.filter_by(user_id=user_id, correct=False).order_by(AnswerRecord.timestamp.desc()).all()
    return jsonify([
        {
            "question_id": r.question_id,
            "user_answer": r.user_answer,
            "timestamp": r.timestamp.isoformat(),
            "question": r.question_snapshot
        }
        for r in records
    ])

@app.route('/api/mark-correct', methods=['POST'])
@jwt_required()
def mark_correct():
    user_id = get_jwt_identity()
    data = request.get_json()
    qid = data.get("question_id")

    record = AnswerRecord.query.filter_by(user_id=user_id, question_id=qid, correct=False).order_by(AnswerRecord.timestamp.desc()).first()
    if record:
        record.correct = True
        db.session.commit()
        return jsonify({"msg": "已標記為正確"})
    else:
        return jsonify({"msg": "找不到紀錄"}), 404

# 靜態頁面路由
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

