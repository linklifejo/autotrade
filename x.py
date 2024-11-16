import sys
import time

from collections import deque
from threading import Timer
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import *
from PyQt5.QtTest import *

class KiwoomTrader:
    def __init__(self):
        # Kiwoom Open API 연결
        self.api = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.account = "1234567890"  # 계좌번호
        self.max_stocks = 5  # 최대 보유 종목 수
        self.recommended_stocks = []  # 추천 종목 리스트
        self.portfolio = {}  # 보유 종목 정보
        self.tr_times = deque()  # 요청 시간을 저장하는 큐
        self.tr_limit_1s = 5     # 1초당 5회 제한
        self.tr_limit_1m = 55    # 1분당 55회 제한
        self.tr_limit_1h = 950   # 1시간당 950회 제한
        self.tr_ready = True     # TR 요청 가능 여부

        # 로그인
        self.api.CommConnect()
        while self.api.GetConnectState() == 0:
            self.log("로그인 성공")

    def log(self, message):
        print(message)

    def enable_tr(self):
        """
        TR 요청을 가능하도록 활성화
        """
        self.tr_ready = True

    def wait_for_tr(self):
        """
        TR 요청 제한을 만족할 때까지 대기
        """
        current_time = time.time()
        self.tr_times.append(current_time)

        # 오래된 요청 제거
        while self.tr_times and current_time - self.tr_times[0] >= 3600:
            self.tr_times.popleft()

        # 제한 조건 확인
        if (
            len(self.tr_times) > self.tr_limit_1s and current_time - self.tr_times[-self.tr_limit_1s] < 1
        ) or (
            len(self.tr_times) > self.tr_limit_1m and current_time - self.tr_times[-self.tr_limit_1m] < 60
        ) or (
            len(self.tr_times) > self.tr_limit_1h and current_time - self.tr_times[-self.tr_limit_1h] < 3600
        ):
            self.log("TR 요청 대기 중...")

            # TR 요청 비활성화 및 타이머 설정
            self.tr_ready = False
            Timer(0.1, self.enable_tr).start()

    def send_order(self, stock_code, order_type, quantity, price):
        """
        매수/매도 주문 실행
        """
        while not self.tr_ready:
            pythoncom.PumpWaitingMessages()  # 메시지 루프 처리

        self.wait_for_tr()
        order_name = "매수주문" if order_type == 1 else "매도주문"
        result = self.api.SendOrder(
            order_name,
            "0101",  # 화면번호
            self.account,
            order_type,
            stock_code,
            quantity,
            price,
            "00",  # 지정가
            ""
        )
        if result == 0:
            self.log(f"[{order_name}] 성공: 종목 {stock_code}, 수량 {quantity}, 가격 {price}")
        else:
            self.log(f"[{order_name}] 실패: {result}")

    def query_balance(self):
        """
        잔고 조회 요청
        """
        self.log("잔고 조회 요청 중...")
        while not self.tr_ready:
            pythoncom.PumpWaitingMessages()  # 메시지 루프 처리

        self.wait_for_tr()
        self.api.SetInputValue("계좌번호", self.account)
        self.api.SetInputValue("비밀번호", "0000")
        self.api.SetInputValue("비밀번호입력매체구분", "00")
        self.api.SetInputValue("조회구분", "2")
        self.api.CommRqData("잔고조회", "opw00004", 0, "0101")

    def handle_recommendations(self):
        """
        추천 종목 매수 처리
        """
        if len(self.portfolio) < self.max_stocks:
            for stock_code in self.recommended_stocks:
                if stock_code not in self.portfolio:
                    self.log(f"종목 {stock_code} 매수 진행")
                    self.send_order(stock_code, 1, 10, 50000)  # 예: 10주, 50,000원
                    if len(self.portfolio) >= self.max_stocks:
                        break

    def check_sell_conditions(self):
        """
        매도 조건 확인 및 실행
        """
        for stock_code, data in list(self.portfolio.items()):
            current_price = self.get_current_price(stock_code)
            buy_price = data['buy_price']
            high_price = data['high_price']

            # 손절 조건: 현재가가 매수가 대비 1.5% 하락
            if current_price <= buy_price * 0.985:
                self.log(f"[손절] 종목 {stock_code} 매도 진행 (현재가: {current_price}, 매수가: {buy_price})")
                self.send_order(stock_code, 2, data['quantity'], current_price)
                del self.portfolio[stock_code]

            # 고가 대비 1.5% 하락 조건
            elif current_price <= high_price * 0.985:
                self.log(f"[고가 대비 하락] 종목 {stock_code} 매도 진행 (현재가: {current_price}, 고가: {high_price})")
                self.send_order(stock_code, 2, data['quantity'], current_price)
                del self.portfolio[stock_code]

    def get_current_price(self, stock_code):
        """
        종목의 현재가 조회 (예시용)
        """
        return 50000

    def start_trading(self):
        """
        메인 루프: 자동 매매 실행
        """
        self.log("자동 매매 시작")
        while True:
            try:
                self.query_balance()
                self.check_sell_conditions()
                self.handle_recommendations()
                pythoncom.PumpWaitingMessages()  # 메시지 루프 처리
            except KeyboardInterrupt:
                self.log("자동 매매 종료")
                break


if __name__ == "__main__":
    trader = KiwoomTrader()
    trader.start_trading()
