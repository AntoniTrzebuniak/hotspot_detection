import datetime
import os
import time
from camera import Camera
import cv2
from detect_hotspot import detect_hotspots


def main():
  # Katalog na zapisywane wyniki
  output_dir = "wyniki_detekcji"
  os.makedirs(output_dir, exist_ok=True)

  # Inicjalizacja kamery
  print("Inicjalizacja kamery termowizyjnej...")
  cam = Camera(dev="/dev/video0", width=320, height=240)

  # Rozgrzewka bufora V4L2 (odrzucenie pierwszych klatek synchronizacyjnych)
  print("Oczekiwanie na synchronizację sygnału...")
  for _ in range(100):
    _ = cam.get_frame()
    time.sleep(0.03)

  frame_id = 0

  try:
    print("System gotowy. Wykonywanie zdjęcia i detekcji...")

    # 1. Pobranie bieżącej klatki
    frame = cam.get_frame()
    if frame is None:
      print("Błąd: Nie udało się pobrać klatki z kamery.")
      return

    frame_id += 1
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    base_name = f"kadr_{frame_id:04d}_{timestamp}"

    # Zapis surowej klatki
    raw_path = os.path.join(output_dir, f"{base_name}_raw.jpg")
    cv2.imwrite(raw_path, frame)
    print(f"Zapisano surowy kadr: {raw_path}")

    # 2. Wykonanie detekcji
    # min_dist_px=150 odpowiada separacji ~7-10 m przy wysokości 20 m
    hotspots = detect_hotspots(
        frame=frame,
        thresh_val=215,
        min_area=2,
        max_area=60,
        min_dist_px=150.0,
        max_targets=2,
    )

    print(f"\n--- WYNIKI DETEKCJI (Znaleziono: {len(hotspots)}) ---")

    # 3. Rysowanie wyników na kopii klatki
    vis_frame = frame.copy()
    if len(vis_frame.shape) == 2:
      vis_frame = cv2.cvtColor(vis_frame, cv2.COLOR_GRAY2BGR)

    log_entries = []

    for i, spot in enumerate(hotspots, start=1):
      cx = spot["x"]
      cy = spot["y"]
      mean_val = spot["mean_val"]
      max_val = spot["max_val"]
      area = spot["area"]

      info = (
          f"Cel #{i}: Środek=({cx:.2f}, {cy:.2f}) | "
          f"Śr. jasność={mean_val:.1f} | Max={max_val:.0f} | Pole={area:.1f}px"
      )
      print(info)
      log_entries.append(
          f"{timestamp},{frame_id},{i},{cx:.2f},{cy:.2f},{mean_val:.1f},{max_val:.0f},{area:.1f}\n"
      )

      # Rysowanie okręgu wokół wykrytego punktu
      pt = (int(round(cx)), int(round(cy)))
      cv2.circle(vis_frame, pt, 8, (0, 0, 255), 1)

      # Krzyżyk / celownik
      cv2.line(
          vis_frame, (pt[0] - 12, pt[1]), (pt[0] + 12, pt[1]), (0, 255, 0), 1
      )
      cv2.line(
          vis_frame, (pt[0], pt[1] - 12), (pt[0], pt[1] + 12), (0, 255, 0), 1
      )

      # Etykieta tekstowa z numerem celu i jasnością
      cv2.putText(
          vis_frame,
          f"#{i} T:{mean_val:.0f}",
          (pt[0] + 10, pt[1] - 5),
          cv2.FONT_HERSHEY_SIMPLEX,
          0.4,
          (0, 255, 255),
          1,
      )

    # 4. Zapis klatki z naniesioną detekcją
    result_path = os.path.join(output_dir, f"{base_name}_detekcja.jpg")
    cv2.imwrite(result_path, vis_frame)
    print(f"Zapisano zwizualizowany wynik: {result_path}")

    # 5. Dopisywanie do logu CSV
    csv_path = os.path.join(output_dir, "hotspots_log.csv")
    csv_exists = os.path.exists(csv_path)
    with open(csv_path, "a") as f:
      if not csv_exists:
        f.write(
            "timestamp,frame_id,target_id,pixel_x,pixel_y,mean_val,max_val,area_px\n"
        )
      for entry in log_entries:
        f.write(entry)

  finally:
    cam.release()
    print("Zwolniono zasoby kamery.")


#if __name__ == "__main__":
 # main()
main()