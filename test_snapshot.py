import sys
sys.path.insert(0, r"C:\Users\PC\Downloads\Claude AI Workbench\kinect")
import KinectBridge
print("Test snapshot...")
result = KinectBridge.snapshot()
print(f"Resultat: {result}")
