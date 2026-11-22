# Teleturniej

Pięć teleturniejów na telewizor: **1 z 10, Jaka to melodia, The Floor, Familiada i Milionerzy**.
Telewizor pokazuje grę w swojej przeglądarce, a każdy gra na swoim telefonie.

Są dwa sposoby uruchomienia, oba bez kupowania czegokolwiek:

| | Gra przez internet | Gra na laptopie |
| --- | --- | --- |
| Serwer | darmowy hosting Render.com | laptop w domowej sieci |
| Laptop w trakcie gry | niepotrzebny | musi być włączony |
| Internet | potrzebny | niepotrzebny |
| Telefon | pełna aplikacja (PWA) | strona lub skrót na ekranie głównym |

## Gra przez internet

Telewizor otwiera stały adres, np. `teleturniej-ab12.onrender.com/tv`, a telefony instalują grę jako aplikację.
Każdy telewizor zakłada własną grę z 4-literowym kodem, więc z jednego serwera mogą korzystać różne domy naraz.

### Jednorazowe wdrożenie (ok. 15 minut)

1. Załóż darmowe konto na [github.com](https://github.com) i utwórz puste repozytorium (**New repository**, może być prywatne).
2. Wyślij do niego projekt. W PowerShellu, w folderze projektu:
   ```
   git init
   git add .
   git commit -m "Teleturniej"
   git branch -M main
   git remote add origin https://github.com/TWOJA-NAZWA/teleturniej.git
   git push -u origin main
   ```
3. Zaloguj się na [render.com](https://render.com) kontem GitHub. Plan darmowy nie wymaga karty płatniczej.
4. Wybierz **New → Blueprint**, wskaż repozytorium i kliknij **Apply**. Render sam odczyta ustawienia z pliku `render.yaml`.
5. Po kilku minutach na stronie usługi pojawi się adres, np. `https://teleturniej-ab12.onrender.com`.

Każdy kolejny `git push` automatycznie aktualizuje grę.

### Gra

1. Na telewizorze otwórz przeglądarkę i wpisz adres usługi z `/tv` na końcu, np. `teleturniej-ab12.onrender.com/tv`. Dodaj go do zakładek.
2. Naciśnij **OK** na pilocie. Włączy to dźwięk, który przeglądarki domyślnie blokują.
3. Zeskanuj telefonem kod QR z ekranu albo wejdź na adres gry i wpisz kod z telewizora. Pierwsza osoba zostaje gospodarzem i wybiera grę.
4. Telefon zaproponuje instalację aplikacji: na Androidzie przyciskiem **Zainstaluj aplikację**, na iPhonie przez **Udostępnij → Do ekranu początkowego**.
   Zainstalowana aplikacja pamięta ostatnią grę, a do nowej dołączysz, wpisując kod z telewizora.

Odświeżenie strony lub chwilowe wyłączenie telefonu czy telewizora nie przerywa gry: telewizor wraca do swojego pokoju, a telefon do rozgrywki.

### Ograniczenia darmowego planu

- **Usypianie.** Serwer usypia, gdy przez 15 minut nie jest otwarty żaden ekran gry, a pierwsze otwarcie po przerwie trwa do minuty. Otwarty ekran TV co minutę daje znać, że gra trwa, więc w jej trakcie serwer nie zaśnie.
- **Restart kasuje trwające gry.** Dzieje się tak po uśpieniu i po każdej aktualizacji. Telewizor sam założy wtedy nową grę z nowym kodem.
- **Muzyka.** W „Jaka to melodia” działają hity bez śpiewu (Deezer), hity ze śpiewem (iTunes) i melodie wbudowane. Własne pliki MP3 działają tylko w grze na laptopie.
- **Limit czasu.** Render daje 750 godzin pracy miesięcznie, czyli wystarczy na jedną usługę działającą bez przerwy.

Gdyby Render przestał być darmowy, załączony `Dockerfile` uruchamia ten sam serwer na innym hostingu z kontenerami.
Serwer czyta port ze zmiennej `PORT`, a publiczny adres podasz opcją `--public-url https://adres`.

## Gra na laptopie (bez internetu)

Potrzebny jest Python 3.11 lub nowszy, a wszystkie urządzenia muszą być w tej samej sieci Wi-Fi.

1. Kliknij dwukrotnie `start.bat` (na Linuksie i macOS uruchom `./start.sh`). Pierwszy start pobiera dwie biblioteki, więc wymaga internetu.
2. W przeglądarce telewizora wpisz adres wypisany w oknie serwera, np. `http://192.168.1.13:8000/tv`.
3. Naciśnij **OK** na pilocie i zeskanuj telefonem kod QR z ekranu.

Pełna instalacja PWA wymaga HTTPS, którego przeglądarki nie dają pod adresem `http://192.168.x.x`. W tym trybie dodasz więc tylko skrót do strony z menu przeglądarki.
Jeśli masz własną domenę i certyfikat, możesz włączyć HTTPS opcjami `--cert`, `--key` i `--public-url`.

### Gdy telefon lub telewizor nie może się połączyć z laptopem

Najczęstszą przyczyną jest zapora Windows. Serwer ostrzega przy starcie, jeśli sieć ma profil **Publiczna**.

- Zmień profil na prywatny (PowerShell jako administrator):
  `Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private`
- Gdy Windows zapyta o dostęp dla Pythona, zezwól na sieci prywatne.
- W sieci, której nie chcesz oznaczać jako prywatną, otwórz tylko port gry dla urządzeń z tej samej podsieci:
  `New-NetFirewallRule -DisplayName "Teleturniej" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Action Allow`
- Sprawdź, czy wszystkie urządzenia są w tej samej sieci. Sieci dla gości i niektóre sieci uczelniane blokują komunikację między urządzeniami.
- Jeśli wykryty adres jest błędny (np. przez VPN albo kartę WSL), podaj go ręcznie: `.\start.bat --ip 192.168.1.13`.
- Zajęty port zmienisz opcją `--port 8080`.

### Muzyka do „Jaka to melodia” na laptopie

Źródło wybiera gospodarz przed grą:

| Źródło | Skąd | Internet |
| --- | --- | --- |
| Hity bez śpiewu (domyślnie) | 30-sekundowe fragmenty wersji instrumentalnych z Deezer | na laptopie, przy pierwszym użyciu utworu |
| Hity ze śpiewem + moje MP3 | 30-sekundowe fragmenty oryginałów z iTunes oraz pliki z `data/music` | na laptopie, przy pierwszym użyciu utworu |
| Tylko moje MP3 | pliki z `data/music` | nie |
| Melodie wbudowane | melodie klasyczne i tradycyjne grane przez syntezator | nie |

Bez internetu i bez własnych plików gra sama przechodzi na melodie wbudowane.

**Hity bez śpiewu** grają jak orkiestra w telewizyjnym teleturnieju: słychać melodię, ale nie słowa.
- Zagraniczne hity mają w Deezer wiele wersji fortepianowych, karaoke i instrumentalnych. Gra wybiera tę, która wymienia oryginalnego wykonawcę (np. „Originally Performed by Queen”), bez chórków. Najchętniej bierze wersję, w której melodię gra instrument.
- Polskie przeboje pochodzą z albumów z instrumentalnymi wersjami (np. Ryszard Szwec Band, Marek Dutkiewicz, KOMBI Łosowski). Ich tytuły nie wymieniają wykonawcy, więc w `data/songs.json` utwór ma wskazany numer nagrania w Deezer (pole `instr`).
- Gdy w wybranej kategorii zabraknie wersji instrumentalnych, gra dopełnia ją oryginałami z tej samej kategorii.

- **Własne utwory:** wrzuć pliki `.mp3`, `.m4a`, `.ogg`, `.aac` lub `.wav` do `data/music`. Nazwij je `Wykonawca - Tytuł.mp3`, bo z nazwy powstaje odpowiedź w grze. Gra startuje od 30. sekundy utworu.
- **Gra bez internetu:** `.\start.bat --prefetch-music` pobierze z góry fragmenty całego katalogu, oryginały i wersje instrumentalne, do `data/cache` (kilkanaście minut, ok. 250 MB).
- **Własny katalog:** utwory do wyszukania są w `data/songs.json`. Nowy zagraniczny hit nie potrzebuje pola `instr`, bo gra sama znajdzie wersję instrumentalną.

Pobrane fragmenty należą do ich właścicieli i są przeznaczone wyłącznie do prywatnej zabawy.

## Telewizory

Wystarczy przeglądarka wbudowana w telewizor:

- **Samsung:** aplikacja **Internet**.
- **LG:** aplikacja **Przeglądarka internetowa**.
- **Android TV / Google TV:** zwykle nie ma przeglądarki, ale w Google Play są darmowe, np. **TV Bro**.

Ekran TV jest pisany zachowawczo pod starsze przeglądarki, ale **nie był testowany na fizycznym telewizorze**.
Jeśli telewizor wygasza ekran w trakcie gry, wyłącz w jego ustawieniach wygaszacz lub automatyczne czuwanie.
Bardzo stare telewizory mogą nie otworzyć adresu HTTPS z powodu nieaktualnych certyfikatów. Wtedy pozostaje gra na laptopie pod adresem HTTP.

## Dla programistów

```
server/        logika gier i serwer (aiohttp); stan gry jest tylko tutaj
  rooms.py     pokoje z kodami: każdy telewizor zakłada własną grę
  games/       każda gra to automat stanów; każdy etap oczekiwania ma limit czasu
web/tv/        ekran telewizora
web/app/       PWA na telefon; ekrany gier opisuje serwer listą bloków
data/          pytania, tablice Familiady, kategorie The Floor, katalog utworów
tests/         testy logiki i kontrola w prawdziwej przeglądarce
render.yaml    wdrożenie na Render.com (python -m server --cloud)
```

Telefon nigdy nie dostaje poprawnej odpowiedzi przed jej ujawnieniem. Telewizor wraca do swojego pokoju dzięki tajnemu kluczowi zapisanemu w przeglądarce, więc nikt nie podejrzy gry, podając się za telewizor.

**Nowe pytania:** dopisz je do plików w `data/`. Format łatwo odczytać z istniejących wpisów, a `tests/test_data.py` wychwyci błędy, np. wskazówkę zdradzającą odpowiedź.

**Punkty w Familiadzie są szacunkowe**, napisane ręcznie, a nie pochodzą z prawdziwej ankiety.

**Testy:**

```
pip install -r requirements-dev.txt
python -m pytest tests
python tests/browser_check.py zrzuty     # rozgrywka w Edge lub Chrome, zrzuty ekranu w folderze „zrzuty”
```

Nazwy programów należą do ich właścicieli. Projekt jest przeznaczony do prywatnej zabawy i przed publiczną dystrybucją wymagałby zmiany nazw.
