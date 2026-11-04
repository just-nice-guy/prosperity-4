import pandas as pd
from matplotlib import pyplot as plt
import numpy as np

prices_2=pd.read_csv('../../../Stage1/Round1/prices_round_1_day_-2.csv',delimiter=";")
trades_2=pd.read_csv('../../../Stage1/Round1/trades_round_1_day_-2.csv',delimiter=";")

prices_1=pd.read_csv('../../../Stage1/Round1/prices_round_1_day_-1.csv',delimiter=";")
trades_1=pd.read_csv('../../../Stage1/Round1/trades_round_1_day_-1.csv',delimiter=";")
prices_1['timestamp']+=prices_2['timestamp'].max()+100
trades_1['timestamp']+=prices_2['timestamp'].max()+100

prices_0=pd.read_csv('../../../Stage1/Round1/prices_round_1_day_0.csv',delimiter=";")
trades_0=pd.read_csv('../../../Stage1/Round1/trades_round_1_day_0.csv',delimiter=";")
prices_0['timestamp']+=prices_1['timestamp'].max()+100
trades_0['timestamp']+=prices_1['timestamp'].max()+100


prices=pd.concat([prices_2, prices_1, prices_0])
trades=pd.concat([trades_2, trades_1, trades_0])

prices[prices['mid_price']==0.0]=np.nan

prices=prices[prices['product']=="ASH_COATED_OSMIUM"]
trades=trades[trades['symbol']=="ASH_COATED_OSMIUM"]

merged = pd.merge(prices, trades, on="timestamp", how="outer")

remove = ['buyer','seller','symbol','currency','product','profit_and_loss','day','mid_price']
for i in remove:
    del merged[i]
