import json
import random
import string
import base64
import codecs
import os
from config import Config

class TaskGenerator:
    """
    Генератор задач.
    Читает шаблоны из JSON и наполняет их случайными данными.
    """

    TEMPLATES = {}
    
    @staticmethod
    def load_templates():
        """Загружает шаблоны из challenges_templates.json"""
        try:
            # Ищем файл в той же папке, где лежит этот скрипт
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, 'challenges_templates.json')
            
            with open(path, 'r', encoding='utf-8') as f:
                TaskGenerator.TEMPLATES = json.load(f)
                print(f"--- [GEN] Templates loaded from {path} ---")
        except FileNotFoundError:
            print("--- [ERROR] challenges_templates.json not found! ---")
            TaskGenerator.TEMPLATES = {}
        except Exception as e:
            print(f"--- [ERROR] Loading templates: {e} ---")
            TaskGenerator.TEMPLATES = {}

    @staticmethod
    def generate_flag():
        """
        Генерирует случайный флаг в формате из конфига.
        Пример: bobr{a1B2c3D4e5}
        """
        # Генерируем 12 случайных символов (буквы + цифры)
        random_content = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        # Собираем флаг, используя настройки из Config
        prefix = getattr(Config, 'FLAG_PREFIX', 'ctf{')
        suffix = getattr(Config, 'FLAG_SUFFIX', '}')
        
        return f"{prefix}{random_content}{suffix}"

    @staticmethod
    def encode_string(text, method, key=None):
        """
        Логика шифрования для категории Cryptography
        """
        try:
            if method == 'base64':
                return base64.b64encode(text.encode()).decode()
            
            elif method == 'hex':
                return text.encode().hex()
            
            elif method == 'rot13':
                return codecs.encode(text, 'rot_13')
            
            elif method == 'reverse_b64':
                # Переворачиваем строку, потом в Base64
                return base64.b64encode(text[::-1].encode()).decode()
            
            elif method == 'base32':
                return base64.b32encode(text.encode()).decode()
            
            elif method == 'binary':
                # Перевод в 010101...
                return ' '.join(format(ord(x), '08b') for x in text)
            
            elif method == 'hex_b64':
                # Сначала в Hex, потом результат в Base64
                hex_data = text.encode().hex()
                return base64.b64encode(hex_data.encode()).decode()
            
            elif method == 'xor_byte':
                # XOR с случайным однобайтовым ключом
                k = random.randint(1, 255)
                return bytes([ord(c) ^ k for c in text]).hex()
            
            elif method == 'vigenere':
                # Шифр Виженера (только для латиницы)
                if not key: key = "BOBR"
                key_idx = 0
                result = ""
                for char in text:
                    if char.isalpha(): # Шифруем только буквы
                        shift = ord(key[key_idx % len(key)].upper()) - 65
                        if char.isupper():
                            result += chr((ord(char) - 65 + shift) % 26 + 65)
                        else:
                            result += chr((ord(char) - 97 + shift) % 26 + 97)
                        key_idx += 1
                    else:
                        result += char # Символы типа { } оставляем как есть
                return result
                
        except Exception as e:
            print(f"Encoding error ({method}): {e}")
            return text
        
        return text

    @staticmethod
    def generate_task(category, difficulty):
        """
        Создает словарь с данными задачи.
        """
        # 1. Проверяем шаблоны
        if not TaskGenerator.TEMPLATES:
            TaskGenerator.load_templates()

        # 2. Ищем подходящие шаблоны
        cat_data = TaskGenerator.TEMPLATES.get(category, {})
        templates_list = cat_data.get(difficulty, [])

        # Фолбэк, если шаблонов нет или категория не найдена
        if not templates_list:
            return {
                "title": f"Random {category}",
                "description": f"Автоматическая задача ({difficulty}). Шаблон не найден.",
                "flag": TaskGenerator.generate_flag(),
                "hint": "Попробуйте сгенерировать другую категорию.",
                "points": 100
            }

        # 3. Выбираем случайный шаблон
        template = random.choice(templates_list)
        
        # 4. Определяем очки
        points_map = {'Easy': 100, 'Medium': 300, 'Hard': 500}
        points = points_map.get(difficulty, 100)

        # 5. Логика формирования флага
        
        # Для Cryptography всегда: сначала генерируем флаг, потом кодируем
        if category == 'Cryptography':
            final_flag = TaskGenerator.generate_flag()
            method = template.get('encode_method', 'base64')
            key = template.get('key', None)
            encoded_str = TaskGenerator.encode_string(final_flag, method, key)
            try:
                final_desc = template['desc_template'].format(encoded_flag=encoded_str)
            except KeyError:
                final_desc = template['desc_template'] + f"<br><br>Data: <code>{encoded_str}</code>"
        else:
            # СТАТИЧЕСКИЙ флаг (Linux, Network, Forensics)
            # В JSON это поле "static_flag"
            if 'static_flag' in template:
                final_flag = template['static_flag']
                final_desc = template['desc_template']
            else:
                # Фолбэк: на всякий случай делаем динамический флаг
                final_flag = TaskGenerator.generate_flag()
                method = template.get('encode_method', 'base64')
                key = template.get('key', None)
                encoded_str = TaskGenerator.encode_string(final_flag, method, key)
                try:
                    final_desc = template['desc_template'].format(encoded_flag=encoded_str)
                except KeyError:
                    final_desc = template['desc_template'] + f"<br><br>Data: <code>{encoded_str}</code>"

        # 6. Возвращаем готовый объект
        return {
            "title": template['title'],
            "description": final_desc,
            "flag": final_flag,
            "hint": "Используйте CyberChef или документацию.",
            "points": points
        }

# Инициализация при первом импорте
TaskGenerator.load_templates()
