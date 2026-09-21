from typing import List, Tuple
import cv2
import numpy as np

# ==============================================================================
# GŁÓWNE PARAMETRY DETEKCJI (ZGODNE Z KODEM MATLAB)
# ==============================================================================
GATE_MIN_MAX_VAL = 225       # Minimalna bezwzględna jasność w kadrze (0-255)
SIGMA_FACTOR = 3             # Mnożnik odchylenia standardowego (mean + k * std)
MIN_AREA = 2                 # Minimalna powierzchnia plamy w px (odpowiednik bwareaopen)
MAX_AREA = 80                # Maksymalna powierzchnia plamy w px
ASPECT_RATIO_MIN = 0.5       # Minimalny stosunek szerokości do wysokości BoundingBox
ASPECT_RATIO_MAX = 2.0       # Maksymalny stosunek szerokości do wysokości BoundingBox
MIN_DIST_PX = 150.0          # Minimalny dystans między celami w px (~7-10 m w terenie)
MAX_TARGETS = 2              # Maksymalna liczba zwracanych punktów
# ==============================================================================


def detect_hotspots(
    frame: np.ndarray,
    gate_min_max_val: int = GATE_MIN_MAX_VAL,
    sigma_factor: float = SIGMA_FACTOR,
    min_area: int = MIN_AREA,
    max_area: int = MAX_AREA,
    aspect_ratio_min: float = ASPECT_RATIO_MIN,
    aspect_ratio_max: float = ASPECT_RATIO_MAX,
    min_dist_px: float = MIN_DIST_PX,
    max_targets: int = MAX_TARGETS,
) -> List[Tuple[int, int]]:
  """Wykrywa współrzędne pikselowe hotspotów na podanej klatce obrazu.

  :param frame: Obraz wejściowy w formacie BGR lub skali szarości.
  :return: Lista krotek [(x1, y1), (x2, y2)] ze środkami celów w pikselach.
  """
  # 1. Konwersja do skali szarości
  if len(frame.shape) == 3:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  else:
    gray = frame

  # 2. Statystyki tła
  mean_bg, std_bg = cv2.meanStdDev(gray)
  mean_bg = float(mean_bg[0][0])
  std_bg = float(std_bg[0][0])
  _, max_val, _, _ = cv2.minMaxLoc(gray)

  # 3. Bramka bezpieczeństwa (odrzucenie klatek bez wyraźnego celu)
  if max_val < gate_min_max_val or (max_val - mean_bg) < (sigma_factor * std_bg):
    return []

  # 4. Próg dynamiczny i binaryzacja
  adaptive_thresh = max(
      float(gate_min_max_val), round(mean_bg + sigma_factor * std_bg)
  )
  adaptive_thresh = min(adaptive_thresh, 254.0)

  _, bw = cv2.threshold(gray, adaptive_thresh, 255, cv2.THRESH_BINARY)

  # 5. Znalezienie konturów (odpowiednik regionprops)
  contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

  candidates = []
  mask = np.zeros(gray.shape, dtype=np.uint8)

  for cnt in contours:
    # W MATLABie regionprops 'Area' to liczba pikseli obiektu.
    # W OpenCV cv2.contourArea mierzy pole wierzchołkowe wg wzoru Greena.
    # Aby odsiać plamy poniżej min_area (w tym bwareaopen(2)), liczymy moment zerowy m00:
    M = cv2.moments(cnt)
    area = M["m00"]
    if area < min_area or area > max_area:
      continue

    # Filtracja po proporcjach kształtu (Aspect Ratio)
    bx, by, bw_w, bh_h = cv2.boundingRect(cnt)
    if bh_h == 0:
      continue
    aspect_ratio = float(bw_w) / float(bh_h)
    if aspect_ratio < aspect_ratio_min or aspect_ratio > aspect_ratio_max:
      continue

    # Statystyki jasności wewnątrz obiektu
    mask.fill(0)
    cv2.drawContours(mask, [cnt], -1, 255, -1)
    mean_intensity, _, _, _ = cv2.mean(gray, mask=mask)

    # Centroid (środek ciężkości)
    cx = M["m10"] / M["m00"]
    cy = M["m01"] / M["m00"]

    # Wskaźnik jakości: całkowita energia plamy (powierzchnia x jasność)
    score = area * mean_intensity

    candidates.append({"x": cx, "y": cy, "score": score})

  if not candidates:
    return []

  # 6. Sortowanie kandydatów według score malejąco
  candidates.sort(key=lambda c: c["score"], reverse=True)

  # 7. Wybór do max_targets z zachowaniem minimalnego dystansu
  selected_hotspots: List[Tuple[float, float]] = []

  for cand in candidates:
    too_close = False
    for sel_x, sel_y in selected_hotspots:
      dist = np.hypot(cand["x"] - sel_x, cand["y"] - sel_y)
      if dist < min_dist_px:
        too_close = True
        break

    if not too_close:
      selected_hotspots.append((int(cand["x"]), int(cand["y"])))
      if len(selected_hotspots) >= max_targets:
        break

  return selected_hotspots