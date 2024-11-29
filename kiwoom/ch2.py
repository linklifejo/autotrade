import sys
import os
import datetime
import time

import pandas as pd
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

        self.event_loop = QEventLoop()
        self.GAIN_PERCENT = 1.01
        self.LOSS_PERCENT = 0.01 # 매입단가 대비 2% 하락 조건
        self.MAX_BUY_STOCK = 1 # 최대 보유 종목 수
        self.MAX_BUY_DIV = 4  # 한 종목당 최대 매수 횟수
        self.MIN_BUY_COST = 1000
        self.MAX_BUY_COST = 20000
        self.order_screen = {}
        self.order_error_log = []
        self.tr_req_scrnum = 0
        self.balance = 0
        self.total_buy_money = 0
        self.buy_money = 0
        self.buy_cnt = 0
        self.cal_cnt = 0
        self.buy_qty = 5
        self.total_qty = 0
        self.now_time = datetime.datetime.now()
        self.realtime_data_scrnum = 5000
        self.tr_reg_scrnum = 5150
        self.max_send_per_sec = 4 # 초당 TR 호출 최대 4번
        self.max_send_per_minute = 55 # 분당 TR 호출 최대 55번
        self.max_send_per_hour = 950 # 시간당 TR 호출 최대 950번
        # self.last_tr_send_times = deque(maxlen=self.max_send_per_hour)
        self.last_tr_send_times = deque(maxlen=self.max_send_per_sec)
        self.tr_req_queue = Queue()
        self.using_condition_name = "급등종목"
        self.realtime_registed_codes = {}
        self.stock_dict = {}
        self.unfinished_order_num_to_info_dict = {}
        self.account_num = None
        self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.unfinished_orders = QTimer()
        self.unfinished_orders.timeout.connect(self.check_unfinished_orders)
        self.stock_sell_timer = QTimer()
        self.stock_sell_timer.timeout.connect(self.stock_sell)
        # self.timer = QTimer(self)
        # self.timer.timeout.connect(self.restart_program)
        # self.timer.start(60000)  # 60초 (1분)        
        self._set_signal_slots() # 키움증권 API와 내부 메소드를 연동
        self._login()
        self.t_9, self.t_start,self.t_sell, self.t_exit, self.t_ai = self.gen_time()

    def gen_time(self):
        t_now = datetime.datetime.now()
        t_9 = t_now.replace(hour=9, minute=0, second=0, microsecond=0)
        t_start = t_now.replace(hour=9, minute=1, second=0, microsecond=0)
        t_ai = t_now.replace(hour=9, minute=30, second=0,microsecond=0)
        t_sell = t_now.replace(hour=15, minute=15, second=0, microsecond=0)
        t_exit = t_now.replace(hour=15, minute=20, second=0,microsecond=0)
        return t_9,t_start,t_sell,t_exit,t_ai

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

    def _after_login(self):
        self.get_account_num()
        self.request_opw00018() 
        self.kiwoom.dynamicCall("GetConditionLoad()") 
        # self.stock_sell_timer.start(200) # 0.2초마다 sell   
        self.unfinished_orders.start(500) # 0.5초마다 order_buied cancel   
        # self.req_upside_info_timer.start(3000)   
        #      
        
    def get_account_num(self):
        account_nums = str(self.kiwoom.dynamicCall("GetLoginInfo(QString)", ["ACCNO"]).rstrip(';'))
        logger.info(f"계좌번호 리스트: {account_nums}")
        self.account_num = account_nums.split(';')[0]
        logger.info(f"사용 계좌 번호: {self.account_num}")     
        


    def get_account_info(self):
        self.tr_req_queue.put([self.request_opw00018]) 

    def get_tmp_high_volatility_info(self):
        self.tr_req_queue.put([self.request_opt10019, "001", True]) 

    def request_opt10019(self, target_market="000", is_upside=True):
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
        self._set_input_value("계좌번호", self.account_num)
        self._set_input_value("비밀번호", "")
        self._set_input_value("비밀번호입력대체구분", "00")
        self._set_input_value("조회구분", "2")
        self._comm_rq_data("opw00018_req", "opw00018", 0, self._get_tr_req_screen_num())
        # self.event_loop.exec_()


    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, unused1, unused2, unused3, unused4):
        if rqname == "opw00018_req":
            self._on_opw00018_req(rqname, trcode)     
        elif rqname == "opt10019_req":
            self._on_opt10019_req(rqname, trcode)
        self.event_loop.exit() 

    def _on_opw00018_req(self, rqname, trcode):
        self.stock_dict.clear()
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
        self.buy_money = int(self.buy_money / self.MAX_BUY_STOCK)
        self.buy_cnt = int(self._get_repeat_cnt(trcode, rqname))
        self.cal_cnt = self.MAX_BUY_STOCK - self.buy_cnt
        logger.info(f"현재평가잔고: {self.balance:,}원")
        logger.info(f"총매입급액: {self.total_buy_money:,}원")
        logger.info(f"보유종목수: {self.buy_cnt:,}개")
        logger.info(f"설정된(max) 가능 거래 종목 수: {self.MAX_BUY_STOCK:,}개")
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
                
            if 종목코드 not in self.realtime_registed_codes:
                self.register_code_to_realtime_list(종목코드)

            if 종목코드  not in self.stock_dict.keys():
                self.stock_dict.update({종목코드:{}})
            
            self.stock_dict[종목코드].update({"보유수량": 보유수량})
 
            self.stock_dict[종목코드].update({"매입가": 매입가})

        for stock in self.stock_dict.keys():
            logger.info(f'{self.stock_dict[stock]}')    
        
            
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

   

    def _is_check_tr_req_condition(self):
        self.now_time = datetime.datetime.now()            
        if len(self.last_tr_send_times) >= self.max_send_per_sec and \
            self.now_time - self.last_tr_send_times[-self.max_send_per_sec] < datetime.timedelta(milliseconds=1000):
            logger.info(f"초 단위 TR 요청 제한! Wait for time to send!")
            return False
        # elif len(self.last_tr_send_times) >= self.max_send_per_minute and \
        #         self.now_time - self.last_tr_send_times[-self.max_send_per_minute] < datetime.timedelta(minutes=1):
        #     # logger.info(f"분 단위 TR 요청 제한! Wait for time to send!")
        #     return False
        
        # elif len(self.last_tr_send_times) >= self.max_send_per_hour and \
        #         self.now_time - self.last_tr_send_times[-self.max_send_per_hour] < datetime.timedelta(minutes=60):
        #     # logger.info(f"분 단위 TR 요청 제한! Wait for time to send!")
        #     return False
        else:
            return True


        
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
        # logger.info("Sending order")
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
    


    def _receive_real_condition(self, strCode, strType, strConditionName, strConditionIndex):
        # logger.info(f"Received real condition, {strCode}, {strType}, {strConditionName}, {strConditionIndex}")
        if strType == "I":
            self.register_code_to_realtime_list(strCode)
                

        # elif strType == "D" and strCode not in self.stock_dict.keys():
        #     if strCode not in self.stock_dict:
        #         self.unregister_code_to_realtime_list(strCode)

    def _receive_tr_condition(self, scrNum, strCodeList, strConditionName, nIndex, nNext):
        # logger.info(f"Received TR Condition, strCodeList: {strCodeList}, strConditionName: {strConditionName}," 
            #   f"nIndex: {nIndex}, nNext: {nNext}, scrNum: {scrNum}")       
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
            if code not in self.realtime_registed_codes.keys():
                self.realtime_registed_codes.update({code:{}})
            self.realtime_registed_codes[code]["화면번호"] = 화면번호

    def unregister_code_to_realtime_list(self, code):
        if len(code) != 0:
            화면번호 = self.realtime_registed_codes[code]["화면번호"]
            self.set_real_remove(화면번호, code)
            logger.info(f"{code}, 실시간 해지(unregister) 완료!")
            self.realtime_registed_codes.pop(code)            

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

            if sJongmokCode in self.stock_dict.keys():
                self.stock_sell(sJongmokCode, 현재가)

            self.stock_buy(sJongmokCode, 현재가)

            # stock_name = self.get_company_name(sJongmokCode)
            # 보유수량 = self.stock_dict[sJongmokCode].get("보유수량", 0)
            # 고가 = self.stock_dict[sJongmokCode].get("고가", 현재가)
            # 매입가 = self.stock_dict[sJongmokCode].get("매입가", 현재가)
            # 고가 = max(현재가, 고가) if 고가 else 현재가
            # self.stock_dict[sJongmokCode].update({"고가":고가})

                # if 보유수량 > 0:
                #     # 매입가 기준 손실 조건
                #     손실_조건 = 현재가 <= 매입가 * 0.995
                #     # 고가 기준 하락 조건
                #     수익_조건 = 현재가 > 매입가 * 1.01

                #     # if 상태 == '매입' and  보유수량 > 0 and (현재가 <= 매입가 * 0.970 or 현재가 <= 고가 * 0.985):
                #     if 손실_조건 == False:
                #         print(현재가,매입가)
                #     if 손실_조건 or 수익_조건:
                #         보유수량 = self.stock_dict[sJongmokCode].get("보유수량")
                #         # logger.info(f"시장가매도[{체결시간}] == {sJongmokCode} {stock_name} {보유수량} {매입가}  {현재가} ==")
                #         화면번호 = self.stock_dict[sJongmokCode].get("화면번호", "5000")
                #         # self.stock_dict[sJongmokCode].update({"상태":'매도'})
                         
                #         self.send_order( 
                #                 "시장가매도주문", # 사용자 구분명
                #                 화면번호, # 화면번호
                #                 self.account_num, # 계좌번호
                #                 2, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                #                 sJongmokCode, # 종목코드
                #                 보유수량, # 주문 수량
                #                 "", # 주문 가격, 시장가의 경우 공백
                #                 "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                #                 "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)

                #         ) 
                #         QTest.qWait(200)

                # else:
                #      os.system("cls") 
                #      del self.stock_dict[sJongmokCode]
                        # self.tr_req_queue.put(
                        #     [
                        #         self.send_order, 
                        #         "시장가매도주문", # 사용자 구분명
                        #         화면번호, # 화면번호
                        #         self.account_num, # 계좌번호
                        #         2, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                        #         sJongmokCode, # 종목코드
                        #         보유수량, # 주문 수량
                        #         "", # 주문 가격, 시장가의 경우 공백
                        #         "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                        #         "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)

                        #     ]
                        # )                         
                    # else:
                    #     if sJongmokCode in self.stock_dict.keys():
                    #         print(f'{sJongmokCode},{stock_name},보유수량:{보유수량},현재가:{현재가},매입가:{매입가},고가:{고가},{현재가 <= 매입가 * 0.970},{현재가 <= 고가 * 0.985}')

        elif sRealType == "주식호가잔량":
            시간 = self._get_comn_realdata(sRealType, 21)
            매도호가1 = int(self._get_comn_realdata(sRealType, 41).strip().replace('-', ''))
            매수호가1 = int(self._get_comn_realdata(sRealType, 51).replace('-', ''))
            매도호가잔량1 = int(self._get_comn_realdata(sRealType, 61).replace('-', ''))
            매수호가잔량1 = int(self._get_comn_realdata(sRealType, 71).replace('-', ''))
            # qty = int(self.buy_money / 매수호가1)
            # # logger.info(f"qty: {qty}, buy_cnt: {self.buy_cnt}, MAX_BUY_STOCK: {self.MAX_BUY_STOCK}, stock_in_dict: {sJongmokCode in self.stock_dict.keys()}")
            # if qty > 0 and 1000 <= 매수호가1 <= 20000 and sJongmokCode not in self.stock_dict.keys() and sJongmokCode not in self.unfinished_order_num_to_info_dict.keys():
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
            logger.info(
                f"Received chejandata! 주문구분: {주문구분}, 주문구분: {주문구분}, 매매구분: {매매구분}, "
                f"Received chejandata! 주문체결시간: {주문체결시간}, 종목코드: {종목코드}, "
                f"종목명: {종목명}, 주문수량: {주문수량}, 주문가격: {주문가격}, 체결수량: {체결수량}, 체결가격: {체결가격}, "
                f"단위체결량: {단위체결량}, 주문번호: {주문번호}, 원주문번호: {원주문번호}"
            )

            if 주문구분 == '매수' and 체결수량 > 0:
                if 종목코드 not in self.stock_dict.keys():
                    self.stock_dict.update({종목코드:{}})
                    매수횟수 = self.MAX_BUY_DIV
                    self.stock_dict[종목코드][ "매수완료"] = False

                self.stock_dict[종목코드][ "매수횟수"] = 매수횟수 - 1
                self.stock_dict[종목코드][ "보유수량"] = 체결수량
                self.stock_dict[종목코드][ "매입가"] = 체결가격
                self.stock_dict[종목코드][ "종목명"] = 종목명

            if 주문구분 in ['매도','매도정정']: 
                self.unfinished_order_num_to_info_dict.update({주문번호 :{}})
                self.unfinished_order_num_to_info_dict[주문번호].update({"종목코드": 종목코드}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"미체결수량": 미체결수량}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"주문체결시간": 주문체결시간}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"주문구분": 주문구분}) 
                self.unfinished_order_num_to_info_dict[주문번호].update({"화면번호": self.order_screen.get(종목코드,"5000")}) 
                
            if 주문구분 == '매도' and 미체결수량 == 0:
                self.cal_cnt += 1
                del self.stock_dict[종목코드]

                self.stock_dict.pop(종목코드,'미존재')
            if 미체결수량 == 0:
                self.unfinished_order_num_to_info_dict.pop(주문번호,None)
            # self.request_opw00018() 

        if sGubun == "1":
            계좌번호 = self.get_chejandata(9201).strip()   
            종목코드 = self.get_chejandata(9001).replace("A", "").strip()    
            종목명 = self.get_chejandata(302).strip()   
            현재가 = 0 if len(self.get_chejandata(933)) == 0 else int(self.get_chejandata(933))
            매입단가 = 0 if len(self.get_chejandata(932)) == 0 else int(self.get_chejandata(932))
            보유수량 = 0 if len(self.get_chejandata(930)) == 0 else int(self.get_chejandata(930))
            평가손익 = 0 if len(self.get_chejandata(934)) == 0 else int(self.get_chejandata(934))
            수익률 = 0 if len(self.get_chejandata(935)) == 0 else float(self.get_chejandata(935))
            logger.info(
                f"Received chejandata! 계좌번호: {계좌번호}, {종목코드}, {종목명}, {보유수량}개(보유) "
                f"현재가: {현재가}, 매입단가: {매입단가}, "
                f"평가손익: {평가손익}, 수익률: {수익률}"
            )  
        

    def receive_msg(self, sScrno, sRQName, sTrcode, sMsg):
        os.system("cls") 
        logger.info(f"Received MSG! 화면번호: {sScrno}, 사용자 구분명: {sRQName}, TR이름: {sTrcode}, 메세지: {sMsg}")  

    def restart_program(self):
            """프로그램을 재시작"""
            print("프로그램 재시작 중...")
            python = sys.executable
            os.execl(python, python, *sys.argv)

    def check_unfinished_orders(self):
        self.stock_sell()          
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
                # logger.info(f"=== 미체결 === 종목코드: {종목코드}, 주문번호: {주문번호}, 미체결수량: {미체결수량}, 매수 취소 주문:")
                self.send_order( 
                            "매수취소주문", # 사용자 구분명
                            화면번호, # 화면번호
                            self.account_num, # 계좌번호
                            3, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                            종목코드, # 종목코드
                            미체결수량, # 주문 수량
                            "", # 주문 가격, 시장가의 경우 공백
                            "00", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                            주문번호, # 주문번호 (정정 주문의 경우 사용, 나머진 공백)

                ) 
                pop_list.append(주문번호)
                QTest.qWait(200)


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

    def stock_buy(self, stock_code, current_price):
        self.now_time = datetime.datetime.now()
        self.t_9, self.t_start, self.t_sell, self.t_exit, self.t_ai = self.gen_time()

        # 1. 매수 가능 시간 확인
        if not (self.t_9 < self.now_time < self.t_sell):
            # print("매수 가능한 시간이 아닙니다.")
            return

        # 3. 매수가격 범위 확인
        if not (self.MIN_BUY_COST <= current_price <= self.MAX_BUY_COST):
            # print(f"매수가격 범위를 벗어남: 현재가={current_price}")
            return

        # 4. 종목 관리 여부 확인
        isCode = stock_code in self.stock_dict

        # 5. 매수 금액 및 수량 계산
        divide_money = self.buy_money / self.MAX_BUY_DIV
        self.buy_qty = int(divide_money / current_price)
        화면번호 = self._get_realtime_data_screen_num()
        # 매수 조건 설정

        # 6. 분할 매수 및 추가 매수 조건 확인
        if isCode == True:
            매입가 = self.stock_dict[stock_code].get('매입가')
            매수횟수 = self.stock_dict[stock_code].get('매수횟수',self.MAX_BUY_DIV) 
            
            if 매수횟수 == 0:
                return
            
            # 매수 조건: 현재가가 매입단가 대비 2% 하락하고 매수 횟수가 2회 미만
            if current_price <= 매입가 * (1 - (self.LOSS_PERCENT-0.01)):
                pass
            else:
                return
        else:
            if self.cal_cnt > 0:
                self.cal_cnt -= 1

        # 7. 주문 실행
        print(f"종목 {stock_code} 매수 (현재가: {current_price}, 매수 횟수: {매수횟수})")
        order_result = self.send_order(
            "시장가매수주문",  # 사용자 구분명
            화면번호,          # 화면번호
            self.account_num,  # 계좌번호
            1,                 # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
            stock_code,        # 종목코드
            self.buy_qty,      # 주문 수량
            "",                # 주문 가격, 시장가의 경우 공백
            "03",              # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
            ""                 # 주문번호, 정정 주문이 아닌 경우 공백
        )
        QTest.qWait(250)

        # 8. 주문 결과 처리
        if order_result == 0:  # 성공 반환값으로 0 가정
            print(f"매수 성공: 종목코드={stock_code}, 수량={self.buy_qty}")
            self.order_screen.update({stock_code: 화면번호})
        else:
            print(f"매수 실패: 종목코드={stock_code}, 오류코드={order_result}")
            self.order_error_log.append({
                "종목코드": stock_code,
                "수량": self.buy_qty,
                "오류코드": order_result,
                "시간": self.now_time.strftime("%Y-%m-%d %H:%M:%S")
            })

        # 9. 대기 시간 추가
        

    def stock_sell(self,stock_code='',current_price=0):
        """
        보유 주식의 매도 처리 로직. 시간대에 따라 매도 조건이 다름.
        """
        self.now_time = datetime.datetime.now()
        self.t_9, self.t_start, self.t_sell, self.t_exit, self.t_ai = self.gen_time()

        # 1. 매도 가능 시간 확인
        if self.t_9 < self.now_time < self.t_sell:  # 9:00 ~ 15:15: 조건부 매도
            self._conditional_sell(stock_code, current_price)
        elif self.t_sell < self.now_time < self.t_exit:  # 15:15 ~ 15:20: 일괄 매도
            self._force_sell()
        elif self.t_exit < self.now_time:  # 15:20 이후: 프로그램 종료
            self._close_program()

    def _conditional_sell(self,stock_code, 현재가):
        """ 조건부 매도 로직: 손실 또는 수익 조건에 따라 매도 """
        if stock_code in self.stock_dict.keys():
            stock_name = self.get_company_name(stock_code)
            화면번호 = self.stock_dict[stock_code].get("화면번호", "5000")
            보유수량 = self.stock_dict[stock_code].get("보유수량", 0)
            매입가 = self.stock_dict[stock_code].get("매입가", None)
            if 매입가 is None or 현재가 is None:
                print(f"매입가 또는 현재가가 유효하지 않습니다: {stock_code}")

            고가 = self.stock_dict[stock_code].get("고가", 현재가)
            고가 = max(현재가, 고가)
            self.stock_dict[stock_code].update({"고가": 고가})

            손실_조건 = 현재가 <= 매입가 * self.LOSS_PERCENT
            수익_조건 = 현재가 >= 매입가 * self.GAIN_PERCENT

            # logger.info(f"[조건부 매도] 종목: {stock_code}, 현재가: {현재가}, 매입가: {매입가}")
            if 손실_조건 or 수익_조건:
                if 보유수량 > 0:
                    # logger.info(f"[시장가 매도] 종목: {stock_code}, 수량: {보유수량}, 현재가: {현재가}, 매입가: {매입가}")
                    self._send_sell_order(stock_code, 화면번호, 보유수량)
                else:
                    print(f"[매도 불가] 보유 수량이 없습니다: {stock_code}")

    def _force_sell(self):
        """ 일괄 매도 로직: 시간 종료 직전 모든 종목 매도 """
        for stock_code in list(self.stock_dict.keys()):
            stock_data = self.stock_dict.get(stock_code, {})
            화면번호 = stock_data.get("화면번호", "5000")
            보유수량 = stock_data.get("보유수량", 0)

            if 보유수량 > 0:
                logger.info(f"[일괄 매도] 종목: {stock_code}, 수량: {보유수량}")
                self._send_sell_order(stock_code, 화면번호, 보유수량)
            else:
                print(f"[일괄 매도 불가] 보유 수량이 없습니다: {stock_code}")

    def _close_program(self):
        """ 프로그램 종료 """
        logger.info("오늘 장 마감. 프로그램을 종료합니다.")
        sys.exit()

    def _send_sell_order(self, stock_code, 화면번호, 보유수량):
        """ 매도 주문 처리 """
        order_result = self.send_order(
            "시장가매도주문",  # 사용자 구분명
            화면번호,          # 화면번호
            self.account_num,  # 계좌번호
            2,                 # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
            stock_code,        # 종목코드
            보유수량,          # 주문 수량
            "",                # 주문 가격, 시장가의 경우 공백
            "03",              # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
            ""                 # 주문번호, 정정 주문이 아닌 경우 공백
        )
        if order_result == 0:  # 성공 반환값으로 0 가정
            print(f"[매도 성공] 종목: {stock_code}, 수량: {보유수량}")
            QTest.qWait(200)
        else:
            print(f"[매도 실패] 종목: {stock_code}, 오류코드: {order_result}")
            self.order_error_log.append({
                "종목코드": stock_code,
                "수량": 보유수량,
                "오류코드": order_result,
                "시간": self.now_time.strftime("%Y-%m-%d %H:%M:%S")
            })

        # if self._is_check_tr_req_condition() and not self.tr_req_queue.empty():
        #     request_func, *func_args = self.tr_req_queue.get()
        #     # logger.info(f"Executing TR request function: {request_func}")
        #     request_func(*func_args) if func_args else request_func()
        #     self.last_tr_send_times.append(self.now_time)
           
if __name__ == "__main__":
    app = QApplication(sys.argv)            
    kiwoom_api = KiwoomAPI()
    sys.exit(app.exec_())