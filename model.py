import os
os.environ['TF_USE_LEGACY_KERAS'] = '1'

from datetime import datetime
import cv2, numpy
from imageai.Detection import ObjectDetection, VideoObjectDetection
import configparser as cfg

config = cfg.ConfigParser()
config.read('./files/model_conf.ini', encoding='utf-8')
numpy.set_printoptions(suppress=False)

class Model:
    def __init__(self, model_path, labels_path):
        try:
            self.timestamp = datetime.now().strftime('%H:%M:%S')
            self.vc = cv2.VideoCapture(0)
            self.model_path = model_path
            self.labels_path = labels_path
            
            os.makedirs("./files/captures", exist_ok=True)
            self.path = f"./files/captures/capture_{self.timestamp}.png"
            self.captured = False
            print(f"[{self.timestamp}] [ModelRecog] model path: {model_path}, labels path: {labels_path}")
            
            if not self.vc.isOpened():
                print(f"[{self.timestamp}] [ModelRecog] Failed to init camera. Check if camera is connected.")
                quit()
                
            print(f"[{self.timestamp}] [ModelRecog] Available camera: {self.vc.getBackendName()}")
            print(f"[{self.timestamp}] [ModelRecog] Model recog init done.")
            
        except IOError as e:
            print(f"[{self.timestamp}] [ModelRecog] IOError: failed to init model recog. Check if files exist.")
            print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")
        except Exception as e:
            print(f"[{self.timestamp}] [ModelRecog] Exception: failed to init model recog.")
            print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")

    def camera_capture(self): # live video feed
        self.execution_path = os.getcwd()
        self.camera = cv2.VideoCapture(0)
        
        self.detector = VideoObjectDetection()
        self.detector.setModelTypeAsYOLOv3()
        self.detector.setModelPath(self.model_path)
        self.detector.loadModel()

        def livefeed(returned_frame):
            cv2.imshow('feed', returned_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.camera.release()
                if hasattr(self, 'cancel_capture'):
                    self.cancel_capture()

        video_path = self.detector.detectObjectsFromVideo(
            camera_input=self.camera, 
            output_file_path=os.path.join(self.execution_path, f"{self.timestamp}_camera_detected_video"), 
            frames_per_second=20, 
            log_progress=True, 
            minimum_percentage_probability=30,
            per_frame_function=livefeed,
            return_detected_frame=True
        )

        print(video_path)
        if self.camera.isOpened():
            self.camera.release()
        cv2.destroyAllWindows()

    def capture(self): # generic default image detection
        print(f"[{self.timestamp}] [ModelRecog] Loading YOLOv3 model. Please wait...")
        self.object = ObjectDetection()
        self.object.setModelTypeAsYOLOv3()
        self.object.setModelPath(self.model_path)
        self.object.loadModel()
        print(f"[{self.timestamp}] [ModelRecog] Model loaded. Starting camera feed.")

        while not self.captured:
            ret, img = self.vc.read()
            
            if not ret or img is None:
                print(f"[{self.timestamp}] [ModelRecog] failed to grab frame. retry")
                continue
            cv2.imshow('camera feed', img)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('c'):
                cv2.imwrite(self.path, img)
                print(f"[{self.timestamp}] [ModelRecog] Image captured. Running detection...")
                self.detections = self.object.detectObjectsFromImage(input_image=self.path, output_image_path=self.path)
                
                for eachObject in self.detections:
                    print(f"[{self.timestamp}] [ModelRecog] detected: {eachObject['name']} with probability: {eachObject['percentage_probability']}")
                result_img = cv2.imread(self.path)
                if result_img is not None:
                    cv2.imshow('result', result_img)
                    cv2.waitKey(0)

            elif key == ord('q'):
                self.cancel_capture()
                break
        self.captured = True
        self.vc.release()
        cv2.destroyAllWindows()

    def cancel_capture(self):
        self.captured = True
        print(f"[{self.timestamp}] [ModelRecog] capture cancelled.")
        
    def getIsitCaptured(self):
        return self.captured