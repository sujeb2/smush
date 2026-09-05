import os, sys
os.environ['TF_USE_LEGACY_KERAS'] = '1'

from datetime import datetime
import threading
import traceback
import cv2, numpy, torch, ultralytics
from imageai.Detection import ObjectDetection, VideoObjectDetection
from ultralytics import YOLO
from ultralytics.nn import modules as utl_modules
from ultralytics.nn.tasks import DetectionModel
import configparser as cfg

def findCompiledDir():
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))

base = findCompiledDir()
config = cfg.ConfigParser()
config.read(os.path.join(base, 'files', 'model_conf.ini'), encoding='utf-8')
numpy.set_printoptions(suppress=False)
imageai_supported = ["yolov3.pt","tiny-yolov3.pt"]
weights=[
    DetectionModel,
    torch.nn.modules.container.Sequential,
    utl_modules.Conv,
    utl_modules.conv.Concat,
    utl_modules.conv.DWConv,
    utl_modules.head.Detect,
    torch.nn.modules.Conv2d,
    torch.nn.modules.batchnorm.BatchNorm2d,
    torch.nn.modules.activation.SiLU,
    utl_modules.block.C3k2,
    utl_modules.block.C3k,
    utl_modules.block.Bottleneck,
    utl_modules.block.SPPF,
    utl_modules.block.C2PSA,
    utl_modules.block.PSABlock,
    utl_modules.block.Attention,
    torch.nn.modules.upsampling.Upsample,
    torch.nn.modules.linear.Identity,
    torch.nn.modules.pooling.MaxPool2d,
    torch.nn.modules.ModuleList
]

class Model:
    def __init__(self, model_path, serial):
        try:
            self.timestamp = datetime.now().strftime('%H:%M:%S')
            print(f'[{self.timestamp}] [ModelRecog] Init model..')
            self.vc = cv2.VideoCapture(0)
            self.model_path = model_path
            self.serial_ignore = True
            # Allow the YOLO checkpoint's model classes with PyTorch 2.6+ weights-only loading.
            torch.serialization.add_safe_globals(weights)
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
        show_preview = config['GENERIC'].getboolean('ShowCaptureVid', fallback=True)
        if show_preview and threading.current_thread() is not threading.main_thread():
            print(f"[{self.timestamp}] [ModelRecog] camera preview disabled in recognition worker.")
            show_preview = False
        self.camera = self.vc
        try:
            if not self.camera.isOpened():
                self.camera = cv2.VideoCapture(0)
            target_fps = config['GENERIC'].getint('CameraFPS', fallback=480)
            if target_fps > 0:
                self.camera.set(cv2.CAP_PROP_FPS, target_fps)
            wait_time_ms = max(1, int(1000 / target_fps)) if target_fps > 0 else 1
            try:
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
                if torch.mps.is_available(): device="mps:0"
                self.model = YOLO(
                    self.model_path,
                    task='detect',
                    verbose=config['GENERIC'].getboolean('Verbose'),
                ).to(device=device)
            except Exception:
                if os.path.basename(self.model_path) not in imageai_supported:
                    raise
                print(f"[{self.timestamp}] [ModelRecog] fallback model load failed. trying default library.")
                traceback.print_exc()
                return self.fallbackLiveFeed(show_preview)

            while not self.captured:
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    print(f"[{self.timestamp}] [ModelRecog] failed to grab frame from camera.")
                    return 1
                self.detections = self.model.predict(source=frame, conf=0.5, stream=True)

                for result in self.detections:
                    if show_preview:
                        try:
                            cv2.imshow('feed', result.plot())
                        except cv2.error:
                            print(f"[{self.timestamp}] [ModelRecog] failed to grab camera.")
                            traceback.print_exc()
                            self._close_live_preview()
                            show_preview = False
                    if config['DETECTION'].getboolean('HasExpectedObject'):
                        self.confident = result.boxes.conf
                        self.names = [result.names[cls.item()] for cls in result.boxes.cls.int()]
                        print(f'[{self.timestamp}] [ModelRecog] confident: {self.confident}, names: {self.names}')
                        for index in (1, 2):
                            expected = config['DETECTION'].get(f'ExpectedObject_{index}')
                            if expected and expected in self.names:
                                if not self.serial_ignore:
                                    self.serial.write(f"obj{index}_detect[{expected}]\n")
                                    while self.serial.read():
                                        pass
                if show_preview:
                    try:
                        key = cv2.waitKey(wait_time_ms) & 0xFF
                    except cv2.error:
                        print(f"[{self.timestamp}] [ModelRecog] camera preview failed")
                        traceback.print_exc()
                        self._close_live_preview()
                        show_preview = False
                    else:
                        if key == ord('q'):
                            self.cancel_capture()
                            return None
        except Exception:
            print(f'[{self.timestamp}] [ModelRecog] recog failed:')
            traceback.print_exc()
            raise
        finally:
            self.camera.release()
            if show_preview:
                self._close_live_preview()

    def _close_live_preview(self):
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            traceback.print_exc()

    def fallbackLiveFeed(self, show_preview):
        self.execution_path = base
        self.detector = VideoObjectDetection()
        if os.path.basename(self.model_path) == 'tiny-yolov3.pt':
            self.detector.setModelTypeAsTinyYOLOv3()
        else:
            self.detector.setModelTypeAsYOLOv3()
        self.detector.setModelPath(self.model_path)
        self.detector.loadModel()

        def livefeed(returned_frame):
            nonlocal show_preview
            if not show_preview:
                return
            try:
                cv2.imshow('feed', returned_frame)
                key = cv2.waitKey(1) & 0xFF
            except cv2.error:
                traceback.print_exc()
                self._close_live_preview()
                show_preview = False
                return
            if key == ord('q'):
                self.camera.release()
                self.cancel_capture()

        video_path = self.detector.detectObjectsFromVideo(
            camera_input=self.camera,
            output_file_path=os.path.join(self.execution_path, "files", "captures", f"{self.timestamp}_camera_detected_video"),
            frames_per_second=20,
            log_progress=True,
            minimum_percentage_probability=30,
            per_frame_function=livefeed,
            return_detected_frame=True,
        )
        print(f'[{self.timestamp}] [ModelRecog] {video_path}')

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
