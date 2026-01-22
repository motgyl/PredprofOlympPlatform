import os
import json
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
import random
from datetime import datetime

# Импортируем модели и настройки
from models import db, User, Category, Challenge, Solve, Difficulty
from config import Config
from generators import TaskGenerator 
from models import Match, MatchmakingQueue
from utils import calculate_elo


app = Flask(__name__)
app.config.from_object(Config)

# Инициализация расширений
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Пожалуйста, войдите в систему."
login_manager.login_message_category = "error"

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

# --- ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ ---
@app.before_request
def init_app_data():
    # Проверяем, была ли инициализация, чтобы не нагружать каждый запрос
    if not hasattr(app, 'app_initialized'):
        with app.app_context():
            # 1. Создаем таблицы, если их нет
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
            app.app_initialized = True

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
    
    # Чтобы подсветить решенные задачи, нам нужен список ID решенных задач текущим юзером
    solved_challenges_ids = [s.challenge_id for s in current_user.solves]
    
    return render_template('challenges.html', 
                           categories=categories, 
                           solved_ids=solved_challenges_ids)

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

    # 2. Проверяем флаг
    if flag_input == challenge.flag:
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
    return render_template('admin/dashboard.html', 
                           users_count=users_count, 
                           challenges_count=challenges_count, 
                           solves_count=solves_count,
                           categories=categories)

# 1. АВТО ГЕНЕРАЦИЯ
@app.route('/admin/generate', methods=['POST'])
@admin_required
def admin_generate():
    count = int(request.form.get('count', 1))
    category_name = request.form.get('category')
    difficulty = request.form.get('difficulty')
    
    category = Category.query.filter_by(name=category_name).first()
    if not category:
        flash(f"Категория {category_name} не найдена (нужно создать в БД)", "error")
        return redirect(url_for('admin_dashboard'))

    gen_count = 0
    for _ in range(count):
        # Используем новый генератор
        task_data = TaskGenerator.generate_task(category_name, difficulty)
        
        new_chall = Challenge(
            title=task_data['title'],
            description=task_data['description'],
            flag=task_data['flag'],
            hint=task_data['hint'],
            points=task_data['points'],
            difficulty=Difficulty(difficulty),
            category_id=category.id,
            author_id=current_user.id
        )
        db.session.add(new_chall)
        gen_count += 1

    db.session.commit()
    flash(f"Сгенерировано {gen_count} задач ({category_name})", "success")
    return redirect(url_for('admin_dashboard'))

# 2. РУЧНОЕ ДОБАВЛЕНИЕ (НОВОЕ)
@app.route('/admin/create', methods=['POST'])
@admin_required
def admin_create_challenge():
    title = request.form.get('title')
    description = request.form.get('description')
    flag = request.form.get('flag')
    points = int(request.form.get('points'))
    difficulty = request.form.get('difficulty')
    category_id = request.form.get('category_id')
    hint = request.form.get('hint')

    new_chall = Challenge(
        title=title,
        description=description,
        flag=flag,
        points=points,
        difficulty=Difficulty(difficulty),
        category_id=category_id,
        hint=hint,
        author_id=current_user.id
    )
    db.session.add(new_chall)
    db.session.commit()
    flash("Задание успешно создано вручную!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/users')
@admin_required
def admin_users():
    # Получаем всех пользователей для списка
    users = User.query.order_by(User.id).all()
    return render_template('admin/users.html', users=users)

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
        
        # Выбираем случайную задачу для дуэли
        # (Желательно исключить задачи, которые они оба уже решили, но для старта возьмем любую случайную)
        all_challenges = Challenge.query.filter_by(difficulty=Difficulty.EASY).all() # Для начала Easy
        if not all_challenges:
            flash("Нет доступных задач для PvP.", "error")
            return redirect(url_for('pvp_lobby'))
            
        duel_task = random.choice(all_challenges)
        
        # Создаем матч
        new_match = Match(
            player1_id=current_user.id,
            player2_id=opponent.id,
            challenge_id=duel_task.id
        )
        db.session.add(new_match)
        
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
    if not match.is_active:
        return render_template('pvp_result.html', match=match)
    
    opponent_id = match.player2_id if match.player1_id == current_user.id else match.player1_id
    opponent = User.query.get(opponent_id)
    
    return render_template('pvp_arena.html', match=match, opponent=opponent, task=match.challenge)

@app.route('/pvp/submit_match', methods=['POST'])
@login_required
def pvp_submit():
    match_id = request.form.get('match_id')
    flag = request.form.get('flag')
    
    match = Match.query.get_or_404(match_id)
    
    if not match.is_active:
        flash("Матч уже завершен!", "error")
        return redirect(url_for('pvp_arena', match_id=match.id))
        
    if flag == match.challenge.flag:
        # ПОБЕДА!
        match.is_active = False
        match.winner_id = current_user.id
        match.end_time = datetime.utcnow()
        
        # Расчет ELO
        loser_id = match.player2_id if match.player1_id == current_user.id else match.player1_id
        loser = User.query.get(loser_id)
        
        new_winner_elo, new_loser_elo = calculate_elo(current_user.elo_rating, loser.elo_rating)
        
        # Обновляем статы
        current_user.elo_rating = new_winner_elo
        current_user.user_points += (match.challenge.points + 50) # Бонус за победу
        
        loser.elo_rating = new_loser_elo
        # Проигравшему утешительные баллы (опционально)
        
        db.session.commit()
        return redirect(url_for('pvp_arena', match_id=match.id))
    else:
        flash("Неверный флаг!", "error")
        return redirect(url_for('pvp_arena', match_id=match.id))

if __name__ == '__main__':
    # Запуск на всех интерфейсах (0.0.0.0) для Docker
    app.run(debug=True, host='0.0.0.0', port=5001)