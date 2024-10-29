import sys
import os
import datetime

import pandas as pd
from loguru import logger

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import *
from collections import deque
from queue import Queue

class KiwoomAPI(QMainWindow):
    def __init__(self):
        super().__init__()

        if os.path.isfile('logfile.log'):
            os.remove('logfile.log')
        logger.add("logfile.log", rotation="1 day", retention="7 days", compression="zip")
        self.tr_req_scrnum = 0
        self.balance = 0
        self.buy_balance = 0
        self.data_cnt = 0
        self.max_buy_cnt = 4
        self.now_time = datetime.datetime.now()
        self.stop_loss_threshold = -.5
        self.realtime_data_scrnum = 5000
        self.tr_reg_scrnum = 5150
        self.max_send_per_sec = 4 # 초당 TR 호출 최대 4번
        self.max_send_per_minute = 55 # 분당 TR 호출 최대 55번
        self.max_send_per_hour = 950 # 시간당 TR 호출 최대 958번
        self.last_tr_send_times = deque(maxlen=self.max_send_per_hour)
        self.tr_req_queue = Queue()
        self.using_condition_name = "스캘핑용"
        self.realtime_registed_codes = {}
        self.stock_dict = {}
        self.unfinished_order_num_to_info_dict = {}
        self.account_num = None
        self.kiwoom = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.req_upside_info_timer = QTimer()
        self.req_upside_info_timer.timeout.connect(self.get_tmp_high_volatility_info)
        self.req_account_info_timer = QTimer()
        self.req_account_info_timer.timeout.connect(self.get_account_info)
        self.check_unfinished_orders_timer = QTimer()
        self.check_unfinished_orders_timer.timeout.connect(self.check_unfinished_orders)
        self.tr_req_check_timer = QTimer()
        self.tr_req_check_timer.timeout.connect(self._send_tr_request)
        self.tr_req_check_timer.start(100) # 0.1초마다 한번 Execute    

        self._set_signal_slots() # 키움증권 API와 내부 메소드를 연동
        self._login()

    def _buy_check(self):
        if self.data_cnt >= self.max_buy_cnt:
            return False
        
        if self.balance <= self.buy_balance:
            return False
        else:
            money = self.balance - self.buy_balance
            if money <= 0:
                return False
            else:
               buy_money = self.balance * 0.5
               buy_money = buy_money / 4
               if buy_money >= money:
                   return True


    def _login(self):
        ret = self.kiwoom.dynamicCall("CommConnect()")
        if ret == 0:
            logger.info("로그인 창 열기 성공!")

    def _event_connect(self, err_code):
        if err_code == 0:
            logger.info("로그인 성공!")                
            self._after_login()
        else:
            raise Exception("로그인 실패!")
        
    def get_account_num(self):
        account_nums = str(self.kiwoom.dynamicCall("GetLoginInfo(QString)", ["ACCNO"]).rstrip(';'))
        logger.info(f"계좌번호 리스트: {account_nums}")
        self.account_num = account_nums.split(';')[0]
        logger.info(f"사용 계좌 번호: {self.account_num}")     

    def _after_login(self):
        self.get_account_num()
        self.req_account_info_timer.start(1500) 
        self.kiwoom.dynamicCall("GetConditionLoad()") # 조건 검색 정보 요청     
        # self.req_upside_info_timer.start(3000)
        self.check_unfinished_orders_timer.start(250)

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

    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, unused1, unused2, unused3, unused4):
        if rqname == "opw00018_req":
            self._on_opw00018_req(rqname, trcode)     
        elif rqname == "opt10019_req":
            self._on_opt10019_req(rqname, trcode)
    
    def _on_opw00018_req(self, rqname, trcode):
        self.balance = int(self._comm_get_data(trcode, "", rqname, 0, "추정예탁자산"))
        self.buy_balance = int(self._comm_get_data(trcode, "", rqname, 0, "총매입금액"))
        self.data_cnt = self._get_repeat_cnt(trcode, rqname)
        logger.info(f"현재평가잔고: {self.balance:,}원")
        logger.info(f"총매입급액: {self.buy_balance:,}원")
        logger.info(f"보유종목수: {self.data_cnt:,}개")
        for i in range(self.data_cnt):
            종목코드 = self._comm_get_data(trcode, "", rqname, i, "종목번호").replace("A","").strip()
            보유수량 = int(self._comm_get_data(trcode, "", rqname, i, "보유수량"))
            매입가 = int(self._comm_get_data(trcode, "", rqname, i, "매입가"))
            if 종목코드  not in self.stock_dict.keys():
                self.stock_dict.update({종목코드:{}})
                self.register_code_to_realtime_list(종목코드)
            self.stock_dict[종목코드].update({"보유수량": 보유수량})
            self.stock_dict[종목코드].update({"매입가": 매입가})

        for stock in self.stock_dict.keys():
            logger.info(self.stock_dict[stock])   
            
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

    def _send_tr_request(self):
        self.now_time = datetime.datetime.now()
        if self._is_check_tr_req_condition() and not self.tr_req_queue.empty():
            request_func, *func_args = self.tr_req_queue.get()
            logger.info(f"Executing TR request function: {request_func}")
            request_func(*func_args) if func_args else request_func()
            self.last_tr_send_times.append(self.now_time)    

    def _is_check_tr_req_condition(self):
        self.now_time = datetime.datetime.now()            
        if len(self.last_tr_send_times) >= self.max_send_per_sec and \
            self.now_time - self.last_tr_send_times[-self.max_send_per_sec] < datetime.timedelta(microseconds=1000):
            logger.info(f"초 단위 TR 요청 제한! Wait for time to send!")
            return False
        elif len(self.last_tr_send_times) >= self.max_send_per_minute and \
                self.now_time - self.last_tr_send_times[-self.max_send_per_minute] < datetime.timedelta(minutes=1):
            logger.info(f"분 단위 TR 요청 제한! Wait for time to send!")
            return False
        
        elif len(self.last_tr_send_times) >= self.max_send_per_hour and \
                self.now_time - self.last_tr_send_times[-self.max_send_per_hour] < datetime.timedelta(minutes=60):
            logger.info(f"분 단위 TR 요청 제한! Wait for time to send!")
            return False
        else:
            return True

    def check_unfinished_orders(self):
        pop_list = []   
        for order_num in self.unfinished_order_num_to_info_dict.keys():
            주문번호 = order_num
            종목코드 = self.unfinished_order_num_to_info_dict[주문번호]["종목코드"]    
            주문체결시간 = self.unfinished_order_num_to_info_dict[주문번호]["주문체결시간"]    
            미체결수량 = self.unfinished_order_num_to_info_dict[주문번호]["미체결수량"]    
            주문구분 = self.unfinished_order_num_to_info_dict[주문번호]["주문구분"]    
            order_time = datetime.datetime.now().replace(
                hour = int(주문체결시간[:-4]),
                minute = int(주문체결시간[-4:-2]),
                second = int(주문체결시간[-2:])
            )
            if 주문구분 == "매수" and datetime.datetime.now() - order_time >= datetime.timedelta(seconds=10):
                logger.info(f"종목코드: {종목코드}, 주문번호: {주문번호}, 미체결수량: {미체결수량}, 매수 취소 주문:")
                self.send_order(
                    "매수취소주문", # 사용자 구분명
                    self.stock_dict[종목코드]["화면번호"], # 화면번호
                    self.account_num, # 계좌번호
                    3, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                    종목코드, # 종목코드
                    미체결수량, #주문 수량
                    "", # 주문 가격, 시장가 외 경우 공백
                    "00", # 주문유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등 (코아스트디오 참소)
                    주문번호, # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
                )
                pop_list.append(주문번호)

            elif 주문구분 == "매도" and datetime.datetime.now() - order_time >= datetime.timedelta(seconds=10):
                logger.info(f"종목코드: {종목코드}, 주문번호: {주문번호}, 미체결수량: {미체결수량}, 매도 취소 주문!")
                self.send_order(
                    "매도취소주문", # 사용자 구분
                    self.stock_dict[종목코드]["화면번호"], # 화면번호
                    self.account_num, # 계좌 번호
                    4, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                    종목코드, # 종목코드
                    미체결수량, # 주문수량
                    "", # 주문 가격, 시장가의 경우 공백
                    "00", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등 (코아스트디오 참소)
                    주문번호, # 주분번호 (정정 주문의 경우 사용, 나머진 공백)
                )
                pop_list.append(주문번호)
            for order_num in pop_list:
                del self.unfinished_order_num_to_info_dict[order_num]
        
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
    
    def _receive_real_condition(self, strCode, strType, strConditionName, strConditionIndex):
        logger.info(f"Received real condition, {strCode}, {strType}, {strConditionName}, {strConditionIndex}")
        if strType == "I":
            self.register_code_to_realtime_list(strCode)
            if self._buy_check() and strCode not in self.stock_dict.keys():
               self.send_order(
                "시장가매수주문", # 사용자 구분명
                self._get_realtime_data_screen_num(), # 화면번호
                self.account_num, 
                1, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                strCode, # 종목코드
                1, # 주문 수량
                "", # 주문 가격, 시장가의 경우 공백
                "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등 (KOAStudio 참조)
                "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
                )  
             
        elif strType == "D" and strCode not in self.stock_dict.keys():
            self.unregister_code_to_realtime_list(strCode)

    def _receive_tr_condition(self, scrNum, strCodeList, strConditionName, nIndex, nNext):
        logger.info(f"Received TR Condition, strCodeList: {strCodeList}, strConditionName: {strConditionName}," 
              f"nIndex: {nIndex}, nNext: {nNext}, scrNum: {scrNum}")       
        for stock_code in strCodeList.split(';'):
            if len(stock_code) == 6 and stock_code not in self.stock_dict.keys():
                self.register_code_to_realtime_list(stock_code) 
                if self._buy_check():
                    self.send_order(
                        "시장가매수주문", # 사용자 구분명
                        self._get_realtime_data_screen_num(), # 화면번호
                        self.account_num, 
                        1, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                        stock_code, # 종목코드
                        1, # 주문 수량
                        "", # 주문 가격, 시장가의 경우 공백
                        "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등 (KOAStudio 참조)
                        "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
                    )  


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
            del self.realtime_registed_codes[code]            

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
            # self.stock_dict[sJongmokCode].update({"현재가": 현재가})

            if sJongmokCode in self.stock_dict.keys():
                self.stock_dict[sJongmokCode].update({"현재가": 현재가})
                매입후고가 = self.stock_dict[sJongmokCode].get("매입후고가", 현재가)
                매입후고가 = max(현재가, 매입후고가) if 매입후고가 else 현재가
                self.stock_dict[sJongmokCode]["매입후고가"] = 매입후고가
                고가대비등락률 = (현재가 - 매입후고가) / 매입후고가 * 100
                if 고가대비등락률 <= self.stop_loss_threshold:
                    logger.info(f"종목코드: {sJongmokCode}, 시장가 매도 진행!")
                    self.send_order(
                        "시장가매도주문", # 사용자 구분명
                        self._get_realtime_data_screen_num(), # 화면번호
                        self.account_num, # 계좌번호
                        2, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                        sJongmokCode, # 종목코드
                        self.stock_dict[sJongmokCode].get("보유수량", 1) , # 주문 수량
                        "", # 주문 가격, 시장가의 경우 공백
                        "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                        "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
                    )
                매입가 = self.stock_dict[sJongmokCode].get("매입가", None)
                보유량 = self.stock_dict[sJongmokCode].get("보유량", None)

                if 매입가 is None:
                    return

                수익률 = (현재가- 매입가) / 매입가 * 100

                if 수익률 <= self.stop_loss_threshold:
                    logger.info(f"종목코드: {sJongmokCode}, 시장가 매도 진행!")
                    self.send_order(
                        "시장가매도주문", # 사용자 구분명
                        self._get_realtime_data_screen_num(), # 화면번호
                        self.account_num, # 계좌번호
                        2, # 주문유형, 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
                        sJongmokCode, # 종목코드
                        self.stock_dict[sJongmokCode].get("보유수량", 1), # 주문 수량
                        "", # 주문 가격, 시장가의 경우 공백
                        "03", # 주문 유형, 00: 지정가, 03: 시장가, 05: 조건부지정가, 06: 최유리지정가, 07: 최우선지정가 등
                        "", # 주문번호 (정정 주문의 경우 사용, 나머진 공백)
                    )

                    보유량 = self.stock_dict[sJongmokCode]["보유수량"]
                    if 보유량 == 0:
                        del self.stock_dict[sJongmokCode]



        elif sRealType == "주식호가잔량":
            시간 = self._get_comn_realdata(sRealType, 21)
            매도호가1 = int(self._get_comn_realdata(sRealType, 41).strip().replace('-', ''))
            매수호가1 = int(self._get_comn_realdata(sRealType, 51).replace('-', ''))
            매도호가잔량1 = int(self._get_comn_realdata(sRealType, 61).replace('-', ''))
            매수호가잔량1 = int(self._get_comn_realdata(sRealType, 71).replace('-', ''))

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
            if 주문번호 not in self.unfinished_order_num_to_info_dict.keys():
                self.unfinished_order_num_to_info_dict.update({주문번호 :{}})
            self.unfinished_order_num_to_info_dict[주문번호].update({"종목코드": 종목코드}) 
            self.unfinished_order_num_to_info_dict[주문번호].update({"미체결수량": 미체결수량}) 
            self.unfinished_order_num_to_info_dict[주문번호].update({"주문체결시간": 주문체결시간}) 
            self.unfinished_order_num_to_info_dict[주문번호].update({"주문구분": 주문구분}) 
            if 미체결수량 == 0:
                del self.unfinished_order_num_to_info_dict[주문번호]

            if 체결수량 > 0:
                if 종목코드 not in self.stock_dict.keys():
                    self.stock_dict.update({종목코드:{}})
                self.stock_dict[종목코드][ "보유수량"] = 체결수량
                self.stock_dict[종목코드][ "매입가"] = 체결가격

        if sGubun == "1":
            logger.info("잔고통보")    

    def receive_msg(self, sScrno, sRQName, sTrcode, sMsg):
        logger.info(f"Received MSG! 화면번호: {sScrno}, 사용자 구분명: {sRQName}, TR이름: {sTrcode}, 메세지: {sMsg}")  

            
if __name__ == "__main__":
    app = QApplication(sys.argv)            
    kiwoom_api = KiwoomAPI()
    sys.exit(app.exec_())
