#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Установка ролевого подхода в профиль MiniMax Code.

Что ставится:
  agents/<роль>/agent.md  ->  <DATA_DIR>/agents/<роль>/agent.md
  agents/<роль>/avatar.png->  <DATA_DIR>/agents/<роль>/avatar.png
  skills/task-decomposition/SKILL.md
                           ->  <DATA_DIR>/skills/task-decomposition/SKILL.md

Зачем так:
  * роль = имя агента в профиле: сессия субагента получает имя роли,
    а в панели - иконку роли (у агента из плагина личность терялась,
    сессия становилась встроенным worker-ом);
  * скилл в профиле - штатное место пользовательских скиллов, он виден
    всем агентам и работает без плагина;
  * плагин не нужен: ни Python на машине запуска, ни ключей, ни сети.

Запуск:
  python -X utf8 scripts/install_roles.py            # поставить
  python -X utf8 scripts/install_roles.py --dry-run  # только показать
  python -X utf8 scripts/install_roles.py --check    # только проверить
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_SRC = REPO / "agents"
SKILL_SRC = REPO / "skills" / "task-decomposition" / "SKILL.md"
SKILL_NAME = "task-decomposition"
AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

PROBLEMS: list[str] = []
CHANGES: list[str] = []


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    out = {}
    key = None
    for line in parts[1].splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key = m.group(1)
            out[key] = m.group(2).strip().strip(chr(34))
        elif key and line.startswith((" ", "\t")):
            out[key] = (out.get(key, "") + " " + line.strip()).strip()
    return out


def runtime_catalog(profile: Path) -> set:
    """Модели из config.yaml рантайма (если файл есть)."""
    cfg = profile / "config.yaml"
    if not cfg.exists():
        return set()
    try:
        import yaml
    except ImportError:
        return set()
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return set()
    out = set()
    providers = (data or {}).get("providers") or {}
    if isinstance(providers, dict):
        for pid, blk in providers.items():
            if not isinstance(blk, dict):
                continue
            for mid in (blk.get("models") or {}):
                out.add(str(pid) + "/" + str(mid))
    return out


def install_file(src: Path, dst: Path, dry_run: bool, check_only: bool) -> str:
    """Возвращает ок / обновлено / расхождение / нет."""
    if not src.exists():
        PROBLEMS.append("нет файла-источника: %s" % src)
        return "нет"
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        return "ок"
    if check_only:
        return "расхождение"
    if dry_run:
        return "обновлено"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return "обновлено"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=os.environ.get("MINIMAX_DATA_DIR")
                    or str(Path.home() / ".minimax"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="только проверить, ничего не писать")
    args = ap.parse_args()
    profile = Path(args.profile)
    if not AGENTS_SRC.is_dir():
        print("НЕТ КАТАЛОГА АГЕНТОВ: %s" % AGENTS_SRC, file=sys.stderr)
        return 2

    roles = sorted(p.name for p in AGENTS_SRC.iterdir() if p.is_dir())
    if not roles:
        print("РОЛЕЙ НЕТ: %s" % AGENTS_SRC, file=sys.stderr)
        return 2

    catalog = runtime_catalog(profile)
    for role in roles:
        src_dir = AGENTS_SRC / role
        agent_md = src_dir / "agent.md"
        if not agent_md.exists():
            PROBLEMS.append("роль %s: нет agent.md" % role)
            continue
        if not AGENT_NAME_RE.match(role):
            PROBLEMS.append("роль %s: недопустимое имя" % role)
            continue
        text = agent_md.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if fm.get("name") != role:
            PROBLEMS.append("роль %s: имя во фронтматтере != имя каталога" % role)
        if not fm.get("description"):
            PROBLEMS.append("роль %s: пустое description" % role)
        model = (fm.get("model") or "").strip()
        if not model:
            PROBLEMS.append("роль %s: не задана модель (model) - роль останется на AUTO" % role)
        else:
            short = model[len("custom_provider:"):] if model.startswith("custom_provider:") else model
            if catalog and short not in catalog:
                PROBLEMS.append("роль %s: модель %s нет в каталоге рантайма - вызов упадёт с MODEL_SELECTION_INVALID" % (role, short))
        dst_dir = profile / "agents" / role
        state = install_file(agent_md, dst_dir / "agent.md", args.dry_run, args.check)
        if state != "ок":
            CHANGES.append("agents/%s/agent.md: %s" % (role, state))
        icon = src_dir / "avatar.png"
        if not icon.exists():
            PROBLEMS.append("роль %s: нет иконки avatar.png" % role)
        else:
            state = install_file(icon, dst_dir / "avatar.png", args.dry_run, args.check)
            if state != "ок":
                CHANGES.append("agents/%s/avatar.png: %s" % (role, state))

    skill_dst = profile / "skills" / SKILL_NAME / "SKILL.md"
    if not SKILL_SRC.exists():
        PROBLEMS.append("нет скилла: %s" % SKILL_SRC)
    else:
        state = install_file(SKILL_SRC, skill_dst, args.dry_run, args.check)
        if state != "ок":
            CHANGES.append("skills/%s/SKILL.md: %s" % (SKILL_NAME, state))

    print("=== install_roles: профиль %s ===" % profile)
    print("ролей: %d, скилл: %s" % (len(roles), SKILL_NAME))
    if CHANGES:
        for c in CHANGES:
            print(" -", c)
    else:
        print("изменений нет: всё идентично")
    if PROBLEMS:
        for p in PROBLEMS:
            print(" !", p)
        print("ИТОГ: FAIL (%d)" % len(PROBLEMS))
        return 1
    print("ИТОГ: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())