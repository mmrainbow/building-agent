import numpy as np
from ultralytics import YOLO

from .base import BasePredictor


class HiddenDangerPredictor(BasePredictor):
    type_names = {
        0: "空鼓",
        1: "渗水",
        2: "脱落",
        3: "裂缝",
    }

    @classmethod
    def calculate_polygon_area(cls, points):
        x = points[:, 0]
        y = points[:, 1]
        return 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

    @classmethod
    def process_results(cls, results):
        all_defects = []
        for result in results:
            defects = []
            if hasattr(result, "obb"):
                for idx, obb in enumerate(result.obb, start=1):
                    points = obb.xyxyxyxy.reshape(4, 2).cpu().numpy()
                    danger_type = int(obb.cls.item())
                    area = cls.calculate_polygon_area(points)
                    defects.append(
                        {
                            "id": idx,
                            "type": cls.type_names.get(danger_type, "Unknown"),
                            "area": float(area),
                            "box": points.tolist(),
                        }
                    )
            all_defects.append(defects)
        return all_defects

    def __init__(self, weights_path):
        super().__init__()
        self.model = YOLO(weights_path).eval()

    def predict(self, images: list) -> list:
        all_results = []
        for i in range(0, len(images), self.batch_size):
            batch = images[i : i + self.batch_size]
            detections = self.model.predict(
                source=batch,
                save=False,
                show=False,
                iou=0.1,
                conf=0.4,
                verbose=False,
            )
            all_results.extend(self.process_results(detections))
        return all_results
