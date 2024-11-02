def _buy_check( cost):
    money = 0
    buy_money = 0
    if self.data_cnt >= self.max_buy_cnt:
        return 0
    
    if self.buy_balance >= self.balance:
        return 0
    
    if self.buy_balance == 0:
        buy_money = self.balance * 0.5
        buy_money = int(buy_money / 4)
        return int(buy_money / cost) / 2
    else:
        buy_money = self.balance - self.buy_balance
        if buy_money >= cost:
            return int(buy_money / cost) / 2
        else:
            return 0