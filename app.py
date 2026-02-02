import os
import json
try:
    import eventlet
    eventlet.monkey_patch()
except Exception:
    eventlet = None
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash
import random
from datetime import datetime, timedelta

# Импортируем модели и настройки
from models import db, User, Category, Challenge, Solve, Difficulty, UserFlag, UserFile, MatchTask, MatchAttempt
from config import Config
from generators import TaskGenerator 
from models import Match, MatchmakingQueue
from utils import calculate_elo
from autotask.examples import SimpleStegano


app = Flask(__name__)
app.config.from_object(Config)

# Инициализация расширений
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Пожалуйста, войдите в систему."
login_manager.login_message_category = "error"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet" if eventlet else "threading")

match_presence = {}
PVP_TASKS_COUNT = int(os.getenv('PVP_TASKS_COUNT', 3))
PVP_MATCH_DURATION_SECONDS = int(os.getenv('PVP_MATCH_DURATION_SECONDS', 600))

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Декоратор для доступа только админам
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Доступ запрещен. Требуются права администратора.", "error")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def _match_room(match_id):
    return f"match_{match_id}"

def _get_match_tasks(match):
    tasks = MatchTask.query.filter_by(match_id=match.id).order_by(MatchTask.order_index).all()
    if tasks:
        return tasks
    if match.challenge_id:
        return [MatchTask(match_id=match.id, challenge_id=match.challenge_id, order_index=0, challenge=match.challenge)]
    return []

def _build_match_state(match):
    tasks = _get_match_tasks(match)
    task_states = {}
    for mt in tasks:
        task_states[mt.challenge_id] = {
            'solved_by_user_id': mt.solved_by_user_id,
            'solved_at': mt.solved_at.isoformat() if mt.solved_at else None
        }

    players = [match.player1_id, match.player2_id]
    stats = {}
    for user_id in players:
        correct_count = MatchAttempt.query.filter_by(match_id=match.id, user_id=user_id, is_correct=True).count()
        incorrect_count = MatchAttempt.query.filter_by(match_id=match.id, user_id=user_id, is_correct=False).count()
        stats[user_id] = {
            'correct': correct_count,
            'incorrect': incorrect_count
        }

    return {
        'task_states': task_states,
        'stats': stats
    }

def _match_end_time(match):
    return match.start_time + timedelta(seconds=PVP_MATCH_DURATION_SECONDS)

def _match_time_left_seconds(match):
    remaining = int((_match_end_time(match) - datetime.utcnow()).total_seconds())
    return max(0, remaining)

def _solved_count_by_user(match_tasks, user_id):
    return sum(1 for mt in match_tasks if mt.solved_by_user_id == user_id)

def _incorrect_count(match_id, user_id):
    return MatchAttempt.query.filter_by(match_id=match_id, user_id=user_id, is_correct=False).count()

def _are_all_tasks_solved(match_tasks):
    return all(mt.solved_by_user_id for mt in match_tasks) if match_tasks else False

def _apply_match_result(match, winner_id=None):
    match.is_active = False
    match.winner_id = winner_id
    match.end_time = datetime.utcnow()

    if not winner_id:
        return

    loser_id = match.player2_id if match.player1_id == winner_id else match.player1_id
    loser = User.query.get(loser_id)
    winner = User.query.get(winner_id)
    if not winner or not loser:
        return

    new_winner_elo, new_loser_elo = calculate_elo(winner.elo_rating, loser.elo_rating)
    winner.elo_rating = new_winner_elo

    match_tasks = _get_match_tasks(match)
    total_points = sum(mt.challenge.points for mt in match_tasks if mt.challenge)
    if total_points == 0 and match.challenge:
        total_points = match.challenge.points
    winner.user_points += (total_points + 50)
    loser.elo_rating = new_loser_elo

def _apply_match_no_score(match):
    match.is_active = False
    match.winner_id = None
    match.end_time = datetime.utcnow()

def _finalize_match_by_counts(match):
    if not match.is_active:
        return False

    match_tasks = _get_match_tasks(match)
    p1_solved = _solved_count_by_user(match_tasks, match.player1_id)
    p2_solved = _solved_count_by_user(match_tasks, match.player2_id)

    winner_id = None
    if p1_solved > p2_solved:
        winner_id = match.player1_id
    elif p2_solved > p1_solved:
        winner_id = match.player2_id
    else:
        p1_incorrect = _incorrect_count(match.id, match.player1_id)
        p2_incorrect = _incorrect_count(match.id, match.player2_id)
        if p1_incorrect < p2_incorrect:
            winner_id = match.player1_id
        elif p2_incorrect < p1_incorrect:
            winner_id = match.player2_id

    _apply_match_result(match, winner_id)
    db.session.commit()
    return True

def _finalize_match_if_expired(match):
    if not match.is_active:
        return False
    if _match_time_left_seconds(match) > 0:
        return False
    return _finalize_match_by_counts(match)

def _process_attempt(user, match_id, challenge_id, flag):
    if not match_id or not challenge_id or not flag:
        return {'ok': False, 'message': 'Нужны match_id, challenge_id и флаг.'}, 400

    match = Match.query.get(match_id)
    if not match:
        return {'ok': False, 'message': 'Матч не найден.'}, 404

    if user.id not in [match.player1_id, match.player2_id]:
        return {'ok': False, 'message': 'Доступ запрещен.'}, 403

    if _finalize_match_if_expired(match):
        return {
            'ok': False,
            'message': 'Время вышло.',
            'match_over': True,
            'winner_id': match.winner_id
        }, 200

    if not match.is_active:
        return {
            'ok': False,
            'message': 'Матч уже завершен.',
            'match_over': True,
            'winner_id': match.winner_id
        }, 200

    match_task = MatchTask.query.filter_by(match_id=match.id, challenge_id=challenge_id).first()
    if not match_task and match.challenge_id != challenge_id:
        return {'ok': False, 'message': 'Задача не относится к матчу.'}, 400

    if match_task and match_task.solved_by_user_id:
        return {'ok': False, 'message': 'Задача уже решена.'}, 200

    user_flag_record = UserFlag.query.filter_by(user_id=user.id, challenge_id=challenge_id).first()
    if not user_flag_record:
        flag_value = TaskGenerator.generate_flag()
        user_flag_record = UserFlag(user_id=user.id, challenge_id=challenge_id, flag=flag_value)
        db.session.add(user_flag_record)
        db.session.commit()

    is_correct = flag == user_flag_record.flag
    attempt = MatchAttempt(
        match_id=match.id,
        user_id=user.id,
        challenge_id=challenge_id,
        is_correct=is_correct
    )
    db.session.add(attempt)

    if is_correct:
        if match_task:
            match_task.solved_by_user_id = user.id
            match_task.solved_at = datetime.utcnow()
            match_tasks = _get_match_tasks(match)
            solved_by_user = _solved_count_by_user(match_tasks, user.id)
            if solved_by_user >= len(match_tasks):
                _apply_match_result(match, user.id)
            elif _are_all_tasks_solved(match_tasks):
                _finalize_match_by_counts(match)
        else:
            _apply_match_result(match, user.id)

    db.session.commit()

    state = _build_match_state(match)
    payload = {
        'ok': True,
        'user_id': user.id,
        'username': user.username,
        'challenge_id': challenge_id,
        'is_correct': is_correct,
        'match_over': not match.is_active,
        'winner_id': match.winner_id,
        'time_left': _match_time_left_seconds(match),
        'stats': state['stats'],
        'task_states': state['task_states']
    }
    return payload, 200

# --- ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ ---
@app.before_request
def init_app_data():
    # Проверяем, была ли инициализация, чтобы не нагружать каждый запрос
    if not hasattr(app, 'app_initialized'):
        with app.app_context():
            # Проверка на пересоздание БД (удалить все и создать заново)
            recreate_flag = os.getenv('RECREATE_DB', 'false').lower() in ('1', 'true', 'yes')
            if recreate_flag:
                try:
                    db.drop_all()
                except Exception:
                    pass
            # 1. Создаем таблицы
            db.create_all()
            
            # 2. Создаем базовые категории
            cats = ['Cryptography', 'Web', 'Logic', 'Reverse', 'Forensics']
            for c_name in cats:
                if not Category.query.filter_by(name=c_name).first():
                    db.session.add(Category(name=c_name))
            
            # 3. Создаем/Обновляем Админа (данные из .env)
            admin_user = os.getenv('ADMIN_USER', 'admin')
            admin_pass = os.getenv('ADMIN_PASS', 'admin123')
            
            admin = User.query.filter_by(username=admin_user).first()
            if not admin:
                # Создаем нового
                admin = User(username=admin_user, is_admin=True)
                admin.set_password(admin_pass)
                db.session.add(admin)
                print(f"--- ADMIN CREATED: {admin_user} ---")
            else:
                # Обновляем права существующего (на случай, если слетели)
                admin.is_admin = True
                # admin.set_password(admin_pass) # Можно раскомментировать, если хотите сбрасывать пароль при рестарте
            
            db.session.commit()

            # (Old template-based auto-generation removed — use manual creation and autotask-based generation)
            app.app_initialized = True

# ==========================================
# SOCKET.IO EVENTS
# ==========================================

@socketio.on('join_match')
def socket_join_match(data):
    if not current_user.is_authenticated:
        emit('join_error', {'message': 'auth'})
        return
    match_id = data.get('match_id')
    if not match_id:
        emit('join_error', {'message': 'match_id_missing'})
        return
    match = Match.query.get(match_id)
    if not match or current_user.id not in [match.player1_id, match.player2_id]:
        emit('join_error', {'message': 'forbidden'})
        return

    _finalize_match_if_expired(match)

    room = _match_room(match_id)
    join_room(room)

    presence = match_presence.setdefault(match_id, {})
    user_sids = presence.setdefault(current_user.id, set())
    first_connection = len(user_sids) == 0
    user_sids.add(request.sid)

    opponent_id = match.player2_id if match.player1_id == current_user.id else match.player1_id
    opponent_connected = opponent_id in presence and len(presence.get(opponent_id, set())) > 0
    emit('opponent_status', {
        'user_id': opponent_id,
        'status': 'connected' if opponent_connected else 'disconnected'
    })

    state = _build_match_state(match)
    emit('state', {
        'match_id': match.id,
        'is_active': match.is_active,
        'winner_id': match.winner_id,
        'time_left': _match_time_left_seconds(match),
        'task_states': state['task_states'],
        'stats': state['stats']
    })

    if first_connection:
        emit('opponent_status', {
            'user_id': current_user.id,
            'status': 'connected'
        }, room=room, include_self=False)

    emit('joined', {'ok': True})

@socketio.on('leave_match')
def socket_leave_match(data):
    match_id = data.get('match_id')
    if not match_id:
        return
    room = _match_room(match_id)
    leave_room(room)

    presence = match_presence.get(match_id, {})
    user_sids = presence.get(current_user.id)
    if user_sids and request.sid in user_sids:
        user_sids.remove(request.sid)
        if not user_sids:
            presence.pop(current_user.id, None)
            emit('opponent_status', {
                'user_id': current_user.id,
                'status': 'disconnected'
            }, room=room, include_self=False)
            match = Match.query.get(match_id)
            if match and match.is_active:
                _apply_match_no_score(match)
                db.session.commit()
                state = _build_match_state(match)
                socketio.emit('attempt_update', {
                    'match_over': True,
                    'winner_id': None,
                    'time_left': _match_time_left_seconds(match),
                    'stats': state['stats'],
                    'task_states': state['task_states']
                }, room=room)

@socketio.on('disconnect')
def socket_disconnect():
    for match_id, presence in list(match_presence.items()):
        for user_id, sids in list(presence.items()):
            if request.sid in sids:
                sids.remove(request.sid)
                if not sids:
                    presence.pop(user_id, None)
                    emit('opponent_status', {
                        'user_id': user_id,
                        'status': 'disconnected'
                    }, room=_match_room(match_id), include_self=False)
                    match = Match.query.get(match_id)
                    if match and match.is_active:
                        _apply_match_no_score(match)
                        db.session.commit()
                        state = _build_match_state(match)
                        socketio.emit('attempt_update', {
                            'match_over': True,
                            'winner_id': None,
                            'time_left': _match_time_left_seconds(match),
                            'stats': state['stats'],
                            'task_states': state['task_states']
                        }, room=_match_room(match_id))
            if not presence:
                match_presence.pop(match_id, None)

@socketio.on('submit_flag')
def socket_submit_flag(data):
    if not current_user.is_authenticated:
        emit('attempt_result', {'ok': False, 'message': 'auth'})
        return
    match_id = data.get('match_id') if data else None
    challenge_id = data.get('challenge_id') if data else None
    flag = (data.get('flag') or '').strip() if data else ''

    payload, _ = _process_attempt(current_user, match_id, challenge_id, flag)
    emit('attempt_result', payload)
    if payload.get('ok'):
        emit('attempt_update', payload, room=_match_room(match_id), include_self=False)

# ==========================================
# РОУТЫ: АВТОРИЗАЦИЯ И ОБЩЕЕ
# ==========================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Проверка на бан
            if user.is_banned:
                flash('Ваш аккаунт заблокирован администратором.', 'error')
                return render_template('login.html')
                
            login_user(user)
            # Если есть параметр 'next', перенаправляем туда, иначе в профиль
            next_page = request.args.get('next')
            return redirect(next_page or url_for('profile'))
        else:
            flash('Неверный логин или пароль', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'error')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()  # Получаем ID нового пользователя
            
            # Создаем флаги для всех активных задач (чтобы новые пользователи получили текущие задачи)
            all_challenges = Challenge.query.filter_by(is_active=True).all()
            base_image = os.path.join(app.root_path, 'autotask', 'frame.png')
            for challenge in all_challenges:
                # Пропускаем, если уже есть запись (безопасность на случай повторов)
                if UserFlag.query.filter_by(user_id=new_user.id, challenge_id=challenge.id).first():
                    continue

                # Если категория Forensics — создаём стегано-изображение и файл
                cat_name = (challenge.category.name.lower() if challenge.category else '')
                flag_value = TaskGenerator.generate_flag()

                if cat_name == 'forensics':
                    user_dir = os.path.join(app.root_path, 'static', 'uploads', challenge.id, new_user.id)
                    steg = SimpleStegano(image_path=base_image)
                    steg.generate(flag=flag_value, save_path=user_dir)

                    user_file = UserFile(
                        user_id=new_user.id,
                        challenge_id=challenge.id,
                        file_path=os.path.join('static', 'uploads', challenge.id, new_user.id, 'stegano_image.png'),
                        file_name='stegano_image.png'
                    )
                    db.session.add(user_file)

                # Сохраняем флаг
                user_flag = UserFlag(
                    user_id=new_user.id,
                    challenge_id=challenge.id,
                    flag=flag_value
                )
                db.session.add(user_flag)
            
            db.session.commit()
            
            login_user(new_user)
            return redirect(url_for('profile'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# ==========================================
# РОУТЫ: ПРОФИЛЬ И РЕЙТИНГ
# ==========================================

# Универсальный роут: /profile (свой) и /profile/<id> (чужой)
@app.route('/profile', defaults={'user_id': None}, methods=['GET', 'POST'])
@app.route('/profile/<user_id>', methods=['GET', 'POST'])
def profile(user_id):
    # 1. ОПРЕДЕЛЯЕМ ПОЛЬЗОВАТЕЛЯ
    if user_id:
        # Если передан ID в URL - ищем этого пользователя
        user = User.query.get_or_404(user_id)
        is_own_profile = current_user.is_authenticated and current_user.id == user.id
    else:
        # Если ID нет - показываем профиль текущего залогиненного
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        user = current_user
        is_own_profile = True

    # 2. РЕДАКТИРОВАНИЕ (Только текст, только владелец)
    if is_own_profile and request.method == 'POST':
        telegram = request.form.get('telegram')
        bio = request.form.get('bio')

        if telegram is not None:
            current_user.telegram = telegram
        if bio is not None:
            current_user.bio = bio

        try:
            db.session.commit()
            flash('Профиль успешно обновлен!', 'success')
        except:
            db.session.rollback()
            flash('Ошибка базы данных.', 'error')
        
        return redirect(url_for('profile', user_id=user.id))

    # 3. ДАННЫЕ ДЛЯ ГРАФИКА (Chart.js)
    # Собираем историю решений
    solves = Solve.query.filter_by(user_id=user.id).order_by(Solve.solved_at).all()
    
    chart_labels = []
    chart_data = []
    running_score = 0
    
    # Точка старта (дата регистрации)
    if user.created_at:
        chart_labels.append(user.created_at.strftime('%Y-%m-%d'))
        chart_data.append(0)

    for solve in solves:
        # Ищем задачу, чтобы узнать сколько очков она стоила
        challenge = Challenge.query.get(solve.challenge_id)
        if challenge:
            running_score += challenge.points
            # Добавляем точку: дата -> сумма очков
            chart_labels.append(solve.solved_at.strftime('%Y-%m-%d %H:%M'))
            chart_data.append(running_score)

    return render_template('profile.html', 
                           user=user, 
                           is_own_profile=is_own_profile,
                           chart_labels=json.dumps(chart_labels),
                           chart_data=json.dumps(chart_data))

@app.route('/board')
def dashboard():
    # Сортировка: ?sort=points или ?sort=elo
    sort_mode = request.args.get('sort', 'elo')

    query = User.query.filter_by(is_admin=False)

    if sort_mode == 'points':
        # Сортировка по очкам
        users = query.order_by(User.user_points.desc()).all()
    else:
        # Сортировка по ELO (по умолчанию)
        users = query.order_by(User.elo_rating.desc()).all()
    
    return render_template('dashboard.html', users=users, sort_mode=sort_mode)

# ==========================================
# РОУТЫ: ЗАДАЧИ (CHALLENGES)
# ==========================================

@app.route('/challenges')
@login_required
def challenges_list():
    # Загружаем категории и связанные с ними задачи
    # Фильтруем категории, в которых есть хотя бы одна задача (опционально)
    categories = Category.query.all()
    categories_with_tasks = []
    for category in categories:
        tasks = Challenge.query.filter_by(category_id=category.id, is_active=True).all()
        if tasks:
            categories_with_tasks.append({'name': category.name, 'tasks': tasks})

    uncategorized = Challenge.query.filter_by(category_id=None, is_active=True).all()
    if uncategorized:
        categories_with_tasks.append({'name': 'Без категории', 'tasks': uncategorized})
    
    # Чтобы подсветить решенные задачи, нам нужен список ID решенных задач текущим юзером
    solved_challenges_ids = [s.challenge_id for s in current_user.solves]
    # Файлы, прикрепленные к текущему пользователю (по задаче)
    user_files = UserFile.query.filter_by(user_id=current_user.id).all()
    files_map = {}
    for uf in user_files:
        files_map.setdefault(uf.challenge_id, []).append(uf)
    
    return render_template('challenges.html', 
                           categories=categories_with_tasks, 
                           solved_ids=solved_challenges_ids,
                           user_files_map=files_map)

@app.route('/challenges/submit', methods=['POST'])
@login_required
def submit_flag():
    challenge_id = request.form.get('challenge_id')
    flag_input = request.form.get('flag', '').strip()
    
    challenge = Challenge.query.get_or_404(challenge_id)
    
    # 1. Проверяем, не решена ли задача уже
    existing_solve = Solve.query.filter_by(user_id=current_user.id, challenge_id=challenge.id).first()
    if existing_solve:
        flash("Вы уже решили эту задачу!", "error")
        return redirect(url_for('challenges_list'))

    # 2. Получаем индивидуальный флаг пользователя для этой задачи
    user_flag_record = UserFlag.query.filter_by(user_id=current_user.id, challenge_id=challenge.id).first()
    
    # Если флага еще нет, создаем его (на случай, если он не был сгенерирован ранее)
    if not user_flag_record:
        # Генерируем новый флаг
        flag_value = TaskGenerator.generate_flag()
        user_flag_record = UserFlag(user_id=current_user.id, challenge_id=challenge.id, flag=flag_value)
        db.session.add(user_flag_record)
        db.session.commit()
    
    # 3. Проверяем флаг
    if flag_input == user_flag_record.flag:
        # Верно! Создаем запись о решении
        solve = Solve(user_id=current_user.id, challenge_id=challenge.id)
        db.session.add(solve)
        
        # Начисляем баллы
        current_user.user_points += challenge.points
        # Начисляем ELO (упрощенная логика: +10 за Easy, +20 Medium...)
        elo_bonus = 10
        if challenge.difficulty.value == 'Medium': elo_bonus = 20
        if challenge.difficulty.value == 'Hard': elo_bonus = 30
        current_user.elo_rating += elo_bonus
        
        db.session.commit()
        flash(f"Флаг принят! Вы получили {challenge.points} очков.", "success")
    else:
        flash("Неверный флаг.", "error")
        
    return redirect(url_for('challenges_list'))

# ==========================================
# --- АДМИН ПАНЕЛЬ ---
# ==========================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    users_count = User.query.count()
    challenges_count = Challenge.query.count()
    solves_count = Solve.query.count()
    # Передаем категории в шаблон
    categories = Category.query.all()
    # Непубликованные задачи (для админа) - те, которые не активны
    unpublished = Challenge.query.filter_by(is_active=False).order_by(Challenge.id.desc()).all()
    return render_template('admin/dashboard.html', 
                           users_count=users_count, 
                           challenges_count=challenges_count, 
                           solves_count=solves_count,
                           categories=categories,
                           unpublished=unpublished)


# old import_templates endpoint removed


@app.route('/admin/publish/<challenge_id>', methods=['POST'])
@admin_required
def admin_publish_challenge(challenge_id):
    ch = Challenge.query.get_or_404(challenge_id)
    ch.is_active = True
    # Создаём флаги для всех пользователей (если ещё нет)
    users = User.query.filter_by(is_admin=False).all()
    base_image = os.path.join(app.root_path, 'autotask', 'frame.png')
    created = 0
    for user in users:
        if UserFlag.query.filter_by(user_id=user.id, challenge_id=ch.id).first():
            continue
        flag_value = TaskGenerator.generate_flag()
        # Если Forensics — генерируем stegano файл
        cat_name = (ch.category.name.lower() if ch.category else '')
        if cat_name == 'forensics':
            user_dir = os.path.join(app.root_path, 'static', 'uploads', ch.id, user.id)
            steg = SimpleStegano(image_path=base_image)
            steg.generate(flag=flag_value, save_path=user_dir)

            user_file = UserFile(
                user_id=user.id,
                challenge_id=ch.id,
                file_path=os.path.join('static', 'uploads', ch.id, user.id, 'stegano_image.png'),
                file_name='stegano_image.png'
            )
            db.session.add(user_file)

        user_flag = UserFlag(user_id=user.id, challenge_id=ch.id, flag=flag_value)
        db.session.add(user_flag)
        created += 1

    db.session.commit()
    flash(f"Задача '{ch.title}' опубликована. Сгенерировано флагов: {created}", 'success')
    return redirect(url_for('admin_dashboard'))

# 1. АВТО ГЕНЕРАЦИЯ
# old admin auto-generation removed; manual creation and autotask-based generation remain

# 2. РУЧНОЕ ДОБАВЛЕНИЕ (НОВОЕ)
@app.route('/admin/create', methods=['POST'])
@admin_required
def admin_create_challenge():
    title = request.form.get('title')
    description = request.form.get('description')
    flag = request.form.get('flag')  # Это может быть формат или просто текст флага
    points = int(request.form.get('points'))
    difficulty = request.form.get('difficulty')
    category_id = request.form.get('category_id')
    hint = request.form.get('hint')

    new_chall = Challenge(
        title=title,
        description=description,
        points=points,
        difficulty=Difficulty(difficulty),
        category_id=category_id,
        hint=hint,
        author_id=current_user.id
    )
    db.session.add(new_chall)
    db.session.flush()  # Получаем ID новой задачи
    
    # Создаем флаги для каждого пользователя
    all_users = User.query.filter_by(is_admin=False).all()
    
    # Определим категорию по id (если нужно для специальных генераторов)
    cat_obj = Category.query.get(category_id) if category_id else None

    if flag:
        # Если флаг содержит {}, то это шаблон для генерации
        if '{' in flag and '}' in flag:
            # Генерируем разные флаги на основе шаблона
            for user in all_users:
                # Генерируем уникальный флаг
                user_flag_value = TaskGenerator.generate_flag()
                user_flag = UserFlag(
                    user_id=user.id,
                    challenge_id=new_chall.id,
                    flag=user_flag_value
                )
                db.session.add(user_flag)
        else:
            # Это обычный флаг - используем его для всех пользователей
            # Особая обработка для Forensics: создаём стегано-файлы
            if cat_obj and cat_obj.name.lower() == 'forensics':
                base_image = os.path.join(app.root_path, 'autotask', 'frame.png')
                public_dir = os.path.join('static', 'uploads', new_chall.id)
                new_chall.public_files_path = public_dir
                for user in all_users:
                    user_dir = os.path.join(app.root_path, public_dir, user.id)
                    steg = SimpleStegano(image_path=base_image)
                    steg.generate(flag=flag, save_path=user_dir)

                    user_flag = UserFlag(
                        user_id=user.id,
                        challenge_id=new_chall.id,
                        flag=flag
                    )
                    db.session.add(user_flag)

                    user_file = UserFile(
                        user_id=user.id,
                        challenge_id=new_chall.id,
                        file_path=os.path.join(public_dir, user.id, 'stegano_image.png'),
                        file_name='stegano_image.png'
                    )
                    db.session.add(user_file)
            else:
                for user in all_users:
                    user_flag = UserFlag(
                        user_id=user.id,
                        challenge_id=new_chall.id,
                        flag=flag
                    )
                    db.session.add(user_flag)
    else:
        # Флаг не указан - генерируем для каждого пользователя
        for user in all_users:
            user_flag = UserFlag(
                user_id=user.id,
                challenge_id=new_chall.id,
                flag=TaskGenerator.generate_flag()
            )
            db.session.add(user_flag)
    
    db.session.commit()
    flash("Задание успешно создано вручную!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/users')
@admin_required
def admin_users():
    # Получаем всех пользователей для списка
    users = User.query.order_by(User.id).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/run-task', methods=['GET', 'POST'])
@admin_required
def admin_run_task():
    """Страница для запуска тасков из autotask"""
    import importlib.util
    import sys
    
    available_tasks = []
    categories = Category.query.order_by(Category.name).all()
    autotask_path = os.path.join(app.root_path, 'autotask')
    
    # Получаем список доступных генераторов
    try:
        # Получаем доступные классы из examples.py
        spec = importlib.util.spec_from_file_location("autotask.examples", 
                                                       os.path.join(autotask_path, 'examples.py'))
        examples_module = importlib.util.module_from_spec(spec)
        sys.modules['autotask.examples'] = examples_module
        spec.loader.exec_module(examples_module)
        
        # Находим все классы генераторов
        generators = {
            'Challenge': examples_module.Challenge,
            'SimpleStegano': examples_module.SimpleStegano,
        }
    except Exception as e:
        generators = {}
        print(f"Error loading generators: {e}")
    
    if request.method == 'POST':
        generator_type = request.form.get('generator_type')
        raw_category_id = request.form.get('category_id')
        category_id = int(raw_category_id) if raw_category_id else None
        task_data = {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'flag': request.form.get('flag'),
            'category_id': category_id
        }
        
        # Параметры в зависимости от типа
        task_data['image_path'] = request.form.get('image_path', 'frame.png') if generator_type == 'SimpleStegano' else None
        task_data['save_path'] = request.form.get('save_path', os.path.join(app.root_path, 'autotask/images/temp'))
        
        try:
            if generator_type not in generators:
                flash(f"Неизвестный генератор: {generator_type}", "error")
                return redirect(url_for('admin_run_task'))
            
            GeneratorClass = generators[generator_type]
            
            # Создаем экземпляр генератора
            if generator_type == 'SimpleStegano':
                image_path = task_data['image_path']
                if not image_path.startswith('/'):
                    image_path = os.path.join(autotask_path, image_path)
                
                task = GeneratorClass(
                    image_path=image_path,
                    description=task_data['description']
                )
            else:
                task = GeneratorClass(description=task_data['description'])
            
            # Запускаем генерацию
            save_path = task_data['save_path']
            os.makedirs(save_path, exist_ok=True)
            
            if generator_type == 'SimpleStegano':
                task.generate(flag=task_data['flag'], save_path=save_path)
            else:
                task.generate(flag=task_data['flag'])
            
            # Получаем информацию о задаче
            info = task.get_info()
            
            # СОХРАНЯЕМ ЗАДАЧУ В БД
            new_challenge = Challenge(
                title=task_data['title'],
                description=info.get('description', task_data['description']),
                hint=info.get('hint', ''),
                points=100,
                difficulty=Difficulty.EASY,
                author_id=current_user.id,
                category_id=task_data['category_id'] or None
            )
            db.session.add(new_challenge)
            db.session.flush()
            
            # Создаем флаги для всех пользователей
            all_users = User.query.filter_by(is_admin=False).all()
            
            if generator_type == 'SimpleStegano':
                # Для стеганографии создаем файлы
                public_dir = os.path.join('static', 'uploads', new_challenge.id)
                new_challenge.public_files_path = public_dir
                
                for user in all_users:
                    # Генерируем уникальный флаг для каждого
                    user_flag_value = TaskGenerator.generate_flag()
                    user_dir = os.path.join(app.root_path, public_dir, user.id)
                    os.makedirs(user_dir, exist_ok=True)
                    
                    # Создаем файл с флагом для пользователя
                    image_path = task_data['image_path']
                    if not image_path.startswith('/'):
                        image_path = os.path.join(autotask_path, image_path)
                    
                    user_steg = GeneratorClass(image_path=image_path)
                    user_steg.generate(flag=user_flag_value, save_path=user_dir)
                    
                    # Сохраняем флаг
                    user_flag = UserFlag(
                        user_id=user.id,
                        challenge_id=new_challenge.id,
                        flag=user_flag_value
                    )
                    db.session.add(user_flag)
                    
                    # Сохраняем файл
                    user_file = UserFile(
                        user_id=user.id,
                        challenge_id=new_challenge.id,
                        file_path=os.path.join(public_dir, user.id, 'stegano_image.png'),
                        file_name='stegano_image.png'
                    )
                    db.session.add(user_file)
            else:
                # Для простого Challenge - генерируем уникальные флаги
                for user in all_users:
                    user_flag_value = TaskGenerator.generate_flag()
                    user_flag = UserFlag(
                        user_id=user.id,
                        challenge_id=new_challenge.id,
                        flag=user_flag_value
                    )
                    db.session.add(user_flag)
            
            db.session.commit()
            
            flash(f"✓ Таск '{task_data['title']}' успешно создан и доступен для всех пользователей!", "success")
            
            return render_template('admin/task_result.html', 
                                   generator_type=generator_type,
                                   task_data=task_data,
                                   task_info=info,
                                   challenge_id=new_challenge.id,
                                   users_count=len(all_users))
            
        except Exception as e:
            flash(f"Ошибка при выполнении таска: {str(e)}", "error")
            return redirect(url_for('admin_run_task'))
    
    return render_template('admin/run_task.html', generators=generators.keys(), categories=categories)


@app.route('/admin/api/create-task', methods=['POST'])
@admin_required
def admin_api_create_task():
    """
    API endpoint для создания задач через autotask генераторы.
    Поддерживает: Simple Challenge, SimpleStegano и другие.
    """
    try:
        data = request.get_json()
        
        # Базовые параметры
        title = data.get('title')
        description = data.get('description')
        difficulty = data.get('difficulty', 'Easy')
        category_id = data.get('category_id')
        points = int(data.get('points', 100))
        hint = data.get('hint', '')
        
        # Параметры генератора
        generator_type = data.get('generator_type', 'simple')  # simple, stegano
        generator_params = data.get('generator_params', {})
        
        if not title or not description:
            return {'error': 'Название и описание обязательны'}, 400
        
        # Создаем новую задачу
        new_chall = Challenge(
            title=title,
            description=description,
            points=points,
            difficulty=Difficulty(difficulty),
            category_id=category_id,
            hint=hint,
            author_id=current_user.id
        )
        db.session.add(new_chall)
        db.session.flush()  # Получаем ID
        
        # Получаем категорию
        cat_obj = Category.query.get(category_id) if category_id else None
        all_users = User.query.filter_by(is_admin=False).all()
        
        # Генерируем задачи в зависимости от типа
        created_count = 0
        
        if generator_type == 'simple':
            # Простой генератор - базовый флаг с шаблоном
            for user in all_users:
                from autotask.examples import Challenge as SimpleChallenge
                simple = SimpleChallenge(description=description)
                flag = TaskGenerator.generate_flag()
                simple.generate(flag=flag)
                
                user_flag = UserFlag(
                    user_id=user.id,
                    challenge_id=new_chall.id,
                    flag=flag
                )
                db.session.add(user_flag)
                created_count += 1
        
        elif generator_type == 'stegano':
            # Стеганография - скрытие флага в изображение
            image_path = generator_params.get('image_path', 'autotask/frame.png')
            full_image_path = os.path.join(app.root_path, image_path)
            
            if not os.path.exists(full_image_path):
                return {'error': f'Изображение не найдено: {image_path}'}, 400
            
            public_dir = os.path.join('static', 'uploads', new_chall.id)
            new_chall.public_files_path = public_dir
            
            for user in all_users:
                from autotask.examples import SimpleStegano
                flag = TaskGenerator.generate_flag()
                user_dir = os.path.join(app.root_path, public_dir, user.id)
                
                steg = SimpleStegano(image_path=full_image_path, description=description)
                steg.generate(flag=flag, save_path=user_dir)
                
                user_flag = UserFlag(
                    user_id=user.id,
                    challenge_id=new_chall.id,
                    flag=flag
                )
                db.session.add(user_flag)
                
                user_file = UserFile(
                    user_id=user.id,
                    challenge_id=new_chall.id,
                    file_path=os.path.join(public_dir, user.id, 'stegano_image.png'),
                    file_name='stegano_image.png'
                )
                db.session.add(user_file)
                created_count += 1
        
        elif generator_type == 'custom':
            # Пользовательский генератор - используем переданный флаг
            flag = data.get('flag')
            if not flag:
                return {'error': 'Флаг обязателен для custom генератора'}, 400
            
            for user in all_users:
                user_flag = UserFlag(
                    user_id=user.id,
                    challenge_id=new_chall.id,
                    flag=flag
                )
                db.session.add(user_flag)
                created_count += 1
        
        db.session.commit()
        
        return {
            'success': True,
            'message': f'Задача создана. Флаги сгенерированы для {created_count} пользователей.',
            'challenge_id': new_chall.id
        }, 201
    
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500


@app.route('/admin/users/<user_id>/<action>')
@admin_required
def admin_user_action(user_id, action):
    user = User.query.get_or_404(user_id)
    
    # Защита: нельзя забанить или удалить другого админа
    if user.is_admin:
        flash("Невозможно применить санкции к администратору.", "error")
        return redirect(url_for('admin_users'))

    if action == 'ban':
        user.is_banned = True
        flash(f"Пользователь {user.username} заблокирован.", "success")
    elif action == 'unban':
        user.is_banned = False
        flash(f"Пользователь {user.username} разблокирован.", "success")
    elif action == 'delete':
        # Сначала удаляем решения пользователя, чтобы не было ошибки внешнего ключа
        Solve.query.filter_by(user_id=user.id).delete()
        # Удаляем самого пользователя
        db.session.delete(user)
        flash(f"Пользователь {user.username} удален.", "success")
    
    db.session.commit()
    return redirect(url_for('admin_users'))


# ==========================================
# PVP СИСТЕМА (1 vs 1)
# ==========================================

@app.route('/pvp')
@login_required
def pvp_lobby():
    # Проверяем, не в игре ли уже пользователь
    active_match = Match.query.filter(
        ((Match.player1_id == current_user.id) | (Match.player2_id == current_user.id)) & 
        (Match.is_active == True)
    ).first()
    
    if active_match:
        return redirect(url_for('pvp_arena', match_id=active_match.id))

    # Проверяем, в очереди ли он
    in_queue = MatchmakingQueue.query.get(current_user.id)
    
    return render_template('pvp.html', in_queue=bool(in_queue))

@app.route('/pvp/join', methods=['POST'])
@login_required
def pvp_join():
    # 1. Проверяем, есть ли кто-то в очереди
    # Ищем соперника с рейтингом +/- 300 (упрощенно - любого, кроме себя)
    opponent_entry = MatchmakingQueue.query.filter(MatchmakingQueue.user_id != current_user.id).first()
    
    if opponent_entry:
        # СОПЕРНИК НАЙДЕН! СОЗДАЕМ МАТЧ
        opponent = User.query.get(opponent_entry.user_id)
        
        # Выбираем случайные 3 задачи для дуэли
        all_challenges = Challenge.query.filter_by(is_active=True).all()
        if len(all_challenges) < PVP_TASKS_COUNT:
            flash("Нет доступных задач для PvP.", "error")
            return redirect(url_for('pvp_lobby'))
        duel_tasks = random.sample(all_challenges, PVP_TASKS_COUNT)
        
        # Создаем матч
        new_match = Match(
            player1_id=current_user.id,
            player2_id=opponent.id,
            challenge_id=duel_tasks[0].id
        )
        db.session.add(new_match)
        db.session.flush()

        for idx, task in enumerate(duel_tasks):
            db.session.add(MatchTask(
                match_id=new_match.id,
                challenge_id=task.id,
                order_index=idx
            ))
        
        # Удаляем соперника из очереди
        db.session.delete(opponent_entry)
        db.session.commit()
        
        return redirect(url_for('pvp_arena', match_id=new_match.id))
        
    else:
        # НИКОГО НЕТ, ВСТАЕМ В ОЧЕРЕДЬ
        if not MatchmakingQueue.query.get(current_user.id):
            queue_entry = MatchmakingQueue(
                user_id=current_user.id, 
                current_elo=current_user.elo_rating
            )
            db.session.add(queue_entry)
            db.session.commit()
            
    return redirect(url_for('pvp_lobby'))

@app.route('/pvp/leave', methods=['POST'])
@login_required
def pvp_leave():
    entry = MatchmakingQueue.query.get(current_user.id)
    if entry:
        db.session.delete(entry)
        db.session.commit()
    return redirect(url_for('pvp_lobby'))

@app.route('/pvp/status')
@login_required
def pvp_status():
    """AJAX endpoint для опроса: нашлась ли игра?"""
    # Проверяем, начался ли матч с участием юзера
    active_match = Match.query.filter(
        ((Match.player1_id == current_user.id) | (Match.player2_id == current_user.id)) & 
        (Match.is_active == True)
    ).first()
    
    if active_match:
        return {'status': 'match_found', 'url': url_for('pvp_arena', match_id=active_match.id)}
    
    return {'status': 'waiting'}

@app.route('/pvp/arena/<int:match_id>')
@login_required
def pvp_arena(match_id):
    match = Match.query.get_or_404(match_id)
    
    # Проверка доступа (только участники)
    if current_user.id not in [match.player1_id, match.player2_id]:
        abort(403)
        
    # Если матч уже завершен
    _finalize_match_if_expired(match)
    if not match.is_active:
        match_tasks = _get_match_tasks(match)
        total_points = sum(mt.challenge.points for mt in match_tasks if mt.challenge)
        return render_template('pvp_result.html', match=match, total_points=total_points)
    
    opponent_id = match.player2_id if match.player1_id == current_user.id else match.player1_id
    opponent = User.query.get(opponent_id)
    
    match_tasks = _get_match_tasks(match)
    state = _build_match_state(match)

    opponent_id = opponent.id
    my_stats = state['stats'].get(current_user.id, {'correct': 0, 'incorrect': 0})
    opponent_stats = state['stats'].get(opponent_id, {'correct': 0, 'incorrect': 0})

    return render_template(
        'pvp_arena.html',
        match=match,
        opponent=opponent,
        tasks=match_tasks,
        task_states=state['task_states'],
        my_stats=my_stats,
        opponent_stats=opponent_stats,
        time_left=_match_time_left_seconds(match),
        match_duration=PVP_MATCH_DURATION_SECONDS
    )

@app.route('/pvp/submit_match', methods=['POST'])
@login_required
def pvp_submit():
    data = request.get_json(silent=True)
    if not data:
        data = request.form
    if not data:
        try:
            raw = request.data.decode('utf-8') if request.data else ''
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}

    match_id = data.get('match_id')
    challenge_id = data.get('challenge_id')
    flag = (data.get('flag') or '').strip()

    payload, status = _process_attempt(current_user, match_id, challenge_id, flag)
    if payload.get('ok'):
        socketio.emit('attempt_update', payload, room=_match_room(match_id), include_self=False)
    return payload, status

@app.route('/pvp/finish/<int:match_id>', methods=['POST'])
@login_required
def pvp_finish(match_id):
    match = Match.query.get_or_404(match_id)
    if current_user.id not in [match.player1_id, match.player2_id]:
        return {'ok': False, 'message': 'Доступ запрещен.'}, 403

    ended = _finalize_match_if_expired(match)
    state = _build_match_state(match)
    payload = {
        'ok': True,
        'match_over': not match.is_active,
        'winner_id': match.winner_id,
        'time_left': _match_time_left_seconds(match),
        'stats': state['stats'],
        'task_states': state['task_states']
    }
    if ended:
        socketio.emit('attempt_update', payload, room=_match_room(match.id))
    return payload, 200

if __name__ == '__main__':
    # Запуск на всех интерфейсах (0.0.0.0) для Docker
    socketio.run(app, debug=True, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)
