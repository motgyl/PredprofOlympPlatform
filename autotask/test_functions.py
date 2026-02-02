# """
# CTF - Система функций для преобразования флагов
# Функции берут flag как строку и возвращают преобразованный результат
# """
# from typing import Callable, Dict, List
# import random
# import string


# # ============================================================================
# # ФУНКЦИИ ШИФРОВАНИЯ И ПРЕОБРАЗОВАНИЯ ФЛАГОВ
# # ============================================================================

# def rot13(flag: str) -> str:
#     """
#     ROT13 шифр - заменяет каждую букву на букву на 13 позиций дальше
#     flag: flag{test} -> synt{grfg}
#     """
#     result = []
#     for char in flag:
#         if char.isalpha():
#             if char.isupper():
#                 result.append(chr((ord(char) - ord('A') + 13) % 26 + ord('A')))
#             else:
#                 result.append(chr((ord(char) - ord('a') + 13) % 26 + ord('a')))
#         else:
#             result.append(char)
#     return ''.join(result)


# def caesar(flag: str, shift: int = 3) -> str:
#     """
#     Caesar шифр - сдвиг на N позиций (по умолчанию 3)
#     flag: flag{test} -> iodj{whvw}
#     """
#     result = []
#     for char in flag:
#         if char.isalpha():
#             if char.isupper():
#                 result.append(chr((ord(char) - ord('A') + shift) % 26 + ord('A')))
#             else:
#                 result.append(chr((ord(char) - ord('a') + shift) % 26 + ord('a')))
#         else:
#             result.append(char)
#     return ''.join(result)


# def base64_encode(flag: str) -> str:
#     """
#     Base64 кодирование
#     flag: flag{test} -> ZmxhZ3t0ZXN0fQ==
#     """
#     import base64
#     return base64.b64encode(flag.encode()).decode()


# def base64_decode(flag: str) -> str:
#     """
#     Base64 декодирование
#     flag: ZmxhZ3t0ZXN0fQ== -> flag{test}
#     """
#     import base64
#     return base64.b64decode(flag.encode()).decode()


# def reverse_string(flag: str) -> str:
#     """
#     Разворот строки
#     flag: flag{test} -> }tset{galf
#     """
#     return flag[::-1]


# def hex_encode(flag: str) -> str:
#     """
#     Hex кодирование
#     flag: flag{test} -> 666c61677b74657374 7d
#     """
#     return flag.encode().hex()


# def hex_decode(flag_hex: str) -> str:
#     """
#     Hex декодирование
#     flag_hex: 666c61677b74657374 7d -> flag{test}
#     """
#     return bytes.fromhex(flag_hex.replace(' ', '')).decode()


# def ascii_shift(flag: str, shift: int = 1) -> str:
#     """
#     Сдвиг ASCII кодов
#     flag: flag{test} -> hmbh)uftu
#     """
#     result = []
#     for char in flag:
#         result.append(chr(ord(char) + shift))
#     return ''.join(result)


# def atbash(flag: str) -> str:
#     """
#     Атбаш шифр - зеркальная замена (a<->z, b<->y и т.д.)
#     flag: flag{test} -> uozi{gvhg}
#     """
#     result = []
#     for char in flag:
#         if char.isalpha():
#             if char.isupper():
#                 result.append(chr(ord('Z') - (ord(char) - ord('A'))))
#             else:
#                 result.append(chr(ord('z') - (ord(char) - ord('a'))))
#         else:
#             result.append(char)
#     return ''.join(result)


# def vigenere_encode(flag: str, key: str = "KEY") -> str:
#     """
#     Виженер шифр
#     flag: flag{test} -> pyhj{bsdt}
#     """
#     key = key.lower()
#     result = []
#     key_index = 0
    
#     for char in flag:
#         if char.isalpha():
#             shift = ord(key[key_index % len(key)]) - ord('a')
#             if char.isupper():
#                 result.append(chr((ord(char) - ord('A') + shift) % 26 + ord('A')))
#             else:
#                 result.append(chr((ord(char) - ord('a') + shift) % 26 + ord('a')))
#             key_index += 1
#         else:
#             result.append(char)
    
#     return ''.join(result)


# def url_encode(flag: str) -> str:
#     """
#     URL кодирование (процент-кодирование)
#     flag: flag{test} -> flag%7Btest%7D
#     """
#     import urllib.parse
#     return urllib.parse.quote(flag)


# def url_decode(flag: str) -> str:
#     """
#     URL декодирование
#     flag: flag%7Btest%7D -> flag{test}
#     """
#     import urllib.parse
#     return urllib.parse.unquote(flag)


# def morse_encode(flag: str) -> str:
#     """
#     Morse кодирование (упрощенное)
#     """
#     morse_dict = {
#         'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.', 'f': '..-.',
#         'g': '--.', 'h': '....', 'i': '..', 'j': '.---', 'k': '-.-', 'l': '.-..',
#         'm': '--', 'n': '-.', 'o': '---', 'p': '.--.', 'q': '--.-', 'r': '.-.',
#         's': '...', 't': '-', 'u': '..-', 'v': '...-', 'w': '.--', 'x': '-..-',
#         'y': '-.--', 'z': '--..', '{': '...-..-', '}': '...-..-', '0': '-----',
#         '1': '.----', '2': '..---', '3': '...--', '4': '....-', '5': '.....',
#         '6': '-....', '7': '--...', '8': '---..', '9': '----.'
#     }
#     return ' '.join(morse_dict.get(c.lower(), c) for c in flag)


# def simple_substitution(flag: str, key: str = None) -> str:
#     """
#     Простая подстановка - замена букв на другие буквы по ключу
#     """
#     if key is None:
#         key = "bcdefghijklmnopqrstuvwxyza"  # Сдвиг на 1
    
#     alphabet = "abcdefghijklmnopqrstuvwxyz"
#     trans_table = str.maketrans(alphabet, key)
    
#     result = []
#     for char in flag:
#         if char.isalpha():
#             result.append(char.lower().translate(trans_table) if char.islower() else char.upper().translate(trans_table))
#         else:
#             result.append(char)
    
#     return ''.join(result)


# # ============================================================================
# # БАЗОВЫЙ КЛАСС CHALLENGE - УПРОЩЕННЫЙ
# # ============================================================================

# class Challenge:
#     """
#     Базовый класс для CTF задачи
#     Содержит описание, функцию преобразования флага и подсказку
#     """
    
#     def __init__(self, challenge_id: str, description: str, 
#                  transform_func: Callable[[str], str], 
#                  hint: str = "", points: int = 100):
#         """
#         Args:
#             challenge_id: Уникальный ID задачи
#             description: Описание задачи для участника
#             transform_func: Функция для преобразования флага
#             hint: Подсказка (опционально)
#             points: Очки за решение
#         """
#         self.challenge_id = challenge_id
#         self.description = description
#         self.transform_func = transform_func
#         self.hint = hint
#         self.points = points
    
#     def process_flag(self, flag: str) -> str:
#         """Применить функцию преобразования к флагу"""
#         return self.transform_func(flag)
    
#     def get_info(self) -> Dict:
#         """Получить информацию о задаче"""
#         return {
#             "id": self.challenge_id,
#             "description": self.description,
#             "hint": self.hint,
#             "points": self.points
#         }
    
#     def show(self) -> None:
#         """Вывести информацию о задаче"""
#         print(f"\n🎯 Задача: {self.challenge_id}")
#         print(f"   {self.description}")
#         if self.hint:
#             print(f"   💡 Подсказка: {self.hint}")
#         print(f"   ⭐ Очки: {self.points}")


# # ============================================================================
# # МЕНЕДЖЕР CHALLENGES
# # ============================================================================

# class ChallengeManager:
#     """Менеджер для управления задачами"""
    
#     def __init__(self):
#         self.challenges: Dict[str, Challenge] = {}
#         self.results: Dict[str, Dict] = {}
    
#     def add_challenge(self, challenge: Challenge) -> None:
#         """Добавить задачу"""
#         self.challenges[challenge.challenge_id] = challenge
    
#     def process_flag(self, challenge_id: str, flag: str) -> str:
#         """
#         Обработать флаг через задачу
        
#         Args:
#             challenge_id: ID задачи
#             flag: Флаг для преобразования
            
#         Returns:
#             Преобразованный результат
#         """
#         if challenge_id not in self.challenges:
#             raise ValueError(f"Задача {challenge_id} не найдена")
        
#         challenge = self.challenges[challenge_id]
#         result = challenge.process_flag(flag)
        
#         self.results[challenge_id] = {
#             "input": flag,
#             "output": result,
#             "challenge_id": challenge_id
#         }
        
#         return result
    
#     def get_challenge(self, challenge_id: str) -> Challenge:
#         """Получить задачу по ID"""
#         if challenge_id not in self.challenges:
#             raise ValueError(f"Задача {challenge_id} не найдена")
#         return self.challenges[challenge_id]
    
#     def list_challenges(self) -> List[str]:
#         """Получить список всех задач"""
#         return list(self.challenges.keys())
    
#     def show_all(self) -> None:
#         """Показать все задачи"""
#         for challenge_id in self.challenges.values():
#             challenge_id.show()
    
#     def get_result(self, challenge_id: str) -> Dict:
#         """Получить результат обработки"""
#         if challenge_id not in self.results:
#             raise ValueError(f"Нет результата для {challenge_id}")
#         return self.results[challenge_id]


# # ============================================================================
# # ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ БЫСТРОГО СОЗДАНИЯ
# # ============================================================================

# def create_crypto_challenges() -> List[Challenge]:
#     """Создает набор криптографических задач"""
#     challenges = [
#         Challenge(
#             "crypto_rot13",
#             "Расшифруй флаг используя ROT13",
#             rot13,
#             "ROT13 - это простой шифр замены, где каждая буква смещена на 13 позиций",
#             100
#         ),
#         Challenge(
#             "crypto_caesar",
#             "Зашифруй флаг используя Caesar с сдвигом на 3",
#             lambda x: caesar(x, 3),
#             "Caesar с сдвигом 3 - замени каждую букву на букву 3 позиции дальше",
#             100
#         ),
#         Challenge(
#             "crypto_atbash",
#             "Используй Atbash шифр (зеркальная замена)",
#             atbash,
#             "Atbash - это древний еврейский шифр, где a->z, b->y и т.д.",
#             150
#         ),
#         Challenge(
#             "crypto_vigenere",
#             "Используй Виженер шифр с ключом KEY",
#             lambda x: vigenere_encode(x, "KEY"),
#             "Виженер - это полиалфавитный шифр, работает с ключом",
#             200
#         ),
#     ]
#     return challenges


# def create_encoding_challenges() -> List[Challenge]:
#     """Создает набор задач на кодирование"""
#     challenges = [
#         Challenge(
#             "encoding_base64",
#             "Закодируй флаг в Base64",
#             base64_encode,
#             "Base64 - стандартное кодирование для передачи бинарных данных",
#             100
#         ),
#         Challenge(
#             "encoding_hex",
#             "Закодируй флаг в Hex (шестнадцатеричное)",
#             hex_encode,
#             "Hex - используй символы 0-9 и a-f",
#             100
#         ),
#         Challenge(
#             "encoding_reverse",
#             "Разверни флаг в обратном порядке",
#             reverse_string,
#             "Просто читай строку с конца",
#             50
#         ),
#         Challenge(
#             "encoding_url",
#             "Закодируй флаг в URL формат",
#             url_encode,
#             "URL кодирование заменяет спецсимволы на %XX",
#             100
#         ),
#     ]
#     return challenges


# def create_all_challenges() -> ChallengeManager:
#     """Создает менеджер со всеми задачами"""
#     manager = ChallengeManager()
    
#     # Добавляем криптографические задачи
#     for challenge in create_crypto_challenges():
#         manager.add_challenge(challenge)
    
#     # Добавляем задачи на кодирование
#     for challenge in create_encoding_challenges():
#         manager.add_challenge(challenge)
    
#     return manager


# # ============================================================================
# # ОСНОВНАЯ ПРОГРАММА
# # ============================================================================

# def main():
#     """Основная демонстрация"""
    
#     print("\n" + "🚩" * 35)
#     print("\n🚀 CTF СИСТЕМА - Преобразование флагов\n")
    
#     # Создаем менеджер с задачами
#     manager = create_all_challenges()
    
#     # Показываем все задачи
#     print("📋 ДОСТУПНЫЕ ЗАДАЧИ:\n")
#     for challenge_id in manager.list_challenges():
#         challenge = manager.get_challenge(challenge_id)
#         print(f"  • {challenge_id}: {challenge.description}")
    
#     # Демонстрация обработки флагов
#     print("\n" + "=" * 70)
#     print("🚩 ДЕМОНСТРАЦИЯ ПРЕОБРАЗОВАНИЯ ФЛАГОВ:\n")
    
#     test_flag = "flag{test}"
    
#     demonstrations = [
#         "crypto_rot13",
#         "crypto_caesar",
#         "encoding_base64",
#         "encoding_hex",
#         "encoding_reverse",
#     ]
    
#     for challenge_id in demonstrations:
#         try:
#             challenge = manager.get_challenge(challenge_id)
#             result = manager.process_flag(challenge_id, test_flag)
            
#             print(f"🎯 {challenge_id}")
#             print(f"   Вход:  {test_flag}")
#             print(f"   Выход: {result}")
#             print()
#         except ValueError as e:
#             print(f"❌ Ошибка: {e}")
    
#     # Показываем результаты
#     print("=" * 70)
#     print("\n✅ РЕЗУЛЬТАТЫ:\n")
#     for challenge_id in demonstrations:
#         result = manager.get_result(challenge_id)
#         print(f"  {challenge_id}: {result['input']} -> {result['output']}")
    
#     print("\n" + "🚩" * 35 + "\n")


