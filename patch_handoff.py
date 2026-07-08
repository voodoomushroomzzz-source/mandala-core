import json
import re

file_path = "honeycombs/sessions/handoff_deepseek.json"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Находим блок session_summary и заменяем его
start = content.find('"session_summary"')
if start == -1:
    print("ERROR: session_summary block not found")
    exit(1)

# Находим конец строки с summary
end = content.find('"', start + 20)
if end == -1:
    print("ERROR: Could not find end of session_summary")
    exit(1)

new_summary = '"session_summary": "Full context transfer after RM-014 v4.1.0 update. Active: Track A (AI-hybrid role 150k+ by July 31) — resume ready, uploaded to hh.ru and Superjob. OpenAI Academy: AI Foundations started (Module 1 completed). Personal project Mandala Symbiosis positioned as key AI portfolio piece. Next tasks: Habr Career and LinkedIn profiles. Global platforms: Remotive, NoDesk, Truly Remote, Indeed, AI Jobs added to roadmap. Focus: AI Ops / Automation Manager roles. Critical rules: pre-check via API, post-check via API, patcher-based updates via Termux.",'

# Заменяем
new_content = content[:start] + new_summary + content[end+1:]

# Также обновляем active_projects
projects_start = new_content.find('"active_projects"')
if projects_start == -1:
    print("ERROR: active_projects block not found")
    exit(1)

# Находим конец блока active_projects
brace_count = 0
in_block = False
projects_end = projects_start
for i in range(projects_start, len(new_content)):
    if new_content[i] == '[' and not in_block:
        in_block = True
    elif in_block:
        if new_content[i] == '[':
            brace_count += 1
        elif new_content[i] == ']':
            if brace_count == 0:
                projects_end = i + 1
                break
            else:
                brace_count -= 1

if projects_end == projects_start:
    print("ERROR: Could not find end of active_projects")
    exit(1)

new_projects = '''"active_projects": [
    {
      "name": "Track A: AI-Hybrid Role Search (150k+ RUB)",
      "path": "honeycombs/roadmaps/active/RM-014_operational_transition.json",
      "version": "v4.1.0",
      "last_updated": "2026-07-07",
      "description": "Two-track roadmap. Track A: AI-hybrid role (AI Ops, Automation Manager) 150 000+ RUB by July 31. Resume ready, uploaded to hh.ru and Superjob. OpenAI Academy: AI Foundations started (Module 1). Next: Habr Career and LinkedIn profiles.",
      "current_focus": "Habr Career profile creation, LinkedIn profile preparation (English version)."
    },
    {
      "name": "Mandala Symbiosis — Personal AI Project",
      "path": "honeycombs/roadmaps/active/RM-014_operational_transition.json#mandala_project",
      "version": "v4.1.0",
      "description": "AI ecosystem with Telegram bot 'Gentle Companion' (Python, 7 users). Integrated AI agents (GPT, Claude, DeepSeek, Kimi, Grok). Positioned as key portfolio piece for AI Operations roles."
    },
    {
      "name": "OpenAI Academy: AI Foundations",
      "path": "external",
      "version": "N/A",
      "description": "Started July 7, 2026. Module 1 completed. Certificate (Credly badge) in progress.",
      "status": "in_progress"
    }
  ]'''

new_content = new_content[:projects_start] + new_projects + new_content[projects_end:]

# Обновляем next_session_plan
plan_start = new_content.find('"next_session_plan"')
if plan_start != -1:
    # Находим конец блока
    brace_count = 0
    in_block = False
    plan_end = plan_start
    for i in range(plan_start, len(new_content)):
        if new_content[i] == '{' and not in_block:
            in_block = True
            brace_count += 1
        elif in_block:
            if new_content[i] == '{':
                brace_count += 1
            elif new_content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    plan_end = i + 1
                    break

    if plan_end != plan_start:
        new_plan = '''"next_session_plan": {
    "priority_1": {
      "title": "Habr Career Profile Creation",
      "description": "Create profile on Habr Career using prepared resume text. Focus on AI Ops positioning.",
      "files": ["honeycombs/roadmaps/active/RM-014_operational_transition.json"]
    },
    "priority_2": {
      "title": "LinkedIn Profile (English)",
      "description": "Prepare and create LinkedIn profile with AI-optimized summary and experience.",
      "files": ["honeycombs/roadmaps/active/RM-014_operational_transition.json"]
    },
    "priority_3": {
      "title": "OpenAI Academy: Module 2",
      "description": "Continue AI Foundations course. Complete Module 2.",
      "files": ["external"]
    }
  }'''
        new_content = new_content[:plan_start] + new_plan + new_content[plan_end:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ handoff_deepseek.json updated successfully")
