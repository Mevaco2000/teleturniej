"""Ocena odpowiedzi mówionych i pisanych na telefonie.

Rozpoznawanie mowy i klawiatura dają odmienione słowa („w Warszawie”), literówki, liczby
słownie i dodatki w rodzaju „chyba to będzie…”. Porównanie idzie więc po słowach treściowych:
końcówki odmiany są obcinane, liczby zamieniane na cyfry, a wypełniacze pomijane.

Błędne opcje pytania służą za próbę kontrolną: odpowiedź, która pasuje do błędnej opcji
równie dobrze jak do poprawnej (np. samo „Bolesław”), nie jest uznawana.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Optional, Sequence

MAX_ALTERNATIVES = 5
MAX_TEXT = 160
ACCEPT = 0.7
WORD_MATCH = 0.85

FILLER = set("""
a aha albo ale ani bede bedzie bo by byc byl byla byli bylo chyba co czy do dla dobra dobrze e ee eee
eh ehm hm hmm hmmm i ich ja jak jakby jakis jakas jest jestem juz kto ktory ktora ktore mi mnie moim
moja moj moja moze mozna mysle na nam no o od odp odpowiadam odpowiedz oraz pewnie po prostu przez
raczej sa se sie ta tak tam ten tego to tu tutaj w we wiec wydaje wlasnie yy yyy yyyy z za ze zeby
""".split())

# Słowa jednostek pomijane, gdy odpowiedź jest liczbą: „100°C” = „sto stopni”.
UNITS = set("""
c celsjusza stopien stopni stopnie stopnia procent procenty procentow km kilometr kilometry kilometrow
kilometra m metr metry metrow metra cm centymetr centymetrow centymetry centymetra kwadratowy kwadratowych
kwadratowe s sekunda sekundy sekund sekunde min minuta minuty minut minute h godzina godziny godzin
dzien dni doba doby tydzien tygodnie tygodni rok roku lata lat latach co kg kilogram kilogramow g gram
gramow l litr litry litrow sztuk razy raz zl zlotych zlote zloty euro dolarow
""".split())

MONTHS = {
    "styczen": 1, "stycznia": 1, "styczniu": 1, "luty": 2, "lutego": 2, "lutym": 2,
    "marzec": 3, "marca": 3, "marcu": 3, "kwiecien": 4, "kwietnia": 4, "kwietniu": 4,
    "maj": 5, "maja": 5, "maju": 5, "czerwiec": 6, "czerwca": 6, "czerwcu": 6,
    "lipiec": 7, "lipca": 7, "lipcu": 7, "sierpien": 8, "sierpnia": 8, "sierpniu": 8,
    "wrzesien": 9, "wrzesnia": 9, "wrzesniu": 9, "pazdziernik": 10, "pazdziernika": 10,
    "pazdzierniku": 10, "listopad": 11, "listopada": 11, "listopadzie": 11,
    "grudzien": 12, "grudnia": 12, "grudniu": 12,
}

PASS_WORDS = {"pas", "pasuje", "dalej", "nastepne", "nastepna", "nastepny", "wiem", "nastepnie"}

SUFFIXES = sorted("""
owie ami ach ego emu owi ich ych imi ymi iem iom om ow em ie ia ii ej ym im iu a e i y o u
""".split(), key=len, reverse=True)

# --- Liczby słownie --------------------------------------------------------

_UNIT_WORDS = {
    0: "zero zera", 1: "jeden jedna jedno jednego jednej jednym jednemu", 2: "dwa dwie dwoch dwom dwoma dwu",
    3: "trzy trzech trzem trzema", 4: "cztery czterech czterem czterema", 5: "piec pieciu piecioma",
    6: "szesc szesciu szescioma", 7: "siedem siedmiu siedmioma", 8: "osiem osmiu osmioma",
    9: "dziewiec dziewieciu dziewiecioma", 10: "dziesiec dziesieciu", 11: "jedenascie jedenastu",
    12: "dwanascie dwunastu", 13: "trzynascie trzynastu", 14: "czternascie czternastu",
    15: "pietnascie pietnastu", 16: "szesnascie szesnastu", 17: "siedemnascie siedemnastu",
    18: "osiemnascie osiemnastu", 19: "dziewietnascie dziewietnastu",
    20: "dwadziescia dwudziestu", 30: "trzydziesci trzydziestu", 40: "czterdziesci czterdziestu",
    50: "piecdziesiat piecdziesieciu", 60: "szescdziesiat szescdziesieciu",
    70: "siedemdziesiat siedemdziesieciu", 80: "osiemdziesiat osiemdziesieciu",
    90: "dziewiecdziesiat dziewiecdziesieciu",
    100: "sto stu", 200: "dwiescie dwustu", 300: "trzysta trzystu", 400: "czterysta czterystu",
    500: "piecset pieciuset", 600: "szescset szesciuset", 700: "siedemset siedmiuset",
    800: "osiemset osmiuset", 900: "dziewiecset dziewieciuset",
}
_ORDINAL_STEMS = {
    1: "pierwsz", 2: "drug", 3: "trzec", 4: "czwart", 5: "piat", 6: "szost", 7: "siodm", 8: "osm",
    9: "dziewiat", 10: "dziesiat", 11: "jedenast", 12: "dwunast", 13: "trzynast", 14: "czternast",
    15: "pietnast", 16: "szesnast", 17: "siedemnast", 18: "osiemnast", 19: "dziewietnast",
    20: "dwudziest", 30: "trzydziest", 40: "czterdziest", 50: "piecdziesiat", 60: "szescdziesiat",
    70: "siedemdziesiat", 80: "osiemdziesiat", 90: "dziewiecdziesiat", 100: "setn",
    200: "dwusetn", 300: "trzechsetn", 400: "czterechsetn", 500: "piecsetn", 600: "szescsetn",
    700: "siedemsetn", 800: "osiemsetn", 900: "dziewiecsetn", 1000: "tysieczn", 2000: "dwutysieczn",
}
_ORDINAL_ENDINGS = ("y", "a", "e", "ego", "ej", "ym", "emu", "i", "ych", "ymi", "im", "iego", "iej", "iemu")
_MULTIPLIERS = {
    1000: "tysiac tysiace tysiecy tysiaca tysiacem tysiacach",
    1_000_000: "milion miliony milionow miliona milionem",
    1_000_000_000: "miliard miliardy miliardow miliarda",
}

_NUMBER_WORDS: dict[str, tuple[int, bool]] = {}
for _value, _forms in _UNIT_WORDS.items():
    for _form in _forms.split():
        _NUMBER_WORDS[_form] = (_value, False)
for _value, _forms in _MULTIPLIERS.items():
    for _form in _forms.split():
        _NUMBER_WORDS[_form] = (_value, True)
for _value, _stem in _ORDINAL_STEMS.items():
    for _ending in _ORDINAL_ENDINGS:
        _NUMBER_WORDS.setdefault(_stem + _ending, (_value, False))

# Tylko I, V i X: same „C” czy „L” to częściej skrót („100°C”) niż liczba rzymska.
_ROMAN = re.compile(r"\b(?=[IVX])(X{0,3})(IX|IV|V?I{0,3})\b")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}


def _roman(match: re.Match) -> str:
    text = match.group(0)
    if not text:
        return text
    total = 0
    for i, ch in enumerate(text):
        value = _ROMAN_VALUES[ch]
        total += -value if i + 1 < len(text) and _ROMAN_VALUES[text[i + 1]] > value else value
    return f" {total} "


def fold_text(text: str) -> str:
    """Małe litery bez polskich znaków i interpunkcji, z cyframi zamiast liczb rzymskich."""
    text = _ROMAN.sub(_roman, text)
    for a, b in (("ł", "l"), ("Ł", "L"), ("−", "-"), ("–", "-"), ("ø", "o"), ("Ø", "O"), ("æ", "ae"),
                 ("Æ", "AE"), ("ß", "ss"), ("đ", "d"), ("þ", "th"), ("’", "'")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = re.sub(r"(?<=\d)[  ](?=\d{3}\b)", "", text)
    text = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", text)
    text = re.sub(r"\btys\b\.?", " tysiac ", text)
    text = re.sub(r"\bmln\b\.?", " milion ", text)
    text = re.sub(r"\bmld\b\.?", " miliard ", text)
    text = text.replace("%", " procent ")
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    return " ".join(text.split())


def _merge_numbers(tokens: list[str]) -> list[str]:
    """Zamienia ciągi liczebników („tysiąc czterysta dziesiątego”) na cyfry („1410”)."""
    out: list[str] = []
    total = current = 0
    pending = False

    def flush() -> None:
        nonlocal total, current, pending
        if pending:
            out.append(str(total + current))
        total = current = 0
        pending = False

    for token in tokens:
        if re.fullmatch(r"\d+", token):
            if pending and current == 0 and total:
                current = int(token)
                continue
            flush()
            current = int(token)
            pending = True
            continue
        if re.fullmatch(r"\d+\.\d+", token):
            flush()
            out.append(str(float(token)))
            continue
        word = _NUMBER_WORDS.get(token)
        if word is None:
            flush()
            out.append(token)
            continue
        value, multiplier = word
        if multiplier:
            total += (current or 1) * value
            current = 0
        elif current and current % 1000 < value:
            # „dwa trzy” to dwie liczby, a „dwadzieścia trzy” jedna.
            flush()
            current = value
        else:
            current += value
        pending = True
    flush()
    return out


@dataclass
class Parsed:
    words: list[str]
    nums: list[str]
    # Słowa ostatniego członu („Curie” i „Skłodowska” w „Maria Skłodowska-Curie”): nazwisko
    # wystarczy za całą odpowiedź.
    last: frozenset = frozenset()

    @property
    def empty(self) -> bool:
        return not self.words and not self.nums


def parse(text: str, keep_units: bool = True, target: bool = False) -> Parsed:
    """Słowa treściowe i liczby. Odpowiedź wzorcowa złożona z samych „wypełniaczy” je zachowuje."""
    raw = text.split()
    last_words = fold_text(raw[-1]).split() if raw else []
    last = frozenset(last_words)
    # Litera na końcu to zwykle oznaczenie („witamina A”), a nie spójnik „a”.
    letter = last_words[-1] if len(last_words) == 1 and len(last_words[0]) == 1 and last_words[0].isalpha() else None
    tokens = _merge_numbers(fold_text(text).split())
    nums, words = [], []
    for token in tokens:
        if re.fullmatch(r"\d+(\.\d+)?", token):
            nums.append(_canonical_number(token))
        elif token in MONTHS:
            words.append(f"miesiac{MONTHS[token]}")
        else:
            words.append(token)
    content = [w for i, w in enumerate(words)
               if w not in FILLER or (letter and i == len(words) - 1 and w == letter)]
    if not content and not nums and target:
        content = words
    if nums and not keep_units:
        content = [w for w in content if w not in UNITS]
    return Parsed(content, nums, last)


def _canonical_number(token: str) -> str:
    value = float(token)
    return str(int(value)) if value == int(value) else repr(value)


# --- Porównywanie słów -----------------------------------------------------


def stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _phonetic(word: str) -> str:
    for a, b in (("ph", "f"), ("th", "t"), ("rh", "r"), ("sch", "sz"), ("sh", "sz"), ("ch", "h"),
                 ("rz", "z"), ("ck", "k"), ("qu", "kw"), ("q", "k"), ("x", "ks"), ("v", "w"),
                 ("y", "i"), ("j", "i"), ("ee", "i"), ("oo", "u")):
        word = word.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", word)


def word_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    sa, sb = stem(a), stem(b)
    if sa == sb and len(sa) >= 3:
        return 0.97
    fa, fb = _phonetic(a), _phonetic(b)
    if fa == fb:
        return 0.95
    if min(len(fa), len(fb)) >= 5 and fa[0] == fb[0]:
        ratio = max(SequenceMatcher(None, fa, fb).ratio(),
                    SequenceMatcher(None, _phonetic(sa), _phonetic(sb)).ratio())
        if ratio >= 0.88:
            return 0.86
    return 0.0


def _best(word: str, pool: Sequence[str]) -> float:
    return max((word_similarity(word, other) for other in pool), default=0.0)


def _key_indexes(target: Parsed) -> set[int]:
    words = target.words
    keys = {i for i, w in enumerate(words) if w in target.last and len(w) >= 4}
    return keys or {max(range(len(words)), key=lambda i: len(words[i]))}


def score(spoken: Parsed, target: Parsed, context: Iterable[str] = (), lenient: bool = False) -> float:
    """Dopasowanie wypowiedzi do jednej odpowiedzi, od 0 do 1."""
    if target.nums:
        if spoken.nums and sorted(spoken.nums) != sorted(target.nums):
            return 0.0
        if not target.words:
            return 1.0 if spoken.nums else 0.0
    if not target.words or not spoken.words:
        return 0.9 if target.nums and spoken.nums else 0.0
    sims = [_best(word, spoken.words) for word in target.words]
    matched = [i for i, value in enumerate(sims) if value >= WORD_MATCH]
    if len(matched) == len(target.words):
        base = sum(sims) / len(sims)
    elif lenient and any(len(target.words[i]) >= 4 and sims[i] >= 0.9 for i in matched):
        base = 0.72 + 0.1 * len(matched) / len(target.words)
    else:
        keys = _key_indexes(target)
        hit = any(i in keys and len(target.words[i]) >= 4 and sims[i] >= 0.9 for i in matched)
        base = 0.72 if hit else 0.0
    if target.nums and spoken.nums:
        base = max(base, 0.9)
    context_words = set(context)
    extras = [w for w in spoken.words
              if w not in context_words and _best(w, target.words) < WORD_MATCH and w not in UNITS]
    if len(extras) > max(2, len(target.words)):
        base *= 0.6
    return base


@dataclass
class Verdict:
    ok: bool
    index: Optional[int]
    heard: str
    empty: bool = False


def _clean_inputs(texts: Iterable) -> list[str]:
    out = []
    for text in texts:
        if isinstance(text, str):
            text = " ".join(text.split())[:MAX_TEXT]
            if text and text not in out:
                out.append(text)
        if len(out) >= MAX_ALTERNATIVES:
            break
    return out


def spoken_texts(message: dict) -> list[str]:
    """Wypowiedź z wiadomości telefonu: tekst i ewentualne inne warianty rozpoznania mowy."""
    alts = message.get("alts")
    return _clean_inputs([message.get("v"), *(alts if isinstance(alts, list) else [])])


def judge(texts: Sequence[str], targets: Sequence[Sequence[str]], context: str = "",
          lenient: bool = False, distractors: Sequence[str] = ()) -> Verdict:
    """Która z odpowiedzi (każda z wariantami) pasuje do wypowiedzi.

    targets: lista odpowiedzi, każda jako lista dopuszczalnych zapisów. Uznana jest najlepiej
    pasująca, o ile wyraźnie wygrywa z dystraktorami, czyli błędnymi opcjami.
    """
    texts = _clean_inputs(texts)
    heard = texts[0] if texts else ""
    parsed_targets = [[parse(form, keep_units=False, target=True) for form in forms] for forms in targets]
    parsed_wrong = [parse(form, keep_units=False, target=True) for form in distractors]
    context_words = parse(context).words if context else []
    best: tuple[float, Optional[int], str] = (0.0, None, heard)
    all_empty = True
    for text in texts:
        spoken = parse(text, keep_units=False)
        if spoken.empty:
            continue
        all_empty = False
        scores = [max(score(spoken, form, context_words, lenient) for form in forms) for forms in parsed_targets]
        wrong = max((score(spoken, form, context_words, lenient) for form in parsed_wrong), default=0.0)
        for index, value in enumerate(scores):
            rivals = [s for i, s in enumerate(scores) if i != index] if not lenient else []
            if value >= ACCEPT and value > wrong and all(value > r for r in rivals) and value > best[0]:
                best = (value, index, text)
    if best[1] is None:
        return Verdict(False, None, heard, empty=all_empty)
    return Verdict(True, best[1], best[2])


def is_pass(texts: Sequence[str]) -> bool:
    for text in _clean_inputs(texts):
        words = fold_text(text).split()
        if words and all(w in PASS_WORDS or w == "nie" for w in words) and any(w in PASS_WORDS for w in words):
            return True
    return False


def answerable(answer: str, question: str = "") -> bool:
    """Czy pytanie w ogóle nadaje się do odpowiedzi z głowy (bez listy opcji)."""
    if re.search(r"\b(z tych|z poniższych|z wymienionych|spośród|z podanych)\b", question, re.I):
        return False
    if re.search(r"[×²³⁻₀-₉]|\d,\d", answer):
        return False
    folded = fold_text(answer)
    if not re.search(r"\d", folded) and len(folded.replace(" ", "")) < 2:
        return False
    return len(answer.split()) <= 3


def voice_ready(answer: str, question: str, wrong: Sequence[str], alts: Sequence[str] = ()) -> bool:
    """Pytanie przechodzi samosprawdzenie: uznaje własną odpowiedź i odrzuca każdą błędną opcję.

    Nie przechodzą np. „World Wide Web” wobec „Wide World Web” albo „8 minut” wobec „8 sekund”;
    takie pytania gra zadaje z listą opcji.
    """
    if not answerable(answer, question):
        return False
    targets = [[answer, *alts]]
    if not judge([answer], targets, context=question, distractors=wrong).ok:
        return False
    return not any(judge([w], targets, context=question, distractors=wrong).ok for w in wrong)
