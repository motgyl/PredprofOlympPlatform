import dotenv

class Config:
    SECRET_KEY = dotenv.get_key('.env', 'SECRET_KEY')