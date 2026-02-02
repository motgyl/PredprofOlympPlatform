from typing import Callable, Dict
import subprocess
import shlex
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class Command:
    """Вспомогательный класс для выполнения команд"""
    
    @staticmethod
    def run(command: str, shell: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        """
        Выполнить команду с помощью subprocess
        
        Args:
            command: Строка команды
            shell: Использовать shell (по умолчанию True)
            check: Проверять код возврата (по умолчанию True)
            
        Returns:
            CompletedProcess с информацией о выполнении
        """
        try:
            if shell:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=check
                )
            else:
                args = shlex.split(command)
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=check
                )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Команда вернула ошибку {e.returncode}: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды: {e}")
            raise


class Challenge:
    """
    Базовый класс для CTF задачи
    Содержит описание, функцию преобразования флага и подсказку
    """
    
    def __init__(self, description: str = "", hint: str = "", dynamic_description: bool = False):
        """
        Args:
            description: Описание задачи для участника
            hint: Подсказка (опционально)
            points: Очки за решение
        """
        self.description = description
        self.hint = hint
        self.dynamic_description = dynamic_description

    def get_info(self) -> Dict:
        """Получить информацию о задаче"""
        return {
            "description": self.description,
            "hint": self.hint,
            "dynamic_description": self.dynamic_description
        }
    
    def generate(self, flag: str):
        """Генерировать задание на основе флага (переопределяется в наследниках)"""
        self.description =self.description.format(flag=flag)
        return True
    
    
class SimpleStegano(Challenge):
    def __init__(self, image_path: str, description: str = "", hint: str = ""):
        super().__init__(description, hint)
        self.image_path = image_path

    def generate(self, flag: str, save_path: str = ""):
        """
        Генерировать стегано изображение с флагом в метаданных
        
        Args:
            flag: Флаг для скрытия
            save_path: Путь для сохранения результата
        """
        try:
            import os
            
            # Создаем директорию если её нет
            if save_path and not os.path.exists(save_path):
                os.makedirs(save_path, exist_ok=True)
            
            output_image = os.path.join(save_path, "stegano_image.png")
            
            # Копируем файл
            result = Command.run(f"cp {self.image_path} {output_image}")
            logger.info(f"Изображение скопировано: {output_image}")
            
            # Добавляем флаг в метаданные
            result = Command.run(
                f"exiftool -overwrite_original -Comment='{flag}' {output_image}"
            )
            logger.info(f"Флаг добавлен в метаданные: {flag}")
            
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка при генерации стегано: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return False