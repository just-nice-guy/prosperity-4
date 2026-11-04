from ob import merged
import numpy as np


#PB defois similaire vers le bas et non vers le haut
def ob_diff(row):
    diff=[]
    b_count=0
    a_count=0
    for i in range(3,0,-1):
        bid=row[f'bid_volume_{i}']
        ask=row[f'ask_volume_{i}']
        if not np.isnan(bid):
            b_count+=1
            if len(diff) < b_count:
                diff.append(bid)
            else:
                diff[b_count-1]+=bid
        if not np.isnan(ask):
            a_count+=1
            if len(diff) < a_count:
                diff.append(-ask)
            else:
                diff[a_count-1]-=ask
    return diff

def micro_price_corrected(row):
    diff=[]
    difu=[]
    b_count=0
    a_count=0
    best=[]
    for i in range(3,0,-1):
        bid=[row[f'bid_price_{i}'],row[f'bid_volume_{i}']]
        ask=[row[f'ask_price_{i}'],row[f'ask_volume_{i}']]
        if not np.isnan(bid[1]):
            b_count+=1
            if len(diff) < b_count:
                diff.append(bid[1])
                difu.append([bid])
            else:
                diff[b_count-1]+=bid[1]
                difu[b_count-1].append(bid)
        if not np.isnan(ask[1]):
            a_count+=1
            if len(diff) < a_count:
                diff.append(-ask[1])
                difu.append([ask])
            else:
                diff[a_count-1]-=ask[1]
                difu[a_count-1].append(ask)
    mi=None
    for i in range(len(diff)):
        if diff[i]==0:
            mi=i
    return (difu[mi][0][0]+difu[mi][1][0])/2

#faudra garder tmp celui d'vaant au moin si non mettre celui d'avant
#ffill apres 30% None

def micro_price_corrected_row(row):
    diff = []
    difu = []
    b_count = 0
    a_count = 0

    for i in range(3, 0, -1):
        bid = [row[f'bid_price_{i}'], row[f'bid_volume_{i}']]
        ask = [row[f'ask_price_{i}'], row[f'ask_volume_{i}']]

        if not np.isnan(bid[1]):
            b_count += 1
            if len(diff) < b_count:
                diff.append(bid[1])
                difu.append([bid])
            else:
                diff[b_count - 1] += bid[1]
                difu[b_count - 1].append(bid)

        if not np.isnan(ask[1]):
            a_count += 1
            if len(diff) < a_count:
                diff.append(-ask[1])
                difu.append([ask])
            else:
                diff[a_count - 1] -= ask[1]
                difu[a_count - 1].append(ask)

    mi = None
    for i in range(len(diff)):
        if diff[i] == 0:
            mi = i

    if mi is None or len(difu[mi]) < 2:
        return np.nan

    return (difu[mi][0][0] + difu[mi][1][0]) / 2


def micro_price_corrected_df(df):
    return df.apply(micro_price_corrected_row, axis=1)








def ob_diff2(row):
    diff=[]
    b_count=0
    a_count=0
    for i in range(1,3+1,1):
        bid=row[f'bid_volume_{i}']
        ask=row[f'ask_volume_{i}']
        if not np.isnan(bid):
            b_count+=1
            if len(diff) < b_count:
                diff.append(bid)
            else:
                diff[b_count-1]+=bid
        if not np.isnan(ask):
            a_count+=1
            if len(diff) < a_count:
                diff.append(-ask)
            else:
                diff[a_count-1]-=ask
    return diff
