import os 
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import copy
import sys
from collections import deque
from queue import Queue
import datetime

from loguru import logger
import pandas as pd
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import Qt, QSettings, QTimer, QAbstractTableModel
from PyQt5 import QtGui, uic
form_class = uic.loadUiType("main.ui")[0]
class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data
    
    def rowCount(self, parent = None):
        return self._data.shape[0]
    
    def columnCount(self, parent=None):
        return self._data.shape[1]
    
    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
            return None

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._data.columns[section]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return self._data.index[section]
        return None

    def setData(self, index, value, role):
        # 항상 False를 반환하여 편집을 비활성화
        return False

    def flags(self, index):
        return Qt.ItemIsEditTable | Qt.ItemIsEnabled | Qt.ItemIsSelecttable

class KiwoomAPI(QMainWindow, form_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.show()

        self.conditionInPushButton.clicked.connect(self.condition_in)
        self.conditionOuputPushButton.clicked.connect(self.condition_out)
        self.settings = QSettings('MyAPP','myApp')
        self.load_settings()
        self.setWindowIcon(QtGui.QIcon('icon.ico'))

        self.max_send_per_sec: int = 4 # 초당 TR 호출 최대 4번
        self.max_send_per_minute: int = 55 # 분당 TR 호출 최대 55번
        self.max_send_per_hour: int = 950 # 시간당 TR 호출 최대 950번
        self.last_tr_send_times = deque(maxlen=self.max_send_per_hour)
        self.tr_req_queue = Queue()
        self.orders_queue = Queue()
        self.unfinished_order_num_to_info_dict = dict()
        self.stock_code_to_info_dict = dict()
        self.scrnum = 5000
        self.condition_name_to_condition_idx_dict = dict()
        self.registered_condition_df = pd.DataFrame(columns=["화면번","조건식이름"])
        self.registered_conditions_list = []
        self.account_info_df = pd.DataFrame(
            columns=[
                "종목명",
                "매매가능수량",
                "보유수량",
                "매입가",
                "현재가",
                "수익률",
                
            ]
        )
    def _get_screen_num(self):
        self.scrnum += 1
        if self.scrnum > 5190:
            self.scrnum = 5000
            return str(self.scrnum)
    def send_condition(self, scr_num, condition_name, condition_idx, n_search):
        # n_search: 조회구분, 0:조건검색식, 1:실시간 조건검색식
        result = self.kiwoom.dynamicCall(
            "SendCondition(QString, QString, int, int)",
            scr_num, condition_name, condition_idx, n_search
        )
        if result == 1:
            logger.info(f"{condition_name} 조건검색 등록!")
            self.registered_condition_df.loc[condition_idx] = {"화면번호":scr_num, "조건식이름":condition_name}
            self.registered_condition_list.append(condition_name)
        elif result != 1 and condition_name in self.registered_conditions_list:
            logger.info(f"{condition_name} 조건검색 이미 등록 완료!")
            self.registered_condition_df.loc[condition_idx] = {"화면번호":scr_num, "조건식이름":condition_name}
        else:
            logger.info(f"{condition_name} 조건검색 등록 실패!")
    
    def _receive_real_condition(self, strCode, strType, strConditionName, strConditionIndex):
        # strType: 이벤트 종류, "I":종목편입, "D": 종목이탈
        # strConditionName: 조건식 이름
        # strConditionIndex: 조건명 인덱스
