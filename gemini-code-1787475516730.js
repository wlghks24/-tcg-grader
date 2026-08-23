// 자동 감지 및 촬영 제어 로직
let isProcessing = false;

function processVideoFrame(videoElement) {
    if (isProcessing) return;

    const cardDetected = detectCardBoundingBox(videoElement); // 카드 영역 감지 함수
    
    if (cardDetected.confidence > 0.85) { // 85% 이상 정밀도로 카드가 포착된 경우
        isProcessing = true;
        triggerAutoCapture(cardDetected.cropArea);
        setTimeout(() => { isProcessing = false; }, 1500); // 연속 촬영 방지 딜레이
    }
}