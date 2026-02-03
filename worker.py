from PyQt6.QtCore import QThread, pyqtSignal
from api_client import APIClient

class AnalysisWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, image=None, prompt="Analyze this code and provide a solution."):
        super().__init__()
        self.image = image
        self.prompt = prompt
        self.api_client = None

    def run(self):
        try:
            if not self.api_client:
                # Initialize here to capture env vars updated in main thread if any
                # But typically it's better to verify earlier.
                self.api_client = APIClient()
            
            # If image is provided, use image analysis; otherwise use text-only prompt
            if self.image:
                result = self.api_client.analyze_image(self.image, self.prompt)
            else:
                result = self.api_client.send_text_prompt(self.prompt)
            
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
