#!/usr/bin/env python3
"""
Honeycomb Scanner v1.0

Скрипт для автоматического сканирования сот в системе Мандалы Симбиоза.
Обнаруживает все соты, проверяет их структуру и обновляет реестр.

Использование:
    python honeycomb_scanner.py scan   # Запустить сканирование
    python honeycomb_scanner.py test   # Тестовый прогон без изменений
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging

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
    """Сканер сот для Мандалы Симбиоза"""
    
    def init(self, base_path: str = "honeycombs"):
        """Инициализация сканера"""
        self.base_path = Path(base_path)
        self.registry_path = Path("honeycombs/registry/index.json")
        self.scanner_config_path = Path("honeycombs/registry/scanner.json")
        
        # Результаты сканирования
        self.honeycombs = []
        self.total_files = 0
        self.total_size_kb = 0
        
        # Статистика
        self.stats = {
            "total_scanned": 0,
            "valid_v2": 0,
            "invalid_v2": 0,
            "no_index": 0,
            "errors": 0
        }
    
    def scan_honeycombs(self) -> List[Dict[str, Any]]:
        """
        Основная функция сканирования сот
        Возвращает список найденных сот
        """
        logger.info(f"Начинаю сканирование сот в {self.base_path}")
        
        # Рекурсивный поиск index.json файлов
        for root, dirs, files in os.walk(self.base_path):
            if "index.json" in files:
                honeycomb_path = Path(root) / "index.json"
                honeycomb_data = self._analyze_honeycomb(honeycomb_path)
                
                if honeycomb_data:
                    self.honeycombs.append(honeycomb_data)
                
                self.stats["total_scanned"] += 1
        
        logger.info(f"Сканирование завершено. Найдено сот: {len(self.honeycombs)}")
        self._log_stats()
        
        return self.honeycombs
    
    def _analyze_honeycomb(self, honeycomb_path: Path) -> Optional[Dict[str, Any]]:
        """
        Анализ отдельной соты
        Возвращает данные соты или None если ошибка
        """
        try:
            # Чтение файла соты
            with open(honeycomb_path, 'r', encoding='utf-8') as f:
                honeycomb_data = json.load(f)
            
            # Проверка минимальной структуры
            if not isinstance(honeycomb_data, dict):
                logger.warning(f"{honeycomb_path}: Не JSON объект")
                self.stats["errors"] += 1
                return None
            
            # Извлечение пути соты (относительно honeycombs/)
            relative_path = honeycomb_path.relative_to(self.base_path).parent
            honeycomb_id = str(relative_path).replace(os.sep, '/')
            
            # Проверка стандарта v2.0
            is_v2_compliant = self._check_v2_compliance(honeycomb_data)
            
            # Подсчёт файлов и размера
            file_count, total_size = self._count_honeycomb_files(honeycomb_path.parent)
            
            honeycomb_info = {
                "honeycomb_id": honeycomb_id if honeycomb_id else ".",
                "path": str(honeycomb_path),
                "relative_path": str(relative_path),
                "is_v2_compliant": is_v2_compliant,
                "file_count": file_count,
                "total_size_kb": total_size,
                "last_modified": os.path.getmtime(honeycomb_path),
                "has_identity": "identity" in honeycomb_data,
                "has_meta": "meta" in honeycomb_data,
                "has_registry": "registry" in honeycomb_data,
                "has_resonance": "resonance" in honeycomb_data
            }
            
            # Добавление информации из identity если есть
            if "identity" in honeycomb_data:
                identity = honeycomb_data["identity"]
                honeycomb_info.update({
                    "name": identity.get("name", "Unknown"),
                    "module_id": identity.get("module_id", "Unknown"),
                    "version": identity.get("version", "Unknown"),
                    "layer": identity.get("layer", 0),
                    "type": identity.get("type", "Unknown"),
                    "status": identity.get("status", "Unknown")
                })
            
            # Обновление статистики
            if is_v2_compliant:
                self.stats["valid_v2"] += 1
            else:
                self.stats["invalid_v2"] += 1
                logger.warning(f"{honeycomb_path}: Не соответствует v2.0 стандарту")
            
            return honeycomb_info
            
        except json.JSONDecodeError as e:
            logger.error(f"{honeycomb_path}: Ошибка JSON: {e}")
            self.stats["errors"] += 1
        except Exception as e:
            logger.error(f"{honeycomb_path}: Ошибка анализа: {e}")
            self.stats["errors"] += 1
        
        return None
    
    def _check_v2_compliance(self, honeycomb_data: Dict[str, Any]) -> bool:
        """
        Проверка соответствия стандарту v2.0
        """
        # Минимальные требования v2.0
        required_sections = ["identity", "meta", "registry"]
        
        for section in required_sections:
            if section not in honeycomb_data:
                return False
        
        # Проверка обязательных полей в identity
        identity = honeycomb_data.get("identity", {})
        required_identity_fields = ["module_id", "name", "version", "layer", "type"]
        
        for field in required_identity_fields:
            if field not in identity:
                return False
        
        return True
    
    def _count_honeycomb_files(self, honeycomb_dir: Path) -> Tuple[int, float]:
        """
        Подсчёт файлов и размера в соте
        """
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
        
        total_size_kb = round(total_size_bytes / 1024, 2)
        return file_count, total_size_kb
    
    def update_registry(self, honeycombs: List[Dict[str, Any]]) -> bool:
        """
        Обновление реестра на основе результатов сканирования
        """
        try:
            # Чтение текущего реестра
            if self.registry_path.exists():
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    registry_data = json.load(f)
            else:
                logger.error(f"Реестр не найден: {self.registry_path}")
                return False
            
            # Обновление данных
            registry_data["total_honeycombs"] = len(honeycombs)
            
            # Обновление категорий
            categories = {
                "core": [],
                "instructions": [],
                "seeds": [],
                "registry": [],
                "roadmaps": [],
                "other": []
            }
            
            total_files_all = 0
            total_size_all = 0
            
            for honeycomb in honeycombs:
                # Определение категории
                honeycomb_id = honeycomb["honeycomb_id"]
                
                if honeycomb_id == ".":
                    category = "core"
                elif honeycomb_id.startswith("instructions"):
                    category = "instructions"
                elif honeycomb_id.startswith("seeds"):
                    category = "seeds"
                elif honeycomb_id.startswith("registry"):
                    category = "registry"
                elif honeycomb_id.startswith("roadmaps"):
                    category = "roadmaps"
                else:
                    category = "other"
                
                # Формирование записи
                honeycomb_entry = {
                    "id": honeycomb["honeycomb_id"],
                    "name": honeycomb.get("name", "Unknown"),
                    "module_id": honeycomb.get("module_id", "Unknown"),
                    "version": honeycomb.get("version", "Unknown"),
                    "layer": honeycomb.get("layer", 0),
                    "type": honeycomb.get("type", "Unknown"),
                    "status": honeycomb.get("status", "Unknown"),
                    "is_v2_compliant": honeycomb["is_v2_compliant"],
                    "file_count": honeycomb["file_count"],
                    "total_size_kb": honeycomb["total_size_kb"],
                    "last_modified": honeycomb["last_modified"]
                }
                
                categories[category].append(honeycomb_entry)
                
                # Суммирование статистики
                total_files_all += honeycomb["file_count"]
                total_size_all += honeycomb["total_size_kb"]
            
            # Обновление реестра
            registry_data["categories"] = categories
            registry_data["total_files"] = total_files_all
            registry_data["total_size_kb"] = round(total_size_all, 2)
            registry_data["last_scan"] = {
                "timestamp": os.path.getmtime(file),
                "honeycombs_found": len(honeycombs),
                "valid_v2": self.stats["valid_v2"],
                "invalid_v2": self.stats["invalid_v2"],
                "errors": self.stats["errors"]
            }
            registry_data["health"] = "healthy" if self.stats["errors"] == 0 else "warning"
            
            # Сохранение обновлённого реестра
            with open(self.registry_path, 'w', encoding='utf-8') as f:
                json.dump(registry_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Реестр обновлён: {len(honeycombs)} сот, {total_files_all} файлов, {total_size_all:.2f} KB")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления реестра: {e}")
            return False
    
    def _log_stats(self):
        """Логирование статистики"""
        logger.info("=== Статистика сканирования ===")
        logger.info(f"Всего просканировано сот: {self.stats['total_scanned']}")
        logger.info(f"Соответствуют v2.0: {self.stats['valid_v2']}")
        logger.info(f"Не соответствуют v2.0: {self.stats['invalid_v2']}")
        logger.info(f"Ошибок анализа: {self.stats['errors']}")
        
    def test_scan(self) -> bool:
        """Тестовый прогон без изменений реестра"""
        logger.info("Запуск тестового сканирования (без изменений реестра)")
        honeycombs = self.scan_honeycombs()
        
        if honeycombs:
            logger.info("Тестовое сканирование успешно")
            for honeycomb in honeycombs[:3]:  # Показать первые 3
                logger.info(f"  • {honeycomb['honeycomb_id']}: {honeycomb.get('name', 'Unknown')} (v{honeycomb.get('version', '?')})")
            if len(honeycombs) > 3:
                logger.info(f"  ... и ещё {len(honeycombs) - 3} сот")
            return True
        else:
            logger.warning("Тестовое сканирование: соты не найдены")
            return False


def main():
    """Основная функция"""
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python honeycomb_scanner.py scan   # Запустить сканирование и обновить реестр")
        print("  python honeycomb_scanner.py test   # Тестовый прогон без изменений")
        return
    
    command = sys.argv[1]
    scanner = HoneycombScanner()
    
    if command == "scan":
        honeycombs = scanner.scan_honeycombs()
        if honeycombs:
            success = scanner.update_registry(honeycombs)
            if success:
                print("Сканирование и обновление реестра успешно завершены")
            else:
                print("Ошибка обновления реестра")
                sys.exit(1)
        else:
            print("Соты не найдены")
            sys.exit(1)
    
    elif command == "test":
        success = scanner.test_scan()
        if not success:
            sys.exit(1)
    
    else:
        print(f"Неизвестная команда: {command}")
        sys.exit(1)


if name == "main":
    main()
