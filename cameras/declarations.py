import cv2
import numpy as np

MIN_STRIP_AREA = 300
MIN_STRIP_RATIO = 2.5
MIN_STRIP_FILL = 0.6
MIN_FIELD_SHARE = 0.25
FIELD_DISTANCE = (0.35, 1.3)
FIELD_SIDEWAYS = 0.6
MAX_PRINT_SATURATION = 70
MIN_PRINT_CONTRAST = 25


def _components(mask: np.ndarray, min_area: float) -> list[tuple[np.ndarray, int]]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    return [(labels == index, int(stats[index, cv2.CC_STAT_AREA])) for index in range(1, count)
            if stats[index, cv2.CC_STAT_AREA] >= min_area]


def count_declarations(image: np.ndarray | None) -> int:
    """Broj deklaracija sa vage na slici: crvena traka uz rub, bijelo polje sa barkodom pa zeleno polje sa znakom."""
    if image is None or not image.size:
        return 0
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    kernel = np.ones((3, 3), np.uint8)
    red = cv2.inRange(hsv, (0, 110, 70), (10, 255, 255)) | cv2.inRange(hsv, (170, 110, 70), (180, 255, 255))
    green = cv2.inRange(hsv, (35, 90, 60), (85, 255, 255))
    red = cv2.morphologyEx(red, cv2.MORPH_OPEN, kernel)
    green = cv2.morphologyEx(green, cv2.MORPH_OPEN, kernel)
    fields = []
    for field, area in _components(green, MIN_STRIP_AREA * MIN_FIELD_SHARE):
        ys, xs = np.nonzero(field)
        fields.append((np.array([xs.mean(), ys.mean()]), area))
    found = 0
    for strip, area in _components(red, MIN_STRIP_AREA):
        ys, xs = np.nonzero(strip)
        (center_x, center_y), (first, second), angle = cv2.minAreaRect(np.column_stack((xs, ys)).astype(np.float32))
        length, width = max(first, second), min(first, second)
        if width <= 0 or length / width < MIN_STRIP_RATIO or area / (length * width) < MIN_STRIP_FILL:
            continue
        radians = np.deg2rad(angle if first >= second else angle + 90)
        axis = np.array([np.cos(radians), np.sin(radians)])
        center = np.array([center_x, center_y])
        for field_center, field_area in fields:
            offset = field_center - center
            along = abs(float(offset @ axis))
            across = float(np.linalg.norm(offset - (offset @ axis) * axis))
            if along > FIELD_SIDEWAYS * length or not FIELD_DISTANCE[0] * length <= across <= FIELD_DISTANCE[1] * length:
                continue
            middle = (center + field_center) / 2
            half = max(2, round(length * 0.1))
            x, y = round(float(middle[0])), round(float(middle[1]))
            window = hsv[max(0, y - half):y + half + 1, max(0, x - half):x + half + 1]
            # Bijelo polje sa barkodom i tekstom: bez boje, a jak kontrast (sto i kutija su jednolični).
            if window.size and window[..., 1].mean() <= MAX_PRINT_SATURATION and window[..., 2].std() >= MIN_PRINT_CONTRAST:
                found += 1
                break
    return found
