"""Kontrola w prawdziwej przeglądarce: serwer, ekran TV i cztery telefony rozgrywają każdą grę.

Testy logiki nie wykryją błędów interfejsu, np. przycisku, który nic nie robi.

    python tests/browser_check.py FOLDER_NA_ZRZUTY [gry] [--real-music]

gry: oot,mil,mila,fam,floor,mel,tour (domyślnie wszystkie; mila to Milionerzy „Wszyscy na drabince”, tour to turniej). --real-music gra wersje instrumentalne hitów z Deezer (wymaga internetu).
Używa Edge lub Chrome zainstalowanego w systemie.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parent.parent
PORT = 8123
BASE = f"http://localhost:{PORT}"

# Podgląd odtwarzacza i syntezatora tworzonych wewnątrz sound.js.
AUDIO_SPY = """
(function () {
  var RealAudio = window.Audio;
  window.__audios = [];
  window.Audio = function () { var a = new RealAudio(); window.__audios.push(a); return a; };
  var RealContext = window.AudioContext;
  window.__contexts = [];
  window.AudioContext = function () { var c = new RealContext(); window.__contexts.push(c); return c; };
})();
"""

errors: list[str] = []
out_dir = Path(".")


def wire(page, label):
    page.on("pageerror", lambda e: errors.append(f"[{label}] {e}"))
    page.on("console", lambda m: errors.append(f"[{label}] konsola: {m.text}") if m.type == "error" else None)
    page.on("requestfailed", lambda r: errors.append(f"[{label}] nieudane żądanie: {r.url} {r.failure}")
            if "/media/" not in r.url else None)


def shot(page, name):
    page.screenshot(path=str(out_dir / f"{name}.png"))
    print("  zrzut:", name)


def tap_text(phone, text, timeout=8000):
    phone.get_by_text(text, exact=False).first.click(timeout=timeout)


def wait_text(page, text, timeout=15000):
    page.get_by_text(text, exact=False).first.wait_for(timeout=timeout)


def phone_showing(phones, selector):
    for phone in phones:
        locator = phone.locator(selector)
        if locator.count() and locator.first.is_enabled():
            return phone, locator
    return None, None


def say(phone, text):
    """Odpowiedź z głowy wpisana w pole (w prawdziwej grze także z mikrofonu)."""
    box = phone.locator("form.answer-box input")
    box.fill(text)
    box.press("Enter")


def try_mic(phone, name):
    """Przeglądarka bez mikrofonu ma pokazać komunikat, a nie wywołać błąd strony."""
    mic = phone.locator("button.mic")
    if not mic.count():
        print("  brak rozpoznawania mowy w tej przeglądarce: zostaje pole tekstowe")
        return
    mic.click()
    time.sleep(1.2)
    print("  mikrofon:", phone.locator(".heard").inner_text() or "(słucha)")
    shot(phone, name)


def click_first_option(phones):
    phone, locator = phone_showing(phones, "button.option:not([disabled])")
    if not phone:
        return False
    try:
        locator.first.click(timeout=1500)
    except PlaywrightError:
        return False  # gra przeszła dalej w trakcie kliknięcia
    return True


def end_game(host):
    quit_button = host.locator("button.quit")
    if quit_button.count():
        quit_button.click()
    else:
        tap_text(host, "Wróć do wyboru gry")
    wait_text(host, "Wybierz grę")


def start_game(host, title, options=()):
    host.locator(".game-card", has_text=title).click()
    for label in options:
        host.locator("button.chip", has_text=label).first.click()
        time.sleep(0.15)
    tap_text(host, "Zaczynamy!")


def play_one_of_ten(tv, phones, host, real_music):
    start_game(host, "1 z 10", ["10 s"])
    wait_text(tv, "Po dwa pytania")
    shot(tv, "oot_1_round")
    tv.locator(".q-card").wait_for(timeout=8000)
    shot(tv, "oot_2_question")

    # Odświeżenie w trakcie pytania nie może przerwać gry ani wylogować gracza.
    tv.reload()
    tv.locator(".q-card").wait_for(timeout=5000)
    tv.keyboard.press("Enter")
    bystander = next(p for p in phones if not p.locator("button.option, form.answer-box").count())
    bystander.reload()
    bystander.locator(".screen.theme-one_of_ten").wait_for(timeout=5000)
    assert not bystander.locator("#join").is_visible(), "odświeżony telefon stracił miejsce w grze"
    print("  odświeżenie TV i telefonu: gra trwa")

    phone, locator = phone_showing(phones, "form.answer-box input")
    if phone:
        assert not tv.locator(".answers").count(), "TV pokazuje opcje w trybie z głowy"
        shot(phone, "phone_oot_answer")
        try_mic(phone, "phone_oot_mic")
        say(phone, "Zanzibar")
        tv.locator(".free-answer").wait_for(timeout=4000)
        shot(tv, "oot_3_reveal")
        accept = host.locator("button.btn", has_text="Uznaj odpowiedź")
        accept.wait_for(timeout=3000)
        shot(host, "phone_oot_accept")
        accept.click()
        wait_text(tv, "uznane przez gospodarza", timeout=3000)
        time.sleep(0.5)  # żarówka szansy zapala się z animacją
        assert tv.locator(".pod.active .bulb.on").count() == 3, "uznanie nie oddało szansy"
        shot(tv, "oot_4_accepted")
        print("  odpowiedź z głowy i uznanie przez gospodarza działają")
    else:
        phone, locator = phone_showing(phones, "button.option")
        assert phone, "żaden telefon nie pokazuje odpowiedzi"
        shot(phone, "phone_oot_answer")
        locator.nth(1).click()
        tv.locator(".answer.correct").wait_for(timeout=4000)
        shot(tv, "oot_3_reveal")
    end_game(host)


def play_millionaires(tv, phones, host, real_music):
    start_game(host, "Milionerzy", ["Jeden fotel + zakłady"])
    wait_text(tv, "Pytanie eliminacyjne")
    shot(tv, "mil_1_qualify")
    for phone in phones:
        phone.locator("button.option").first.click()
    tv.locator(".mil-qualify .hex.correct").wait_for(timeout=20000)
    shot(tv, "mil_2_qualify_reveal")
    tv.locator(".ladder").wait_for(timeout=10000)
    time.sleep(0.5)
    shot(tv, "mil_3_question")
    hot = next(p for p in phones if p.get_by_text("ostateczna odpowiedź").count())
    others = [p for p in phones if p is not hot]
    shot(hot, "phone_mil_hot")
    # Widzowie obstawiają: jeden dobrą odpowiedź za 250, drugi pomyłkę za wszystko.
    shot(others[0], "phone_mil_bet")
    others[0].locator("button.btn", has_text="250").first.click()
    others[1].locator("button.btn", has_text="Va banque").nth(1).click()
    wait_text(tv, "Zakłady widzów", timeout=3000)
    wait_text(others[0], "Obstawiasz dobrą odpowiedź", timeout=3000)
    print("  zakłady widzów przyjęte")
    hot.locator("button.btn", has_text="50:50").click()
    time.sleep(0.3)
    assert hot.locator(".option.gone").count() == 2, "50:50 nie ukryło dwóch odpowiedzi"
    hot.locator("button.btn", has_text="Publiczność").click()
    wait_text(tv, "Pytanie do publiczności")
    shot(tv, "mil_4_audience")
    for phone in others:
        phone.locator("button.option:not(.gone)").first.click()
    tv.locator(".poll").wait_for(timeout=15000)
    time.sleep(0.9)
    shot(tv, "mil_5_poll")
    hot.locator("button.option:not(.gone)").first.click()
    time.sleep(0.2)
    shot(tv, "mil_6_selected")
    tap_text(hot, "ostateczna odpowiedź")
    tv.locator(".hex.correct").wait_for(timeout=6000)
    tv.locator(".bet-line .good, .bet-line .bad").first.wait_for(timeout=3000)
    shot(tv, "mil_7_reveal")
    shot(others[0], "phone_mil_bet_result")
    end_game(host)


def play_millionaires_all(tv, phones, host, real_music):
    start_game(host, "Milionerzy", ["Wszyscy na drabince", "30 s"])
    wait_text(tv, "Wszyscy na drabince")
    tv.locator(".mil-players").wait_for(timeout=10000)
    time.sleep(0.4)
    shot(tv, "mila_1_question")
    shot(phones[0], "phone_mila_question")
    darek = phones[3]
    # Darek się wycofuje i od razu zostaje publicznością.
    darek.locator("button.btn", has_text="Wycofuję się").click()
    darek.locator("button.option").first.wait_for(timeout=3000)
    shot(darek, "phone_mila_audience")
    darek.locator("button.option").nth(1).click()
    # Celina bierze 50:50 i zatwierdza.
    phones[2].locator("button.btn", has_text="50:50").click()
    time.sleep(0.3)
    assert phones[2].locator(".option.gone").count() == 2, "50:50 nie ukryło dwóch odpowiedzi"
    phones[2].locator("button.option:not(.gone)").first.click()
    tap_text(phones[2], "ostateczna odpowiedź")
    # Ania dzwoni do Darka, który już nie gra.
    phones[0].locator("button.btn", has_text="Telefon").click()
    phones[0].locator("button.btn", has_text="Darek").click()
    wait_text(darek, "Dzwoni", timeout=3000)
    shot(darek, "phone_mila_friend")
    darek.locator("button.option").first.click()
    wait_text(phones[0], "Darek: A", timeout=3000)
    shot(phones[0], "phone_mila_call_result")
    shot(tv, "mila_2_decisions")
    for phone in (phones[0], phones[1]):
        phone.locator("button.option").nth(2).click()
        tap_text(phone, "ostateczna odpowiedź")
    wait_text(tv, "Sprawdzamy", timeout=4000)
    time.sleep(0.3)
    shot(tv, "mila_3_locked")
    tv.locator(".hex.correct").wait_for(timeout=6000)
    time.sleep(0.5)
    shot(tv, "mila_4_reveal")
    print("  wszyscy na drabince: wycofanie, publiczność, telefon do gracza i odsłonięcie działają")
    end_game(host)


def play_familiada(tv, phones, host, real_music):
    start_game(host, "Familiada", ["15 s"])
    wait_text(tv, "Drużyny")
    shot(tv, "fam_1_teams")
    tv.locator(".fam-board").wait_for(timeout=15000)
    time.sleep(0.3)
    shot(tv, "fam_2_duel")
    phone, _ = phone_showing(phones, "button.buzz")
    assert phone, "nikt nie ma przycisku zgłoszenia"
    shot(phone, "phone_fam_buzz")
    phone.locator("button.buzz").dispatch_event("pointerdown")
    phone.locator("form.answer-box input").wait_for(timeout=4000)
    shot(phone, "phone_fam_answer")
    # Pytanie z ekranu TV wskazuje tablicę w bazie; odpowiedź pada małymi literami i bez końcówki,
    # tak jak mógłby ją zapisać telefon.
    question = tv.locator(".fam-question").inner_text().strip()
    boards = json.loads((PROJECT / "data" / "familiada.json").read_text(encoding="utf-8"))
    board = next(b for b in boards if b["q"] == question)
    spoken = [a[0].lower().rstrip("ęą") for a in board["answers"]]
    say(phone, "kosmiczny odkurzacz")
    time.sleep(0.5)
    shot(tv, "fam_3_picked")
    words = spoken[:2] + ["kosmiczny odkurzacz", "latający dywan"] + spoken[2:]
    for word in words * 2:
        if tv.locator(".fam-row.earned").count() and tv.locator(".strike.on").count():
            break
        active, _ = phone_showing(phones, "form.answer-box input")
        if active:
            try:
                say(active, word)
            except PlaywrightError:
                pass  # gra przeszła dalej w trakcie wpisywania
        else:
            buzzer, _ = phone_showing(phones, "button.buzz")
            if buzzer:
                buzzer.locator("button.buzz").dispatch_event("pointerdown")
        time.sleep(0.6)
    assert tv.locator(".fam-row.earned").count(), "żadna odpowiedź z głowy nie trafiła na tablicę"
    shot(tv, "fam_4_board")
    end_game(host)


def play_floor(tv, phones, host, real_music):
    start_game(host, "The Floor", ["9 pól", "30 s"])
    tv.locator(".board").wait_for(timeout=8000)
    time.sleep(0.5)
    shot(tv, "floor_1_board")
    wait_text(tv, "wybiera przeciwnika", timeout=15000)
    time.sleep(0.3)
    shot(tv, "floor_2_pick")
    phone, locator = phone_showing(phones, "button.btn:has(.dot)")
    assert phone, "nikt nie wybiera przeciwnika"
    shot(phone, "phone_floor_pick")
    locator.first.click()
    tv.locator(".duel-screen").wait_for(timeout=5000)
    shot(tv, "floor_3_intro")
    tv.locator(".card").wait_for(timeout=8000)
    assert not tv.locator(".card-option").count(), "TV pokazuje opcje w trybie z głowy"
    shot(tv, "floor_4_duel")
    active, _ = phone_showing(phones, "form.answer-box input")
    if active:
        shot(active, "phone_floor_duel")
        say(active, "Zanzibar")
        tv.locator(".feedback.bad").wait_for(timeout=3000)
        shot(tv, "floor_5_after_answer")
        shot(active, "phone_floor_wrong")
        active.locator("form.answer-box input").wait_for(timeout=4000)
        say(active, "pas")
        tv.locator(".feedback.pass").wait_for(timeout=3000)
        print("  The Floor: zła odpowiedź z głowy i słowo „pas” działają")
    end_game(host)


def check_audio(tv, real_music):
    if real_music:
        state = tv.evaluate("() => { var a = window.__audios[0]; return {src: a.currentSrc, paused: a.paused, t: a.currentTime}; }")
        time.sleep(1.2)
        later = tv.evaluate("() => window.__audios[0].currentTime")
        print(f"  odtwarzacz: {state['src']} pauza={state['paused']} czas {state['t']:.2f} -> {later:.2f} s")
        assert "/media/song/" in state["src"], "odtwarzacz nie gra pliku z serwera"
        assert not state["paused"] and later > state["t"], "utwór nie jest odtwarzany"
    else:
        running = tv.evaluate("() => window.__contexts.some(function (c) { return c.state === 'running'; })")
        print("  syntezator aktywny:", running)
        assert running, "kontekst audio nie działa mimo naciśnięcia OK"


def play_melody(tv, phones, host, real_music):
    # Tutaj tryb „Do wyboru”, żeby kontrola obejmowała też listę opcji.
    start_game(host, "Jaka to melodia", ["Hity bez śpiewu" if real_music else "Melodie wbudowane", "6",
                                         "Do wyboru (łatwiej)"])
    tv.locator(".eq.playing").wait_for(timeout=45000)
    time.sleep(0.6)
    shot(tv, "mel_1_play")
    check_audio(tv, real_music)
    phone, _ = phone_showing(phones, "button.buzz")
    assert phone, "brak przycisku zgłoszenia"
    shot(phone, "phone_mel_buzz")
    phone.locator("button.buzz").dispatch_event("pointerdown")
    phone.locator("button.option").first.wait_for(timeout=4000)
    shot(phone, "phone_mel_answer")
    time.sleep(0.2)
    shot(tv, "mel_2_answer")
    if real_music:
        assert tv.evaluate("() => window.__audios[0].paused"), "muzyka gra mimo zgłoszenia"
    phone.locator("button.option").first.click()
    time.sleep(0.5)
    shot(tv, "mel_3_after_answer")
    tv.locator(".reveal-track").wait_for(timeout=25000)
    time.sleep(0.5)
    shot(tv, "mel_4_reveal")
    if real_music:
        art = tv.locator("img.art")
        if art.count():
            assert art.evaluate("el => el.naturalWidth") > 0, "okładka się nie załadowała"
            print("  okładka załadowana")
    end_game(host)


def play_tournament(tv, phones, host, real_music):
    # Krótka pierwsza gra: The Floor bez botów i z 30-sekundowym zegarem.
    host.locator(".game-card", has_text="The Floor").click()
    for label in ("Tylko gracze", "30 s"):
        host.locator("button.chip", has_text=label).first.click()
        time.sleep(0.15)
    host.locator("button.back").click()
    start_game(host, "Turniej", ["Szybki (3)", "Tak"])
    wait_text(tv, "Typujcie na telefonach")
    shot(tv, "tour_1_predict")
    shot(phones[1], "phone_tour_predict")
    names = ["Ania", "Bartek", "Celina", "Darek"]
    for phone in phones:
        for name in names[:3]:
            phone.locator("button.btn", has_text=name).first.click()
            time.sleep(0.1)
    tv.locator(".board").wait_for(timeout=8000)
    wait_text(tv, "Turniej · gra 1 z 3")
    shot(tv, "tour_2_first_game")
    # Nikt nie odpowiada: pojedynki kończą się na zegarze. Wyzywający od razu wybiera rywala.
    deadline = time.time() + 240
    while time.time() < deadline and not tv.get_by_text("Wyniki:").count():
        phone, locator = phone_showing(phones, "button.btn:has(.dot)")
        if phone:
            try:
                locator.first.click(timeout=1000)
            except PlaywrightError:
                pass
        time.sleep(1)
    wait_text(tv, "Wyniki: The Floor", timeout=5000)
    time.sleep(0.5)
    shot(tv, "tour_3_scores")
    shot(phones[0], "phone_tour_scores")
    host.locator("button.btn", has_text="Dalej").click()
    wait_text(tv, "Tabela turnieju", timeout=4000)
    time.sleep(0.5)
    shot(tv, "tour_4_table")
    host.locator("button.btn", has_text="Dalej").click()
    wait_text(tv, "Familiada", timeout=4000)
    shot(tv, "tour_5_next")
    print("  turniej: typowanie, gra w turnieju, wyniki z punktami i tabela działają")
    end_game(host)


GAMES = {
    "oot": play_one_of_ten,
    "mil": play_millionaires,
    "mila": play_millionaires_all,
    "fam": play_familiada,
    "floor": play_floor,
    "mel": play_melody,
    "tour": play_tournament,
}


def lobby_checks(tv, phones, host):
    # Nazwa gracza to tekst od użytkownika: musi zostać tekstem także na ekranie TV.
    assert tv.locator(".lobby-player b").count() == 0, "imię gracza zostało zinterpretowane jako HTML"
    assert tv.get_by_text("<b>x</b>").count() == 1, "imię z HTML nie jest widoczne jako tekst"
    print("  imię z HTML wyświetlone jako tekst")
    target = phones[-1]
    host.locator(".players li", has_text="<b>x</b>").locator("button.kick").click()
    target.locator("#join").wait_for(timeout=4000)
    wait_text(tv, "W grze: 3")
    print("  usunięty gracz wraca do ekranu dołączania")
    target.fill("#name", "Darek")
    target.locator("button[type=submit]").click()
    target.locator(".screen.lobby").wait_for(timeout=4000)


def launch(pw):
    for channel in ("msedge", "chrome"):
        try:
            return pw.chromium.launch(channel=channel, headless=True)
        except PlaywrightError:
            continue
    raise SystemExit("Potrzebna jest przeglądarka Edge lub Chrome.")


def main():
    global out_dir
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    real_music = "--real-music" in sys.argv
    out_dir = Path(args[0] if args else "zrzuty")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = args[1].split(",") if len(args) > 1 else list(GAMES)

    server = subprocess.Popen([sys.executable, "-m", "server", "--port", str(PORT), "--ip", "192.168.1.13"], cwd=PROJECT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    failed = True
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"{BASE}/app/", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as pw:
            browser = launch(pw)
            tv_context = browser.new_context(viewport={"width": 1920, "height": 1080})
            tv_context.add_init_script(AUDIO_SPY)
            tv = tv_context.new_page()
            wire(tv, "tv")
            tv.goto(f"{BASE}/tv")
            wait_text(tv, "Zeskanuj telefonem")
            time.sleep(0.4)
            shot(tv, "lobby_0_empty")
            assert tv.locator("#unlock").is_visible(), "brak prośby o włączenie dźwięku"
            tv.keyboard.press("Enter")
            assert not tv.locator("#unlock").is_visible(), "przycisk OK nie odblokował dźwięku"
            code = tv.locator(".room-code").inner_text().strip()
            assert len(code) == 4, f"brak kodu gry na TV: {code!r}"
            tv.reload()
            tv.locator(".room-code").wait_for(timeout=5000)
            assert tv.locator(".room-code").inner_text().strip() == code, "odświeżony TV założył nową grę"
            tv.keyboard.press("Enter")
            phones = []
            for index, name in enumerate(["Ania", "Bartek", "Celina", "<b>x</b>"]):
                context = browser.new_context(viewport={"width": 390, "height": 780}, has_touch=True, is_mobile=True,
                                              device_scale_factor=2)
                phone = context.new_page()
                wire(phone, name)
                if index == 3:
                    # Ręczne wpisanie kodu: najpierw pomyłka, potem właściwy kod małymi literami.
                    phone.goto(f"{BASE}/")
                    wrong = "ZZZZ" if code != "ZZZZ" else "YYYY"
                    phone.fill("#room", wrong)
                    phone.fill("#name", name)
                    phone.locator("button[type=submit]").click()
                    wait_text(phone, "Nie ma gry o kodzie", timeout=4000)
                    shot(phone, "phone_0_wrong_code")
                    phone.fill("#room", code.lower())
                    assert phone.input_value("#room") == code, "kod nie zamienił się na wielkie litery"
                else:
                    # Tak otwiera grę zeskanowany kod QR.
                    phone.goto(f"{BASE}/app/?r={code}")
                    phone.fill("#name", name)
                    assert phone.input_value("#room") == code, "kod z QR nie trafił do formularza"
                if index == 0:
                    shot(phone, "phone_0_join")
                phone.locator("button[type=submit]").click()
                phone.locator(".screen.lobby").wait_for(timeout=4000)
                phones.append(phone)
            host = phones[0]
            host.on("dialog", lambda d: d.accept())
            time.sleep(0.4)
            print("Poczekalnia:")
            lobby_checks(tv, phones, host)
            time.sleep(0.3)
            shot(tv, "lobby_1_players")
            shot(host, "phone_1_host_lobby")
            shot(phones[1], "phone_2_guest_lobby")
            host.locator(".game-card", has_text="Milionerzy").click()
            time.sleep(0.3)
            shot(tv, "lobby_2_selected")
            shot(host, "phone_3_host_game")
            host.locator("button.back").click()
            for key in only:
                print("Gra:", key)
                GAMES[key](tv, phones, host, real_music)
            browser.close()
        failed = False
    finally:
        server.terminate()
        try:
            output, _ = server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            output, _ = server.communicate()
        if "Traceback" in output or "ERROR" in output:
            print("--- wyjście serwera ---")
            print(output[-3000:])
            failed = True
    print("--- błędy przeglądarek ---")
    print("\n".join(errors) if errors else "brak")
    print("WYNIK:", "BŁĄD" if failed or errors else "OK")
    sys.exit(1 if failed or errors else 0)


main()
