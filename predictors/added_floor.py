import torch
from torch import nn
from torchvision import models, transforms

from .base import BasePredictor


class AddedFloorPredictor(BasePredictor):
    class EfficientNetV2MultiLabel(nn.Module):
        def __init__(self, num_classes):
            super().__init__()
            self.base_model = models.efficientnet_v2_l(weights=None)
            in_features = self.base_model.classifier[1].in_features
            self.base_model.classifier = nn.Sequential(
                nn.Dropout(p=0.5),
                nn.Linear(in_features, num_classes),
                nn.Sigmoid(),
            )

        def forward(self, x):
            return self.base_model(x)

    def __init__(self, weights_path):
        super().__init__()
        self.model = self.EfficientNetV2MultiLabel(1)
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
            probs = self.model(processed).detach().cpu().numpy().flatten()
            batch_results = ["无加层" if p > 0.5 else "有加层" for p in probs]
            results.extend(batch_results)
        return results
