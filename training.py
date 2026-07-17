from imageai.Detection.Custom import DetectionModelTrainer
import os

class Trainer:
    def __init__(self, model_path):
        self.model_path = model_path

    def train_model(self):
        trainer = DetectionModelTrainer()
        trainer.setModelTypeAsYOLOv3()
        trainer.setDataDirectory(data_directory=self.model_path)
        trainer.setTrainConfig(object_names_array=self.get_labels(), batch_size=4, num_experiments=100, train_from_pretrained_model="yolo.h5")
        trainer.trainModel()

    def get_labels(self):
        with open(self.labels_path, 'r') as f:
            labels = [line.strip() for line in f.readlines()]
        return labels