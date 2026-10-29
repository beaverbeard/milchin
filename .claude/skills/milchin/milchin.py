#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""milchin.py — детерминированная типографика и юникод-гигиена русского текста.

Скрипт-«типограф». Чистый Python 3 stdlib (re, unicodedata, sys, argparse) —
без внешних зависимостей.

Имя — в честь Аркадия Эммануиловича Мильчина, автора «Справочника издателя и
автора», канонического свода по русской типографике и оформлению.

Назначение: применить ТОЛЬКО детерминированные («ДА» / надёжные, и «частично» под
флагом) правила типографики, не трогая зону смысла/грамматики (это работа LLM/человека).

=============================================================================
РЕАЛИЗОВАННЫЕ ПРАВИЛА (детерминированно, автозамена)
=============================================================================
Ряды правил: T (типографика), D (расширенная типографика), W (веб/юникод-гигиена),
             S (научно-техническое). Полные обоснования и риски — в README.

Защита зон (КРИТИЧНО, до любой типографики, восстановление после — W11/W12):
  - inline-code `...`, fenced ```...```  -> плейсхолдеры (содержимое не трогаем)
  - URL (http/https/<URL>)               -> плейсхолдеры
  - markdown-ссылки [текст](url)         -> текст типографим, url НЕ трогаем
  - @mentions, #hashtags                 -> плейсхолдеры

Юникод-гигиена (WEB):
  W9  — NFC-нормализация входа (не NFKC/NFKD)
  W3  — strip ведущего BOM (U+FEFF)
  W2  — удаление zero-width / invisible (U+200B,200C,2060,FEFF,00AD,200E,200F,2061-2064)
  W14 — soft hyphen U+00AD -> удалить
  W15 — узкие пробелы U+202F,U+2009,U+2007 -> NBSP/обычный
  W6  — mojibake closed-list (a-dash->em, a-apos->апостроф, a-laquo->«, a-hellip->…, Â+sp->NBSP)
  W1  — омоглифы: латиница внутри кириллического токена -> кириллица (TR39 confusables)
  W4  — англ. «умные» кавычки в рус. контексте -> ёлочки

Базовая типографика (T-ряд):
  T14 — двойные/множественные пробелы -> один
  T15 — пробел перед .,;:!?»)  -> убрать
  T16 — пробел после «(        -> убрать
  T1  — прямые " -> «ёлочки» (с учётом вложенности -> „лапки")
  T3  — дефис между словами (с пробелами) -> em-dash
  T4  — числовой диапазон \\d-\\d -> en-dash (без пробелов)
  T5  — NBSP после однобуквенных предлогов/союзов
  T6  — NBSP между числом и единицей/знаком (кг, %, ₽, № ...)
  T9  — NBSP перед em-dash
  T11 — сокращения «т. е.», «и т. д.», «и т. п.», «в т. ч.» -> NBSP внутри
  T12 — многоточие ... -> …

Научно-техническое (S-ряд, безопасные):
  S1  — знак умножения единиц x/х/* -> · (между обозначениями единиц)
  S6  — угловые градусы/мин/сек слитно с числом (20°), НО °C/°F не трогаем
  S23 — рег. номер № + NBSP перед числом

Из typograf.js (TG-ряд, безопасные):
  TG1 — `!!` -> `!` (ровно два)        TG2 — `!?` -> `?!`
  TG3 — сдвоенные `,,` `;;` `??` -> один (`::` и `..` не трогаем)
  TG4 — `?…`/`!…` -> `?..`/`!..`
  TG5 — NBSP после стр./гл./рис./кв./см./г./ул., § + номер, римское + в./вв.
  TG6 — диапазоны годов (гг.), веков (вв.), дней (+ месяц) -> en-dash без пробелов
  TG7 — наращение после цифры: `25-ый` -> `25-й`, `90-ые` -> `90-е`, `5-ого` -> `5-го`
  TG8 — хвостовые пробелы в конце строки -> убрать

Спорные — под флагами конфига (дефолты = рус. веб-традиция):
  --percent-space  (T7)  : по умолчанию OFF (слитно «10%»)
  --no-initials-space (T10): по умолчанию инициалы с NBSP («А. С. Пушкин»)
  --ruble          (TG9) : по умолчанию OFF («5 руб.» -> «5 ₽»)
  --iso-dates      (TG10): по умолчанию OFF (2026-06-09 -> 09.06.2026)

=============================================================================
НЕ РЕАЛИЗОВАНО (зона LLM/человека — НЕ автозаменяем)
=============================================================================
  - Минус U+2212 в формулах/температуре (T17, S11): дефис vs минус неотличимы без смысла.
  - Разряды больших чисел (T8/D1): риск задеть годы, телефоны, ID.
  - Десятичный разделитель .->, (T23/D2): неотличим от версий/дат/IP — ВЫСОКИЙ риск.
  - Прямая речь, перестановка знаков у кавычек (T18).
  - Буква ё (T22), выбор наращения по грамматике (T21/D3; TG7 только укорачивает
    заведомо лишние буквы), -тся/-ться (O2), н/нн (O3),
    «не» слитно/раздельно (O4), смысловая пунктуация (O9-O11).
  - Единообразие по документу (D35-D37, S17/S18) — это детект, не автоправка.
  - HTML-сущности (W5) — зависит от parse_mode публикации; по умолчанию не трогаем.
  - Эмодзи VS-нормализация (W8) — стиль.
Полные обоснования и риски — в указанных спеках.
"""

import argparse
import os
import re
import sys
import tempfile
import unicodedata

# ---------------------------------------------------------------------------
# Символьные константы (через escape, чтобы файл был устойчив к копированию)
# ---------------------------------------------------------------------------
NBSP = " "        # неразрывный пробел
EMDASH = "—"      # em-dash
ENDASH = "–"      # en-dash
ELLIPSIS = "…"    # …
LAQUO, RAQUO = "«", "»"   # « »
LDQUO, RDQUO = "„", "“"   # „ "  (рус. вложенные «лапки»)
MULSIGN = "·"     # · знак умножения
APOS = "’"        # апостроф
DEGREE = "°"      # °

# Однобуквенные предлоги/союзы (T5)
ONE_LETTER = "аиовкосуя" \
             "АИОВКОСУЯ"

# Единицы/знаки для NBSP число+единица (T6/D14/D16/D17)
UNIT_TOKENS = [
    "кг", "г", "км", "см", "мм", "м", "т", "л", "мл", "ч", "мин", "с",
    "млн", "млрд", "трлн", "тыс", "₽", "$", "€", "%", DEGREE, "№", "§",
]

# Confusables (W1, Unicode TR39) — латиница -> кириллица. Только однозначные пары.
LAT_TO_CYR = {
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р",
    "x": "х", "y": "у",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н",
    "K": "К", "M": "М", "O": "О", "P": "Р", "T": "Т",
    "X": "Х", "Y": "У",
}

# Zero-width / invisible (W2). U+200D (ZWJ), U+FE0F НЕ трогаем (клей эмодзи, W7).
ZERO_WIDTH = {
    "​", "‌", "⁠", "­",  # ZWSP, ZWNJ, WJ, soft-hyphen(W14)
    "‎", "‏",                       # LRM, RLM
    "⁡", "⁢", "⁣", "⁤",   # math invisibles
}
BOM = "﻿"

# Узкие/тонкие пробелы (W15): U+202F -> NBSP; U+2009/U+2007 -> обычный
NARROW_SPACES = {" ": NBSP, " ": " ", " ": " "}

# Mojibake closed-list (W6) — только безопасные однозначные
MOJIBAKE = [
    ("â€”", EMDASH),    # a-trema + euro + ldq  -> em-dash
    ("â€“", EMDASH),
    ("â€™", APOS),      # -> апостроф
    ("â€œ", LAQUO),     # -> «
    ("â€¦", ELLIPSIS),  # -> …
    ("Â ", NBSP),            # Â + NBSP -> NBSP
    ("Â ", NBSP),                 # Â + space -> NBSP
]

# Сентинелы плейсхолдеров — Private Use Area
PH_OPEN = ""
PH_CLOSE = ""


class Counter:
    """Внутренний счётчик правок по ID правила."""

    def __init__(self):
        self.counts = {}

    def add(self, rule, n=1):
        if n:
            self.counts[rule] = self.counts.get(rule, 0) + n

    def total(self):
        return sum(self.counts.values())

    def summary_lines(self):
        if not self.counts:
            return ["milchin: правок нет"]
        lines = ["milchin: правок всего {}".format(self.total())]
        for rule in sorted(self.counts):
            lines.append("  {:<6} {}".format(rule, self.counts[rule]))
        return lines


# ---------------------------------------------------------------------------
# ЗАЩИТА ЗОН (W11 / W12)
# ---------------------------------------------------------------------------
class ZoneProtector:
    """Вырезает защищённые зоны в плейсхолдеры, восстанавливает после.

    Для markdown-ссылок [текст](url): текст остаётся в потоке (типографим),
    маскируется только url.
    """

    def __init__(self):
        self.store = []
        self.ph_re = re.compile(re.escape(PH_OPEN) + r"(\d+)" + re.escape(PH_CLOSE))

    def _stash(self, text):
        idx = len(self.store)
        self.store.append(text)
        return PH_OPEN + str(idx) + PH_CLOSE

    def mask(self, text):
        # 0. YAML-фронтматтер в начале файла: `---` … `---`. Кавычки/двоеточия там —
        #    синтаксис YAML, не типографика; ёлочки сломали бы парсинг. Маскируем целиком.
        text = re.sub(r"\A---\r?\n.*?\r?\n---(?=\r?\n|\Z)",
                      lambda m: self._stash(m.group(0)), text, flags=re.DOTALL)
        # 1. fenced code blocks
        text = re.sub(r"```.*?```|~~~.*?~~~",
                      lambda m: self._stash(m.group(0)), text, flags=re.DOTALL)
        # 2. inline code (учёт двойных бэктиков)
        text = re.sub(r"(`+)(?:(?!\1).)*?\1",
                      lambda m: self._stash(m.group(0)), text, flags=re.DOTALL)
        # 3. markdown-ссылка [текст](url): текст НЕ маскируем, url — да
        def _link(m):
            inner, url = m.group(1), m.group(2)
            return "[" + inner + "](" + self._stash(url) + ")"
        text = re.sub(r"\[([^\]]*)\]\(([^)]+)\)", _link, text)
        # 4. угловые ссылки <url>
        text = re.sub(r"<https?://[^>\s]+>",
                      lambda m: self._stash(m.group(0)), text)
        # 5. голые URL
        text = re.sub(r"https?://[^\s<>\)\]]+",
                      lambda m: self._stash(m.group(0)), text)
        # 6. @mentions и #hashtags (W11)
        text = re.sub(r"(?<!\w)@[\w_]+",
                      lambda m: self._stash(m.group(0)), text)
        text = re.sub(r"(?<!\w)#[\w]+",
                      lambda m: self._stash(m.group(0)), text)
        return text

    def unmask(self, text):
        prev = None
        while prev != text:
            prev = text
            text = self.ph_re.sub(lambda m: self.store[int(m.group(1))], text)
        return text


# ---------------------------------------------------------------------------
# ЮНИКОД-ГИГИЕНА (WEB-ряд)
# ---------------------------------------------------------------------------
def rule_W9_nfc(text, c):
    """W9 — NFC-нормализация (не NFKC/NFKD)."""
    out = unicodedata.normalize("NFC", text)
    if out != text:
        c.add("W9")
    return out


def rule_W3_bom(text, c):
    """W3 — strip ведущего BOM U+FEFF."""
    if text.startswith(BOM):
        c.add("W3")
        return text[1:]
    return text


def rule_W2_zerowidth(text, c):
    """W2 — удалить zero-width/invisible (кроме ZWJ/VS-16). W14 (soft hyphen)."""
    out = []
    n = 0
    for ch in text:
        if ch in ZERO_WIDTH or ch == BOM:  # не-ведущий BOM = мусор
            n += 1
            continue
        out.append(ch)
    if n:
        c.add("W2", n)
    return "".join(out)


def rule_W15_narrow(text, c):
    """W15 — узкие/тонкие пробелы -> NBSP/обычный."""
    n = 0
    for src, dst in NARROW_SPACES.items():
        cnt = text.count(src)
        if cnt:
            text = text.replace(src, dst)
            n += cnt
    if n:
        c.add("W15", n)
    return text


def rule_W6_mojibake(text, c):
    """W6 — mojibake closed-list."""
    n = 0
    for src, dst in MOJIBAKE:
        cnt = text.count(src)
        if cnt:
            text = text.replace(src, dst)
            n += cnt
    if n:
        c.add("W6", n)
    return text


_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _is_cyrillic(ch):
    return "CYRILLIC" in unicodedata.name(ch, "")


def _is_latin(ch):
    return "LATIN" in unicodedata.name(ch, "")


def rule_W1_homoglyphs(text, c):
    """W1 — латиница внутри кириллического токена -> кириллица.

    Трогаем ТОЛЬКО смешанные токены, где все латинские буквы имеют confusable-аналог.
    Чистая латиница (iPhone, On Media) не трогается.
    """
    n = [0]

    def fix(m):
        tok = m.group(0)
        has_cyr = any(_is_cyrillic(ch) for ch in tok)
        has_lat = any(_is_latin(ch) for ch in tok)
        if not (has_cyr and has_lat):
            return tok
        lat_chars = [ch for ch in tok if _is_latin(ch)]
        if not all(ch in LAT_TO_CYR for ch in lat_chars):
            return tok
        out = "".join(LAT_TO_CYR.get(ch, ch) if _is_latin(ch) else ch for ch in tok)
        if out != tok:
            n[0] += 1
        return out

    text = _TOKEN_RE.sub(fix, text)
    if n[0]:
        c.add("W1", n[0])
    return text


def rule_W4_curly_quotes(text, c):
    """W4 — англ. «умные» парные кавычки -> ёлочки. Апостроф ’ в латыни не трогаем."""
    n = [0]

    def dq(m):
        n[0] += 1
        return LAQUO + m.group(1) + RAQUO

    text = re.sub("“([^“”]*)”", dq, text)
    if n[0]:
        c.add("W4", n[0])
    return text


# ---------------------------------------------------------------------------
# ПРОБЕЛЫ (T14, T15, T16)
# ---------------------------------------------------------------------------
def rule_T14_multispace(text, c):
    """T14 — двойные/множественные обычные пробелы -> один (NBSP не трогаем).

    Только в середине строки (`(?<=\\S)`): ведущий отступ не схлопываем — он значим
    в markdown (вложенные списки, indented-блоки).
    """
    n = [0]

    def sub(m):
        n[0] += 1
        return " "

    text = re.sub(r"(?<=\S)\x20{2,}", sub, text)
    if n[0]:
        c.add("T14", n[0])
    return text


def rule_T15_space_before_punct(text, c):
    """T15 — пробел перед .,;:!?»)  -> убрать."""
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1)

    text = re.sub(r"[ \t]+([.,;:!?»\)])", sub, text)
    if n[0]:
        c.add("T15", n[0])
    return text


def rule_T16_space_after_open(text, c):
    """T16 — пробел после «( -> убрать."""
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1)

    text = re.sub(r"([«\(])[ \t]+", sub, text)
    if n[0]:
        c.add("T16", n[0])
    return text


# Буква (кир/лат) — для T24. \w не годится: захватывает цифры и `_`.
_LETTER = r"[A-Za-zА-Яа-яЁё]"


def rule_T24_space_after_punct(text, c):
    """T24 — вставить пробел после `,;:!?`, если знак слиплся со следующим словом.

    Зеркало T15 (там убираем пробел ПЕРЕД знаком). Частая опечатка быстрого набора:
    «Короче,рассказываю» -> «Короче, рассказываю».

    Безопасно по построению: триггерит только перед БУКВОЙ. Цифра после знака не
    трогается — это исключает десятичные дроби (3,14), время (14:30), счёт (3:4),
    разряды (1,500). Эмотиконы (`:)`, `:(`), `?!` перед не-буквой — мимо.
    Точку НЕ трогаем сознательно: аббревиатуры (т.д.), расширения (readme.md),
    дроби и инициалы дали бы ложные срабатывания.
    """
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1) + " "

    text = re.sub(r"([,;:!?])(?=" + _LETTER + r")", sub, text)
    if n[0]:
        c.add("T24", n[0])
    return text


# ---------------------------------------------------------------------------
# КАВЫЧКИ (T1, T2)
# ---------------------------------------------------------------------------
def rule_T1_quotes(text, c):
    """T1/T2 — прямые " -> «ёлочки», вложенные -> „лапки".

    Защита: не трогать дюймы (цифра+"). Балансировка уровней.
    """
    n = [0]

    def process(s):
        result = []
        depth = 0
        chars = list(s)
        for i, ch in enumerate(chars):
            if ch == '"':
                prev = chars[i - 1] if i > 0 else ""
                if depth == 0:
                    if prev.isdigit():        # дюймы 5"
                        result.append(ch)
                        continue
                    result.append(LAQUO)
                    depth = 1
                    n[0] += 1
                elif depth == 1:
                    # пробел/открывающая перед " -> открываем вложенный уровень
                    if prev in (" ", NBSP, "(", LAQUO, ""):
                        result.append(LDQUO)
                        depth = 2
                    else:
                        result.append(RAQUO)
                        depth = 0
                    n[0] += 1
                else:  # depth == 2
                    result.append(RDQUO)
                    depth = 1
                    n[0] += 1
            else:
                result.append(ch)
        return "".join(result)

    text = process(text)
    if n[0]:
        c.add("T1", n[0])
    return text


# ---------------------------------------------------------------------------
# ТИРЕ / ДЕФИС (T3, T4)
# ---------------------------------------------------------------------------
def rule_T4_range_endash(text, c):
    """T4 — числовой диапазон \\d-\\d -> en-dash. Защита: телефоны, ISO-даты."""
    n = [0]
    protected = []

    def stash(m):
        protected.append(m.group(0))
        return PH_OPEN + "R" + str(len(protected) - 1) + PH_CLOSE

    text = re.sub(r"(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d-])", stash, text)  # ISO-дата (и в 2026-10-29_файл)
    text = re.sub(r"\b\d+(?:-\d+){2,}\b", stash, text)          # телефоны

    def sub(m):
        n[0] += 1
        return m.group(1) + ENDASH + m.group(2)

    text = re.sub(r"(\d)-(\d)", sub, text)
    text = re.sub(re.escape(PH_OPEN) + r"R(\d+)" + re.escape(PH_CLOSE),
                  lambda m: protected[int(m.group(1))], text)
    if n[0]:
        c.add("T4", n[0])
    return text


def rule_T3_word_emdash(text, c):
    """T3 — дефис между словами с пробелами -> em-dash. Не трогать «что-то».

    Граница слева — «непробельный символ + обычный пробел» (mid-line), а не любой
    `\\s`: иначе дефис в начале строки после `\\n` (маркер markdown-списка `- пункт`
    или тире диалога) ошибочно превращался бы в em-dash. Inter-word тире всегда
    стоит после слова и обычного пробела.

    Один-или-несколько дефисов `-`/`--`/`---` -> один em-dash: авторская конвенция
    набора `--`/`---` для тире (Т-01 канона). CLI-флаги `--fix` не задеты — у них
    нет пробела слева.
    """
    n = [0]

    def sub(m):
        n[0] += 1
        return " " + EMDASH + " "

    text = re.sub(r"(?<=\S)\x20[-‐]+\x20", sub, text)
    if n[0]:
        c.add("T3", n[0])
    return text


def rule_D8_year_abbr(text, c):
    """D8 — NBSP между числом и «гг.» (годы): `1990–1995 гг.` -> NBSP перед гг.

    Одиночное `г.` (год) уже привязывается через T6 (там `г` = грамм, исход совпадает),
    но `гг.` T6 не ловит (`(?![\\w])` отсекает вторую `г`). Закрываем именно `гг.`.
    """
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1) + NBSP + "гг"

    text = re.sub(r"(\d)\x20(гг)(?=\.)", sub, text)
    if n[0]:
        c.add("D8", n[0])
    return text


# ---------------------------------------------------------------------------
# NBSP-привязки (T5, T6, T9, T11, S23)
# ---------------------------------------------------------------------------
def rule_T11_abbrev(text, c):
    """T11/D23 — графические сокращения с NBSP: т. е., и т. д., и т. п., в т. ч."""
    n = [0]
    repls = [
        (r"\bи\s+т\.\s*д\.", "и" + NBSP + "т." + NBSP + "д."),
        (r"\bи\s+т\.\s*п\.", "и" + NBSP + "т." + NBSP + "п."),
        (r"\bв\s+т\.\s*ч\.", "в" + NBSP + "т." + NBSP + "ч."),
        (r"\bт\.\s*е\.", "т." + NBSP + "е."),
    ]
    for pat, dst in repls:
        def sub(m, _dst=dst):
            n[0] += 1
            return _dst
        text = re.sub(pat, sub, text)
    if n[0]:
        c.add("T11", n[0])
    return text


def rule_T5_prepositions(text, c):
    """T5 — NBSP после однобуквенных предлогов/союзов.

    Граница слева — zero-width lookbehind (начало строки / пробел / «(»), а не
    поглощаемый разделитель: иначе в цепочке предлогов («А в 2026») совпадение
    съедало бы пробел перед следующим предлогом, и тот оставался без NBSP до
    второго прогона (баг идемпотентности + пропуск правки).
    """
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1) + NBSP

    text = re.sub(r"(?<![^\s(])([" + ONE_LETTER + r"])\x20", sub, text)
    if n[0]:
        c.add("T5", n[0])
    return text


def rule_T6_number_unit(text, c):
    """T6/D14/D16 — NBSP между числом и единицей/знаком.

    Знак ° трактуется отдельно: NBSP только перед температурой (°C/°F/°С);
    угловые градусы (20°) обрабатывает S6 (слитно) до этого правила.
    """
    n = [0]
    # % ведёт T7 (слитно/NBSP по флагу); здесь NBSP перед % был бы снят T7 — фантомная правка.
    plain = [u for u in UNIT_TOKENS if u not in (DEGREE, "%")]
    units = "|".join(re.escape(u) for u in sorted(plain, key=len, reverse=True))
    pat = re.compile(r"(\d)\x20?(" + units + r")(?![\w])")

    def sub(m):
        n[0] += 1
        return m.group(1) + NBSP + m.group(2)

    text = pat.sub(sub, text)

    # ° только как температура: NBSP перед «°C/°F/°С»
    def sub_temp(m):
        n[0] += 1
        return m.group(1) + NBSP + DEGREE + m.group(2)

    text = re.sub(r"(\d)\x20?" + DEGREE + r"([CFСcf])", sub_temp, text)

    if n[0]:
        c.add("T6", n[0])
    return text


def rule_S23_number_sign(text, c):
    """S23 — № + NBSP перед числом."""
    n = [0]

    def sub(m):
        n[0] += 1
        return "№" + NBSP + m.group(1)

    text = re.sub(r"№\s*(\d)", sub, text)
    if n[0]:
        c.add("S23", n[0])
    return text


def rule_T9_nbsp_before_dash(text, c):
    """T9 — NBSP перед em-dash."""
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1) + NBSP + EMDASH

    text = re.sub(r"(\S)\x20" + EMDASH, sub, text)
    if n[0]:
        c.add("T9", n[0])
    return text


# ---------------------------------------------------------------------------
# СИМВОЛЫ (T12, S1, S6)
# ---------------------------------------------------------------------------
def rule_T12_ellipsis(text, c):
    """T12 — многоточие ... -> …"""
    n = [0]

    def sub(m):
        n[0] += 1
        return ELLIPSIS

    text = re.sub(r"\.{3,}", sub, text)
    if n[0]:
        c.add("T12", n[0])
    return text


# Обозначения единиц измерения (рус. + лат.) для S1 — знак умножения только между ними
UNITS_MULSIGN = {
    "м", "см", "мм", "км", "дм", "мкм", "нм",
    "г", "кг", "мг", "т", "ц",
    "с", "мс", "мкс", "нс", "ч", "мин",
    "А", "мА", "кА", "В", "мВ", "кВ", "Вт", "кВт", "МВт", "мВт",
    "Дж", "кДж", "Н", "Па", "кПа", "МПа", "Гц", "кГц", "МГц", "ГГц",
    "Ом", "кОм", "МОм", "Кл", "Тл", "Вб", "Ф", "Гн", "См",
    "моль", "кд", "лм", "лк", "л", "мл", "рад", "ср", "К",
    "N", "m", "kg", "s", "A", "V", "W", "kW", "J", "Pa", "Hz", "Ohm",
}


def rule_S1_mulsign(text, c):
    """S1 — знак умножения единиц `x`/`х`/`*` -> `·` ТОЛЬКО между обозначениями единиц.

    Жёсткая защита от ложных срабатываний (баг: «подход» → «под·од»):
    - оператор обязан иметь пробел(ы) с ОБЕИХ сторон (реальная запись «Н x м», не буква «х» внутри слова);
    - оба соседних токена обязаны быть в whitelist единиц `UNITS_MULSIGN`.
    """
    n = [0]

    def sub(m):
        left, op, right = m.group(1), m.group(2), m.group(3)
        if op in "xх*" and left in UNITS_MULSIGN and right in UNITS_MULSIGN:
            n[0] += 1
            return left + MULSIGN + right
        return m.group(0)

    # \s+ с обеих сторон — оператор не может быть буквой внутри слитного слова
    text = re.sub(r"\b([A-Za-zА-я]{1,4})\s+([xх*])\s+"
                  r"([A-Za-zА-я]{1,4})\b", sub, text)
    if n[0]:
        c.add("S1", n[0])
    return text


def rule_S6_angle_degree(text, c):
    """S6 — угловые градусы/мин/сек слитно с числом (20°), НО °C/°F не трогаем."""
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1) + m.group(2)

    pat = re.compile(r"(\d)\x20(" + DEGREE + r"(?![CFСcf])|′|″)")
    text = pat.sub(sub, text)
    if n[0]:
        c.add("S6", n[0])
    return text


# ---------------------------------------------------------------------------
# TG — безопасные правила из typograf.js (MIT, github.com/typograf/typograf)
# ---------------------------------------------------------------------------
MONTHS_GEN = ("января|февраля|марта|апреля|мая|июня|июля|августа|"
              "сентября|октября|ноября|декабря")
_ROMAN = r"[IVXLC]+"


def rule_TG1_double_exclamation(text, c):
    """TG1 — `!!` -> `!` (ровно два; `!!!` — экспрессия автора, не трогаем)."""
    text, k = re.subn(r"(?<!!)!!(?![!?])", "!", text)
    c.add("TG1", k)
    return text


def rule_TG2_exclamation_question(text, c):
    """TG2 — `!?` -> `?!` (канонический порядок: вопрос, затем восклицание)."""
    text, k = re.subn(r"(?<![!?])!\?(?![!?])", "?!", text)
    c.add("TG2", k)
    return text


def rule_TG3_double_punct(text, c):
    """TG3 — сдвоенные `,,` `;;` `??` -> один знак (ровно два, слева не пробел).

    `::` и `..` сознательно НЕ трогаем: `std::`, IPv6 `::1`, пути `../`,
    разговорное двухточие «Ну.. ладно» (авторское недо-многоточие — решает человек).
    """
    k = 0
    for ch in (",", ";"):
        e = re.escape(ch)
        text, n = re.subn(r"(?<=[^\s" + e + r"])" + e + e + r"(?!" + e + r")", ch, text)
        k += n
    text, n = re.subn(r"(?<=[^\s?!])\?\?(?![?!])", "?", text)
    c.add("TG3", k + n)
    return text


def rule_TG4_hellip_after_mark(text, c):
    """TG4 — `?…`/`!…` (и `?...`) -> `?..`/`!..`: после ?/! многоточие — две точки.

    Запускается после T12 (`...` уже `…`). Порядок `…?` не переставляем — это выбор автора.
    """
    text, k = re.subn(r"([?!])" + ELLIPSIS, r"\1..", text)
    c.add("TG4", k)
    return text


def rule_TG5_nbsp_abbr(text, c):
    """TG5 — NBSP после сокращений: стр./гл./рис./кв. + число, см. + слово,
    г./ул. + название, § + номер, римское + в./вв.

    `см.` и `г.` после числа — это сантиметры и год (`5 см. Дальше`, `2026 г. Москва`):
    там может стоять конец предложения, такие случаи не трогаем.
    """
    n = [0]

    def sub(m):
        n[0] += 1
        return m.group(1) + NBSP

    after_num = r"(?<!\d\x20)(?<!\d" + NBSP + r")"
    pats = [
        r"(?<![\w.])([Сс]тр\.|[Гг]л\.|[Рр]ис\.|[Кк]в\.)\x20(?=\d|[IVXLC]+\b)",
        after_num + r"(?<![\w.])([Сс]м\.)\x20(?=[\w«(])",
        after_num + r"(?<![\w.])(г\.|ул\.)\x20(?=[А-ЯЁ\d])",
        r"(§+)\x20?(?=\d|[IVXLC]+\b)",
    ]
    for pat in pats:
        text = re.sub(pat, sub, text)
    text = re.sub(r"(\b" + _ROMAN + r")\x20(?=вв?\.)", sub, text)
    if n[0]:
        c.add("TG5", n[0])
    return text


def rule_TG6_ranges(text, c):
    """TG6 — диапазоны годов/веков/дней через en-dash без пробелов (D9, typograf
    dash/years, dash/centuries, dash/daysMonth).

    Дефис без пробелов уже ловит T4; здесь — варианты с пробелами и с em-dash, которые
    T3 иначе превратил бы в «1990 — 1995». Срабатывает только при якоре: `г./гг.` после
    годов, `в./вв.` после веков, месяц в родительном после дней. Запуск ДО T3.
    """
    n = [0]
    dash = r"[\x20" + NBSP + r"]?[-" + ENDASH + EMDASH + r"][\x20" + NBSP + r"]?"

    def sub(m):
        n[0] += 1
        return m.group(1) + ENDASH + m.group(2)

    text = re.sub(r"(?<![\d.,:])(\d{4})" + dash + r"(\d{4})(?=[\x20" + NBSP + r"]?гг?\.)",
                  sub, text)
    text = re.sub(r"\b(" + _ROMAN + r")" + dash + r"(" + _ROMAN + r")(?=[\x20" + NBSP
                  + r"]?вв?\.)", sub, text)
    text = re.sub(r"(?<![\d.,:])([12]?\d|3[01])" + dash + r"([12]?\d|3[01])(?=[\x20" + NBSP
                  + r"](?:" + MONTHS_GEN + r")\b)", sub, text)
    if n[0]:
        c.add("TG6", n[0])
    return text


# Наращение: двух-/трёхбуквенное там, где по норме короче (D3/D10, typograf number/ordinals).
ORDINAL_SHORT = {
    "ый": "й", "ой": "й", "ий": "й", "ая": "я", "ое": "е", "ые": "е", "ее": "е",
    "ую": "ю", "ым": "м", "ом": "м", "им": "м", "ых": "х", "их": "х",
    "ого": "го", "его": "го", "ому": "му", "ему": "му", "ыми": "ми", "ими": "ми",
}


def rule_TG7_ordinals(text, c):
    """TG7 — лишние буквы в наращении после цифры: `25-ый` -> `25-й`, `90-ые` -> `90-е`,
    `5-ого` -> `5-го`. Только closed-list окончаний и только после арабской цифры."""
    n = [0]
    ends = "|".join(sorted(ORDINAL_SHORT, key=len, reverse=True))

    def sub(m):
        n[0] += 1
        return m.group(1) + "-" + ORDINAL_SHORT[m.group(2)]

    text = re.sub(r"(\d)-(" + ends + r")(?![А-Яа-яЁё\w])", sub, text)
    if n[0]:
        c.add("TG7", n[0])
    return text


def rule_TG8_trailing_space(text, c):
    """TG8 — хвостовые пробелы/табы/NBSP в конце строки -> убрать.

    Markdown hard break (`  ` в конце строки) T14 и раньше схлопывал — новых потерь нет.
    """
    text, k = re.subn(r"[\x20\t" + NBSP + r"]+(?=\r?\n|\Z)", "", text)
    c.add("TG8", k)
    return text


def rule_TG9_ruble(text, c):
    """TG9 (флаг --ruble) — `руб.`/`р.` после числа -> NBSP + ₽. Редполитика, по умолчанию OFF.

    В конце предложения точка сокращения была и концом фразы — её сохраняем (`₽.`).
    """
    n = [0]

    def sub(m):
        n[0] += 1
        tail = "." if m.group(2) is not None else ""
        return m.group(1) + NBSP + "₽" + tail

    text = re.sub(r"(\d(?:[\x20" + NBSP + r"](?:тыс\.|млн|млрд|трлн))?)[\x20" + NBSP
                  + r"]?(?:руб|р)\.((?=\s*\Z)|(?=\s+[А-ЯЁA-Z])|(?=\r?\n))?", sub, text)
    if n[0]:
        c.add("TG9", n[0])
    return text


def rule_TG10_iso_date(text, c):
    """TG10 (флаг --iso-dates) — ISO-дата `2026-06-09` -> `09.06.2026`. По умолчанию OFF:
    в рабочих текстах ISO бывает намеренной (имена файлов, логи)."""
    n = [0]

    def sub(m):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
            return m.group(0)
        n[0] += 1
        return d + "." + mo + "." + y

    text = re.sub(r"(?<![\w.\-])(\d{4})-(\d{2})-(\d{2})(?![\w\-])", sub, text)
    if n[0]:
        c.add("TG10", n[0])
    return text


# ---------------------------------------------------------------------------
# СПОРНЫЕ — под флагами
# ---------------------------------------------------------------------------
def rule_T7_percent(text, c, percent_space):
    """T7 — % с пробелом/без. Дефолт: слитно (percent_space=False)."""
    n = [0]
    if percent_space:
        def sub(m):
            n[0] += 1
            return m.group(1) + NBSP + "%"
        text = re.sub(r"(\d)%", sub, text)
    else:
        def sub(m):
            n[0] += 1
            return m.group(1) + "%"
        text = re.sub(r"(\d)[\x20 ]%", sub, text)
    if n[0]:
        c.add("T7", n[0])
    return text


def rule_T10_initials(text, c, initials_space):
    """T10/D24 — инициалы. Дефолт: с NBSP («А. С. Пушкин»)."""
    n = [0]
    if initials_space:
        def sub(m):
            n[0] += 1
            return (m.group(1) + "." + NBSP + m.group(2) + "." + NBSP + m.group(3))
        text = re.sub(r"([А-Я])\.\s*([А-Я])\.\s*"
                      r"([А-Я][а-я]+)", sub, text)
    if n[0]:
        c.add("T10", n[0])
    return text


# ---------------------------------------------------------------------------
# КОНВЕЙЕР
# ---------------------------------------------------------------------------
def proofread(text, percent_space=False, initials_space=True, ruble=False, iso_dates=False):
    """Полный конвейер в рекомендованном спеками порядке. -> (text, Counter)."""
    c = Counter()

    text = rule_W9_nfc(text, c)
    text = rule_W3_bom(text, c)

    zp = ZoneProtector()
    text = zp.mask(text)

    # юникод-гигиена
    text = rule_W2_zerowidth(text, c)
    text = rule_W15_narrow(text, c)
    text = rule_W6_mojibake(text, c)
    text = rule_W1_homoglyphs(text, c)
    text = rule_W4_curly_quotes(text, c)

    # пробелы
    text = rule_TG8_trailing_space(text, c)  # до T5: хвостовой пробел не должен стать NBSP
    text = rule_T14_multispace(text, c)
    text = rule_T15_space_before_punct(text, c)
    text = rule_T16_space_after_open(text, c)
    text = rule_T24_space_after_punct(text, c)  # до T5: вставленный пробел может стать NBSP

    # сдвоенные знаки (TG1 до TG2: `!!?` не должен стать `!?!`)
    text = rule_TG1_double_exclamation(text, c)
    text = rule_TG2_exclamation_question(text, c)
    text = rule_TG3_double_punct(text, c)

    # кавычки
    text = rule_T1_quotes(text, c)

    # тире/дефис (диапазон раньше словесного; TG10 до T4 — T4 защищает ISO-даты)
    if iso_dates:
        text = rule_TG10_iso_date(text, c)
    text = rule_TG6_ranges(text, c)  # до T3: «1990 - 1995 гг.» иначе станет em-dash
    text = rule_T4_range_endash(text, c)
    text = rule_T3_word_emdash(text, c)
    text = rule_D8_year_abbr(text, c)

    # S6 (угловые градусы слитно) — ДО T6, чтобы не вставить NBSP в «45 °»
    text = rule_S6_angle_degree(text, c)

    # NBSP-привязки и сокращения
    text = rule_T11_abbrev(text, c)
    text = rule_T5_prepositions(text, c)
    text = rule_T6_number_unit(text, c)
    text = rule_S23_number_sign(text, c)
    text = rule_T9_nbsp_before_dash(text, c)
    text = rule_TG5_nbsp_abbr(text, c)
    text = rule_TG7_ordinals(text, c)

    # символы
    text = rule_T12_ellipsis(text, c)
    text = rule_TG4_hellip_after_mark(text, c)  # после T12: `?...` уже `?…`
    text = rule_S1_mulsign(text, c)

    # спорные под флагами
    text = rule_T7_percent(text, c, percent_space)
    text = rule_T10_initials(text, c, initials_space)
    if ruble:
        text = rule_TG9_ruble(text, c)

    text = zp.unmask(text)
    return text, c


# ---------------------------------------------------------------------------
# SELFTEST
# ---------------------------------------------------------------------------
SELFTESTS = [
    ("T14 двойные пробелы", "это  тест", "это тест", {}),
    ("T14 ведущий отступ markdown сохранять", "* a\n  - b", "* a\n  - b", {}),
    ("T15 пробел перед знаком", "слово )тут", "слово)тут", {}),
    ("T16 пробел после скобки", "( текст)", "(текст)", {}),
    ("T24 пробел после запятой", "Короче,рассказываю",
     "Короче, рассказываю", {}),
    ("T24 пробел после ?", "Что?Дальше", "Что? Дальше", {}),
    ("T24 двоеточие перед буквой", "Итог:всё готово", "Итог: всё готово", {}),
    ("T24 десятичную дробь не трогать", "число 3,14 тут", None, {}),
    ("T24 время не трогать", "матч 14:30 начало", None, {}),
    ("T24 счёт не трогать", "счёт 3:4 матч", None, {}),
    ("T24 точку не трогать (расширение)", "файл readme.md тут", None, {}),
    ("T12 многоточие", "вот...", "вот" + ELLIPSIS, {}),
    ("T1 кавычки ёлочки", 'он сказал "да" мне',
     "он сказал " + LAQUO + "да" + RAQUO + " мне", {}),
    ("T1 дюймы не трогать", 'диагональ 5" экран', 'диагональ 5" экран', {}),
    ("T1 вложенные лапки",
     'текст "внешний "вложенный" текст" конец',
     "текст " + LAQUO + "внешний " + LDQUO + "вложенный" + RDQUO + " текст"
     + RAQUO + " конец", {}),
    ("T3 дефис между словами", "это - тест",
     "это" + NBSP + EMDASH + " тест", {}),
    ("T3 двойной дефис -- -> em", "это -- тест",
     "это" + NBSP + EMDASH + " тест", {}),
    ("T3 markdown-список не трогать", "- первый\n- второй",
     "- первый\n- второй", {}),
    ("D8 гг. NBSP", "за 1990-1995 гг.",
     "за 1990" + ENDASH + "1995" + NBSP + "гг.", {}),
    ("T3 тире диалога в начале строки не трогать", "Текст.\n- Реплика",
     "Текст.\n- Реплика", {}),
    ("T4 диапазон en-dash", "стр 10-15", "стр 10" + ENDASH + "15", {}),
    ("T4 ISO-дата не трогать", "дата 2026-06-09 ок", "дата 2026-06-09 ок", {}),
    ("T4 ISO-дата в имени файла не трогать", "файл 2026-10-29_отчёт.md", None, {}),
    ("T5 предлог NBSP", "в доме", "в" + NBSP + "доме", {}),
    ("T5 цепочка предлогов (идемпотентность)", "я и о деле",
     "я" + NBSP + "и" + NBSP + "о" + NBSP + "деле", {}),
    ("T6 число+единица", "вес 5 кг ровно", "вес 5" + NBSP + "кг ровно", {}),
    ("T9 NBSP перед тире", "слово " + EMDASH + " это",
     "слово" + NBSP + EMDASH + " это", {}),
    ("T11 и т. д.", "и т.д. далее",
     "и" + NBSP + "т." + NBSP + "д. далее", {}),
    ("T11 т. е.", "т.е. значит",
     "т." + NBSP + "е. значит", {}),
    ("W2 zero-width", "сло​во", "слово", {}),
    ("W3 BOM", BOM + "текст", "текст", {}),
    ("W6 mojibake тире", "пауза â€” конец",
     "пауза" + NBSP + EMDASH + " конец", {}),
    ("W1 омоглиф (lat c в кир)", "cлово", "слово", {}),
    ("W1 чистая латиница не трогать", "iPhone тут", "iPhone тут", {}),
    ("W4 curly->ёлочки", "“тест”", LAQUO + "тест" + RAQUO, {}),
    ("W9 NFC й", "йкраткое", "йкраткое", {}),
    ("S23 № NBSP", "№" + "5", "№" + NBSP + "5", {}),
    ("S6 угол слитно", "угол 45 " + DEGREE + " поворот", "угол 45" + DEGREE + " поворот", {}),
    ("S6 температура не трогать", "20 " + DEGREE + "C тепло",
     "20" + NBSP + DEGREE + "C тепло", {}),
    ("zone: код не трогать", "вот `a  -  b` код", "вот `a  -  b` код", {}),
    ("zone: YAML-фронтматтер не трогать",
     '---\ntitle: "Имя: подзаголовок"\nrange: 2020-2024\n---\nТекст - тут.',
     '---\ntitle: "Имя: подзаголовок"\nrange: 2020-2024\n---\nТекст' + NBSP + EMDASH + " тут.", {}),
    ("zone: URL не трогать", "ссылка http://a.com/x-y тут",
     "ссылка http://a.com/x-y тут", {}),
    ("zone: @mention не трогать", "привет @user_name тут",
     "привет @user_name тут", {}),
    ("zone: md-ссылка текст типографим, url нет",
     'см [тут  текст](http://a.com/x-y)',
     "см [тут текст](http://a.com/x-y)", {}),
    ("T7 percent слитно (дефолт)", "рост 5 %", "рост 5%", {}),
    ("T7 percent с пробелом (флаг)", "рост 5%", "рост 5" + NBSP + "%",
     {"percent_space": True}),
    ("T10 инициалы NBSP", "А. С. Пушкин",
     "А." + NBSP + "С." + NBSP + "Пушкин", {}),
    ("S1 знак умножения единиц", "сила Н x м",
     "сила Н" + MULSIGN + "м", {}),
    ("S1 регрессия: буква х в слове не трогается",
     "новый подход последних успеху хорошим", None, {}),
    ("S1 регрессия: х между не-единицами не трогается",
     "до х шт", None, {}),
    # --- TG: безопасные правила typograf.js ---
    ("TG1 !! -> !", "Ура!! Дальше", "Ура! Дальше", {}),
    ("TG1 !!! не трогать (экспрессия)", "Ура!!! Дальше", None, {}),
    ("TG2 !? -> ?!", "Серьёзно!? Да", "Серьёзно?! Да", {}),
    ("TG3 ,, -> ,", "раз,, два", "раз, два", {}),
    ("TG3 ?? -> ?", "Что?? Как", "Что? Как", {}),
    ("TG3 :: и .. не трогать", "Ну.. ладно, адрес fe80::1", None, {}),
    ("TG4 ?... -> ?..", "Неужели?... Да", "Неужели?.. Да", {}),
    ("TG4 !… -> !..", "Вот!" + ELLIPSIS, "Вот!..", {}),
    ("TG5 стр./рис. + число", "см. рис. 3 на стр. 5",
     "см." + NBSP + "рис." + NBSP + "3 на стр." + NBSP + "5", {}),
    ("TG5 г./ул. + название", "живёт г. Москва, ул. Ленина",
     "живёт г." + NBSP + "Москва, ул." + NBSP + "Ленина", {}),
    ("TG5 год перед новой фразой не трогать", "было в 2026 г. Москва",
     "было в" + NBSP + "2026" + NBSP + "г. Москва", {}),
    ("TG5 сантиметры перед новой фразой не трогать", "длина 5 см. Дальше",
     "длина 5" + NBSP + "см. Дальше", {}),
    ("TG5 купил рис. без числа не трогать", "купил рис. Потом", None, {}),
    ("TG5 § + номер", "по §5 и § 7", "по §" + NBSP + "5 и" + NBSP + "§" + NBSP + "7", {}),
    ("TG5 век римскими", "XIX в. и XX вв.", "XIX" + NBSP + "в. и" + NBSP + "XX" + NBSP + "вв.", {}),
    ("TG6 годы с пробелами", "в 1990 - 1995 гг.",
     "в" + NBSP + "1990" + ENDASH + "1995" + NBSP + "гг.", {}),
    ("TG6 века через em-dash", "XIX" + EMDASH + "XX вв.", "XIX" + ENDASH + "XX" + NBSP + "вв.", {}),
    ("TG6 дни месяца", "10 - 15 мая", "10" + ENDASH + "15 мая", {}),
    ("TG6 без якоря не трогать (счёт)", "счёт 10 - 15 в пользу",
     "счёт 10" + NBSP + EMDASH + " 15 в" + NBSP + "пользу", {}),
    ("TG7 25-ый -> 25-й", "25-ый раз", "25-й раз", {}),
    ("TG7 90-ые, 5-ого", "в 90-ые до 5-ого", "в" + NBSP + "90-е до 5-го", {}),
    ("TG7 верное наращение не трогать", "5-й и 2-го", "5-й и" + NBSP + "2-го", {}),
    ("TG8 хвостовые пробелы", "строка  \nи \t\nконец ", "строка\nи\nконец", {}),
    ("TG8 код с хвостовыми пробелами не трогать", "```\ncode  \n```", None, {}),
    ("T6 трлн NBSP", "5 трлн долга", "5" + NBSP + "трлн долга", {}),
    ("TG9 руб. без флага не трогать", "цена 5 руб. в день", "цена 5 руб. в" + NBSP + "день", {}),
    ("TG9 руб. -> ₽ (флаг)", "цена 5 руб. в день",
     "цена 5" + NBSP + "₽ в" + NBSP + "день", {"ruble": True}),
    ("TG9 руб. в конце фразы — точка остаётся (флаг)", "Стоит 300 руб. Дорого",
     "Стоит 300" + NBSP + "₽. Дорого", {"ruble": True}),
    ("TG10 ISO-дата без флага не трогать", "дата 2026-06-09 ок", None, {}),
    ("TG10 ISO-дата (флаг)", "дата 2026-06-09 ок", "дата 09.06.2026 ок", {"iso_dates": True}),
    ("TG10 имя файла с датой не трогать (флаг)", "файл 2026-10-29_отчёт.md", None, {"iso_dates": True}),
    ("T6/T7 проценты слитно — без фантомных правок", "со скилом 95%, без него 75%", None, {}),
    ("zone: TG в коде и URL не трогать", "`a!!b` http://a.com/2020-2021?x=1,,2",
     None, {}),
]


def _run_cli_selftests():
    """CLI-уровневые проверки --in-place (файловый ввод/вывод, не proofread).
    Возвращает (passed, failed, log_lines)."""
    passed = failed = 0
    log = []

    def ok(cond, desc):
        nonlocal passed, failed
        if cond:
            passed += 1
            log.append("PASS  {}".format(desc))
        else:
            failed += 1
            log.append("FAIL  {}".format(desc))

    dirty = 'Он сказал "привет" - и ушёл...'
    d = tempfile.mkdtemp(prefix="milchin-selftest-")
    try:
        fpath = os.path.join(d, "draft.md")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(dirty)
        expected, _ = proofread(dirty)

        # 1) --in-place пишет исправленный текст в тот же файл
        rc = main(["--fix", "--in-place", "--file", fpath])
        after = open(fpath, encoding="utf-8").read()
        ok(rc == 0 and after == expected and after != dirty,
           "--in-place записал исправленный текст в файл")

        # 2) идемпотентность: повторный прогон не меняет файл
        rc2 = main(["--fix", "--in-place", "--file", fpath])
        after2 = open(fpath, encoding="utf-8").read()
        ok(rc2 == 0 and after2 == after, "--in-place идемпотентен (повторный прогон — 0 правок)")

        # 3) отказ без --file (argparse.error → SystemExit)
        raised = False
        try:
            main(["--fix", "--in-place"])
        except SystemExit:
            raised = True
        ok(raised, "--in-place без --file — отказ")

        # 4) отказ вместе с --check
        raised2 = False
        try:
            main(["--check", "--in-place", "--file", fpath])
        except SystemExit:
            raised2 = True
        ok(raised2, "--in-place с --check — отказ")
    finally:
        try:
            for fn in os.listdir(d):
                os.remove(os.path.join(d, fn))
            os.rmdir(d)
        except OSError:
            pass
    return passed, failed, log


def run_selftest():
    passed = failed = 0
    for desc, src, expected, kwargs in SELFTESTS:
        unchanged = expected is None  # None = текст не должен меняться
        if unchanged:
            expected = src
        got, cnt = proofread(src, **kwargs)
        # без изменений — и счётчик 0: иначе отчёт врёт о правках (фантомные пары правил)
        if got == expected and not (unchanged and cnt.total()):
            passed += 1
            print("PASS  {}".format(desc))
        else:
            failed += 1
            print("FAIL  {}".format(desc))
            print("        вход:    {!r}".format(src))
            print("        ожидал:  {!r}".format(expected))
            print("        получил: {!r}".format(got))
            if got == expected:
                print("        счётчик: {} правок при неизменном тексте".format(cnt.total()))
    cli_passed, cli_failed, cli_log = _run_cli_selftests()
    for line in cli_log:
        print(line)
    total = len(SELFTESTS) + cli_passed + cli_failed
    print("\n{} PASS, {} FAIL из {} (вкл. {} CLI --in-place)".format(
        passed + cli_passed, failed + cli_failed, total, cli_passed + cli_failed))
    return (failed + cli_failed) == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _atomic_write(path, text):
    """Атомарная запись: tmp-файл рядом + os.replace. Не оставляет полу-записанный
    файл при сбое; идемпотентность и наборы правил — целиком в proofread()."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="milchin",
        description="Мильчин — типограф русского текста: ёлочки, тире, неразрывные "
                    "пробелы, юникод-гигиена. Детерминированно, без LLM, без зависимостей.")
    p.add_argument("--file", help="входной файл (иначе stdin)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--fix", action="store_true",
                      help="исправить и напечатать в stdout (по умолчанию)")
    mode.add_argument("--check", action="store_true",
                      help="не менять; сводка счётчиков в stderr, stdout пуст")
    mode.add_argument("--report", action="store_true",
                      help="исправленный текст в stdout + сводка в stderr")
    mode.add_argument("--selftest", action="store_true",
                      help="прогнать встроенные тесты, вывести PASS/FAIL")
    p.add_argument("--in-place", action="store_true",
                   help="записать результат в тот же файл (только с --fix --file; "
                        "атомарно через tmp+os.replace; сводка в stderr)")
    p.add_argument("--percent-space", action="store_true",
                   help="T7: NBSP перед %% (дефолт: слитно)")
    p.add_argument("--no-initials-space", action="store_true",
                   help="T10: не привязывать инициалы NBSP (дефолт: привязывать)")
    p.add_argument("--ruble", action="store_true",
                   help="TG9: «руб.»/«р.» после числа -> ₽ (дефолт: не трогать)")
    p.add_argument("--iso-dates", action="store_true",
                   help="TG10: ISO-дата 2026-06-09 -> 09.06.2026 (дефолт: не трогать)")
    args = p.parse_args(argv)

    if args.selftest:
        return 0 if run_selftest() else 1

    if args.in_place:
        if not args.file:
            p.error("--in-place требует --file (нечего писать на месте)")
        if args.check or args.report:
            p.error("--in-place совместим только с --fix (запись на месте)")

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    fixed, c = proofread(
        text,
        percent_space=args.percent_space,
        initials_space=not args.no_initials_space,
        ruble=args.ruble,
        iso_dates=args.iso_dates,
    )

    if args.check:
        for line in c.summary_lines():
            print(line, file=sys.stderr)
        return 0

    if args.report:
        sys.stdout.write(fixed)
        for line in c.summary_lines():
            print(line, file=sys.stderr)
        return 0

    if args.in_place:
        _atomic_write(args.file, fixed)
        for line in c.summary_lines():
            print(line, file=sys.stderr)
        return 0

    sys.stdout.write(fixed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
