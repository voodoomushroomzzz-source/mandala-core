import pathlib
path = pathlib.Path('bot.py')
code = path.read_text('utf-8')

# 1. health()
code = code.replace(
    'status = "ready" if _store.get("ready") else "loading"',
    'status = "ready" if any(us.get("ready") for us in _store.values() if isinstance(us, dict)) else "loading"'
)

# 2. store_add_resonance
code = code.replace(
    '        _store[telegram_id]["profile"] = profile\n        # profile.json is the source of truth',
    '        store_set_profile(telegram_id, profile)\n        # profile.json is the source of truth'
)

# 3. _load_user
code = code.replace(
    '        await _sync_pending()  # immediate',
    '        _fire_sync()  # fire-and-forget'
)

# 4. /groups
code = code.replace(
    '    groups = _store.get("groups", {}).get("groups", [])',
    '    groups = store_get_groups(user_id).get("groups", [])'
)

# 5. cmd_profile
import re
old = r'@router\.message\(Command\("profile"\)\)\n@router\.message\(F\.text == "🌾 Профиль"\)\nasync def cmd_profile\(message: Message, state: FSMContext = None\):.*?(?=\n@router\.message\(Command\("resonance"\)\))'
new = '@router.message(Command("profile"))\n@router.message(F.text == "🌾 Профиль")\nasync def cmd_profile(message: Message, state: FSMContext = None):\n    user_id = str(message.from_user.id)\n    await _show_profile(user_id, message)'
code = re.sub(old, new, code, flags=re.DOTALL)

ok1 = 'any(us.get("ready") for us in _store.values()' in code
ok2 = 'store_set_profile(telegram_id, profile)' in code
ok3 = '_fire_sync()  # fire-and-forget' in code
ok4 = 'groups = store_get_groups(user_id).get' in code
ok5 = 'await _show_profile(user_id, message)' in code

for name, ok in [('health',ok1),('store_add_resonance',ok2),('_load_user',ok3),('/groups',ok4),('cmd_profile',ok5)]:
    print(f'{"✅" if ok else "❌"} {name}')

if ok1 and ok2 and ok3 and ok4 and ok5:
    path.write_text(code, 'utf-8')
    print('All 5 fixes applied. bot.py saved.')
else:
    print('Some fixes NOT applied. File unchanged.')
