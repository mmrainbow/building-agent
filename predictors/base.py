from typing import List

import cv2
import numpy as np
import torch
from torchvision import transforms


class BasePredictor:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = 2

    def predict(self, images: List[np.ndarray]) -> List:
        raise NotImplementedError

    def transform_image(
        self,
        image_list: List[np.ndarray],
        trans: transforms.Compose,
    ) -> torch.Tensor:
        if not isinstance(trans, transforms.Compose):
            raise TypeError("trans should be a Compose object")

        tensor_list = []
        for image in image_list:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            tensor_list.append(trans(rgb_image))
        return torch.stack(tensor_list).to(self.device)

    def load_images_from_paths(self, paths: List[str]) -> List[np.ndarray]:
        images = []
        for path in paths:
            image = cv2.imread(path)
            if image is None:
                raise ValueError(f"Failed to read image: {path}")
            images.append(image)
        return images
