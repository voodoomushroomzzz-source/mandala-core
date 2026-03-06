#!/usr/bin/env python3
# -- coding: utf-8 --
"""
Тестовый скрипт для проверки работы HoneycombScanner

Этот скрипт тестирует функциональность сканера сот и проверяет:
1. Сканирование директории honeycombs/
2. Анализ найденных сот
3. Генерацию реестра
4. Сохранение реестра в файл
"""

import os
import sys
from scanner import HoneycombScanner


def test_basic_scan():
    """Тест базового сканирования"""
    print("🧪 Тест 1: Базовое сканирование директории honeycombs/")
    
    scanner = HoneycombScanner()
    honeycombs = scanner.scan_directory()
    
    print(f"   Найдено сот: {len(honeycombs)}")
    print(f"   Статистика: {scanner.scan_stats}")
    
    if len(honeycombs) == 0:
        print("   ⚠️ Внимание: соты не найдены!")
        return False
    
    return True


def test_categorization():
    """Тест категоризации сот"""
    print("\n🧪 Тест 2: Категоризация сот по типам")
    
    scanner = HoneycombScanner()
    scanner.scan_directory()
    categories = scanner.categorize_honeycombs()
    
    if not categories:
        print("   ⚠️ Категории не найдены")
        return False
    
    print(f"   Найдено категорий: {len(categories)}")
    for category, data in categories.items():
        print(f"   • {category}: {data['count']} сот")
    
    return True


def test_statistics():
    """Тест расчёта статистики"""
    print("\n🧪 Тест 3: Расчёт статистики по сотам")
    
    scanner = HoneycombScanner()
    scanner.scan_directory()
    stats = scanner.calculate_statistics()
    
    print(f"   Всего сот: {stats.get('total_honeycombs', 0)}")
    print(f"   Активных сот: {stats.get('active_honeycombs', 0)}")
    print(f"   Неактивных сот: {stats.get('inactive_honeycombs', 0)}")
    print(f"   Средний размер: {stats.get('average_size_kb', 0)} KB")
    
    return True


def test_registry_generation():
    """Тест генерации реестра"""
    print("\n🧪 Тест 4: Генерация реестра сот")
    
    scanner = HoneycombScanner()
    scanner.scan_directory()
    registry = scanner.generate_registry()
    
    # Проверяем обязательные поля
    required_fields = ['identity', 'meta', 'content']
    for field in required_fields:
        if field not in registry:
            print(f"   ❌ Отсутствует поле {field} в реестре")
            return False
    
    print(f"   ✅ Реестр сгенерирован успешно")
    print(f"   • Идентификация: {registry['identity'].get('name', 'N/A')}")
    print(f"   • Всего сот в реестре: {registry['content'].get('registry', {}).get('total_honeycombs', 0)}")
    
    return True


def test_registry_save():
    """Тест сохранения реестра в файл"""
    print("\n🧪 Тест 5: Сохранение реестра в файл")
    
    scanner = HoneycombScanner()
    scanner.scan_directory()
    
    # Тестовый путь для сохранения
    test_output_path = "test_registry_output.json"
    
    success = scanner.save_registry(test_output_path)
    
    if success:
        print(f"   ✅ Реестр сохранён в {test_output_path}")
        
        # Проверяем, что файл существует
        if os.path.exists(test_output_path):
            file_size = os.path.getsize(test_output_path)
            print(f"   • Размер файла: {file_size} байт")
            
            # Читаем и проверяем структуру
            import json
            with open(test_output_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                
            if 'identity' in content and 'content' in content:
                print(f"   • Структура валидна")
            
            # Удаляем тестовый файл
            os.remove(test_output_path)
            print(f"   • Тестовый файл удалён")
        else:
            print(f"   ❌ Файл не создан")
            return False
    else:
        print(f"   ❌ Ошибка при сохранении реестра")
        return False
    
    return True


def run_all_tests():
    """Запуск всех тестов"""
    print("🚀 Запуск тестов HoneycombScanner")
    print("="  50)
    
    tests = [
        test_basic_scan,
        test_categorization,
        test_statistics,
        test_registry_generation,
        test_registry_save
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"   ✅ Тест пройден")
            else:
                failed += 1
                print(f"   ❌ Тест не пройден")
        except Exception as e:
            failed += 1
            print(f"   💥 Ошибка в тесте {test_func.name}: {e}")
    
    print("="  50)
    print(f"📊 Итоги тестирования:")
    print(f"   ✅ Пройдено: {passed}")
    print(f"   ❌ Провалено: {failed}")
    
    if failed == 0:
        print("🎉 Все тесты пройдены успешно!")
        return True
    else:
        print(f"⚠️ Провалено тестов: {failed}")
        return False


def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Тестовый скрипт для HoneycombScanner',
        epilog='Пример: python test_scanner.py --all'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Запустить все тесты'
    )
    
    parser.add_argument(
        '--scan',
        action='store_true',
        help='Запустить тест сканирования'
    )
    
    parser.add_argument(
        '--categorize',
        action='store_true',
        help='Запустить тест категоризации'
    )
    
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Запустить тест статистики'
    )
    
    parser.add_argument(
        '--registry',
        action='store_true',
        help='Запустить тест генерации реестра'
    )
    
    parser.add_argument(
        '--save',
        action='store_true',
        help='Запустить тест сохранения реестра'
    )
    
    parser.add_argument(
        '--path',
        type=str,
        default='honeycombs',
        help='Путь к директории для тестирования (по умолчанию: honeycombs/)'
    )
    
    args = parser.parse_args()
    
    # Если не указаны аргументы, показываем помощь
    if not any([args.all, args.scan, args.categorize, args.stats, args.registry, args.save]):
        parser.print_help()
        return 0
    
    # Меняем путь для сканера если указан
    if args.path != 'honeycombs':
        global HoneycombScanner
        HoneycombScanner = lambda: HoneycombScanner(args.path)
    
    if args.all:
        success = run_all_tests()
        return 0 if success else 1
    
    # Запуск отдельных тестов
    test_results = []
    
    if args.scan:
        print("🔍 Запуск теста сканирования...")
        test_results.append(test_basic_scan())
    
    if args.categorize:
        print("📊 Запуск теста категоризации...")
        test_results.append(test_categorization())
    
    if args.stats:
        print("📈 Запуск теста статистики...")
        test_results.append(test_statistics())
    
    if args.registry:
        print("📋 Запуск теста генерации реестра...")
        test_results.append(test_registry_generation())
    
    if args.save:
        print("💾 Запуск теста сохранения реестра...")
        test_results.append(test_registry_save())
    
    # Подводим итоги
    if test_results:
        passed = sum(1 for r in test_results if r)
        total = len(test_results)
        print(f"\n📊 Результаты: {passed}/{total} тестов пройдено")
        return 0 if passed == total else 1
    
    return 0


if name == 'main':
    sys.exit(main())