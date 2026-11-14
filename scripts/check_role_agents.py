
#!/usr/bin/env python3
"""Проверка ролевых агентов роутера: стиль, контракт ответа, иконка.

Запуск: python -X utf8 scripts/check_role_agents.py [--profile PATH]
Код возврата: 0 - все проверки пройдены, 1 - есть нарушения.

Проверяется (по каждой из 30 ролей матрицы role_delegation):
1. Файл agent.md существует, читается как UTF-8 и не содержит NUL-байтов.
2. Фронтматтер: name совпадает с именем роли, есть description и displayName.
3. Домашний стиль MCode: блок persona, заголовок "# Role:", секции уровня "#"
   (How You Work / Response Format / What You Must Not Do / When To Stop),
   блок "Return:" в конце, длина тела 60-110 строк.
4. Язык: тело английский, ответ на русский - в "# Response Format" первой
   строкой стоит точная инструкция, ключи JSON английские.
5. Машинный контракт: пример ответа разбирается как JSON; у авторских ролей
   есть solution/assumptions/self_tests/risks/confidence, у критических -
   reviews с cid/ac_results/defects/rubric, у дефектов - location/claim/
   evidence/severity.
6. Иконка: avatar.png рядом с промптом, валидный PNG, в фронтматтере строка
   avatar: avatar.png внутри блока x-mavis:.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO / "agents"
PROFILE_AGENTS = Path.home() / ".minimax" / "agents"

# Обязательные роли роутера (авторы и критики общего
# протокола разбора решений): у них обязательный контракт.
# Оставшиеся роли имеют свой контракт по брифу.
AUTHOR = ["architecture", "research", "refactor_plan", "release_note",
          "patch_proposal", "source_synthesis", "triage"]
CRITIC = ["security_verdict", "bulk_process", "fact_check", "expert_review"]
JUDGE = ["verify"]
# Ревью-роли: пишут не решение, а вердикт с находками.
REVIEWER = ["code_review"]
FREE = ["audit", "compliance_check", "second_opinion", "root_cause", "customer_notice",
        "draft", "doc_digest", "summarize", "extract", "rewrite", "locate", "design",
        "log_triage", "classify", "gather", "deep_code_explain",
        "bug_fixer", "design_auditor", "ui_implementer", "ui_researcher"]

SECTIONS = ["# How You Work", "# Response Format", "# What You Must Not Do", "# When To Stop"]
LANG_LINE = "Отвечай на русском. Все ключи JSON — строго английские, как в схеме ниже."
AUTHOR_KEYS = {"solution", "assumptions", "self_tests", "risks", "confidence"}
CRITIC_KEYS = {"cid", "ac_results", "defects", "rubric"}
DEFECT_KEYS = {"location", "claim", "evidence", "severity"}
REVIEWER_KEYS = {"verdict", "findings", "assumptions", "risks", "confidence"}
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_ok(path: Path) -> str:
    """Проверка PNG: сигнатура, CRC чанков, color type, длина распакованного IDAT.

    Раньше иконки ролей делались скриптом с color type 6 (RGBA), а пиксели
    писались по 3 байта (RGB). Файл получался битым: сигнатура верная, рантайм
    отдавал его с 200, но браузер картинку не рисовал - роль оставалась без
    иконки. Поэтому проверяем не только сигнатуру, но и целостность данных.
    """
    import struct
    import zlib
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        return "not a PNG"
    offset = 8
    idat = b""
    width = height = color_type = None
    while offset < len(data):
        if offset + 8 > len(data):
            return "truncated chunk header"
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        ctype = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if offset + 12 + length > len(data):
            return "truncated chunk payload"
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if crc != zlib.crc32(ctype + payload) & 0xFFFFFFFF:
            return "bad CRC in chunk %s" % ctype.decode("ascii", "replace")
        if ctype == b"IHDR":
            width, height, _depth, color_type = struct.unpack(">IIBB", payload[:10])
        if ctype == b"IDAT":
            idat += payload
        offset += 12 + length
    if width is None or not idat:
        return "no IHDR or IDAT"
    try:
        raw = zlib.decompress(idat)
    except zlib.error as exc:
        return "IDAT does not inflate: %s" % exc
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        return "unknown color type %s" % color_type
    expected = height * (1 + width * channels)
    if len(raw) != expected:
        return ("IDAT holds %d bytes, expected %d for %dx%d color type %s"
                % (len(raw), expected, width, height, color_type))
    return ""

PROBLEMS: list[str] = []


def bad(role: str, msg: str) -> None:
    PROBLEMS.append("%s: %s" % (role, msg))


def json_examples(text: str) -> list:
    """Все JSON-объекты из раздела Response Format (fenced и без fence)."""
    m = re.search(r"(?s)# Response Format(.*?)(?=\n# |\Z)", text)
    section = m.group(1) if m else text
    out = []
    for fenced in re.findall(r"(?s)" + chr(96) * 3 + r"json(.*?)" + chr(96) * 3, section):
        try:
            out.append(json.loads(fenced))
        except Exception:
            pass
    if not out:
        depth = 0
        start = None
        for i, ch in enumerate(section):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    chunk = section[start:i + 1]
                    try:
                        out.append(json.loads(chunk))
                    except Exception:
                        pass
                    start = None
    return out


def english_keys(obj) -> bool:
    if isinstance(obj, dict):
        return all(isinstance(k, str) and k.isascii() for k in obj) and all(
            english_keys(v) for v in obj.values())
    if isinstance(obj, list):
        return all(english_keys(v) for v in obj)
    return True


def normalize_agent_text(text: str) -> str:
    """Приводит файл агента к сравнимому виду.

    Рантайм MCode переписывает файл агента: добавляет contextWindow, переносит
    описание на следующую строку и нормализует ссылку модели. Эти правки не
    меняют содержание роли, поэтому при сравнении профиля с репозиторием они
    игнорируются.
    """
    lines = [ln for ln in text.splitlines()
             if not re.match(r"^\s*contextWindow:", ln)]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def matrix_roles() -> set:
    """Роли боевой матрицы (role_delegation) - независимый список ролей.

    Набор агентов должен совпадать с матрицей: иначе удаление каталога
    роли молча уменьшит число проверяемых агентов.
    """
    path = REPO / "router" / "llm-routing.yaml"
    if not path.exists():
        # Публичный репозиторий содержит только ролевой подход - матрицы
        # ролей в нём нет, сверять набор агентов не с чем.
        print("[ок] матрица ролей отсутствует - сверка набора агентов пропущена")
        return set()
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        bad("(матрица)", "матрица ролей не читается: %s" % exc)
        return set()
    matrix = data.get("role_delegation") or {}
    if not isinstance(matrix, dict) or not matrix:
        bad("(матрица)", "в матрице нет секции role_delegation")
        return set()
    return set(matrix.keys())


def check_role(role: str, agents_dir: Path, profile_dir: Path) -> None:
    path = agents_dir / role / "agent.md"
    if not path.exists():
        bad(role, "нет файла agent.md")
        return
    raw = path.read_bytes()
    if b"\x00" in raw:
        bad(role, "в файле NUL-байты")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        bad(role, "файл не UTF-8: %s" % exc)
        return

    if not re.search(r"(?m)^name:\s*" + re.escape(role) + r"\s*$", text):
        bad(role, "в фронтматтере нет name: %s" % role)
    if not re.search(r"(?m)^description:\s*\S", text):
        bad(role, "нет description")
    else:
        # Описание роли - источник выбора для вызывающей модели (она видит
        # реестр через mavis_agent_list). Без явного триггера выбора роль
        # неотличима от соседней по тематике.
        desc = re.search(r"(?m)^description:\s*(.+)$", text).group(1).strip()
        if "Use when:" not in desc:
            bad(role, "в description нет триггера 'Use when:' (роль не выбрать по результату)")
    if not re.search(r"(?m)^\s*displayName:\s*\S", text):
        bad(role, "нет displayName")
    if "{{#if persona.enabled}}" not in text:
        bad(role, "нет блока persona")
    if not re.search(r"(?m)^# Role:\s*\S", text):
        bad(role, "нет заголовка # Role:")
    for sec in SECTIONS:
        if sec not in text:
            bad(role, "нет секции " + sec)
    if not re.search(r"(?m)^Return:", text):
        bad(role, "нет блока Return:")
    body = text.split("---", 2)[-1]
    lines = len(body.splitlines())
    if not (60 <= lines <= 110):
        bad(role, "длина тела %d строк (норма 60-110)" % lines)
    if LANG_LINE not in text:
        bad(role, "нет инструкции о языке ответа")
    ru = len(re.findall(r"[А-Яа-яЁё]", body))
    if ru > 900:
        bad(role, "тело осталось русским (%d кириллических символов)" % ru)

    examples = json_examples(text)
    if not examples:
        bad(role, "в Response Format нет разбираемого JSON-примера")
    else:
        for ex in examples:
            if not english_keys(ex):
                bad(role, "в JSON-примере есть неанглийские ключи")
        if role in AUTHOR:
            if not any(AUTHOR_KEYS <= set(ex) for ex in examples):
                bad(role, "нет авторского контракта %s" % sorted(AUTHOR_KEYS))
        if role in CRITIC:
            ok = False
            for ex in examples:
                reviews = ex.get("reviews") if isinstance(ex, dict) else None
                if isinstance(reviews, list) and reviews:
                    item = reviews[0]
                    if isinstance(item, dict) and CRITIC_KEYS <= set(item):
                        defects = item.get("defects")
                        if isinstance(defects, list) and all(
                                isinstance(d, dict) and DEFECT_KEYS <= set(d) for d in defects):
                            ok = True
            if not ok:
                bad(role, "нет критического контракта reviews[%s] с defects[] (список)" % sorted(CRITIC_KEYS))
        if role in REVIEWER:
            if not any(REVIEWER_KEYS <= set(ex) for ex in examples):
                bad(role, "нет ревью-контракта %s" % sorted(REVIEWER_KEYS))
        if role in JUDGE:
            if not any(isinstance(ex, dict) and "reviews" in ex for ex in examples):
                bad(role, "у судьи нет reviews")

    # иконка
    icon = agents_dir / role / "avatar.png"
    if not icon.exists():
        bad(role, "нет иконки avatar.png")
    else:
        problem = png_ok(icon)
        if problem:
            bad(role, "avatar.png битый: %s" % problem)
    if not re.search(r"(?m)^\s*avatar:\s*avatar\.png\s*$", text):
        bad(role, "во фронтматтере нет avatar: avatar.png")
    xm = re.search(r"(?ms)^x-mavis:\n((?:[ \t]+.*\n)*)", text)
    if xm and "avatar: avatar.png" not in xm.group(1):
        bad(role, "avatar указан не внутри блока x-mavis:")
    # профиль: тот же файл (пропавший агент в профиле - тоже дефект:
    # после обновления MCode каталог роли мог исчезнуть, и гвард обязан это видеть)
    if profile_dir is not agents_dir:
        live = profile_dir / role / "agent.md"
        if not live.exists():
            bad(role, "в профиле нет агента (%s) - доставка неполная" % live)
        elif normalize_agent_text(live.read_text(encoding="utf-8")) != normalize_agent_text(
                raw.decode("utf-8") if isinstance(raw, bytes) else raw):
            bad(role, "профиль отличается от репозитория (запустите mcode_sync.py --force)")
        live_icon = profile_dir / role / "avatar.png"
        if not live_icon.exists():
            bad(role, "в профиле нет иконки (%s)" % live_icon)
        elif icon.exists() and live_icon.read_bytes() != icon.read_bytes():
            bad(role, "иконка в профиле отличается от репозитория")


def check_skill_channel() -> None:
    """Скилл должен передавать роль голым именем агента.

    При вызове с префиксом плагина (`<плагин>:<роль>`) дочерняя сессия
    получает встроенного исполнителя: личность роли теряется, и в панели
    субагентов вместо роли показывается встроенный агент.
    """
    skill = REPO / "skills" / "task-decomposition" / "SKILL.md"
    if not skill.exists():
        return
    txt = skill.read_text(encoding="utf-8", errors="replace")
    if "agent_name=<роль>" not in txt:
        bad("(скилл)", "в SKILL.md нет правила agent_name=<роль>")
    if "task-decomposition:" in txt:
        bad("(скилл)", "в SKILL.md встречается вызов роли с префиксом плагина")
    # Скилл - памятка процедуры, а не дубль глобального контракта: держать его
    # компактным, без копий правил пункта 15/18/19.
    size = skill.stat().st_size
    if size > 5120:
        bad("(скилл)", "SKILL.md раздулся: %d байт (порог 5120) - дубли глобального контракта" % size)
    # Dynamic Workflow не используется: нужен официальный CLI MCode, запуск
    # только вручную в dashboard, а выбор роли в ctx.agent не документирован.
    if re.search(r"(?i)dynamic[ -]?workflow", txt):
        bad("(скилл)", "в SKILL.md осталось упоминание Dynamic Workflow - механизм нерабочий")
    if "mavis_agent_list" not in txt:
        bad("(скилл)", "в SKILL.md нет указания, где взять список ролей (mavis_agent_list)")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=str(PROFILE_AGENTS))
    ap.add_argument("--no-profile", action="store_true",
                    help="не сверять с профилем (только репозиторий)")
    args = ap.parse_args()
    profile_dir = Path(args.profile)
    roles = sorted(p.name for p in AGENTS_DIR.iterdir() if p.is_dir()) if AGENTS_DIR.is_dir() else []
    if not roles:
        print("НЕТ КАТАЛОГА АГЕНТОВ:", AGENTS_DIR)
        return 1
    required = matrix_roles()
    if required:
        for role in sorted(required - set(roles)):
            bad("(матрица)", "роль есть в матрице, но нет агента: %s" % role)
        for role in sorted(set(roles) - required):
            bad("(матрица)", "агент есть, но такой роли нет в матрице: %s" % role)
    for role in roles:
        check_role(role, AGENTS_DIR, profile_dir if not args.no_profile else AGENTS_DIR)
    check_skill_channel()
    print("=== check_role_agents: проверено ролей %d (в матрице %d) ===" % (len(roles), len(required)))
    if PROBLEMS:
        for p in PROBLEMS:
            print(" -", p)
        print("ИТОГ: FAIL (%d)" % len(PROBLEMS))
        return 1
    print("ИТОГ: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
