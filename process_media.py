import argparse
import os
import cv2
from detect_hotspot import detect_hotspots


def draw_targets(frame, targets):
  """Rysuje celowniki wokół wykrytych punktów."""
  vis = frame.copy()
  if len(vis.shape) == 2:
    vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)

  for i, (cx, cy) in enumerate(targets, start=1):
    ix, iy = int(round(cx)), int(round(cy))
    # Zielony okrąg
    cv2.circle(vis, (ix, iy), 6, (0, 255, 0), 1)
    # Czerwony krzyżyk
    cv2.line(vis, (ix - 8, iy), (ix + 8, iy), (0, 0, 255), 1)
    cv2.line(vis, (ix, iy - 8), (ix, iy + 8), (0, 0, 255), 1)
    # Etykieta ze współrzędnymi
    cv2.putText(
        vis,
        f"#{i} ({ix},{iy})",
        (ix + 8, iy - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (0, 255, 255),
        1,
    )
  return vis


def process_image(img_path, output_dir):
  frame = cv2.imread(img_path)
  if frame is None:
    print(f"Błąd: Nie można wczytać pliku {img_path}")
    return

  targets = detect_hotspots(frame)
  print(f"Obraz: {img_path} | Wykryto punktów: {len(targets)}")
  for idx, (x, y) in enumerate(targets, 1):
    print(f"  Cel #{idx}: X={x:.2f}, Y={y:.2f}")

  vis = draw_targets(frame, targets)

  base_name = os.path.basename(img_path)
  out_name = f"detekcja_{base_name}"
  out_path = os.path.join(output_dir, out_name)
  cv2.imwrite(out_path, vis)
  print(f"Zapisano wynik do: {out_path}")


def process_video(video_path, output_dir):
  cap = cv2.VideoCapture(video_path)
  if not cap.isOpened():
    print(f"Błąd: Nie można otworzyć pliku wideo {video_path}")
    return

  width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
  height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
  fps = cap.get(cv2.CAP_PROP_FPS)
  if fps <= 0 or np.isnan(fps):
    fps = 25.0

  base_name = os.path.basename(video_path)
  name_without_ext, _ = os.path.splitext(base_name)
  out_path = os.path.join(output_dir, f"detekcja_{name_without_ext}.mp4")

  fourcc = cv2.VideoWriter_fourcc(*"mp4v")
  writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

  frame_idx = 0
  detected_frames = 0

  print(f"Przetwarzanie wideo: {video_path} ({width}x{height} @ {fps:.1f} fps)")

  while True:
    ret, frame = cap.read()
    if not ret:
      break

    frame_idx += 1
    targets = detect_hotspots(frame)

    if targets:
      detected_frames += 1
      print(f"Klatka {frame_idx:05d}: Wykryto {len(targets)} cel(e)")

    vis = draw_targets(frame, targets)
    writer.write(vis)

  cap.release()
  writer.release()
  print(
      f"\nZakończono. Przeanalizowano {frame_idx} klatek (detekcje w"
      f" {detected_frames} klatkach)."
  )
  print(f"Zapisano wideo wynikowe do: {out_path}")


if __name__ == __name__:
  parser = argparse.ArgumentParser(
      description="Testowanie detekcji na zdjęciu lub filmie."
  )
  parser.add_argument(
      "input_path", type=str, help="Ścieżka do pliku graficznego lub wideo"
  )
  parser.add_argument(
      "--out",
      type=str,
      default="output_tests",
      help="Katalog zapisu wyników (domyślnie: output_tests)",
  )
  args = parser.parse_args()

  os.makedirs(args.out, exist_ok=True)

  video_exts = {".mp4", ".mkv", ".avi", ".mov", ".ts"}
  _, ext = os.path.splitext(args.input_path.lower())

  if ext in video_exts:
    process_video(args.input_path, args.out)
  else:
    process_image(args.input_path, args.out)