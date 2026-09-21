import os
import cv2


from typing import List, Optional, Tuple
import cv2
import numpy as np


class CameraCalibrator:
  """Klasa do usuwania czarnej ramki, kompensacji skalowania oraz prostowania

  dystorsji obiektywu kamery termowizyjnej.
  """

  def __init__(
      self,
      # Granice aktywnego obrazu wewnątrz klatki grabbera (320x240)
      # [y_min, y_max, x_min, x_max] - dostosowane do widocznej ramki z grabbera
      roi_crop: Tuple[int, int, int, int] = (16, 226, 9, 312),
      # Docelowa rozdzielczość natywna sensora (zazwyczaj 256x192)
      native_res: Tuple[int, int] = (256, 192),
      # Macierz kamery K (dla wyprostowanego aktywnego obrazu po cropie)
      camera_matrix: Optional[np.ndarray] = None,
      # Współczynniki dystorsji [k1, k2, p1, p2, k3]
      dist_coeffs: Optional[np.ndarray] = None,
  ):
    self.y_min, self.y_max, self.x_min, self.x_max = roi_crop
    self.crop_w = self.x_max - self.x_min
    self.crop_h = self.y_max - self.y_min
    self.native_w, self.native_h = native_res

    # Domyślne przybliżenie macierzy kamery K jeśli brak dokładnej kalibracji szachownicą
    # Dla sensora po wycięciu ramki: cx w środku, ogniskowa ~ szerokość * 1.15
    if camera_matrix is None:
      fx = self.crop_w * 1.2
      fy = self.crop_h * 1.2
      cx = self.crop_w / 2.0
      cy = self.crop_h / 2.0
      self.K = np.array(
          [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64
      )
    else:
      self.K = np.array(camera_matrix, dtype=np.float64)

    # Domyślne współczynniki dystorsji (dystorsja beczkowata obiektywu 4mm)
    # Wartość k1 ujemna prostuje "beczkę"
    if dist_coeffs is None:
      self.dist = np.array([-0.18, 0.05, 0.0, 0.0, 0.0], dtype=np.float64)
    else:
      self.dist = np.array(dist_coeffs, dtype=np.float64)

  def crop_frame(self, frame: np.ndarray) -> np.ndarray:
    """Wycina aktywny obszar termiczny, odrzucając czarną ramkę grabbera."""
    return frame[self.y_min : self.y_max, self.x_min : self.x_max]

  def transform_point_to_active(
      self, pt_grabber: Tuple[float, float]
  ) -> Tuple[float, float]:
    """Transformuje współrzędną (x, y) z surowej klatki grabbera (320x240) do
    układu aktywnego obrazu bez czarnej ramki.
    """
    gx, gy = pt_grabber
    ax = gx - self.x_min
    ay = gy - self.y_min
    return ax, ay

  def undistort_point(
      self, pt_active: Tuple[float, float], to_native: bool = True
  ) -> Tuple[float, float]:
    """Wyrównuje dystorsję optyczną punktu.

    :param pt_active: Punkt (x, y) w układzie aktywnego obrazu (po usunięciu
      ramki)
    :param to_native: Czy przeskalować wynik do natywnej rozdzielczości (np.
      256x192)
    :return: Skorygowany punkt (x_rect, y_rect)
    """
    # cv2.undistortPoints wymaga wektora o kształcie (N, 1, 2)
    src_pt = np.array([[[pt_active[0], pt_active[1]]]], dtype=np.float64)

    # Odprostowanie z zachowaniem projekcji do macierzy K
    undistorted = cv2.undistortPoints(src_pt, self.K, self.dist, P=self.K)
    ux, uy = undistorted[0, 0, 0], undistorted[0, 0, 1]

    if to_native:
      ux = ux * (self.native_w / float(self.crop_w))
      uy = uy * (self.native_h / float(self.crop_h))

    return float(ux), float(uy)

  def process_grabber_point(
      self, pt_grabber: Tuple[float, float], to_native: bool = True
  ) -> Tuple[float, float]:
    """Wykonuje pełną transformację: Grabber (320x240) -> Odcięcie ramki ->
    Usunięcie dystorsji -> Skalowanie.
    """
    ax, ay = self.transform_point_to_active(pt_grabber)
    return self.undistort_point((ax, ay), to_native=to_native)

  def undistort_image(self, frame_cropped: np.ndarray) -> np.ndarray:
    """Prostuje dystorsję na całym wyciętym obrazie (używane głównie do podglądu)."""
    h, w = frame_cropped.shape[:2]
    new_K, _ = cv2.getOptimalNewCameraMatrix(
        self.K, self.dist, (w, h), 0, (w, h)
    )
    return cv2.undistort(frame_cropped, self.K, self.dist, None, new_K)

class Camera:

  def __init__(self, dev="/dev/video0", width=320, height=240):
    self.cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    for _ in range(100):
      _ = self.get_frame()

    self.calibrator = CameraCalibrator()

  def get_frame(self, CROP_BORDER: bool = True) -> Optional[np.ndarray]:
    ret, frame = self.cap.read()
    if not ret:
      return None
    return frame
    if CROP_BORDER:
      return self.calibrator.crop_frame(frame)
    return frame

  def release(self):
    self.cap.release()

  def save_frame(self, frame, filename):
    cv2.imwrite(filename, frame)