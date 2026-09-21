import datetime
import os
import cv2

FIFO_PATH = "/tmp/cam_trigger"
DEV_VIDEO = "/dev/video0"
WIDTH = 320
HEIGHT = 240

# Usunięcie starego potoku, jeśli istnieje
if os.path.exists(FIFO_PATH):
  os.remove(FIFO_PATH)
os.mkfifo(FIFO_PATH)

# Inicjalizacja strumienia V4L2
cap = cv2.VideoCapture(DEV_VIDEO, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

print("Kamera otwarta. Oczekiwanie na komendy w /tmp/cam_trigger...")
frame_counter = 0

# Otwarcie potoku FIFO w trybie nieblokującym
fifo_fd = os.open(FIFO_PATH, os.O_RDONLY | os.O_NONBLOCK)

try:
  while True:
    ret, frame = cap.read()
    if not ret:
      continue

    # Odczyt poleceń z potoku
    try:
      cmd = os.read(fifo_fd, 64).decode().strip()
    except BlockingIOError:
      cmd = ""

    if cmd == "snap":
      frame_counter += 1
      now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
      filename = f"kadr_{frame_counter:04d}_{now}.jpg"

      # Konwersja do skali szarości, jeśli obraz ma 3 kanały
      print(frame.shape)
      gray = (
          cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
          if len(frame.shape) == 3
          else frame
      )
      cv2.imwrite(filename, gray)
      print(f"Zapisano: {filename}")

    elif cmd == "exit":
      print("Zamykanie programu...")
      break

finally:
  cap.release()
  os.close(fifo_fd)
  if os.path.exists(FIFO_PATH):
    os.remove(FIFO_PATH)
