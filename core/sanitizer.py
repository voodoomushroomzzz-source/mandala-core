import os

def scan_core():
    """Проверяет файлы репозитория на соответствие стандартам Мандалы."""
    print("🔍 Запуск сканирования Ядра...")
    
    rules = {
        ".md": ["#", "##"], # Markdown должен иметь заголовки
        ".py": ["import", "def"] # Скрипты должны иметь импорты и функции
    }
    
    for root, dirs, files in os.walk("."):
        for file in files:
            if any(file.endswith(ext) for ext in rules):
                check_file(os.path.join(root, file), rules)

def check_file(path, rules):
    ext = os.path.splitext(path)[1]
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        for marker in rules[ext]:
            if marker not in content:
                print(f"⚠️  Узел [{path}] нарушает структуру: отсутствует '{marker}'")
                return
    print(f"✅ Узел [{path}] прошел проверку.")

if __name__ == "__main__":
    scan_core()