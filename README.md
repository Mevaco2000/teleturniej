# Sutoliada

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

### Odpowiedzi z głowy (mikrofon)

W 1 z 10, Familiadzie, The Floor i Jaka to melodia nie ma listy odpowiedzi. Gracz stuka duży mikrofon i mówi odpowiedź albo ją wpisuje. Milionerzy zostają przy ABCD, bo tak wygląda ten format.

- **Rozpoznawanie mowy** robi przeglądarka telefonu (Chrome na Androidzie, Safari na iPhonie). Wymaga HTTPS, więc działa w grze przez internet. Przy pierwszym użyciu telefon zapyta o zgodę na mikrofon. Gdy mikrofonu nie ma, zostaje pole tekstowe, w którym zadziała też dyktowanie z klawiatury.
- **Ocena odpowiedzi** jest wyrozumiała: przyjmuje odmianę („w Warszawie”), samo nazwisko („Kopernik”), liczby słownie („tysiąc czterysta dziesięć”) i dodatki typu „chyba”. Nie przejdzie wyliczanka kilku odpowiedzi ani odpowiedź, która pasuje też do innej opcji (samo „Bolesław”).
- **Gospodarz jak prowadzący:** w 1 z 10 po źle ocenionej odpowiedzi widzi przycisk **Uznaj odpowiedź**, gdy telefon coś przekręcił.
- **The Floor:** mikrofon słucha przez cały Twój czas, a słowo „pas” losuje nowe hasło.
- Kilka pytań nie nadaje się do odpowiedzi z głowy (wzory chemiczne, „Który z tych…”). Przy nich telefon sam pokaże opcje.
- Łatwiejszy tryb z listą odpowiedzi włączysz w opcjach gry: **Odpowiedzi → Do wyboru**.
- W 1 z 10 opcja **Pytania** ustawia poziom. **Trudne** (domyślnie) losuje w rundzie 1 pytania średnie, w rundzie 2 trudne, a w finale trudne i bardzo trudne. **Normalne** zaczyna od łatwych.

### Milionerzy dla wielu osób

Opcja **Tryb** w Milionerach:

- **Wszyscy na drabince** (domyślnie): wszyscy odpowiadają naraz na te same pytania. Każdy ma własne koła ratunkowe i sam decyduje, kiedy się wycofać. Zła odpowiedź spada do kwoty gwarantowanej. Kto odpadnie albo się wycofa, zostaje publicznością: jego głosy tworzą wynik koła „publiczność”, a grający mogą do niego zadzwonić. Zegar nie staje dla nikogo. Telewizor po zamknięciu odpowiedzi pokazuje, kto co zaznaczył.
- **Jeden fotel + zakłady**: klasyczne eliminacje i jedna osoba na fotelu. Reszta ma po 1000 żetonów i przy każdym pytaniu obstawia 100, 250, 500 albo wszystko, czy gracz odpowie dobrze. Trafny zakład zwraca stawkę z nadwyżką równą stawce, nietrafiony ją zabiera, a gdy gracz się wycofa, zakłady wracają do właścicieli. W rankingu przy remisie wygrywa więcej żetonów.

### Turniej

„Turniej” na liście gier łączy gry w jedną rozgrywkę: 1 z 10, Familiada, The Floor, Jaka to melodia i na koniec Milionerzy. W opcjach są też wersje „Bez muzyki” i „Szybki” (The Floor, Familiada, Milionerzy).

- **Punkty za miejsce** w każdej grze: 10, 7, 5, 3, 2, a dalej po 1. Remis daje te same punkty. Boty z The Floor się nie liczą, a w Familiadzie miejsce drużyny dostaje każdy jej członek.
- **Typowanie podium** przed każdą grą: każdy wskazuje na telefonie, kto zajmie 1., 2. i 3. miejsce. Trafione miejsce daje 3 pkt, pomyłka o jedno miejsce 1 pkt. W Familiadzie się nie typuje, bo drużyny są losowane dopiero na starcie.
- Po każdej grze telewizor pokazuje wyniki (miejsca, typy, punkty), a potem tabelę turnieju. Gospodarz może przewinąć je przyciskiem **Dalej**.
- Każda gra używa ustawień, które wybierzesz dla niej w menu, np. tryb Milionerów albo rozmiar planszy w The Floor.
- Gra, która nie może ruszyć (muzyka bez włączonego telewizora) albo się przerwie, zostaje pominięta, a turniej toczy się dalej.

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
Z tego samego powodu w grze na laptopie nie ma przycisku mikrofonu: odpowiedzi wpisuje się w pole albo dyktuje mikrofonem z klawiatury telefonu.
Jeśli masz własną domenę i certyfikat, możesz włączyć HTTPS opcjami `--cert`, `--key` i `--public-url`.

### Gdy telefon lub telewizor nie może się połączyć z laptopem

Najczęstszą przyczyną jest zapora Windows. Serwer ostrzega przy starcie, jeśli sieć ma profil **Publiczna**.

- Zmień profil na prywatny (PowerShell jako administrator):
  `Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private`
- Gdy Windows zapyta o dostęp dla Pythona, zezwól na sieci prywatne.
- W sieci, której nie chcesz oznaczać jako prywatną, otwórz tylko port gry dla urządzeń z tej samej podsieci:
  `New-NetFirewallRule -DisplayName "Sutoliada" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Action Allow`
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
  answers.py   ocena odpowiedzi mówionych i pisanych (odmiana, liczby słownie, próba z błędnych opcji)
  games/       każda gra to automat stanów; każdy etap oczekiwania ma limit czasu
web/tv/        ekran telewizora
web/app/       PWA na telefon; ekrany gier opisuje serwer listą bloków
data/          pytania, tablice Familiady, kategorie The Floor, katalog utworów
tests/         testy logiki i kontrola w prawdziwej przeglądarce
render.yaml    wdrożenie na Render.com (python -m server --cloud)
```

Telefon nigdy nie dostaje poprawnej odpowiedzi przed jej ujawnieniem. Telewizor wraca do swojego pokoju dzięki tajnemu kluczowi zapisanemu w przeglądarce, więc nikt nie podejrzy gry, podając się za telewizor.

**Nowe pytania:** dopisz je do plików w `data/`. Format łatwo odczytać z istniejących wpisów, a `tests/test_data.py` wychwyci błędy, np. wskazówkę zdradzającą odpowiedź.
Inne dopuszczalne zapisy odpowiedzi podasz w polu `"alt"`, np. `{"q": "…", "a": "Ocean Spokojny", "alt": ["Pacyfik"], …}`. Tak samo działa to w hasłach The Floor, a w Familiadzie jako trzeci element odpowiedzi: `["Ręcznik", 34, ["ręczniki"]]`.

**Punkty w Familiadzie są szacunkowe**, napisane ręcznie, a nie pochodzą z prawdziwej ankiety.

**Testy:**

```
pip install -r requirements-dev.txt
python -m pytest tests
python tests/browser_check.py zrzuty     # rozgrywka w Edge lub Chrome, zrzuty ekranu w folderze „zrzuty”
```

Nazwy programów należą do ich właścicieli. Projekt jest przeznaczony do prywatnej zabawy i przed publiczną dystrybucją wymagałby zmiany nazw.
