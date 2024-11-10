from PyQt5.QtCore import QTimer, QObject, QCoreApplication
import time
import sys
import os
from loguru import logger
class TRRequestLimiter(QObject):
    def __init__(self, max_requests_per_second=5, max_requests_per_minute=55):
        super().__init__()
        if os.path.isfile('logfile.log'):
           os.remove('logfile.log')
        logger.add("logfile.log", rotation="1 day", retention="7 days", compression="zip")
        
        self.max_requests_per_second = max_requests_per_second  # 1초에 최대 요청 횟수
        self.max_requests_per_minute = max_requests_per_minute  # 1분에 최대 요청 횟수
        self.request_counter_second = 0  # 현재 1초 동안 진행된 요청 횟수
        self.request_counter_minute = 0  # 현재 1분 동안 진행된 요청 횟수
        self.last_request_time = time.time()  # 마지막 요청 시간
        self.last_minute_reset_time = time.time()  # 마지막 1분 리셋 시간
        self.waiting_requests = []  # 대기 중인 요청을 위한 리스트

        # QTimer 설정 (1초마다 대기 큐 처리)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.handle_waiting_requests)  # 1초마다 대기 큐 처리
        self.timer.start(1000)  # 1초 간격으로 실행

    def can_request(self):
        """
        현재 시간에 요청을 처리할 수 있는지 확인
        """
        current_time = time.time()

        # 1초마다 요청 횟수 초기화
        if current_time - self.last_request_time >= 1:
            self.request_counter_second = 0
            self.last_request_time = current_time

        # 1분마다 요청 횟수 초기화
        if current_time - self.last_minute_reset_time >= 60:
            self.request_counter_minute = 0
            self.last_minute_reset_time = current_time

        # 1초에 요청 제한 확인
        if self.request_counter_second >= self.max_requests_per_second:
            return False

        # 1분에 요청 제한 확인
        if self.request_counter_minute >= self.max_requests_per_minute:
            return False

        return True

    def process_request(self, stock, action):
        """
        요청을 처리하는 함수
        """
        current_time = time.time()
        self.request_counter_second += 1  # 요청 카운트를 증가 (1초 기준)
        self.request_counter_minute += 1  # 요청 카운트를 증가 (1분 기준)
        logger.info(f"요청 성공: {stock} {action} (시간: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))})")

    def handle_waiting_requests(self):
        """
        대기 중인 요청들을 처리하는 함수
        """
        current_time = time.time()

        # 대기 큐에서 요청을 뒤에서부터 처리 (리스트를 수정하면서 인덱스 오류를 방지)
        for i in range(len(self.waiting_requests) - 1, -1, -1):
            stock, action, wait_time = self.waiting_requests[i]
            # 대기 시간 체크 후 처리 가능한 요청 처리
            if current_time - wait_time >= 1:  # 1초가 지나면 처리할 수 있음
                if self.can_request():
                    self.process_request(stock, action)  # 요청 처리
                    self.waiting_requests.pop(i)  # 요청 큐에서 제거
                else:
                    # 요청이 아직 제한을 초과했다면 다시 큐에 넣기
                    self.waiting_requests[i] = (stock, action, wait_time)

    def make_request(self, stock, action):
        """
        요청을 대기시키고 제한이 풀리면 요청을 실행하는 함수
        """
        current_time = time.time()  # 현재 시간
        
        if self.can_request():
            self.process_request(stock, action)  # 즉시 요청을 처리
        else:
            # 제한 초과 시 대기 큐에 요청을 추가하고 처리 대기
            self.waiting_requests.append((stock, action, current_time))
            logger.info(f"요청 제한 초과: {stock} {action}. 대기 중... (시간: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))})")

# 테스트 코드
if __name__ == "__main__":
    app = QCoreApplication(sys.argv)  # QCoreApplication 객체 생성 (이벤트 루프 시작)
    
    tr_limiter = TRRequestLimiter(max_requests_per_second=5, max_requests_per_minute=55)

    # A, B, C 주식에 대해 매수/매도 요청을 보냄
    logger.info("----- 매수 매도 요청 시작 -----")
    tr_limiter.make_request("A", "buy")
    tr_limiter.make_request("B", "buy")
    tr_limiter.make_request("C", "buy")
    tr_limiter.make_request("A", "sell")
    tr_limiter.make_request("B", "sell")
 
    # 요청 제한 초과
    tr_limiter.make_request("C", "sell")

    # 대기 큐는 QTimer에 의해 자동으로 처리됩니다.
    logger.info("대기 큐는 자동으로 처리됩니다. 프로그램 종료까지 대기 중...")

    sys.exit(app.exec_())  # 이벤트 루프 실행
