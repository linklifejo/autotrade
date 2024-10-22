import os
import sys
from PyQt5.QAxContainer import *
from PyQt5.QtCore import * 
from PyQt5.QtTest import *
from config.errorCode import *
from config.kiwoomType import *
import requests
from bs4 import BeautifulSoup # type: ignore
import logging

class Kiwoom(QAxWidget):
    def __init__(self):
        super().__init__()
        # 로그 설정 (INFO 레벨 이상의 로그만 기록)
        if os.path.isfile('app.log'):
            os.remove('app.log')
        logging.basicConfig(level=logging.INFO,  # INFO 레벨 이상의 로그만 기록
                            format='%(asctime)s - %(levelname)s - %(message)s',  # 로그 메시지 형식
                            datefmt='%Y-%m-%d %H:%M:%S',  # 날짜 형식
                            handlers=[
                                logging.FileHandler("app.log", encoding='utf-8'),  # 로그 파일에 기록
                                logging.StreamHandler()  # 콘솔에도 출력
                            ])

        # 로거 생성
        self.logging = logging.getLogger(__name__)


        self.realType = RealType()
        ######## 이벤트루프 모음
        self.login_event_loop = QEventLoop()
        self.detail_account_info_event_loop = QEventLoop()
        self.calculator_event_loop = QEventLoop()
        self.condition_event_loop = QEventLoop()
        ############################

        ########변수모음
        self.pw = '0000'
        self.account_codes = 0
        self.deposit = 0
        self.ok_deposit = 0
        self.total_buy_money_result = 0
        self.total_profit_loss_rate_result = 0
        self.condition_list = None  # 조건식 목록 저장할 변수
        self.portfolio_stock_dict = {}
        self.account_num = None
        self.account_stock_dict = {}
        self.not_account_stock_dict = {}
        self.jango_dict = {}
        ########################

        #########스크린번호
        self.screen_my_info = '2000'
        self.screen_calculation_stock = '4000'
        self.screen_real_stock = '5000' #종목별 할당할 종목등록 스크린 번호
        self.screen_meme_stock = '6000' #종목별 할당할 주문용 스크린 번호
        self.screen_start_stop_real = '1000'

        ########################
        #######계좌 관련 변수
        self.use_money = 0
        self.use_money_percent = 0.5
        ########################
        ##### 종목 분석용
        self.calcul_data = []
        #######################
        self.get_ocx_instance()
        self.event_slots()
        self.real_event_slots()

        self.signal_login_commConnect() # 로그인
        self.get_account_info()    # 계좌번호 가져오기
        self.detail_account_info() # 예수금 가져오기
        self.detail_account_mystock() # 계좌평가잔고내역
        self.not_concluded_account() # 미체결 요청
        # self.calculator_fnc() # 종목 분석용, 임시용으로 실행
        # self.read_code() #  종목들 불러온다
        condition_list = self.get_condition_list()
        if condition_list:
            print("조건식 목록:", condition_list)
            # 조건검색식을 사용해 종목 조회 (예시: 두 번째 조건식 사용)
            condition_index, condition_name = condition_list[1].split('^')
            self.logging.info(condition_name,condition_index)
            self.send_condition("0101", condition_name, int(condition_index), 1)  # 실시간 조회를 원하지 않으면 0, 실시간 조회를 원하면 1
        else:
            print("조건식이 없습니다. HTS에서 조건식을 등록했는지 확인하세요.")

        # self.get_codes()
        self.screen_number_setting() # 스크린 번호를 할당
        w = []
        p = []
        self.dynamicCall('SetRealReg(QString, QString, QString, QString)',self.screen_start_stop_real, '', self.realType.REALTYPE['장시작시간']['장운영구분'], '0')
        for code in self.portfolio_stock_dict.keys():
            if code in self.account_stock_dict.keys():
                w.append(code)
            else:
                p.append(code)
        w.sort()
        w.extend(p)
        for code in w:
            screen_num = self.portfolio_stock_dict[code]['스크린번호']
            fids = self.realType.REALTYPE['주식체결']['체결시간']
            code_nm = self.dynamicCall('GetMasterCodeName(QString)', code)
            self.dynamicCall('SetRealReg(QString, QString, QString, QString)',screen_num, code, fids, '1')
            if code != '':
                if code in self.account_stock_dict.keys():
                    check = '보유'
                else:
                    check = '포트'
                self.logging.info('실시간 등록 코드[%s] :%s %s, 스크린번호: %s, fid번호: %s' % (check,code,code_nm, screen_num, fids))

    def get_condition_list(self):
        self.logging.info("조건식을 불러옵니다...")
        ret = self.dynamicCall("GetConditionLoad()")
        self.logging.info(f"GetConditionLoad() 호출 결과: {ret}")
        self.condition_event_loop.exec_()  # 이벤트 대기
        return self.condition_list  # 조건식 목록 반환

    def _receive_condition_ver(self, ret, msg):
        self.logging.info(f"_receive_condition_ver 호출됨: ret={ret}, msg={msg}")
        if ret == 1:
            conditions = self.dynamicCall("GetConditionNameList()")
            self.condition_list = conditions.split(';')[:-1]  # 마지막 빈 값 제외
            self.logging.info(f"받은 조건식 목록: {self.condition_list}")
        else:
            self.logging.info(f"조건식 리스트 가져오기 실패: {msg}")
        self.condition_event_loop.exit()

    def send_condition(self, screen_no, condition_name, condition_index, is_real_time):
        self.logging.info(f"조건식 실행: {condition_name} (인덱스: {condition_index})")
        self.dynamicCall("SendCondition(QString, QString, int, int)", screen_no, condition_name, condition_index, is_real_time)

    def _receive_tr_condition(self, screen_no, code_list, condition_name, index, next):
        codes = code_list.split(';')[:-1]  # 마지막이 빈 값이므로 제외
        for code in codes:
            if code not in self.portfolio_stock_dict.keys():
                self.portfolio_stock_dict.update({code: {}})
            screen_num = self.screen_real_stock
            fids = self.realType.REALTYPE['주식체결']['체결시간']
            code_nm = self.dynamicCall('GetMasterCodeName(QString)', code)
            self.dynamicCall('SetRealReg(QString, QString, QString, QString)',screen_num, code, fids, '1')
            if code != '':
                    check = '검색'
            self.logging.info('실시간 등록 코드[%s] :%s %s, 스크린번호: %s, fid번호: %s' % (check,code,code_nm, screen_num, fids))            
        self.screen_number_setting() # 스크린 번호를 할당   

    def _receive_real_condition(self, code, event_type, condition_name, condition_index):
        code_nm = self.dynamicCall('GetMasterCodeName(QString)', code)
        self.logging.info(f"실시간 조건 변경 - 종목코드: {code} {code_nm}, 이벤트 타입: {event_type}, 조건명: {condition_name}, 인덱스: {condition_index}")           
        if code in self.portfolio_stock_dict.keys():
            if event_type == 'D':
                del self.portfolio_stock_dict[code]
        else:
             if event_type == 'I':
                 self.portfolio_stock_dict.update({code:{}})
        self.screen_number_setting()

    def get_ocx_instance(self):
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")    

    def event_slots(self):
        self.OnEventConnect.connect(self.login_slot)    
        self.OnReceiveTrData.connect(self.trdata_slot)  
        self.OnReceiveMsg.connect(self.msg_slot)  

    def real_event_slots(self):
        self.OnReceiveRealData.connect(self.realdata_slot)
        self.OnReceiveChejanData.connect(self.chejan_slot)
        self.OnReceiveTrCondition.connect(self._receive_tr_condition)
        self.OnReceiveConditionVer.connect(self._receive_condition_ver)
        self.OnReceiveRealCondition.connect(self._receive_real_condition)

    def login_slot(self, errCode):
        self.logging.info(errors(errCode))
        self.login_event_loop.exit()

    def signal_login_commConnect(self):
        self.dynamicCall('CommConnect()')
        self.login_event_loop.exec_()

    def get_account_info(self):
        account_list = self.dynamicCall('GetLoginInfo(QString)','ACCNO')
        self.account_num = account_list.split(';')[0]
        # print('나의 보유 계좌번호 %s ' % self.account_num) #8087676111
        # user_id = self.dynamicCall('GetLoginInfo(String)','USER_ID')

    def detail_account_info(self):
        self.dynamicCall('SetInputValue(QString,QString)','계좌번호',self.account_num)
        self.dynamicCall('SetInputValue(QString,QString)','비밀번호',self.pw)
        self.dynamicCall('SetInputValue(QString,QString)','비밀번호입력매체구분','00')
        self.dynamicCall('SetInputValue(QString,QString)','조회구분','2')
        self.dynamicCall('CommRqData(String,String,int,String)','예수금상세현황요청','opw00001','0',self.screen_my_info)
        self.detail_account_info_event_loop.exec_()
    
    def detail_account_mystock(self, sPrevNext='0'):
        self.dynamicCall('SetInputValue(QString,QString)','계좌번호',self.account_num)
        self.dynamicCall('SetInputValue(QString,QString)','비밀번호',self.pw)
        self.dynamicCall('SetInputValue(QString,QString)','비밀번호입력매체구분','00')
        self.dynamicCall('SetInputValue(QString,QString)','조회구분','2')
        self.dynamicCall('CommRqData(QString,QString,int,QString)','계좌평가잔고내역요청','opw00018',sPrevNext,self.screen_my_info)
        self.detail_account_info_event_loop.exec_()
    

    def not_concluded_account(self, sPrevNext='0'):
        self.dynamicCall('SetInputValue(QString,QString)','계좌번호',self.account_num)
        self.dynamicCall('SetInputValue(QString,QString)','체결구분','1')
        self.dynamicCall('SetInputValue(QString,QString)','매매구분','0')
        self.dynamicCall('CommRqData(QString,QString,int,QString)','실시간미체결요청','opt10075',sPrevNext,self.screen_my_info)
        self.detail_account_info_event_loop.exec_()
       
    def trdata_slot(self, sScrNo, sRQName, sTrCode, sRecordName, sPrevNext):
        '''
        스크린번호
        내가 요청했을 때 지은 이름
        요청id
        사용안함
        다음페이지가 있는지
        '''

        if sRQName == '예수금상세현황요청':
            self.deposit = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, 0, '예수금')
            self.deposit = int(self.deposit)
            self.use_money = self.deposit * self.use_money_percent
            self.use_money = int(self.use_money / 4)
            self.logging.info(f'종목당 매수가능금액: {self.use_money:,}원')
            self.ok_deposit = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, 0, '출금가능금액')
            self.ok_deposit = int(self.ok_deposit)
            self.logging.info(f'출금가능금액: {self.ok_deposit:,}원')
            self.logging.info(f'예수금: {self.deposit:,}원')
            self.detail_account_info_event_loop.exit()

        if sRQName == '계좌평가잔고내역요청':
            total_buy_money = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, 0, '총매입금액')
            self.total_buy_money_result = int(total_buy_money)
            total_profit_loss_rate = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, 0, '총수익률(%)')
            self.total_profit_loss_rate_result = float(total_profit_loss_rate)
            self.logging.info(f'매수금액: {self.total_buy_money_result:,}원')
            self.logging.info(f'수익률: {self.total_profit_loss_rate_result:,}%')
            
            rows = self.dynamicCall('GetRepeatCnt(QString, QString)', sTrCode, sRQName)
            cnt = 0
            for i in range(rows):

                code = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '종목번호') 
                code = code.strip()[1:] #A00001 종목번호가 이런식으로 되어있고,이유는 주식(A), 채권 ... 그룹분류로 보임 ** 중요함
                code_nm = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '종목명')
                stock_quantity = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '보유수량')
                buy_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '매입가')
                learn_rate = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '수익률(%)')
                current_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '현재가')
                total_chegual_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '매입금액')
                possible_quantity = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '매매가능수량')

                if code in self.account_stock_dict:
                    pass
                else:
                    self.account_stock_dict.update({code: {}})
                code_nm = code_nm.strip()
                stock_quantity = int(stock_quantity.strip())
                buy_price = int(buy_price.strip())
                learn_rate = float(learn_rate.strip())
                current_price = int(current_price.strip())
                total_chegual_price = int(total_chegual_price.strip())
                possible_quantity = int(possible_quantity.strip())

                self.account_stock_dict[code].update({'종목명': code_nm})
                self.account_stock_dict[code].update({'보유수량': stock_quantity})
                self.account_stock_dict[code].update({'매입가': buy_price})
                self.account_stock_dict[code].update({'수익률(%)': learn_rate})
                self.account_stock_dict[code].update({'현재가': current_price})
                self.account_stock_dict[code].update({'매입금액': total_chegual_price})
                self.account_stock_dict[code].update({'매매가능수량': possible_quantity})
                cnt += 1
                self.logging.info(f'보유종목 {cnt}: {self.account_stock_dict[code]}\n') 
            self.account_codes = cnt
            self.logging.info(f'보유종목: {self.account_codes:,}개, {self.account_stock_dict.keys()}\n')   

            if sPrevNext == '2':
                self.detail_account_mystock(sPrevNext='2')   
            else:        
                self.detail_account_info_event_loop.exit()

        elif sRQName == '실시간미체결요청':
            rows = self.dynamicCall('GetRepeatCnt(QString, QString)', sTrCode, sRQName)

            for i in range(rows):
                code = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '종목번호')
                code_nm = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '종목명')
                order_no = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '주문번호')
                order_status = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '주문상태') # 접수, 확인, 체결
                order_quantity = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '주문수량')
                order_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '주문가격')
                order_gubun = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '주문구분') # -매도, +매수, -매도결정, +매수결정 
                not_quantity = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '미체결수량')
                ok_quantity = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '체결량')

                code = code.strip()
                code_nm = code_nm.strip()
                order_no = int(order_no.strip())
                order_status = order_status.strip()
                order_quantity = int(order_quantity.strip())
                order_gubun = order_gubun.strip().lstrip('+').lstrip('-')
                not_quantity = int(not_quantity.strip())
                ok_quantity = int(ok_quantity.strip())

                if order_no in self.not_account_stock_dict:
                    pass
                else:
                    self.not_account_stock_dict.update({order_no:{}})
                # nasd = self.not_account_stock_dict[order_no]
                # nasd.update({'종목코드': code}) 빠르다~~
                self.not_account_stock_dict[order_no].update({'종목코드': code})
                self.not_account_stock_dict[order_no].update({'종목명': code_nm})
                self.not_account_stock_dict[order_no].update({'주문번호': order_no})
                self.not_account_stock_dict[order_no].update({'주문상태': order_status})
                self.not_account_stock_dict[order_no].update({'주문수량': order_quantity})
                self.not_account_stock_dict[order_no].update({'주문가격': order_price})
                self.not_account_stock_dict[order_no].update({'주문구분': order_gubun})
                self.not_account_stock_dict[order_no].update({'미체결수량': not_quantity})
                self.not_account_stock_dict[order_no].update({'체결량': ok_quantity})
                # print('미체결 종목 %s' % self.not_account_stock_dict[order_no])
            self.detail_account_info_event_loop.exit()



        elif '주식일봉차트조회' == sRQName:
            code = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, 0, '종목코드')
            code = code.strip()
            cnt = self.dynamicCall('GetRepeatCnt(QString, QString)', sTrCode, sRQName)
            for i in range(cnt):
                data = []
            current_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '현재가')
            value = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '거래량')
            trading_value = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '거래대금')
            date = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '일자')
            start_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '시가')
            high_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '고가')
            low_price = self.dynamicCall('GetCommData(QString, QString, int, QString)', sTrCode, sRQName, i, '저가')
            data.append('')
            data.append(current_price.strip())
            data.append(value.strip())
            data.append(trading_value.strip())
            data.append(date.strip())
            data.append(start_price.strip())
            data.append(high_price.strip())
            data.append(low_price.strip())
            data.append('')

            self.calcul_data.append(data.copy())
            print(self.calcul_data)


            if sPrevNext =='2':
                self.day_kiwoom_db(code=code, sPrevNext=sPrevNext)
            else:
                print('총 일수 %s' % len(self.calcul_data))
                pass_success =  False
                #120일 이평선을 그릴만큼의 데이터가 있는지 체크
                if self.calcul_data == None or len(self.calcul_data) < 120:
                    pass_success = False
                else:
                    #120일 이상 되면은
                    total_price = 0
                    for value in self.calcul_data[:120]:
                        total_price += int(value[1])
                    moving_average_price = total_price / 120
                    #오늘자 주가가 120일 이평선에 걸쳐있는지 확인
                    bottom_stock_price = False
                    check_price = None
                    if int(self.calcul_data[0][7]) <= moving_average_price and moving_average_price <= int(self.calcul_data[0][6]):
                        print('오늘 주가 120이평선에 걸쳐있는 것 확인')
                        bottom_stock_price = True
                        check_price = int(self.calcul_data[0][6])
                    #과거 일봉들이 120일 이평선보다 밑에 있는지 확인, 
                    #그렇게 확인을 하다가 일봉이 120일 이평선보다 위에 있으면 계산 진행
                    prev_price = None #과거의 일봉 저가
                    if bottom_stock_price == True:
                        moving_average_price_prev = 0
                        price_top_moving = False
                        idx = 1
                        while True:
                            if len(self.calcul_data[idx:]) <120: #120일치가 있는지 계속 확인
                                print('120일치가 없음')
                                break
                            total_price = 0
                            for value in self.calcul_data[idx:120+idx]:
                                total_price += int(value[1])
                            moving_average_price_prev = total_price / 120

                            if moving_average_price_prev <= int(self.calcul_data[idx][6]) and idx <= 20:
                                print('20일 동안 주가가 120일 이평선과 같거나 위에 있으면 조건 통과 못함')
                                price_top_moving = False
                                break
                            elif int(self.calcul_data[idx][7]) > moving_average_price_prev and idx > 20:
                                print('120일 이평선 위에 있는 일봉 확인됨')
                                price_top_moving = True
                                prev_price = int(self.calcul_data[idx][7])
                                break
                            idx += 1
                        # 해당 부분 이평선이 가장 최근 일자의 이평선 가격보다 낮은지 확인
                        if price_top_moving == True:
                            if moving_average_price > moving_average_price_prev and check_price > prev_price:
                                print('포착된 이평선의 가격이 오늘자(최근일자) 이평선 가격보다 낮은 것 확인됨')
                                print('포착된 부분의 일봉 저가가 오늘자 일봉의 고가보다 낮은지 확인됨')
                                pass_success = True
                if pass_success == True:
                    print('조건부 통과됨')
                    code_nm = self.dynamicCall('GetMasterCodeName(QString)', code)
                    f = open('files/condition_stock.txt', 'a', encoding='utf8')
                    f.write('%s\t%s\t%s\n' % (code, code_nm, str(self.calcul_data[0][1])))
                    f.close()             
                self.calcul_data.clear()

                self.calculator_event_loop.exit()
            
    def get_code_list_by_market(self, market_code):
        code_list = self.dynamicCall('GetCodeListByMarket(QString)', market_code)
        code_list = code_list.split(';')[:-1]
        return code_list

    def calculator_fnc(self):
        code_list = self.get_code_list_by_market('10') # 10은 코스닥, 0은 코스피
        self.logging.info('코스닥 갯수 %s' % len(code_list))
        for idx, code in enumerate(code_list):
            self.dynamicCall('DisconnectRealData(QString)', self.screen_calculation_stock)
            self.logging.info('%s / %s :KOSDAQ Stock Code : %s is updating... ' % (idx+1, len(code_list), code))
            self.day_kiwoom_db(code=code)

    def day_kiwoom_db(self, code=None, date=None, sPrevNext='0'):
        QTest.qWait(3600)
        self.dynamicCall('SetInputValue(QString, QString)', '종목코드', code)            
        self.dynamicCall('SetInputValue(QString, QString)', '수정주가구분', '1')            
        if date != None:
            self.dynamicCall('SetInputValue(QString, QString)', '기준일자', date)            
        self.dynamicCall('CommRqData(QString, QString, int, QString)', '주식일봉차트조회','opt10081', sPrevNext, self.screen_calculation_stock) # Tr서버로 전송 -Transaction
        self.calculator_event_loop.exec_()

    def read_code(self):
        if os.path.exists('files/condition_stock.txt'):
            f = open('files/condition_stock.txt','r', encoding='utf8')
            lines = f.readline()          
            for line in lines:
                if line != '':
                    ls = line.split('\t')
                    stock_code = ls[0]
                    stock_name = ls[1]
                    stock_price = int(ls[2].split('\n')[0])
                    stock_price = abs(stock_price)
                    self.portfolio_stock_dict.update({stock_code:{'종목명':stock_name,'현재가':stock_price}})
            f.close()
            self.logging.info(self.portfolio_stock_dict)


 
    def screen_number_setting(self):
        screen_overwrite = []
        #계좌평가잔고내역에 있는 종목들 불러오기
        for code in self.account_stock_dict.keys():
            if code not in screen_overwrite:
                screen_overwrite.append(code)
        #미체결에 있는 종목들
        for order_number in self.not_account_stock_dict.keys():
            code = self.not_account_stock_dict[order_number]['종목코드']

            if code not in screen_overwrite:
                screen_overwrite.append(code)
        #포트폴리오에 담겨있는 종목들 불러오기
        for code in self.jango_dict.keys():
            if code not in screen_overwrite:
                screen_overwrite.append(code)
        for code in self.portfolio_stock_dict.keys():
            if code not in screen_overwrite:
                screen_overwrite.append(code)
        #스크린번호 할당
        cnt = 0
        for code in screen_overwrite:
            temp_screen = int(self.screen_real_stock)
            meme_screen = int(self.screen_meme_stock)
            if(cnt % 50) == 0:
                temp_screen += 1
                self.screen_real_stock = str(temp_screen)
            if(cnt % 50) == 0:
                meme_screen += 1
                self.screen_meme_stock = str(meme_screen)

            if code in self.portfolio_stock_dict.keys():
                self.portfolio_stock_dict[code].update({'스크린번호': str(self.screen_real_stock)})
                self.portfolio_stock_dict[code].update({'주문용스크린번호': str(self.screen_meme_stock)})
            if code not in self.portfolio_stock_dict.keys():
                self.portfolio_stock_dict.update({code:{'스크린번호': str(self.screen_real_stock),'주문용스크린번호': str(self.screen_meme_stock)}})

            cnt += 1

        # print(self.portfolio_stock_dict)
    # 파일삭제
    def file_delete(self):
        if os.path.isfile('files/condition_stock.txt'):
            os.remove('files/condition_stock.txt')
            
    #송수신 메세지 get
    def msg_slot(self, sScrNo, sRQName, sTrCode, msg):
        self.logging.info(f'스크린: {sScrNo}, 요청이름: {sRQName}, tr코드: {sTrCode} --- {msg}')
 

    def codes(self):
        COST = 100  # 최소 단가
        VOLUME = 300000  # 최소 거래량
        results = []
        codes = []

        for chk in [0, 1]:  # 0은 코스피, 1은 코스닥
            url = f'https://finance.naver.com/sise/sise_rise.naver?sosok={chk}'
            response = requests.get(url)
            if response.status_code == 200:
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                trs = soup.select('table.type_2 tr')
                del trs[0:2]  # 제목 행 제거
                
                for tr in trs:
                    record = []
                    tds = tr.find_all('td')
                    for td in tds:
                        if td.select('a[href]'):
                            code = td.find('a').get('href').split('=')[-1].strip().replace(',', '')
                            name = td.get_text().strip().replace(',', '')
                            
                            record.append(code)  # 주식 코드
                            if name == '':
                                name = '없다'
                            record.append(name)  # 업체명
                        else:
                            data = td.get_text().strip().replace(',', '')
                            if data.isdigit():
                                record.append(int(data))
                            else:
                                record.append(data)
                    if len(record) >= 7 and record[3] >= COST and record[6] >= VOLUME:
                        grade = record[5].replace('+','').replace('%','')
                        # 저장은 하고 있지만 코드만 사용 나중에 사용에 대한 고려
                        results.append({'code':record[1],'name':record[2],'price':record[3],'grade':float(grade),'volume':record[6],'stock': chk})  # 업체명과 시장 구분(0 또는 1) 추가
                        # print(f"{row['code']} {row['name']} {row['price']} {row['grade']} {row['volume']} {row['stock']}")
                        # codes.append(record[1])

                        

            else:
                self.logging.info("Failed to retrieve data:", response.status_code)
        results.sort(key=lambda x: x['grade'], reverse=True)
        # 상위 10개 요소의 'code' 값만을 포함하는 새로운 리스트 생성
        codes = [result['code'] for result in results[:10]]
        return codes
    
    def get_codes(self):
         for code in self.codes():
            if code in self.portfolio_stock_dict.keys():
                pass
            else:
                self.portfolio_stock_dict.update({code:{}})

    def chejan_slot(self, sGubun, nItemCnt, sFIdList):
        if int(sGubun) == 0:
            sCode = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['종목코드'])[1:]
            stock_name = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['종목명'])
            stock_name = stock_name.strip()
            origin_order_num = self.dynamicCall('GetChejanData(int)',
                                                 self.realType.REALTYPE['주문체결']['원주문번호'])
            order_number = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['주문번호'])
            order_status = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['주문상태'])
            order_quan = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['주문수량'])
            order_quan = int(order_quan)

            order_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['주문가격'])
            order_price = int(order_price)

            not_chegual_quan = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['미체결수량'])
            not_chegual_quan = int(not_chegual_quan)

            order_gubun = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['주문구분']) # 출력: -매도, +매수
            order_gubun = order_gubun.strip().lstrip('+').lstrip('-')

            chegual_time_str = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['주문/체결시간'])

            chegual_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['체결가'])
            if chegual_price == '':
                chegual_price = 0
            else:
                chegual_price = int(chegual_price)

            chegual_quantity = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['체결량'])
            if chegual_quantity == '':
                chegual_quantity = 0
            else:
                chegual_quantity = int(chegual_quantity)

            current_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['현재가'])
            if current_price == "":
               current_price = "0"  # 기본값 설정
            current_price = abs(int(current_price))

            first_sell_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['(최우선)매도호가'])
            first_sell_price = abs(int(first_sell_price))

            first_buy_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['주문체결']['(최우선)매수호가'])
            first_buy_price = abs(int(first_buy_price))

            # 새로 들어온 주문이면 주문번호 할당
            if order_number  not in self.not_account_stock_dict.keys():
                self.not_account_stock_dict.update({order_number: {}})

            self.not_account_stock_dict[order_number].update({'종목코드': sCode})
            self.not_account_stock_dict[order_number].update({'주문번호': order_number})
            self.not_account_stock_dict[order_number].update({'종목명': stock_name})
            self.not_account_stock_dict[order_number].update({'주문상태': order_status})
            self.not_account_stock_dict[order_number].update({'주문수량': order_quan})
            self.not_account_stock_dict[order_number].update({'주문가격': order_price})
            self.not_account_stock_dict[order_number].update({'미체결수량': not_chegual_quan})
            self.not_account_stock_dict[order_number].update({'원주문번호': origin_order_num})
            self.not_account_stock_dict[order_number].update({'주문번호': order_gubun})
            self.not_account_stock_dict[order_number].update({'주문/체결시간': chegual_time_str})
            self.not_account_stock_dict[order_number].update({'체결가': chegual_price})
            self.not_account_stock_dict[order_number].update({'체결량': chegual_quantity})
            self.not_account_stock_dict[order_number].update({'현재가': current_price})
            self.not_account_stock_dict[order_number].update({'(최우선)매도호가': first_sell_price})
            self.not_account_stock_dict[order_number].update({'(최우선)매수호가': first_buy_price})

            # print(self.not_account_stock_dict)
            
        elif int(sGubun) == 1:

            account_num = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['계좌번호'])
            sCode = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['종목코드'])[1:]
            stock_name = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['종목명'])
            stock_name = stock_name.strip()

            current_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['현재가'])
            current_price = abs(int(current_price))

            stock_quan = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['보유수량'])
            stock_quan = int(stock_quan)

            like_quan = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['주문가능수량'])
            like_quan = int(like_quan)

            buy_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['매입단가'])
            buy_price = abs(int(buy_price))

            total_buy_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['총매입가'])
            total_buy_price = abs(int(total_buy_price))

            meme_gubun = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['매도매수구분'])
            meme_gubun = self.realType.REALTYPE['매도수구분'][meme_gubun]

            first_sell_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['(최우선)매도호가'])
            first_sell_price = abs(int(first_sell_price))
            
            first_buy_price = self.dynamicCall('GetChejanData(int)', self.realType.REALTYPE['잔고']['(최우선)매수호가'])
            first_buy_price = abs(int(first_buy_price))

            if sCode not in self.jango_dict.keys():
                self.jango_dict.update({sCode:{}})

            self.jango_dict[sCode].update({'현재가': current_price})
            self.jango_dict[sCode].update({'종목코드': sCode})
            self.jango_dict[sCode].update({'종목명': stock_name})
            self.jango_dict[sCode].update({'보유수량': like_quan})
            self.jango_dict[sCode].update({'주문가능수량': buy_price})
            self.jango_dict[sCode].update({'매입단가': total_buy_price})
            self.jango_dict[sCode].update({'매도매수구분': meme_gubun})
            self.jango_dict[sCode].update({'(최우선)매도호가': first_sell_price})
            self.jango_dict[sCode].update({'(최우선)매수호가': first_buy_price})

            if stock_quan == 0:
                del self.jango_dict[sCode]
                self.dynamicCall('SetRealRemove(QString, QString)', self.portfolio_stock_dict[sCode]['스크린번호'], sCode)

            self.detail_account_info() # 예수금 가져오기
            self.detail_account_mystock() # 계좌평가잔고내역
            self.not_concluded_account() # 미체결 요청
            self.screen_number_setting() # 스크린 번호를 할당
                

    
    # 장 시작유무를 확인한다.
    # 키움증권 서버에 나의 포트롤리오 주식정보를(주식코드)를 등록하여, 서버가 실시간으로 변화를 책크하여
    # 변화가 감지되면(즉,누군가가 거래를 하면), 즉시, 틱 정보를 클라이언트(자동매매프로그램)에 보내오고,
    # 매매로직에 근거하여 매수 / 매도를 결정한다.
    def realdata_slot(self, sCode, sRealType, sRealData):
        # 장 시작유무를 확인한다.
        if sRealType == '장시시작시간':
            fid = self.realType.REALTYPE[sRealType]['장운영구분']
            value = self.dynamicCall('GetCommRealData(QString, int)', sCode, fid)
            if value == '0':
                self.logging.info('장 시작 전')
            elif value == '3':
                self.logging.info('장 시작')
            elif value == '2':
                self.logging.info('장 종료, 동시호가로 넘어감')
            elif value == '4':
                self.logging.info('3시30분 장 종료')
                for code in self.portfolio_stock_dict.keys():
                    self.dynamicCall(
                        'SetRealRemove(QString, QString)', self.portfolio_stock_dict[code]['스크린번호'], code
                    )
                    QTest.qWait(5000)
                self.file_delete()
                self.calculator_fnc()
                sys.exit()

        # 키움서버에서 매매==거래(타인들..)가 발생하여       
        # 키움서버에서 보내온 틱정보를 근거로 필요한 기초 정보를 축출한다.
        elif sRealType == '주식체결':
            a = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['체결시간']) # HHMMSS
            b = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['현재가'])   # +(-) 2500
            b = abs(int(b))
            c = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['전일대비']) # 출력 : +(-)50
            c = abs(int(c))
            d = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['등락율']) # 출력 : +(-)12.23
            d = float(d)
            e = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['(최우선)매도호가'])
            e = abs(int(e))
            f = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['(최우선)매수호가'])
            f = abs(int(f))
            g = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['거래량']) # (틱봉에 있는 거래량) == 왜냐하면 틱데이타 변화를 반영하는거니까
            g = abs(int(g))
            h = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['누적거래량']) # 합계 거래량
            h = abs(int(h))
            i = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['고가']) # 오늘 고가
            i = abs(int(i))
            j = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['시가'])
            j = abs(int(j))
            k = self.dynamicCall('GetCommRealData(QString, int)', sCode, self.realType.REALTYPE[sRealType]['저가'])
            k = abs(int(k))

            if sCode not in self.portfolio_stock_dict:
                self.portfolio_stock_dict.update({sCode:{}})
            self.portfolio_stock_dict[sCode].update({'체결시간': a})
            self.portfolio_stock_dict[sCode].update({'현재가': b})
            self.portfolio_stock_dict[sCode].update({'전일대비': c})
            self.portfolio_stock_dict[sCode].update({'등락율': d})
            self.portfolio_stock_dict[sCode].update({'(최우선)매도호가': e})
            self.portfolio_stock_dict[sCode].update({'(최우선)매수호가': f})
            self.portfolio_stock_dict[sCode].update({'거래량': g})
            self.portfolio_stock_dict[sCode].update({'누적거래량': h})
            self.portfolio_stock_dict[sCode].update({'고가': i})
            self.portfolio_stock_dict[sCode].update({'시가': j})
            self.portfolio_stock_dict[sCode].update({'저가': k})
            # print(self.portfolio_stock_dict[sCode])

            # 신규매도 / 신규매수를 결정하는 즉, 매수 할거냐 매도 할거냐를 결정하고 주문을 낸다.
            # 계좌잔고평가내역에 있고 오늘 산 잔고에는 없을 경우 ==== 
        
            if sCode in self.account_stock_dict.keys() and sCode not in self.jango_dict.keys():
                asd = self.account_stock_dict[sCode]
                meme_rate = (b - asd['매입가']) / asd['매입가'] * 100
                
                if asd['매매가능수량'] > 0 and (meme_rate > 5 or meme_rate < -5):
                    order_success = self.dynamicCall('SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)',
                                    ['신규매도', self.portfolio_stock_dict[sCode]['주문용스크린번호'], self.account_num, 2,
                                    sCode, asd['보유수량'], 0, self.realType.SENDTYPE['거래구분']['시장가'],''])
                    
                    if order_success == 0:
                        self.logging.info(f"주문 성공: {sCode}, 매입가: {asd['매입가']}, 보유수량: {asd['보유수량']}, 수익률: {meme_rate}%")
                        del self.account_stock_dict[sCode]
                    else:
                        self.logging.info(f"주문 실패: {sCode}, 오류 코드: {order_success}")

                # 오늘 산 잔고에 있을 경우
            elif sCode in self.jango_dict.keys():
                jd = self.jango_dict[sCode]
                meme_rate = (b - jd['매입단가']) / jd['매입단가'] * 100
                if jd['주문가능수량'] > 0 and (meme_rate > 5 or meme_rate < -5):
                    order_success = self.dynamicCall(
                        'SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)',
                        ['신규매도',self.portfolio_stock_dict[sCode]['주문용스크린번호'], self.account_num, 2, sCode, jd['보유수량'],
                         0, self.realType.SENDTYPE['거래구분']['시장가'],'']
                    )   
                    if order_success == 0:
                        self.logging.info(f"주문 성공: {sCode}, 보유수량: {jd['보유수량']}, 수익률: {meme_rate}%")
                    else:
                        self.logging.info(f"주문 실패: {sCode}, 오류 코드: {order_success}")

            # 등락율이 2.0% 이상이고 오늘 산 잔고액에 없을 경우
            elif e > 0 and (1.0 <= d <= 2.0) and sCode not in self.account_stock_dict.keys() and sCode in self.portfolio_stock_dict.keys():
                result = (self.use_money * 0.1) / e
                quantity = int(result)
                order_success = self.dynamicCall(
                    'SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)',
                    ['신규매수', self.portfolio_stock_dict[sCode]['주문용스크린번호'], self.account_num, 1, sCode, quantity, e, self.realType.SENDTYPE['거래구분']['지정가'], '']
                )
                if order_success == 0:
                    self.logging.info('매수주문 전달 성공')
                else:
                    self.logging.info('매수주문 전달 실패')


            not_meme_list = list(self.not_account_stock_dict.keys())
            for order_num in not_meme_list:
                code = self.not_account_stock_dict[order_num]['종목코드']
                meme_price = self.not_account_stock_dict[order_num]['주문가격']
                not_quantity = self.not_account_stock_dict[order_num]['미체결수량']
                # order_gubun = self.not_account_stock_dict[order_num]['주문구분']
                order_gubun = '신규매수'

                if order_gubun == '신규매수' and not_quantity > 0 and e > meme_price:
                    
                    order_success = self.dynamicCall(
                        'SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)',
                        ['매수취소', self.portfolio_stock_dict[sCode]['주문용스크린번호'], self.account_num, 3, code, 0, 0,
                         self.realType.SENDTYPE['거래구분']['지정가'], order_num]
                    )
                    if order_success == 0:
                        self.logging.info('매수취소 전달 성공')
                    else:
                        self.logging.info('매수취소 전달 실패')

                elif not_quantity == 0:
                    del self.not_account_stock_dict[order_num]