import sys
import pandas as pd

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt, QAbstractTableModel
from PyQt5 import uic

form_class = uic.loadUiType("main.ui")[0]

class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent = None):
        return self._data.shape[0]
    
    def columnCount(self, parent = None):
        return self._data.shape[1]
    
    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return str(self._data.iloc[index.row(),index.column()])
            return None
    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._data.columns[section]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return self._data.index[section]
        return None
    
    def setData(self, index, value, role):
        return False
    
    def flags(self, index):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

class QtDesignerExample(QMainWindow, form_class):
    def __init__(self):
        super().__init__()    
        self.setupUi(self)
        self.show()

        self.myPushButton.clicked.connect(self.button_clicked)
    def button_clicked(self):
        self.myLabel.setText("button_clicked!")
        self.myLineEdit.setText("2024-05-18")
        self.myComboBox.addItems(["2024-05-18"," 2024-05-17", "2024-05-16"])    
        sample_df = pd.DataFrame({"A":[1, 2, 3], "B":[4, 5, 6], "C":[7, 8, 9]})
        pd_model = PandasModel(sample_df)
        self.myTableView.setModel(pd_model)
        print(self.myLabel.text())
        print(self.myLineEdit.text())
        print(self.myComboBox.currentText())
if __name__ == "__main__":
    app = QApplication(sys.argv)
    qt_designer_example = QtDesignerExample()
    sys.exit(app.exec_())            