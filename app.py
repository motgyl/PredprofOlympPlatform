from flask import Flask, render_template, session, url_for, redirect
from config import Config

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY


class GuestUser:
    is_authenticated = False
    username = "Guest"


@app.route('/')
def home():
    if 'username' not in session:
        session['username'] = GuestUser().username
        session['is_login'] = GuestUser().is_authenticated

    return render_template('index.html', current_user=session)

@app.route('/login')
def login():
    return render_template('login.html', current_user=session)


@app.route('/logout')
def logout():
    if session["is_login"]:
        session["is_login"] = False
    return render_template("index.html", current_user=session)


@app.route('/register')
def register():
    return render_template('register.html', current_user=session)


@app.route('/knowledge_base')
def knowledge_base():
    return render_template('knowledge.html', current_user=session)


@app.route('/profile')
def profile():
    return render_template('profile.html', current_user=session)

@app.route('/board')
def dashboard():
    return render_template('dashboard.html', current_user=session)


@app.route('/pvp')
def pvp():
    return render_template('pvp.html', current_user=session)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)