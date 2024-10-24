from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop

class KiwoomAPI:
    def __init__(self):
        self.app = QApplication([])
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

        self.login_event_loop = QEventLoop()
        self.condition_event_loop = QEventLoop()

        self.condition_list = None  # 조건식 목록 저장할 변수
        self.data = []

        self.ocx.OnEventConnect.connect(self._event_connect)

        self.ocx.OnReceiveConditionVer.connect(self._receive_condition_ver)
        self.ocx.OnReceiveTrCondition.connect(self._receive_tr_condition)
        self.ocx.OnReceiveRealCondition.connect(self._receive_real_condition)

        self.ocx.OnReceiveTrData.connect(self._receive_tr_data)
        self.login()
        
    def login(self):
        self.ocx.dynamicCall("CommConnect()")
        self.login_event_loop.exec_()

    def _event_connect(self, err_code):
        if err_code == 0:
            print("로그인 성공")
        else:
            print("로그인 실패")
        self.login_event_loop.exit()

    def get_condition_list(self):
        print("조건식을 불러옵니다...")
        ret = self.ocx.dynamicCall("GetConditionLoad()")
        print(f"GetConditionLoad() 호출 결과: {ret}")
        self.condition_event_loop.exec_()  # 이벤트 대기
        return self.condition_list  # 조건식 목록 반환

    def _receive_condition_ver(self, ret, msg):
        print(f"_receive_condition_ver 호출됨: ret={ret}, msg={msg}")
        if ret == 1:
            conditions = self.ocx.dynamicCall("GetConditionNameList()")
            self.condition_list = conditions.split(';')[:-1]  # 마지막 빈 값 제외
            print(f"받은 조건식 목록: {self.condition_list}")
        else:
            print(f"조건식 리스트 가져오기 실패: {msg}")
        self.condition_event_loop.exit()

    def send_condition(self, screen_no, condition_name, condition_index, is_real_time):
        print(f"조건식 실행: {condition_name} (인덱스: {condition_index})")
        self.ocx.dynamicCall("SendCondition(QString, QString, int, int)", screen_no, condition_name, condition_index, is_real_time)

    def _receive_tr_condition(self, screen_no, code_list, condition_name, index, next):
        codes = code_list.split(';')[:-1]  # 마지막이 빈 값이므로 제외
        for code in codes:
            print(f"종목코드: {code}")
            self.data.append(code)
            self.get_stock_info(code)

    def _receive_real_condition(self, code, event_type, condition_name, condition_index):
        print(f"실시간 조건 변경 - 종목코드: {code}, 이벤트 타입: {event_type}, 조건명: {condition_name}, 인덱스: {condition_index}")
        if event_type == 'I':
            self.data.append(code)

    def get_stock_info(self, code):
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", "주식기본정보요청", "opt10001", 0, "0101")

    def _receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next):
        if rqname == "주식기본정보요청":
            name = self.ocx.dynamicCall("CommGetData(QString, QString, QString, int, QString)", trcode, "", recordname, 0, "종목명")
            price = self.ocx.dynamicCall("CommGetData(QString, QString, QString, int, QString)", trcode, "", recordname, 0, "현재가")
            print(f"종목명: {name.strip()}, 현재가: {price.strip()}")


if __name__ == "__main__":
    kiwoom = KiwoomAPI()

    # 조건식 목록 가져오기
    condition_list = kiwoom.get_condition_list()
    
    if condition_list:
        print("조건식 목록:", condition_list)
        # 조건검색식을 사용해 종목 조회 (예시: 두 번째 조건식 사용)
        condition_index, condition_name = condition_list[1].split('^')
        print(condition_name,condition_index)
        kiwoom.send_condition("0101", condition_name, int(condition_index), 1)  # 실시간 조회를 원하지 않으면 0, 실시간 조회를 원하면 1
    else:
        print("조건식이 없습니다. HTS에서 조건식을 등록했는지 확인하세요.")
    # PyQt 이벤트 루프 실행
    kiwoom.app.exec_()
