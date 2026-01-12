import dotenv

class Config:
    SECRET_KEY = dotenv.get_key('.env', 'SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = dotenv.get_key('.env', 'DATABASE_URL') or 'postgresql://username:password@localhost/dbname'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = dotenv.get_key('.env', 'UPLOAD_FOLDER') or './static/uploads'