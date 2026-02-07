import json
import os

def check_resonance():
    # Список критически важных узлов для работы Ядра
    nodes = ['core/roles.json', 'core/state.json', 'core/resonance_frame.md']
    
    print("--- MANDALA CORE: ПРОВЕРКА ЦЕЛОСТНОСТИ ---")
    
    missing_nodes = []
    for node in nodes:
        if os.path.exists(node):
            print(f"[OK] Узел обнаружен: {node}")
        else:
            print(f"[MISSING] Узел отсутствует: {node}")
            missing_nodes.append(node)

    if missing_nodes:
        print(f"--- СТАТУС: РЕЗОНАНС НАРУШЕН (Отсутствует файлов: {len(missing_nodes)}) ---")
        return False

    try:
        with open('core/state.json', 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        entropy = state['current_context']['entropy_index']
        purity = (1 - entropy) * 100
        
        print(f"[OK] Чистота системы (Ахимса): {purity}%")
        print(f"[OK] Активная роль: {state['current_context']['active_role']}")
        print("--- СТАТУС: 100% РЕЗОНАНС УСТАНОВЛЕН ---")
        return True
    except Exception as e:
        print(f"[ERROR] Ошибка чтения состояния: {e}")
        return False

if __name__ == "__main__":
    check_resonance()
