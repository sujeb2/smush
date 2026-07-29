from ultralytics import YOLO

class Trainer:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = YOLO(self.model_path)
        self.train_model()

    def train_model(self):
        print("training start.")
        self.train = self.model.train(data="exp-2/dataset.yaml", epochs=100, imgsz=640)
        print("train done")

    def get_labels(self):
        with open(self.labels_path, 'r') as f:
            labels = [line.strip() for line in f.readlines()]
        return labels

Trainer("files/models/yolo26x.pt")