import sys
import os
import datetime
import time
import pandas as pd
from threading import Timer
from loguru import logger

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import *
from PyQt5.QtTest import *
from collections import deque
from queue import Queue

class KiwoomAPI(QMainWindow):
    def __init__(self):
        super().__init__()

        if os.path.isfile('logfile.log'):
            os.remove('logfile.log')
        logger.add("logfile.log", rotation="1 day", retention="7 days", compression="zip")

        self.portfolio = {}
        self.max_stocks = 5  # 최대 보유 종목 수
        self.recommended_stocks = {}  # 추천 종목 리스트
        self.tr_times = deque()  # 요청 시간을 저장하는 큐
        self.tr_limit_1s = 5     # 1초당 5회 제한
        self.tr_limit_1m = 55    # 1분당 55회 제한
        self.tr_limit_1h = 950   # 1시간당 950회 제한
        self.tr_ready = True     # TR 요청 가능 여부
        self.event_loop = QEventLoop()
        self.order_screen = {}
        self.tr_req_scrnum = 0
        self.balance = 0
        self.total_buy_money = 0
        self.buy_money = 0
        self.now_time = datetime.datetime.now()
        self.stop_loss_threshold = -1.5
        self.realtime_data_scrnum = 5000
        self.tr_reg_scrnum = 5150
        self.using_condition_name = "급등종목"
        self.unfinished_order_num_to_info_dict = {}
        self.account_num = None
        self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.unfinished_orders = QTimer()
        self.unfinished_orders.timeout.connect(self.check_unfinished_orders)
        self._set_signal_slots() # 키움증권 API와 내부 메소드를 연동
        self._login()
        self.t_9, self.t_start,self.t_sell, self.t_exit, self.t_ai = self.gen_time()

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
            logger.info("TR 요청 대기 중...")

            # TR 요청 비활성화 및 타이머 설정
            self.tr_ready = False
            Timer(0.1, self.enable_tr).start()    
    def exit_all_sell(self):
        """
        3:15 all_sell
        """
        self.now_time = datetime.datetime.now()
        self.t_9, self.t_start,self.t_sell, self.t_exit, self.t_ai = self.gen_time()
        if self.t_sell < self.now_time < self.t_exit:  # PM 03:15 ~ PM 03:20 : 일괄 매도
            for stock_code, data in list(self.portfolio.items()):
                self.send_orders(stock_code, 2, data['보유수량'])
                del self.portfolio[stock_code]  
        if self.t_exit < self.now_time:  # PM 03:20 ~ :프로그램 종료
            logger.info(f"오늘 장 마감~~ 프로그램을 종료 합니다.")
            sys.exit()              
    def handle_recommendations(self):
        """
        추천 종목 매수 처리
        """
        QTest.qWait(2000)
        remaining_slots = self.max_stocks - len(self.portfolio)  # 남은 매수 가능한 종목 수
        if remaining_slots > 0:
            for stock_code in self.recommended_stocks.keys():
                if stock_code not in self.portfolio.keys():
                    self.send_orders(stock_code, 1, 10)  # 예: 10주, 50,000원
                    logger.info(f"종목 {stock_code} 매수 진행")
                    # 남은 슬롯 수 감소
                    remaining_slots -= 1

                    # 남은 슬롯이 0이면 루프 종료
                    if remaining_slots <= 0:
                        break

    def check_sell_conditions(self):
        """
        매도 조건 확인 및 실행
        """
        for stock_code, data in list(self.portfolio.items()):
            현재가 = self.get_current_price(stock_code)
            매입가 = data['매입가']
            고가 = data.get('고가',현재가)

            # 손절 조건: 현재가가 매수가 대비 1.5% 하락
            if 현재가 <= 매입가 * 0.985:
                logger.info(f"[손절] 종목 {stock_code} 매도 진행 (현재가: {현재가}, 매입가: {매입가})")
                self.send_orders(stock_code, 2, data['보유수량'])
                del self.portfolio[stock_code]

            # 고가 대비 1.5% 하락 조건
            elif 현재가 <= 고가 * 0.985:
                logger.info(f"[고가 대비 하락] 종목 {stock_code} 매도 진행 (현재가: {현재가}, 고가: {고가})")
                self.send_orders(stock_code, 2, data['보유수량'])
                del self.portfolio[stock_code]        
    def start_trading(self):
        """
        메인 루프: 자동 매매 실행
        """
        logger.info("자동 매매 시작")
        while True:
            try:
                self.request_opw00018()
                self.check_sell_conditions()
                self.handle_recommendations()
                self.check_unfinished_orders() 
                self.exit_all_sell()
            except KeyboardInterrupt:
                logger.info("자동 매매 종료")
                sys.exit()
                

    def gen_time(self):
        t_now = datetime.datetime.now()
        t_9 = t_now.replace(hour=9, minute=0, second=0, microsecond=0)
        t_start = t_now.replace(hour=9, minute=1, second=0, microsecond=0)
        t_ai = t_now.replace(hour=9, minute=30, second=0,microsecond=0)
        t_sell = t_now.replace(hour=15, minute=15, second=0, microsecond=0)
        t_exit = t_now.replace(hour=15, minute=20, second=0,microsecond=0)
        return t_9,t_start,t_sell,t_exit,t_ai

    def get_current_price(self,code):
        data = int(self.kiwoom.GetMasterLastPrice(code).strip().replace('-',''))  # 현재가 가져오기
        return data
    def get_company_name(self,code):
        company_name = self.kiwoom.GetMasterCodeName(code).strip()  # 업체명 가져오기
        return company_name
    def _login(self):
        ret = self.kiwoom.dynamicCall("CommConnect()")
        if ret == 0:
            logger.info("로그인 창 열기 성공!")
        self.event_loop.exec_()

    def _event_connect(self, err_code):
        if err_code == 0:
            logger.info("로그인 성공!")                
            self._after_login()
        else:
            raise Exception("로그인 실패!")
        self.event_loop.exit()
        
        
    def get_account_num(self):
        account_nums = str(self.kiwoom.dynamicCall("GetLoginInfo(QString)", ["ACCNO"]).rstrip(';'))
        logger.info(f"계좌번호 리스트: {account_nums}")
        self.account_num = account_nums.split(';')[0]
        logger.info(f"사용 계좌 번호: {self.account_num}")     
        

    def _after_login(self):
        self.get_account_num()
        self.kiwoom.dynamicCall("GetConditionLoad()") # 조건 검색 정보 요청 
        self.start_trading()    

    def get_account_info(self):
        self.tr_req_queue.put([self.request_opw00018]) 

    def get_tmp_high_volatility_info(self):
        self.tr_req_queue.put([self.request_opt10019, "001", True]) 

    def request_opt10019(self, target_market="000", is_upside=True):
        self.wait_for_tr()
        self._set_input_value("시장구분", target_market)
        self._set_input_value("등락구분", "1" if is_upside else "2") # 급등기준
        self._set_input_value("시간구분", "1") # 1분전
        self._set_input_value("시간", "분") # 분
        self._set_input_value("거래량구분", "00100") # 10만주이상
        self._set_input_value("종목조건", "0") # 전체조건
        self._set_input_value("신용조건", "0") # 전체조건
        self._set_input_value("가격조건", "0") # 전체조건
        self._set_input_value("상하한포함", "0") # 미포함
        self._comm_rq_data("opt10019_req", "opt10019", 0, self._get_tr_req_screen_num())

    def request_opw00018(self):
        self.wait_for_tr()
        self._set_input_value("계좌번호", self.account_num)
        self._set_input_value("비밀번호", "")
        self._set_input_value("비밀번호입력대체구분", "00")
        self._set_input_value("조회구분", "2")
        self._comm_rq_data("opw00018_req", "opw00018", 0, self._get_tr_req_screen_num())
        self.event_loop.exec_()


    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, unused1, unused2, unused3, unused4):
        if rqname == "opw00018_req":
            self._on_opw00018_req(rqname, trcode)     
        elif rqname == "opt10019_req":
            self._on_opt10019_req(rqname, trcode)
        self.event_loop.exit() 

    def _on_opw00018_req(self, rqname, trcode):
        try:
            self.balance = int(self._comm_get_data(trcode, "", rqname, 0, "추정예탁자산").replace('-',''))
        except ValueError:
            print("Failed to convert balance data to integer.")
            self.balance = 0  # Assign a default value or handle it as needed
        except Exception as e:
            print(f"An error occurred: {e}")
            self.balance = 0  # Optional: handle with a default value or other logic

        try:
            self.total_buy_money = int(self._comm_get_data(trcode, "", rqname, 0, "총매입금액"))
        except ValueError:
            print("Failed to convert balance data to integer.")
            self.total_buy_money = 0  # Assign a default value or handle it as needed
        except Exception as e:
            print(f"An error occurred: {e}")
            self.total_buy_money = 0  # Optional: handle with a default value or other logic

        self.buy_money = self.balance * 0.5
        self.buy_money = int(self.buy_money / 4)
        self.buy_cnt = int(self._get_repeat_cnt(trcode, rqname))
        self.cal_cnt = self.max_stocks - self.buy_cnt
        logger.info(f"현재평가잔고: {self.balance:,}원")
        logger.info(f"총매입급액: {self.total_buy_money:,}원")
        logger.info(f"보유종목수: {self.buy_cnt:,}개")
        logger.info(f"설정된(max) 가능 거래 종목 수: {self.max_stocks:,}개")
        logger.info(f"현재가능 거래 종목 수: {self.cal_cnt:,}개")

        for i in range(self.buy_cnt):
            종목코드 = self._comm_get_data(trcode, "", rqname, i, "종목번호").replace("A","").strip()
            try:
                보유수량 = int(self._comm_get_data(trcode, "", rqname, i, "보유수량"))
            except ValueError:
                print("Failed to convert balance data to integer.")
                보유수량 = 0  # Assign a default value or handle it as needed
            except Exception as e:
                print(f"An error occurred: {e}")
                보유수량 = 0  # Optional: handle with a default value or other logic            
            try:
                매입가 = int(self._comm_get_data(trcode, "", rqname, i, "매입가"))
            except ValueError:
                print("Failed to convert balance data to integer.")
                매입가 = 0  # Assign a default value or handle it as needed
            except Exception as e:
                print(f"An error occurred: {e}")
                매입가 = 0  # Optional: handle with a default value or other logic
                
            if 종목코드 not in self.recommended_stocks:
                self.register_code_to_realtime_list(종목코드)

            if 종목코드  not in self.portfolio.keys():
                self.portfolio.update({종목코드:{}})
            
            self.portfolio[종목코드].update({"보유수량": 보유수량})
 
            self.portfolio[종목코드].update({"매입가": 매입가})

        for stock in self.portfolio.keys():
            logger.info(f'{self.portfolio[stock]}')    
        
            
    def _on_opt10019_req(self, rqname, trcode):
        data_cnt = self._get_repeat_cnt(trcode, rqname)
        for i in range(data_cnt):
            종목코드 = self._comm_get_data(trcode, "", rqname, i, "종목코드")
            종목분류 = self._comm_get_data(trcode, "", rqname, i, "종목분류")
            종목명 = self._comm_get_data(trcode, "", rqname, i, "종목명")
            전일대비기호 = self._comm_get_data(trcode, "", rqname, i, "전일대비기호")
            전일대비 = self._comm_get_data(trcode, "", rqname, i, "전일대비")
            등락률 = self._comm_get_data(trcode, "", rqname, i, "등락률")
            기준가 = self._comm_get_data(trcode, "", rqname, i, "기준가")
            현재가 = self._comm_get_data(trcode, "", rqname, i, "현재가")
            기준대비 = self._comm_get_data(trcode, "", rqname, i, "기준대비")
            거래량 = self._comm_get_data(trcode, "", rqname, i, "거래량")
            급등률 = self._comm_get_data(trcode, "", rqname, i, "급등률")
            logger.info(f"종목코드: {종목코드}, 종목분류: {종목분류}, 종목명: {종목명}")

    def check_unfinished_orders(self):
                  
        pop_list = []   
        for order_num in self.unfinished_order_num_to_info_dict.keys():
            주문번호 = order_num
            종목코드 = self.unfinished_order_num_to_info_dict[주문번호]["종목코드"]    
            주문체결시간 = self.unfinished_order_num_to_info_dict[주문번호]["주문체결시간"]    
            미체결수량 = self.unfinished_order_num_to_info_dict[주문번호]["미체결수량"]    
            주문구분 = self.unfinished_order_num_to_info_dict[주문번호]["주문구분"]    
            화면번호 = self.unfinished_order_num_to_info_dict[주문번호]["화면번호"]    
            order_time = datetime.datetime.now().replace(
                hour = int(주문체결시간[:-4]),
                minute = int(주문체결시간[-4:-2]),
                second = int(주문체결시간[-2:])
            )
            if 주문구분 == "매수" and datetime.datetime.now() - order_time >= datetime.timedelta(seconds=10):
                logger.info(f"=== 미체결 === 종목코드: {종목코드}, 주문번호: {주문번호}, 미체결수량: {미체결수량}, 매수 취소 주문:")
                self.tr_req_queue.put(
                        [
                            self.send_order, 
                            "매수취소주문", # 사용자 구분명
                            화면번호, # 화면번호
                            self.account_num, # 계좌번호
                            3, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                            종목코드, # 종목코드
                            미체결수량, # 주문 수량
                            "", # 주문 가격, 시장가의 경우 공백
                            "00", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                            주문번호, # 주문번호 (정정 주문의 경우 사용, 나머진 공백)

                        ]
                        ) 
                pop_list.append(주문번호)

            # elif 주문구분 == "매도" and datetime.datetime.now() - order_time >= datetime.timedelta(seconds=10):
            #     logger.info(f"종목코드: {종목코드}, 주문번호: {주문번호}, 미체결수량: {미체결수량}, 매도 취소 주문!")
            #     self.tr_req_queue.put(
            #             [
            #                 self.send_order, 
            #                 "매도취소주문", # 사용자 구분명
            #                 "5000", # 화면번호
            #                 self.account_num, # 계좌번호
            #                 4, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
            #                 종목코드, # 종목코드
            #                 미체결수량, # 주문 수량
            #                 "", # 주문 가격, 시장가의 경우 공백
            #                 "00", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
            #                 주문번호, # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
            #             ]
            #             ) 

                # pop_list.append(주문번호)
        for order_num in pop_list:
            self.unfinished_order_num_to_info_dict.pop(order_num, None)
        
    def _set_signal_slots(self):
        self.kiwoom.OnEventConnect.connect(self._event_connect)

        self.kiwoom.OnReceiveRealData.connect(self._receive_realdata)
        self.kiwoom.OnReceiveTrData.connect(self._receive_tr_data)
        self.kiwoom.OnReceiveChejanData.connect(self.receive_chejandata)
        self.kiwoom.OnReceiveMsg.connect(self.receive_msg)

        self.kiwoom.OnReceiveConditionVer.connect(self._receive_condition)
        self.kiwoom.OnReceiveRealCondition.connect(self._receive_real_condition)
        self.kiwoom.OnReceiveTrCondition.connect(self._receive_tr_condition)

    def send_order(self, sRQName, sScreenNo, sAccNo, nOrderType, sCode, nQty, nPrice, sHogaGb, sOrgOrderNo):
        logger.info("Sending order")
        return self.kiwoom.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                                       [sRQName, sScreenNo, sAccNo, nOrderType, sCode, nQty, nPrice, sHogaGb, sOrgOrderNo])
        
    
    def _get_repeat_cnt(self, trcode, rqname):
        ret = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)   
        return ret
    
    def _set_input_value(self, id, value):
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", id, value)

    def _comm_rq_data(self, rqname, trcode, next, screen_no):
        self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", rqname,trcode,next,screen_no)

    def _comm_get_data(self, code, real_type, field_name, index, item_name):
        ret = self.kiwoom.dynamicCall(
            "CommGetData(QString, QString, QString, int, QString)", code, real_type, field_name, index, item_name
        )
        return ret.strip()
    def send_orders(self, stock_code, order_type, quantity):
        """
        매수/매도 주문 실행
        """
        current_price = self.get_current_price(stock_code)
        order_name = "시장가 매수주문" if order_type == 1 else "시장가 매도주문"
        while not self.tr_ready:
            logger.info(f'{order_name} 대기.....!')

        self.wait_for_tr()
        화면번호 = self._get_realtime_data_screen_num() if order_type == 1 else self.portfolio[stock_code].get('화면번호','5000')
        화면번호 = self._get_realtime_data_screen_num()
        if order_type == 2:
            pass
        elif order_type == 1:
            if current_price < 1000 or current_price > 20000:
                return
        result = self.send_order( 
                    "시장가매수주문", # 사용자 구분명
                    화면번호, # 화면번호
                    self.account_num, # 계좌번호
                    1, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                    stock_code, # 종목코드
                    # qty, # 주문 수량
                    quantity, # 주문 수량
                    "", # 주문 가격, 시장가의 경우 공백
                    "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                    "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
        )
        if result == 0:
            logger.info(f"[{order_name}] 성공: 종목 {stock_code}, 수량 {quantity}")
        else:
            logger.info(f"[{order_name}] 실패: {result}")  


    def _receive_real_condition(self, strCode, strType, strConditionName, strConditionIndex):
        logger.info(f"Received real condition, {strCode}, {strType}, {strConditionName}, {strConditionIndex}")
        if strType == "I":
            self.register_code_to_realtime_list(strCode)

        elif strType == "D" and strCode not in self.portfolio.keys():
            self.unregister_code_to_realtime_list(strCode)

    def _receive_tr_condition(self, scrNum, strCodeList, strConditionName, nIndex, nNext):
        logger.info(f"Received TR Condition, strCodeList: {strCodeList}, strConditionName: {strConditionName}," 
              f"nIndex: {nIndex}, nNext: {nNext}, scrNum: {scrNum}")       
        for stock_code in strCodeList.split(';'):
            if len(stock_code) == 6:
                self.register_code_to_realtime_list(stock_code) 

    def set_real(self, scrNum, strCodeList, strFidList, strRealType):
        self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)", scrNum, strCodeList, strFidList, strRealType)   

    def set_real_remove(self, scrNum, rmCode):
        self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", scrNum, rmCode)         

    def register_code_to_realtime_list(self, code):
        fid_list = "10;12;20;21;41;51;61;71"
        if len(code) != 0:
            화면번호 = self._get_realtime_data_screen_num()
            self.set_real(화면번호, code, fid_list,"1")
            logger.info(f"{code}, 실시간 등록 완료!")
            if code not in self.recommended_stocks.keys():
                self.recommended_stocks.update({code:{}})
            self.recommended_stocks[code]["화면번호"] = 화면번호

    def unregister_code_to_realtime_list(self, code):
        if len(code) != 0:
            화면번호 = self.recommended_stocks[code]["화면번호"]
            self.set_real_remove(화면번호, code)
            logger.info(f"{code}, 실시간 해지(unregister) 완료!")
            self.recommended_stocks.pop(code)            

    def _get_tr_req_screen_num(self):
        self.tr_req_scrnum += 1
        if self.tr_req_scrnum > 5288:
            self.tr_req_scrnum = 5150

        return str(self.tr_req_scrnum)
    def _get_realtime_data_screen_num(self):
        self.realtime_data_scrnum += 1
        if self.realtime_data_scrnum > 5150:
            self.realtime_data_scrnum = 5000
        return str(self.realtime_data_scrnum)    
    
    def _receive_condition(self):
        condition_info = self.kiwoom.dynamicCall("GetConditionNameList()").split(';')
        for condition_name_idx_str in condition_info:
            if len(condition_name_idx_str) == 0:
                continue
            condition_idx, condition_name = condition_name_idx_str.split('^')
            if condition_name == self.using_condition_name:
                self.send_condition(self._get_realtime_data_screen_num(), condition_name, condition_idx, 1)
    
    def send_condition(self, scrNum, condtition_name, nidx, nsearch):
        # nsearch: 조회구분, 0:조건검색, 1:실시간 조건검색
        result = self.kiwoom.dynamicCall("SendCondition(QString, QString, int, int)", scrNum, condtition_name, nidx, nsearch)
        if result == 1:
            logger.info(f"{condtition_name} 조건검색 등록")

    def _get_comn_realdata(self, strCode, nFid):
        return self.kiwoom.dynamicCall("GetCommRealData(QString, int)", strCode, nFid)   
    
    def _receive_realdata(self, sJongmokCode, sRealType, sRealData):
        if sRealType == "주식체결":
            현재가 = int(self._get_comn_realdata(sRealType, 10).replace('-', '')) # 현재가
            등락률 = float(self._get_comn_realdata(sRealType, 12))     
            체결시간 = self._get_comn_realdata(sRealType, 20)
            # logger.info(f"종목코드: {sJongmokCode}, 체결시간: {체결시간}, 현재가: {현재가}, 등락률: {등락률}")
 
            if self.portfolio[sJongmokCode]["보유수량"] == 0:
                del self.portfolio[sJongmokCode]
            # QTest.qWait(1)

        elif sRealType == "주식호가잔량":
            시간 = self._get_comn_realdata(sRealType, 21)
            매도호가1 = int(self._get_comn_realdata(sRealType, 41).strip().replace('-', ''))
            매수호가1 = int(self._get_comn_realdata(sRealType, 51).replace('-', ''))
            매도호가잔량1 = int(self._get_comn_realdata(sRealType, 61).replace('-', ''))
            매수호가잔량1 = int(self._get_comn_realdata(sRealType, 71).replace('-', ''))
            # qty = int(self.buy_money / 매수호가1)
            # # logger.info(f"qty: {qty}, buy_cnt: {self.buy_cnt}, max_buy_cnt: {self.max_buy_cnt}, stock_in_dict: {sJongmokCode in self.portfolio.keys()}")
            # if qty > 0 and 1000 <= 매수호가1 <= 20000 and sJongmokCode not in self.portfolio.keys() and sJongmokCode not in self.unfinished_order_num_to_info_dict.keys():
            #     self.tr_req_queue.put(
            #         [
            #             self.send_order, 
            #             "지정가매수주문", # 사용자 구분명
            #             self._get_realtime_data_screen_num(), # 화면번호
            #             self.account_num, # 계좌번호
            #             1, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
            #             sJongmokCode, # 종목코드
            #             # qty, # 주문 수량
            #             1, # 주문 수량
            #             매수호가1, # 주문 가격, 시장가의 경우 공백
            #             "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
            #             "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)

            #         ]
            #     )

            # print(
            #     f"종목코드: {sJongmokCode}, 시간: {시간}, 매도호가1: {매도호가1}, 매수호가1: {매수호가1}, "
            #     f"매도호가잔량1: {매도호가잔량1}, 매수호가잔량1: {매수호가잔량1}"
            # )
        
    def get_chejandata(self, nFid):
        ret = self.kiwoom.dynamicCall("GetChejanData(int)", nFid)    
        return ret
    
    def receive_chejandata(self, sGubun, nItemCnt, sFidList):
        # sGubun: 체결구분 접수와 체결시 '0'값, 국내주식 잔고전달은 '1'값, 파생잔고 전달은 '4'
        if sGubun == "0":
            종목코드 = self.get_chejandata(9001).replace("A", "").strip()    
            종목명 = self.get_chejandata(302).strip()    
            주문체결시간 = self.get_chejandata(908).strip()    
            주문수량 = 0 if len(self.get_chejandata(900)) == 0 else int(self.get_chejandata(900))
            주문가격 = 0 if len(self.get_chejandata(901)) == 0 else int(self.get_chejandata(901))
            체결수량 = 0 if len(self.get_chejandata(911)) == 0 else int(self.get_chejandata(911))
            체결가격 = 0 if len(self.get_chejandata(910)) == 0 else int(self.get_chejandata(910))
            미체결수량 = 0 if len(self.get_chejandata(902)) == 0 else int(self.get_chejandata(902))
            주문구분 = self.get_chejandata(905).replace("-", "").strip()    
            매매구분 = self.get_chejandata(906).strip()    
            단위체결가 = 0 if len(self.get_chejandata(914)) == 0 else int(self.get_chejandata(914))
            단위체결량 = 0 if len(self.get_chejandata(915)) == 0 else int(self.get_chejandata(915))
            원주문번호 = self.get_chejandata(904).strip()    
            주문번호 = self.get_chejandata(9203).strip()    
            # print(
            #     f"Received chejandata! 주문체결시간: {주문체결시간}, 종목코드: {종목코드}, "
            #     f"종목명: {종목명}, 주문수량: {주문수량}, 주문가격: {주문가격}, 체결수량: {체결수량}, 체결가격: {체결가격}, "
            #     f"단위체결량: {단위체결량}, 주문번호: {주문번호}, 원주문번호: {원주문번호}"
            # )
            if 체결수량 == 0:
                self.unfinished_order_num_to_info_dict.update({주문번호 :{}})
                self.unfinished_order_num_to_info_dict[주문번호].update({"종목코드": 종목코드}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"미체결수량": 미체결수량}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"주문체결시간": 주문체결시간}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"주문구분": 주문구분}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"화면번호": self.order_screen.get(종목코드,"5000")}) 
            else:    

                if 종목코드 not in self.portfolio.keys():
                        self.portfolio.update({종목코드:{}})
                self.portfolio[종목코드][ "보유수량"] = 체결수량
                self.portfolio[종목코드][ "매입가"] = 체결가격
            if 미체결수량 == 0:
                self.unfinished_order_num_to_info_dict.pop(주문번호,None)
            
        if sGubun == "1":
            logger.info("잔고통보")    
        # self.tr_req_queue.put([self.request_opw00018])   


    def receive_msg(self, sScrno, sRQName, sTrcode, sMsg):
        logger.info(f"Received MSG! 화면번호: {sScrno}, 사용자 구분명: {sRQName}, TR이름: {sTrcode}, 메세지: {sMsg}")  
        # self.tr_req_queue.put([self.request_opw00018])   

        

            
if __name__ == "__main__":
    app = QApplication(sys.argv)            
    kiwoom_api = KiwoomAPI()
    sys.exit(app.exec_())