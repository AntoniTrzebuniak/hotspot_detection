import os
import cv2


class Camera:

  def __init__(self, dev="/dev/video0", width=320, height=240):
    self.cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    for _ in range(100):
      _ = self.get_frame()

  def get_frame(self):
    ret, frame = self.cap.read()
    if not ret:
      return None
    return frame

  def release(self):
    self.cap.release()

  def save_frame(self, frame, filename):
    cv2.imwrite(filename, frame)