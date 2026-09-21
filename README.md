# Hotspot detection

Moduł służy do wykrywania jasnych, małych obszarów (hotspotów) na obrazie z kamery termowizyjnej. Docelowo jest to komponent większego programu sterującego dronem:

1. program drona otrzymuje trigger wykonania zdjęcia,
2. `Camera` pobiera aktualną klatkę z kamery,
3. `detect_hotspots` analizuje klatkę,
4. program nadrzędny zapisuje zdjęcie, wynik detekcji i ewentualnie przelicza współrzędne pikselowe na pozycję w terenie.

## Pliki

- `camera.py` - klasa `Camera`, czyli otwarcie urządzenia V4L2 i pobranie pojedynczej klatki.
- `detect_hotspot.py` - funkcja `detect_hotspots(frame, ...)`, zawierająca algorytm detekcji.
- `main.py` - obecny przykład jednorazowego pobrania klatki, zapisania wyników i logu CSV. Wymaga dostosowania do aktualnego API detektora, dlatego nie jest najlepszym punktem wejścia dla programu drona.
- `process_media.py` - pomocniczy skrypt do testowania detekcji na obrazie lub wideo. Nie jest częścią docelowego sterowania dronem.
- `camera_streamer.py` - starszy, niezależny wariant pracy z FIFO `/tmp/cam_trigger`. Nie jest potrzebny, jeśli program drona wywołuje `Camera` bezpośrednio.

## Wymagania

- Python 3
- OpenCV z obsługą V4L2 (`opencv-python` lub pakiet systemowy OpenCV)
- NumPy
- Linux z urządzeniem kamery widocznym jako `/dev/video0` albo inna ścieżka V4L2

Przykładowa instalacja w środowisku wirtualnym:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install opencv-python numpy
```

Na Raspberry Pi lub innym komputerze pokładowym należy dodatkowo sprawdzić, czy użytkownik ma dostęp do urządzenia kamery, np. przez grupę `video`.

## API kamery

```python
from camera import Camera

camera = Camera(dev="/dev/video0", width=320, height=240)
try:
    frame = camera.get_frame()
    if frame is None:
        raise RuntimeError("Nie udało się pobrać klatki z kamery")
finally:
    camera.release()
```

`get_frame()` zwraca klatkę OpenCV jako `numpy.ndarray` albo `None`, gdy odczyt się nie powiedzie. Domyślnie (`CROP_BORDER=True`) zwracany obraz jest:

- przycięty z ramki grabbera według `roi_crop=(16, 226, 9, 312)`,
- przeskalowany do `256 x 192`,
- nadal w formacie BGR, jeśli wejściowa kamera zwróciła obraz trójkanałowy.

Jeśli program nadrzędny potrzebuje surowej klatki grabbera, należy jawnie wywołać `camera.get_frame(CROP_BORDER=False)`. Wtedy oczekiwana rozdzielczość to `320 x 240`, o ile urządzenie zaakceptuje tę konfigurację.

`release()` trzeba wywołać przy każdym zakończeniu pracy, również po błędzie. Obecna klasa nie zgłasza w konstruktorze, że urządzenie nie otworzyło się poprawnie, dlatego program nadrzędny powinien sprawdzić dostęp do kamery przez pierwszy odczyt i traktować `None` jako błąd krytyczny.

Kamera próbuje skonfigurować urządzenie jako:

- urządzenie: `/dev/video0`,
- rozdzielczość wejściowa: `320 x 240`,
- format V4L2: `YUYV`.

Wartości `width` i `height` dotyczą wejścia kamery, ale aktualny `CameraCalibrator` zakłada crop właściwy dla `320 x 240`. Zmiana rozdzielczości wymaga równoczesnego przeliczenia `roi_crop`; nie należy zmieniać tylko argumentów konstruktora.

### Kalibracja i prostowanie obrazu

`Camera` tworzy `CameraCalibrator`, ale domyślna ścieżka `get_frame()` wykonuje tylko `crop_and_rescale()`. Nie wykonuje `undistort_image()`. Prostowanie całej klatki trzeba wywołać jawnie:

```python
raw_frame = camera.get_frame(CROP_BORDER=False)
rectified_frame = camera.calibrator.undistort_image(raw_frame)
```

`process_grabber_point((x, y))` przyjmuje punkt w układzie surowego grabbera `320x240` i zwraca punkt w wyprostowanym układzie `256x192`. Nie należy używać tej metody dla współrzędnych zwróconych przez domyślne `get_frame()`, ponieważ te współrzędne są już w obrazie po cropie i skalowaniu.

## API detekcji

```python
from detect_hotspot import detect_hotspots

hotspots = detect_hotspots(frame)
for x, y in hotspots:
    print(f"Hotspot: x={x:.1f}, y={y:.1f}")
```

## Przykładowa integracja z programem nadrzędnym

```python
from camera import Camera
from detect_hotspot import detect_hotspots

camera = Camera(dev="/dev/video0", width=320, height=240)
try:
    frame = camera.get_frame()
    if frame is None:
        raise RuntimeError("Nie udało się pobrać klatki z kamery")
    hotspots = detect_hotspots(frame)
finally:
    camera.release()
```

Ważne: wynik to lista krotek `(x, y)`, a nie lista słowników. Współrzędne są pikselowe, liczone od lewego górnego rogu obrazu:

- `x` rośnie w prawo,
- `y` rośnie w dół.

Brak wykrycia jest sygnalizowany przez pustą listę `[]`.

### Parametry algorytmu

Najważniejsze ustawienia można przekazać przy wywołaniu:

```python
hotspots = detect_hotspots(
    frame,
    gate_min_max_val=225,
    sigma_factor=3,
    min_area=2,
    max_area=80,
    aspect_ratio_min=0.5,
    aspect_ratio_max=2.0,
    min_dist_px=150.0,
    max_targets=2,
)
```

Algorytm najpierw odrzuca klatkę, jeśli nie ma wystarczająco jasnego i wyraźnego obiektu, następnie wyznacza dynamiczny próg `mean + sigma_factor * std`, filtruje kontury po powierzchni i proporcjach, a na końcu wybiera najmocniejsze punkty z zachowaniem minimalnej odległości.

Parametry są zależne od kamery, wysokości lotu i optyki. `min_dist_px` nie jest odległością w metrach. Relację piksel-metr trzeba wyznaczyć kalibracją dla konkretnej wysokości i pola widzenia.

## Zalecany przepływ w programie drona

Program sterujący dronem powinien wywoływać własny kod integracyjny w reakcji na trigger, a nie uruchamiać nowy proces kamery dla każdego zdjęcia. Przykład minimalnego adaptera:

```python
from datetime import datetime, timezone
from pathlib import Path

import cv2

from camera import Camera
from detect_hotspot import detect_hotspots


def capture_and_detect(camera, output_dir):
    frame = camera.get_frame()
    if frame is None:
        raise RuntimeError("Kamera nie zwróciła klatki")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / f"{timestamp}_raw.jpg"
    if not cv2.imwrite(str(raw_path), frame):
        raise IOError(f"Nie udało się zapisać obrazu: {raw_path}")

    hotspots = detect_hotspots(frame)
    return {
        "timestamp": timestamp,
        "image_path": str(raw_path),
        "hotspots": [{"pixel_x": x, "pixel_y": y} for x, y in hotspots],
    }


camera = Camera(dev="/dev/video0", width=320, height=240)
try:
    # Ten fragment powinien zostać wywołany przez zdarzenie/trigger z autopilota.
    result = capture_and_detect(camera, "wyniki_detekcji")
    print(result)
finally:
    camera.release()
```

W rzeczywistym systemie wywołanie `capture_and_detect()` powinno być połączone z komunikatem z autopilota lub kontrolera misji. Należy unikać blokowania pętli sterowania dronem: zapis obrazu i detekcję można przekazać do kolejki lub osobnego wątku/procesu, o ile dostęp do kamery pozostaje kontrolowany przez jednego właściciela.

Typowy wynik przekazywany dalej może wyglądać tak:

```json
{
  "timestamp": "2026-09-21T07:34:25.123456Z",
  "image_path": "wyniki_detekcji/20260921T073425_123456Z_raw.jpg",
  "hotspots": [
    {"pixel_x": 161.5, "pixel_y": 92.0}
  ]
}
```

Same współrzędne pikselowe nie są jeszcze pozycją GPS. Do geolokalizacji potrzebne będą między innymi: GPS drona, wysokość, orientacja kamery, orientacja drona, parametry obiektywu oraz kalibracja transformacji obrazu na teren.

## Uruchomienie testu na pojedynczym obrazie

Po poprawieniu lub pominięciu obecnego `test_detection.py` można testować detektor bez kamery:

```python
import cv2
from detect_hotspot import detect_hotspots

frame = cv2.imread("kadr.jpg")
if frame is None:
    raise RuntimeError("Nie można wczytać obrazu")

for x, y in detect_hotspots(frame):
    print(f"x={x:.1f}, y={y:.1f}")
```

## Kolejność integracji

1. Uruchomić kamerę na komputerze pokładowym i sprawdzić odczyt klatek.
2. Sprawdzić, że pierwszy odczyt nie zwraca `None` i że obraz ma oczekiwany rozmiar `256x192`.
3. Podłączyć trigger z autopilota do `capture_and_detect()`.
4. Przekazywać dalej wynik wraz z timestampem i identyfikatorem zdjęcia.
5. Dopiero po walidacji offline włączyć reakcję drona na wykryty hotspot.

## Review: problemy do rozwiązania przed integracją

Poniższe punkty dotyczą bezpośrednio kontraktu modułów używanych przez program nadrzędny:

1. **Brak jawnej informacji o nieotwartej kamerze.** `Camera.__init__()` nie sprawdza `cap.isOpened()`. Błąd urządzenia może ujawnić się dopiero jako `None` z `get_frame()`. W systemie drona należy dodać kontrolę inicjalizacji albo wymusić kontrolę pierwszej klatki przed startem misji.
2. **Kontrakt rozdzielczości jest ukryty.** Argumenty `width` i `height` konfigurują grabber, ale `CameraCalibrator` ma stałe granice cropa i wynik `256x192`. Każda inna rozdzielczość może dać błędny obraz lub błędne współrzędne.
3. **Koszt inicjalizacji kamery jest stały.** Konstruktor odrzuca 100 klatek bez przerwy. To może opóźniać reakcję na trigger i utrudnia testowanie. Rozgrzewkę lepiej kontrolować jawnie w programie nadrzędnym albo parametrizować.
4. **Domyślna klatka nie jest prostowana optycznie.** `get_frame()` przycina i skaluje obraz, ale nie wywołuje `undistort_image()`. Detektor pracuje więc na obrazie z dystorsją, a `process_grabber_point()` korzysta z innego układu współrzędnych niż wynik detekcji.
5. **Brak walidacji wejścia detektora.** `detect_hotspots()` zakłada poprawny, niepusty `numpy.ndarray` w skali szarości lub BGR. `None`, obraz BGRA, tablica o złym typie albo pusty obraz mogą zakończyć się wyjątkiem OpenCV zamiast kontrolowanym wynikiem.
6. **Typ wyniku nie zgadza się z implementacją.** Adnotacja deklaruje `List[Tuple[int, int]]`, a centroid jest najpierw liczony jako float i dopiero rzutowany na `int`. Program nadrzędny powinien traktować wynik jako współrzędne całkowite, ale warto ustalić ten kontrakt formalnie.
7. **Parametry detekcji są wrażliwe na skalę.** `min_area`, `max_area` i `min_dist_px` dotyczą obrazu po przeskalowaniu do `256x192`. Zmiana rozdzielczości lub cropa wymaga ponownej kalibracji, a `min_dist_px` nie jest odległością w metrach.

Przed lotem należy przetestować osobno: brak kamery, brak klatki, obraz bez hotspotu, jeden hotspot, dwa hotspoty oraz hotspoty znajdujące się bliżej niż `min_dist_px`.