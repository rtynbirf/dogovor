#!/usr/bin/env python3
"""ДОГОВОР-ФСМ v1 · автомат статусов правил агента.

Форма карточки (6 строк, зерно коллеги-оппонента): кто / действие / условия /
результат / при_сбое / пересмотр. Эмерджентная добавка дома: у карточки есть
происхождение (правило без шрама или канона = настроение) и статус с датой.

Статусы: ЗАЯВЛЕНА → ПИЛОТ → {ПОДТВЕРЖДЕНО, СНЕСЕНА, ЗАМЕНЕНА}; ЗАМЕНЕНА → ПИЛОТ;
СНЕСЕНА — терминал. ПОДТВЕРЖДЕНО даёт только ≥2 разных исполнителей в реальных
случаях; чтение и критика исполнением не считаются.

Вердикты: ЧИТАЕМО / КАРТОЧКА КРИВАЯ / СТАТУС ЛОЖЕН / ПЕРЕХОД ЗАПРЕЩЁН /
ГРАНИЦА НЕ ПРИОСТАНАВЛИВАЕТСЯ.

Python 3.9+, stdlib only.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

FIELDS = ("кто", "действие", "условия", "результат", "при_сбое", "пересмотр")
LIMITS = {"кто": 15, "действие": 30, "условия": 25, "результат": 25, "при_сбое": 25, "пересмотр": 15}
TOTAL_LIMIT = 130
STATUSES = ("ЗАЯВЛЕНА", "ПИЛОТ", "ПОДТВЕРЖДЕНО", "СНЕСЕНА", "ЗАМЕНЕНА")
TRANSITIONS = {
    ("ЗАЯВЛЕНА", "ПИЛОТ"), ("ПИЛОТ", "ПОДТВЕРЖДЕНО"), ("ПИЛОТ", "СНЕСЕНА"),
    ("ПИЛОТ", "ЗАМЕНЕНА"), ("ПОДТВЕРЖДЕНО", "ЗАМЕНЕНА"), ("ПОДТВЕРЖДЕНО", "СНЕСЕНА"),
    ("ЗАМЕНЕНА", "ПИЛОТ"),
}
TERMINALS = {"СНЕСЕНА"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _words(text):
    return len([w for w in re.split(r"\s+", str(text)) if w])


def check_card(card, today=None):
    """Возвращает (вердикт, причины)."""
    today = today or date.today()
    if not isinstance(card, dict):
        return "КАРТОЧКА КРИВАЯ", ["карточка не словарь"]
    curve, lies = [], []  # две корзины причин: кривая форма и ложный статус (Е29: классы явные)
    for f in FIELDS:
        v = card.get(f)
        if not isinstance(v, str) or not v.strip():
            curve.append(f"поле пусто: {f}")
        elif _words(v) > LIMITS[f]:
            curve.append(f"лимит слов поля {f}: {_words(v)} > {LIMITS[f]}")
    total = sum(_words(card.get(f, "")) for f in FIELDS)
    if total > TOTAL_LIMIT:
        curve.append(f"лимит читаемости карточки: {total} > {TOTAL_LIMIT} слов")
    if not isinstance(card.get("происхождение"), str) or not card.get("происхождение", "").strip():
        curve.append("правило без происхождения = настроение")
    st = card.get("статус")
    if st not in STATUSES:
        lies.append(f"статус неизвестен: {st!r}")
        return "СТАТУС ЛОЖЕН", lies
    de = card.get("дата_конца")
    if st == "ПИЛОТ":
        if not isinstance(de, str) or not ISO.match(de or ""):
            lies.append("ПИЛОТ без даты конца — правило без срока = вечный закон")
        else:
            try:
                if date.fromisoformat(de) <= today:
                    lies.append(f"дата конца пилота в прошлом: {de}")
            except ValueError:
                lies.append(f"дата конца не ISO: {de!r}")
    if st == "ПОДТВЕРЖДЕНО":
        execs = card.get("исполнители") or []
        if not isinstance(execs, list) or len({str(e) for e in execs}) < 2:
            lies.append("ПОДТВЕРЖДЕНО требует ≥2 разных исполнителей реальных случаев")
    reasons = lies + curve
    if reasons:
        return ("СТАТУС ЛОЖЕН" if lies else "КАРТОЧКА КРИВАЯ"), reasons
    return "ЧИТАЕМО", []


def transition(old, new):
    if old in TERMINALS:
        return "ПЕРЕХОД ЗАПРЕЩЁН", [f"{old} — терминал"]
    if (old, new) not in TRANSITIONS:
        return "ПЕРЕХОД ЗАПРЕЩЁН", [f"{old} → {new} не в таблице"]
    if new == "ПОДТВЕРЖДЕНО":
        return "ПЕРЕХОД ЗАПРЕЩЁН", ["переход в ПОДТВЕРЖДЕНО даёт только check_card с ≥2 исполнителями"]
    return "ПЕРЕХОД ЛЕГАЛЕН", []


def veto_suspend_boundary(tries_to_suspend):
    return ("ГРАНИЦА НЕ ПРИОСТАНАВЛИВАЕТСЯ", ["жёсткие границы не приостанавливаются вето непонимания"]) \
        if tries_to_suspend else ("ВЕТО ЛЕГАЛЕН", [])


def selftest():
    today = date.today()
    ok = fail = 0

    def vector(name, got_verdict, want_verdict):
        nonlocal ok, fail
        if got_verdict == want_verdict:
            ok += 1
            print(f"  вектор {ok + fail}: {name} -> {got_verdict} [OK]")
        else:
            fail += 1
            print(f"  вектор {ok + fail}: {name} -> {got_verdict}, ожидалось {want_verdict} [ПРОВАЛ]")

    base = {"кто": "любой агент дома", "действие": "исполняет правило как записано",
            "условия": "при живой пробе ключа", "результат": "зелёная проба до первого вызова",
            "при_сбое": "запись в реестр с корнем и правилом, без имени",
            "пересмотр": "через 2 недели",
            "происхождение": "закон №11 дома; I6", "статус": "ПИЛОТ",
            "дата_конца": str(date.fromordinal(today.toordinal() + 14)), "исполнители": ["Z.ai"]}
    v, _ = check_card(base, today); vector("валидная карточка", v, "ЧИТАЕМО")
    c = dict(base); del c["условия"]; v, _ = check_card(c, today); vector("пропущено поле", v, "КАРТОЧКА КРИВАЯ")
    c = dict(base); c["действие"] = "слово " * 31; v, _ = check_card(c, today); vector("перелимит слов поля", v, "КАРТОЧКА КРИВАЯ")
    c = dict(base); del c["дата_конца"]; v, _ = check_card(c, today); vector("ПИЛОТ без даты конца", v, "СТАТУС ЛОЖЕН")
    c = dict(base); c["дата_конца"] = "2020-01-01"; v, _ = check_card(c, today); vector("дата конца в прошлом", v, "СТАТУС ЛОЖЕН")
    c = dict(base); c["статус"] = "ПОДТВЕРЖДЕНО"; del c["дата_конца"]; v, _ = check_card(c, today); vector("ПОДТВЕРЖДЕНО с одним исполнителем", v, "СТАТУС ЛОЖЕН")
    c = dict(base); c["исполнители"] = ["A", "B"]; c["статус"] = "ПОДТВЕРЖДЕНО"; del c["дата_конца"]; v, _ = check_card(c, today); vector("ПОДТВЕРЖДЕНО с двумя исполнителями", v, "ЧИТАЕМО")
    c = dict(base); c["происхождение"] = ""; v, _ = check_card(c, today); vector("карточка без происхождения", v, "КАРТОЧКА КРИВАЯ")
    c = dict(base); c["статус"] = "ВЕЧНЫЙ ЗАКОН"; v, _ = check_card(c, today); vector("неизвестный статус", v, "СТАТУС ЛОЖЕН")
    v, _ = transition("ЗАЯВЛЕНА", "ПОДТВЕРЖДЕНО"); vector("ЗАЯВЛЕНА→ПОДТВЕРЖДЕНО", v, "ПЕРЕХОД ЗАПРЕЩЁН")
    v, _ = transition("СНЕСЕНА", "ПИЛОТ"); vector("СНЕСЕНА→ПИЛОТ (терминал)", v, "ПЕРЕХОД ЗАПРЕЩЁН")
    v, _ = transition("ПИЛОТ", "ПОДТВЕРЖДЕНО"); vector("ПИЛОТ→ПОДТВЕРЖДЕНО без исполнителей", v, "ПЕРЕХОД ЗАПРЕЩЁН")
    v, _ = transition("ПИЛОТ", "СНЕСЕНА"); vector("ПИЛОТ→СНЕСЕНА", v, "ПЕРЕХОД ЛЕГАЛЕН")
    v, _ = transition("ЗАМЕНЕНА", "ПИЛОТ"); vector("ЗАМЕНЕНА→ПИЛОТ (новая волна)", v, "ПЕРЕХОД ЛЕГАЛЕН")
    v, _ = veto_suspend_boundary(True); vector("вето пытается снять границу", v, "ГРАНИЦА НЕ ПРИОСТАНАВЛИВАЕТСЯ")
    v, _ = veto_suspend_boundary(False); vector("вето называет шаг правила", v, "ВЕТО ЛЕГАЛЕН")

    print(f"ДОГОВОР: векторы {ok}/{ok + fail}; незаконные переходы пойманы; все вердикты достижимы")
    return fail == 0


def check_dir(path):
    path = Path(path)
    cards = sorted(path.glob("*.json"))
    if not cards:
        print("КАРТОЧЕК НЕТ — договор пуст")
        return False
    bad = 0
    seen = set()
    for f in cards:
        try:
            card = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"{f.name}: КАРТОЧКА КРИВАЯ (json: {e})"); bad += 1; continue
        cid = card.get("id", f.name)
        if cid in seen:
            print(f"{f.name}: КАРТОЧКА КРИВАЯ (дубль id {cid!r})"); bad += 1; continue
        seen.add(cid)
        v, reasons = check_card(card)
        print(f"{f.name} [{card.get('статус')} до {card.get('дата_конца', '—')}]: {v}")
        for r in reasons:
            print(f"  - {r}")
        bad += v != "ЧИТАЕМО"
    print(f"ДОГОВОР: карточек {len(cards)}, ЧИТАЕМО {len(cards) - bad}, кривых {bad}")
    return bad == 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args or not args:
        sys.exit(0 if selftest() else 1)
    if "--check" in args:
        i = args.index("--check")
        sys.exit(0 if check_dir(args[i + 1]) else 1)
    print(__doc__)
    sys.exit(2)
