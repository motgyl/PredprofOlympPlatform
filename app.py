from flask import Flask, render_template, redirect, url_for, flash, request
from models import db, User, Category, Challenge, Solve, MatchmakingQueue
from config import Config
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from file_check import allowed_file
import os

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

@app.before_request
def create_tables():
    if not hasattr(app, 'tables_created'):
        with app.app_context():
            db.create_all()
            app.tables_created = True

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
            login_user(user)
            return redirect(url_for('profile'))
        else:
            flash('Неверный логин или пароль', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Имя пользователя уже занято', 'error')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('profile'))

    return render_template('register.html')

@app.route('/knowledge_base')
def knowledge_base():
    return render_template('knowledge.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        telegram = request.form.get('telegram')
        bio = request.form.get('bio')
        
        current_user.telegram = telegram
        current_user.bio = bio

        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{current_user.id}_{filename}"
                
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(save_path)
                
                current_user.avatar_url = f"/static/uploads/{unique_filename}"

        try:
            db.session.commit()
            flash('Профиль успешно обновлен!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при сохранении.', 'error')
            
        return redirect(url_for('profile'))

    return render_template('profile.html', user=current_user)

@app.route('/board')
def dashboard():
    sort_mode = request.args.get('sort', 'elo')

    if sort_mode == 'points':
        users = User.query.order_by(User.user_points.desc()).all()
    elif sort_mode == 'elo':
        users = User.query.order_by(User.elo_rating.desc()).all()
    else:
        flash('Неверный режим сортировки', 'error')
        return redirect(url_for('home'))
    
    return render_template('dashboard.html', users=users, sort_mode=sort_mode)

@app.route('/pvp')
def pvp():
    return render_template('pvp.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)