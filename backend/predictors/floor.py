import numpy as np
from ultralytics import YOLO

from .base import BasePredictor
from .floor_recognition import detect_columns, exclude_points, get_main_building


class FloorPredictor(BasePredictor):
    def __init__(self, building_model_path, outer_obj_model_path):
        super().__init__()
        self.building_model = YOLO(building_model_path).eval()
        self.outer_obj_model = YOLO(outer_obj_model_path).eval()

    def predict(self, images: list) -> list:
        floor_results = []
        for image in images:
            buildings = self.building_model.predict(
                source=image,
                imgsz=640,
                save=False,
                conf=0.5,
                iou=0.55,
                show=False,
                verbose=False,
            )
            outer_objects = self.outer_obj_model.predict(
                source=image,
                imgsz=960,
                save=False,
                conf=0.5,
                iou=0.6,
                show=False,
                verbose=False,
            )

            main_building = get_main_building(buildings[0])
            points = exclude_points(main_building, outer_objects[0])
            columns = detect_columns(points) if points else []

            floors = 1
            max_column = None
            for column in columns:
                if floors < len(column):
                    floors = len(column)
                    max_column = column

            if floors > 1 and main_building is not None and max_column:
                y_distance = (
                    main_building[1]
                    + main_building[3] / 2
                    - max_column[0][1]
                    - max_column[0][3] / 2
                )
                height_diff = [
                    max_column[i][1] - max_column[i + 1][1]
                    for i in range(floors - 1)
                ]
                max_diff = np.max(height_diff) if height_diff else 0
                if max_diff > 0 and y_distance / max_diff > 1.5:
                    floors += 1

            floor_results.append(f"{floors}层")
        return floor_results
