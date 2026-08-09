import os, sys
os.environ['TF_USE_LEGACY_KERAS'] = '1'

from datetime import datetime
import cv2, numpy, torch
from imageai.Detection import ObjectDetection, VideoObjectDetection
from ultralytics import YOLO
import configparser as cfg

def findCompiledDir():
    if "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        return os.path.dirname(os.path.abspath(__file__))

base = findCompiledDir()
config = cfg.ConfigParser()
config.read(os.path.join(base, 'files', 'model_conf.ini'), encoding='utf-8')
numpy.set_printoptions(suppress=False)
imageai_supported = ["yolov3.pt","tiny-yolov3.pt"]

class Model:
    def __init__(self, model_path, serial):
        try:
            self.timestamp = datetime.now().strftime('%H:%M:%S')
            print(f'[{self.timestamp}] [ModelRecog] Init model..')
            self.vc = cv2.VideoCapture(0)
            self.model_path = model_path
            self.serial_ignore = True
            if(config['GENERIC']['IgnoreGPUWarning'] == 'False'):
                if(not torch.cuda.is_available()):
                    print(f"[{self.timestamp}] [ModelRecog] This program requires CUDA version 8.6>= to run. Please check if driver is installed correctly or Supported GPU is installed in your computer. Check URL to see CUDA>=8.6 supported GPU. (https://developer.nvidia.com/cuda/gpus)")
                    exit(1)
                print(f"[{self.timestamp}] [ModelRecog] Found GPU: {torch.cuda.get_device_name()}")
                print(f"[{self.timestamp}] [ModelRecog] GPU Capability: {torch.cuda.get_device_capability()})")
            if(config['DETECTION'].getboolean('LightMode')):
                print(f"[{self.timestamp}] [ModelRecog] Light mode enabled. Using low resolution for camera capture.")
                self.vc.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                self.vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                self.model_path = model_path.replace("yolov3.pt", imageai_supported[1])
            
            os.makedirs(os.path.join(base, "files", "captures"), exist_ok=True)
            self.path = os.path.join(base, "files", "captures", f"capture_{self.timestamp}.png")
            self.captured = False
            print(f"[{self.timestamp}] [ModelRecog] model path: {model_path}")
            
            if not self.vc.isOpened():
                print(f"[{self.timestamp}] [ModelRecog] Failed to init camera. Check if camera is connected.")
                exit(1)
            
            if serial != None:
                self.serial = serial
                self.serial_ignore = False

            print(f"[{self.timestamp}] [ModelRecog] Available camera: {self.vc.getBackendName()}")
            print(f"[{self.timestamp}] [ModelRecog] Model recog init done.")
            
        except IOError as e:
            print(f"[{self.timestamp}] [ModelRecog] IOError: failed to init model recog. Check if files exist.")
            print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")
        except Exception as e:
            print(f"[{self.timestamp}] [ModelRecog] Exception: failed to init model recog.")
            print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")

    def liveFeedCapture(self): # live video feed
        try:
            self.camera = self.vc if self.vc.isOpened() else cv2.VideoCapture(0)
            target_fps = config['GENERIC'].getint('CameraFPS', fallback=480)*2
            self.camera.set(cv2.CAP_PROP_FPS, target_fps)
            wait_time_ms = int(1000 / target_fps) if target_fps > 0 else 1
                
            self.model = YOLO(self.model_path, task='detect', verbose=config['GENERIC'].getboolean('Verbose')).to("cpu" if not torch.cuda.is_available() else "cuda:0")
            while True:    
                ret, frame = self.camera.read()
                    
                if not ret or frame is None:
                    print(f"[{self.timestamp}] [ModelRecog] failed to grab frame from camera.")
                    self.camera.release()
                    cv2.destroyAllWindows()
                    return 1
                self.detections = self.model.predict(source=frame, conf=0.5, stream=True)
                    
                for result in self.detections:
                    annotated_frame = result.plot()
                    cv2.imshow('feed', annotated_frame)
                    if(config['DETECTION'].getboolean('HasExpectedObject') and not config['DETECTION'].get('ExpectedObject_1') == None or not config['DETECTION'].get('ExpectedObject_2') == None):
                        self.confident = result.boxes.conf
                        self.names = [result.names[cls.item()] for cls in result.boxes.cls.int()]
                        print(f'[{self.timestamp}] [ModelRecog] confident: {self.confident}, names: {self.names}')
                        if(config['DETECTION']['ExpectedObject_1'] in self.names):
                            self.serial.write(f"obj1_detect[{config['DETECTION']['ExpectedObject_1']}]\n")
                            self.camera.release()
                            cv2.destroyAllWindows()
                            return 0
                        elif(config['DETECTION']['ExpectedObject_2'] in self.names):
                            self.serial.write(f"obj2_detect[{config['DETECTION']['ExpectedObject_2']}]\n")
                            self.camera.release()
                            cv2.destroyAllWindows()
                            return 0
                key = cv2.waitKey(wait_time_ms) & 0xFF
                if key == ord('q'):
                    self.camera.release()
                    if hasattr(self, 'cancel_capture'):
                        self.cancel_capture()
                    cv2.destroyAllWindows()
                    return None
        except Exception as e:
            print(f'[{self.timestamp}] [ModelRecog] Ultralytics error occurred. Using fallback imageai ({e})')
            self.execution_path = base
            self.camera = cv2.VideoCapture(0)
            
            self.detector = VideoObjectDetection()
            if(config['GENERIC'].getboolean('LightMode')):
                self.detector.setModelTypeAsTinyYOLOv3()
            else:
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
                output_file_path=os.path.join(self.execution_path, "files", "captures", f"{self.timestamp}_camera_detected_video"), 
                frames_per_second=20, 
                log_progress=True, 
                minimum_percentage_probability=30,
                per_frame_function=livefeed,
                return_detected_frame=True
            )

            print(f'[{self.timestamp}] [ModelRecog] {video_path}')
            if self.camera.isOpened():
                self.camera.release()
            cv2.destroyAllWindows()

    def testCapture(self):
        print(f"[{self.timestamp}] [ModelRecog] Model load start.")
        if(not config['DETECTION'].getboolean('UseNonSupportedModel')): # only for yolov3
            self.object = ObjectDetection()
            if(config['GENERIC'].getboolean('LightMode')):
                self.object.setModelTypeAsTinyYOLOv3()
            else:
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
                    self.detections = self.model.predict(source=self.path, conf=0.25, stream=True)
                    
                    for result in self.detections:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            class_name = result.names[class_id]
                            probability = float(box.conf[0]) * 100
                            
                            print(f"[{self.timestamp}] [ModelRecog] detected: {class_name} with probability: {probability:.2f}%")
                            
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
        else: # ultralytics
            self.model = YOLO(self.model_path, verbose=config['GENERIC'].getboolean("Verbose"))
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
                    self.detections = self.model.predict(source=self.path, conf=0.10, stream=True)
                    
                    for result in self.detections:
                        for i in range(len(result.boxes)):
                            class_id = int(result.boxes.cls[i])
                            class_name = result.names[class_id]
                            probability = float(result.boxes.conf[i]) * 100
                            
                            print(f"[{self.timestamp}] [ModelRecog] detected: {class_name} with probability: {probability:.2f}%")
                        annotated_img = result.plot() 
                        cv2.imshow('result', annotated_img)
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
