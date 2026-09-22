import os
import cv2


from typing import List, Optional, Tuple
import cv2
import numpy as np


class CameraCalibrator:

  def __init__(
      self,
      # Współrzędne ramki z grabbera [y_min, y_max, x_min, x_max]
      # Jeśli lewa strona opada, sprawdź czy x_min nie powinno być np. 10 lub 11
      roi_crop: Tuple[int, int, int, int] = (16, 226, 9, 312),
      native_res: Tuple[int, int] = (256, 192),
      # Współczynnik k1: jeśli linia nadal jest wygięta w łuk, zwiększ ujemną wartość (np. z -0.22 na -0.26)
      k1: float = -0.31,
      k2: float = 0.08,
      # Ewentualne przesunięcie środka optycznego od środka geometrycznego kadru (w pikselach)
      center_offset: Tuple[float, float] = (0.0, 0.0),
  ):
    self.y_min, self.y_max, self.x_min, self.x_max = roi_crop
    self.native_w, self.native_h = native_res

    # Wyznaczamy macierz K bezpośrednio w przestrzeni natywnej 256x192
    # Ogniskowa dla obiektywu 4mm na matrycy 12um: fx = fy = 4.0 / 0.012 = 333.3 px
    fx = 330.0
    fy = 330.0
    cx = (self.native_w / 2.0) + center_offset[0]  # 128.0 domyślnie
    cy = (self.native_h / 2.0) + center_offset[1]  # 96.0 domyślnie

    self.K = np.array(
        [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64
    )

    # Wektor dystorsji: k1, k2, p1, p2, k3
    # Płaskie soczewki termiczne rzadko wymagają p1/p2 (dystorsja tangencjalna)
    self.dist = np.array([k1, k2, 0.0, 0.0, 0.0], dtype=np.float64)

    # Przygotowanie map remapowania dla maksymalnej wydajności (sub-milisekunda na klatkę)
    self.new_K, _ = cv2.getOptimalNewCameraMatrix(
        self.K, self.dist, (self.native_w, self.native_h), 0
    )
    self.map1, self.map2 = cv2.initUndistortRectifyMap(
        self.K,
        self.dist,
        None,
        self.new_K,
        (self.native_w, self.native_h),
        cv2.CV_16SC2,
    )

  def crop_and_rescale(self, frame: np.ndarray) -> np.ndarray:
    """Wycina czarną ramkę i przywraca natywne proporcje 256x192."""
    cropped = frame[self.y_min : self.y_max, self.x_min : self.x_max]
    return cv2.resize(
        cropped, (self.native_w, self.native_h), interpolation=cv2.INTER_AREA
    )

  def undistort_image(self, frame: np.ndarray) -> np.ndarray:
    """Przyjmuje surową klatkę 320x240, wycina ramkę, skaluje do 256x192 i prostuje dystorsję."""
    #native_frame = self.crop_and_rescale(frame)
    # cv2.remap jest znacznie szybsze niż cv2.undistort na Raspberry Pi 5
    return cv2.remap(frame, self.map1, self.map2, cv2.INTER_LINEAR)

  def process_grabber_point(
      self, pt_grabber: Tuple[float, float]
  ) -> Tuple[float, float]:
    """Przelicza punkt z surowej klatki grabbera (320x240) bezpośrednio do

    wyprostowanego układu sensora (256x192).
    """
    gx, gy = pt_grabber

    # 1. Translacja po obcięciu ramki
    crop_w = self.x_max - self.x_min
    crop_h = self.y_max - self.y_min
    ax = gx - self.x_min
    ay = gy - self.y_min

    # 2. Skalowanie do przestrzeni natywnej 256x192
    nx = ax * (self.native_w / float(crop_w))
    ny = ay * (self.native_h / float(crop_h))

    # 3. Odprostowanie punktu w macierzy natywnej
    src_pt = np.array([[[nx, ny]]], dtype=np.float64)
    undistorted = cv2.undistortPoints(src_pt, self.K, self.dist, P=self.new_K)
    return float(undistorted[0, 0, 0]), float(undistorted[0, 0, 1])

  def undistort_point(self, pt: Tuple[float, float]) -> Tuple[float, float]:
    """Usuwa dystorsję z punktu (x, y) pobranego z klatki po crop and rescale (256x192).

    Nie wykonuje żadnego ponownego przycinania ani skalowania!
    """
    src_pt = np.array([[[pt[0], pt[1]]]], dtype=np.float64)
    undistorted = cv2.undistortPoints(
        src_pt, self.K, self.dist, P=self.new_K
    )
    return float(undistorted[0, 0, 0]), float(undistorted[0, 0, 1])


class Camera:

  def __init__(self, dev="/dev/video0", width=320, height=240):
    self.cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    self.calibrator = CameraCalibrator()
    for _ in range(100):
      _ = self.get_frame()

  def get_frame(self, CROP_BORDER: bool = True) -> Optional[np.ndarray]:
    ret, frame = self.cap.read()
    if not ret:
      return None
    if CROP_BORDER:
      return self.calibrator.crop_and_rescale(frame)
    return frame

  def release(self):
    self.cap.release()

  def save_frame(self, frame, filename):
    cv2.imwrite(filename, frame)