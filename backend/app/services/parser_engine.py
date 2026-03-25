from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.models.schemas import ParseResponse


def parse_plan(file_path: Path) -> ParseResponse:
    if file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        image = cv2.imread(str(file_path), cv2.IMREAD_GRAYSCALE)
    else:
        img = Image.open(file_path).convert("L")
        image = np.array(img)

    if image is None:
        return ParseResponse(walls=[], room_polygons=[], labels=[])

    edges = cv2.Canny(image, 80, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=30, maxLineGap=6)

    walls: list[list[list[float]]] = []
    if lines is not None:
        for ln in lines[:250]:
            x1, y1, x2, y2 = ln[0]
            walls.append([[float(x1), float(y1)], [float(x2), float(y2)]])

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    room_polygons: list[list[list[float]]] = []
    for cnt in contours:
        eps = 0.01 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, eps, True)
        if cv2.contourArea(approx) < 600:
            continue
        poly = [[float(p[0][0]), float(p[0][1])] for p in approx]
        room_polygons.append(poly)

    labels: list[str] = []
    return ParseResponse(walls=walls, room_polygons=room_polygons, labels=labels)
