#!/usr/bin/env python3
"""
Honeycomb Scanner v1.0.0
Модуль сканирования сот для Мандалы Симбиоза

Автоматически сканирует директорию honeycombs/ и регистрирует все соты в системе.
"""

import os
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import hashlib

Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('honeycomb_scanner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(name)


class HoneycombScanner:
    """Основной класс для сканирования и регистрации сот"""
    
    def init(self, base_path: str = "honeycombs"):
        """
        Инициализация сканера
        
        Args:
            base_path: Базовый путь к директории honeycombs
        """
        self.base_path = Path(base_path)
        self.registry_path = Path("honeycombs/registry/index.json")
        self.scanner_config_path = Path("honeycombs/registry/scanner.json")
        
        # Конфигурация сканера
        self.config = self._load_config()
        
        # Результаты сканирования
        self.honeycombs: List[Dict[str, Any]] = []
        self.new_honeycombs: List[str] = []
        self.modified_honeycombs: List[str] = []
        self.deleted_honeycombs: List[str] = []
        self.validation_errors: List[Dict[str, Any]] = []
        
        # Статистика
        self.stats = {
            "total_scanned": 0,
            "valid_v2": 0,
            "invalid_v2": 0,
            "errors": 0,
            "warnings": 0,
            "total_files": 0,
            "total_size_kb": 0
        }
        
        # Кэш предыдущего сканирования
        self.previous_scan_cache: Dict[str, Any] = {}
        
    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации сканера"""
        try:
            with open(self.scanner_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            return {
                "scanning_logic": {
                    "depth": "рекурсивно все уровни вложенности",
                    "target_files": ["index.json"],
                    "validation_rules": ["Проверка структуры v2.0"],
                    "update_triggers": ["Новая сота обнаружена", "Сота изменена"]
                }
            }
    
    def scan_all_honeycombs(self, force_rescan: bool = False) -> Dict[str, Any]:
        """
        Основное сканирование всех сот
        
        Args:
            force_rescan: Принудительное полное сканирование
            
        Returns:
            Словарь с результатами сканирования
        """
        logger.info("=" * 60)
        logger.info("НАЧАЛО СКАНИРОВАНИЯ СОТ")
        logger.info(f"Базовый путь: {self.base_path}")
        logger.info(f"Конфигурация: {self.config.get('identity', {}).get('name', 'Unknown')}")
        logger.info("=" * 60)
        
        # Загрузка предыдущего состояния реестра
        self._load_previous_state()
        
        # Рекурсивное сканирование
        self._recursive_scan(self.base_path)
        
        # Обновление реестра
        if self.honeycombs:
            registry_updated = self._update_registry()
        else:
            logger.warning("Соты не найдены!")
            registry_updated = False
        
        # Формирование отчёта
        report = self._generate_report()
        
        # Сохранение состояния сканирования
        self._save_scan_state()
        
        logger.info("=" * 60)
        logger.info("СКАНИРОВАНИЕ ЗАВЕРШЕНО")
        logger.info(f"Найдено сот: {len(self.honeycombs)}")
        logger.info(f"Новых: {len(self.new_honeycombs)}")
        logger.info(f"Изменённых: {len(self.modified_honeycombs)}")
        logger.info(f"Удалённых: {len(self.deleted_honeycombs)}")
        logger.info(f"Ошибок валидации: {len(self.validation_errors)}")
        logger.info("=" * 60)
        
        return report
    
    def _load_previous_state(self):
        """Загрузка предыдущего состояния реестра для сравнения"""
        try:
            if self.registry_path.exists():
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
                
                # Кэширование информации о предыдущих сотах
                if "honeycombs" in registry:
                    for honeycomb in registry["honeycombs"]:
                        honeycomb_id = honeycomb.get("honeycomb_id", "")
                        if honeycomb_id:
                            self.previous_scan_cache[honeycomb_id] = {
                                "hash": honeycomb.get("hash", ""),
                                "last_modified": honeycomb.get("last_modified", 0),
                                "file_count": honeycomb.get("file_count", 0)
                            }
                logger.info(f"Загружено {len(self.previous_scan_cache)} записей из предыдущего реестра")
        except Exception as e:
            logger.error(f"Ошибка загрузки предыдущего состояния: {e}")
    
    def _recursive_scan(self, directory: Path):
        """
        Рекурсивное сканирование директории
        
        Args:
            directory: Директория для сканирования
        """
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    # Пропускаем некоторые системные директории
                    if item.name.startswith('.') or item.name.startswith('__'):
                        continue
                    
                    # Проверяем наличие index.json в директории
                    index_file = item / "index.json"
                    if index_file.exists():
                        self._analyze_honeycomb(index_file)
                    
                    # Рекурсивный вызов для поддиректорий
                    self._recursive_scan(item)
        except Exception as e:
            logger.error(f"Ошибка сканирования директории {directory}: {e}")
            self.stats["errors"] += 1
    
    def _analyze_honeycomb(self, honeycomb_path: Path):
        """
        Анализ и валидация соты
        
        Args:
            honeycomb_path: Путь к файлу index.json соты
        """
        try:
            # Чтение файла соты
            with open(honeycomb_path, 'r', encoding='utf-8') as f:
                honeycomb_data = json.load(f)
            
            # Извлечение идентификатора соты
            honeycomb_dir = honeycomb_path.parent
            relative_path = honeycomb_dir.relative_to(self.base_path)
            honeycomb_id = str(relative_path).replace(os.sep, '/')
            
            # Вычисление хэша содержимого
            content_hash = self._calculate_hash(honeycomb_data)
            
            # Проверка структуры v2.0
            is_valid, validation_details = self._validate_v2_structure(honeycomb_data)
            
            # Подсчёт файлов и размера
            file_count, total_size_kb = self._count_honeycomb_files(honeycomb_dir)
            
            # Извлечение информации из identity
            identity = honeycomb_data.get("identity", {})
            
            # Формирование записи соты
            honeycomb_info = {
                "honeycomb_id": honeycomb_id,
                "path": str(honeycomb_path),
                "relative_path": str(relative_path),
                "name": identity.get("name", "Unknown"),
                "module_id": identity.get("module_id", "Unknown"),
                "version": identity.get("version", "Unknown"),
                "layer": identity.get("layer", 0),
                "type": identity.get("type", "Unknown"),
                "status": identity.get("status", "active"),
                "description": identity.get("description", ""),
                "tags": identity.get("tags", []),
                "resonance": identity.get("resonance", "0%"),
                
                # Техническая информация
                "is_v2_compliant": is_valid,
                "validation_details": validation_details,
                "hash": content_hash,
                "last_modified": os.path.getmtime(honeycomb_path),
                "file_count": file_count,
                "total_size_kb": total_size_kb,
                "scan_timestamp": datetime.now().isoformat()
            }
            
            # Проверка изменений
            self._detect_changes(honeycomb_id, honeycomb_info)
            
            # Добавление в список
            self.honeycombs.append(honeycomb_info)
            
            # Обновление статистики
            self.stats["total_scanned"] += 1
            self.stats["total_files"] += file_count
            self.stats["total_size_kb"] += total_size_kb
            
            if is_valid:
                self.stats["valid_v2"] += 1
                logger.info(f"✓ {honeycomb_id}: {honeycomb_info['name']} (v{honeycomb_info['version']})")
            else:
                self.stats["invalid_v2"] += 1
                self.stats["warnings"] += 1
                logger.warning(f"✗ {honeycomb_id}: Не соответствует v2.0")
                self.validation_errors.append({
                    "honeycomb_id": honeycomb_id,
                    "name": honeycomb_info["name"],
                    "errors": validation_details.get("errors", []),
                    "warnings": validation_details.get("warnings", [])
                })
                
        except json.JSONDecodeError as e:
            logger.error(f"{honeycomb_path}: Ошибка JSON: {e}")
            self.stats["errors"] += 1
        except Exception as e:
            logger.error(f"{honeycomb_path}: Ошибка анализа: {e}")
            self.stats["errors"] += 1
    
    def _calculate_hash(self, data: Dict[str, Any]) -> str:
        """Вычисление хэша JSON данных"""
        try:
            # Сортировка ключей для консистентности
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(json_str.encode('utf-8')).hexdigest()
        except:
            return "error"
    
    def _validate_v2_structure(self, honeycomb_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Валидация структуры соты по стандарту v2.0
        
        Returns:
            Кортеж (валидна ли структура, детали валидации)
        """
        details = {
            "errors": [],
            "warnings": [],
            "missing_sections": [],
            "missing_fields": []
        }
        
        # Проверка обязательных секций
        required_sections = ["identity", "meta", "content"]
        for section in required_sections:
            if section not in honeycomb_data:
                details["errors"].append(f"Отсутствует обязательная секция: {section}")
                details["missing_sections"].append(section)
        
        # Проверка identity секции
        if "identity" in honeycomb_data:
            identity = honeycomb_data["identity"]
            required_fields = ["module_id", "name", "version", "layer", "type"]
            
            for field in required_fields:
                if field not in identity:
                    details["errors"].append(f"Отсутствует обязательное поле identity.{field}")
                    details["missing_fields"].append(f"identity.{field}")
            
            # Проверка формата module_id
            if "module_id" in identity:
                module_id = identity["module_id"]
                if not isinstance(module_id, str) or len(module_id.strip()) == 0:
                    details["warnings"].append("module_id должен быть непустой строкой")
        
        # Проверка meta секции
        if "meta" in honeycomb_data:
            meta = honeycomb_data["meta"]
            if "description" not in meta:
                details["warnings"].append("Рекомендуется добавить описание в meta.description")
        
        # Определение результата
        is_valid = len(details["errors"]) == 0
        
        return is_valid, details
    
    def _count_honeycomb_files(self, honeycomb_dir: Path) -> Tuple[int, float]:
        """Подсчёт JSON файлов в соте"""
        file_count = 0
        total_size_bytes = 0
        
        try:
            for root, dirs, files in os.walk(honeycomb_dir):
                for file in files:
                    if file.endswith('.json'):
                        file_path = Path(root) / file
                        file_count += 1
                        total_size_bytes += os.path.getsize(file_path)
        except Exception as e:
            logger.warning(f"Ошибка подсчёта файлов в {honeycomb_dir}: {e}")
            self.stats["errors"] += 1
        
        total_size_kb = round(total_size_bytes / 1024, 2)
        return file_count, total_size_kb
    
    def _detect_changes(self, honeycomb_id: str, honeycomb_info: Dict[str, Any]):
        """Обнаружение изменений в соте"""
        if honeycomb_id in self.previous_scan_cache:
            previous = self.previous_scan_cache[honeycomb_id]
            
            # Проверка хэша
            if previous.get("hash") != honeycomb_info["hash"]:
                self.modified_honeycombs.append(honeycomb_id)
                logger.info(f"  → Изменена: {honeycomb_id}")
        else:
            # Новая сота
            self.new_honeycombs.append(honeycomb_id)
            logger.info(f"  + Новая: {honeycomb_id}")
    
    def _update_registry(self) -> bool:
        """Обновление главного реестра"""
        try:
            # Загрузка текущего реестра
            if self.registry_path.exists():
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
            else:
                # Создание нового реестра
                registry = {
                    "registry_info": {
                        "name": "Главный реестр сот Мандалы Симбиоза",
                        "version": "v2.0",
                        "created": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat(),
                        "scanner_version": self.config.get("identity", {}).get("version", "v1.0.0")
                    },
                    "honeycombs": [],
                    "statistics": {},
                    "health_status": {}
                }
            
            # Обновление информации о реестре
            registry["registry_info"]["last_updated"] = datetime.now().isoformat()
            registry["registry_info"]["last_scan"] = datetime.now().isoformat()
            registry["registry_info"]["scanner_version"] = self.config.get("identity", {}).get("version", "v1.0.0")
            
            # Обновление списка сот
            registry["honeycombs"] = self.honeycombs
            
            # Обновление статистики
            registry["statistics"] = {
                "total_honeycombs": len(self.honeycombs),
                "valid_v2_compliant": self.stats["valid_v2"],
                "invalid_v2_compliant": self.stats["invalid_v2"],
                "total_files": self.stats["total_files"],
                "total_size_kb": round(self.stats["total_size_kb"], 2),
                "new_honeycombs": len(self.new_honeycombs),
                "modified_honeycombs": len(self.modified_honeycombs),
                "deleted_honeycombs": len(self.deleted_honeycombs),
                "validation_errors": len(self.validation_errors),
                "scan_errors": self.stats["errors"],
                "last_scan_timestamp": datetime.now().isoformat()
            }
            
            # Обновление статуса здоровья
            health_status = "healthy"
            if self.stats["errors"] > 0:
                health_status = "error"
            elif self.stats["invalid_v2"] > 0:
                health_status = "warning"
            
            registry["health_status"] = {
                "status": health_status,
                "validation_errors": self.validation_errors,
                "new_honeycombs": self.new_honeycombs,
                "modified_honeycombs": self.modified_honeycombs,
                "deleted_honeycombs": self.deleted_honeycombs
            }
            
            # Сохранение обновлённого реестра
            with open(self.registry_path, 'w', encoding='utf-8') as f:
                json.dump(registry, f, indent=2, ensure_ascii=False, sort_keys=True)
            
            logger.info(f"Реестр обновлён: {self.registry_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления реестра: {e}")
            return False
    
    def _generate_report(self) -> Dict[str, Any]:
        """Генерация отчёта о сканировании"""
        return {
            "scan_report": {
                "timestamp": datetime.now().isoformat(),
                "scanner_version": self.config.get("identity", {}).get("version", "v1.0.0"),
                "base_path": str(self.base_path),
                "duration_seconds": None,  # Можно добавить измерение времени
                "status": "completed"
            },
            "summary": {
                "total_honeycombs_found": len(self.honeycombs),
                "new_honeycombs": self.new_honeycombs,
                "modified_honeycombs": self.modified_honeycombs,
                "deleted_honeycombs": self.deleted_honeycombs,
                "validation_errors_count": len(self.validation_errors)
            },
            "statistics": self.stats,
            "validation_errors": self.validation_errors,
            "honeycombs_by_layer": self._group_by_layer(),
            "honeycombs_by_type": self._group_by_type()
        }
    
    def _group_by_layer(self) -> Dict[int, List[str]]:
        """Группировка сот по слоям"""
        layers = {}
        for honeycomb in self.honeycombs:
            layer = honeycomb.get("layer", 0)
            if layer not in layers:
                layers[layer] = []
            layers[layer].append(honeycomb["honeycomb_id"])
        return layers
    
    def _group_by_type(self) -> Dict[str, List[str]]:
        """Группировка сот по типам"""
        types = {}
        for honeycomb in self.honeycombs:
            honeycomb_type = honeycomb.get("type", "unknown")
            if honeycomb_type not in types:
                types[honeycomb_type] = []
            types[honeycomb_type].append(honeycomb["honeycomb_id"])
        return types
    
    def _save_scan_state(self):
        """Сохранение состояния сканирования для следующего запуска"""
        try:
            state_file = Path("honeycombs/registry/scan_state.json")
            state_data = {
                "last_scan": datetime.now().isoformat(),
                "honeycomb_hashes": {
                    honeycomb["honeycomb_id"]: honeycomb["hash"] 
                    for honeycomb in self.honeycombs
                },
                "statistics": self.stats,
                "scanner_config": self.config.get("identity", {})
            }
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Сохранено состояние сканирования: {state_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния: {e}")


def main():
    """Основная функция CLI"""
    if len(sys.argv) < 2:
        print("=" * 60)
        print("HONEYCOMB SCANNER v1.0.0")
        print("Модуль сканирования сот Мандалы Симбиоза")
        print("=" * 60)
        print("\nИспользование:")
        print("  python honeycomb_scanner.py scan     # Запустить сканирование")
        print("  python honeycomb_scanner.py test     # Тестовый прогон")
        print("  python honeycomb_scanner.py validate # Только валидация")
        print("  python honeycomb_scanner.py report   # Отчёт без сканирования")
        print("\nОпции:")
        print("  --force      Принудительное полное сканирование")
        print("  --verbose    Подробный вывод")
        print("  --log-file   Сохранить логи в файл")
        return
    
    command = sys.argv[1]
    force_rescan = "--force" in sys.argv
    verbose = "--verbose" in sys.argv
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    scanner = HoneycombScanner()
    
    if command == "scan":
        print("Запуск сканирования сот...")
        report = scanner.scan_all_honeycombs(force_rescan)
        
        print("\n" + "=" * 60)
        print("ОТЧЁТ СКАНА")
        print("=" * 60)
        print(f"Всего сот: {len(scanner.honeycombs)}")
        print(f"Новых: {len(scanner.new_honeycombs)}")
        print(f"Изменённых: {len(scanner.modified_honeycombs)}")
        print(f"Удалённых: {len(scanner.deleted_honeycombs)}")
        print(f"Ошибок валидации: {len(scanner.validation_errors)}")
        print(f"Реестр обновлён: {'Да' if scanner.honeycombs else 'Нет'}")
        
        if scanner.validation_errors:
            print("\nОШИБКИ ВАЛИДАЦИИ:")
            for error in scanner.validation_errors[:5]:  # Показываем первые 5
                print(f"  • {error['honeycomb_id']}: {error['name']}")
                for err in error.get('errors', [])[:3]:
                    print(f"    - {err}")
            if len(scanner.validation_errors) > 5:
                print(f"    ... и ещё {len(scanner.validation_errors) - 5} ошибок")
        
        print("\nСКАНИРОВАНИЕ ЗАВЕРШЕНО")
        
    elif command == "test":
        print("Тестовый прогон сканирования...")
        # Тестовый режим - сканируем, но не сохраняем
        scanner.scan_all_honeycombs(force_rescan)
        print(f"Найдено сот: {len(scanner.honeycombs)}")
        print(f"Валидных v2.0: {scanner.stats['valid_v2']}")
        print(f"Невалидных v2.0: {scanner.stats['invalid_v2']}")
        
        if scanner.honeycombs:
            print("\nПервые 5 сот:")
            for honeycomb in scanner.honeycombs[:5]:
                print(f"  • {honeycomb['honeycomb_id']}: {honeycomb['name']} (v{honeycomb['version']})")
        
    elif command == "validate":
        print("Режим валидации...")
        scanner.scan_all_honeycombs(force_rescan)
        
        if scanner.validation_errors:
            print(f"\nНайдено {len(scanner.validation_errors)} ошибок валидации:")
            for error in scanner.validation_errors:
                print(f"\n{honeycomb['honeycomb_id']}: {honeycomb['name']}")
                for err in error.get('errors', []):
                    print(f"  ✗ {err}")
                for warn in error.get('warnings', []):
                    print(f"  ! {warn}")
        else:
            print("Все соты соответствуют стандарту v2.0!")
            
    elif command == "report":
        print("Генерация отчёта...")
        # Можно добавить генерацию HTML или Markdown отчёта
        print("Функция отчёта в разработке")
        
    else:
        print(f"Неизвестная команда: {command}")
        sys.exit(1)


if name == "main":
    main()
