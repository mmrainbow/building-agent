import numpy as np
import torch
from torch import nn
from torchvision import models, transforms

from .base import BasePredictor


class MaterialPredictor(BasePredictor):
    class EfficientNetV2MultiLabel(nn.Module):
        def __init__(self, num_classes):
            super().__init__()
            self.base = models.efficientnet_v2_l(weights=None)
            in_features = self.base.classifier[1].in_features
            self.base.classifier = nn.Sequential(
                nn.Dropout(p=0.5),
                nn.Linear(in_features, num_classes),
                nn.Sigmoid(),
            )

        def forward(self, x):
            return self.base(x)

    def __init__(self, weights_path):
        super().__init__()
        self.type_dict = np.asarray(
            [
                "Unknown1",
                "Unknown2",
                "Stone Hanging",
                "Mortar",
                "Glass Curtain Wall",
                "Unknown3",
                "Real Stone Paint",
                "Coating",
                "Aluminum Plate",
                "Face Brick",
                "Mosaic",
                "Unknown4",
            ]
        )
        self.model = self.EfficientNetV2MultiLabel(12)
        self.model.load_state_dict(torch.load(weights_path, map_location=self.device))
        self.model.to(self.device)
        self.model.eval()
        self.transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Resize((448, 448)),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def predict(self, images: list) -> list:
        results = []
        for i in range(0, len(images), self.batch_size):
            batch = images[i : i + self.batch_size]
            processed = self.transform_image(batch, self.transform)
            probs = self.model(processed).detach().cpu().numpy()
            batch_results = []
            for prob in probs:
                selected = self.type_dict[prob > 0.3]
                if len(selected) == 0:
                    max_idx = int(np.argmax(prob))
                    result = f"{self.type_dict[max_idx]}(low confidence)"
                else:
                    result = ",".join(selected)
                batch_results.append(result)
            results.extend(batch_results)
        return results
