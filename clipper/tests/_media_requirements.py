"""Availability gates check native code, never a geometry test's placeholder."""
try:
    import cv2
    OPENCV_AVAILABLE=bool(getattr(cv2,'__file__',None) and getattr(cv2,'getBuildInformation',None))
except ImportError:
    OPENCV_AVAILABLE=False
OPENCV_REASON='Actual OpenCV is unavailable on this QA host; native decoding/CV must run on the target environment.'


def words(text,step=.4):
    return [{'word_id':i,'word':s,'start':i*step,'end':i*step+step*.85,'probability':.94} for i,s in enumerate(text.split())]
