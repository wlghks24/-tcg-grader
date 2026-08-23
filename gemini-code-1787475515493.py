# auto_repair_engine.py 내 카드 센터링/크롭 보정 알고리즘
import cv2
import numpy as np

def auto_center_and_crop(image_bytes):
    # 바이너리 이미지 변환 및 에지 감지
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 75, 200)

    # 윤곽선 감지 및 가장 큰 카드 윤곽선 탐색
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        
        # 꼭짓점이 4개인 코너 감지 시 영역 평탄화 및 센터링 진행
        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            rect = order_points(pts) # 4개 점 정렬
            
            # 규격화된 카드 크기로 센터링 워핑(Warping)
            width, height = 630, 880
            dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img, M, (width, height))
            
            _, encoded_img = cv2.imencode('.jpg', warped)
            return encoded_img.tobytes()
            
    return image_bytes