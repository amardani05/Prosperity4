import matplotlib
matplotlib.use('Agg')  # no GUI needed, saves to file
import matplotlib.pyplot as plt
import pandas as pd

prices_d1 = pd.read_csv('training_capsule/prices_round_0_day_-1.csv', sep=';')
trades_d1 = pd.read_csv('training_capsule/trades_round_0_day_-1.csv', sep=';')

tomatoes_prices_d1 = prices_d1[prices_d1['product'] == 'TOMATOES'].reset_index(drop=True)
tomatoes_trades_d1 = trades_d1[trades_d1['symbol'] == 'TOMATOES'].reset_index(drop=True)

# Merge trades with nearest price timestamp
combined = pd.merge_asof(
    tomatoes_trades_d1.sort_values('timestamp'),
    tomatoes_prices_d1[['timestamp', 'mid_price']].sort_values('timestamp'),
    on='timestamp'
)
combined['side'] = (combined['price'] - combined['mid_price']).apply(lambda x: 1 if x > 0 else -1)
combined['cumflow'] = combined['side'].cumsum()

# Plot trade flow vs mid price
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
ax1.plot(tomatoes_prices_d1['timestamp'].values, tomatoes_prices_d1['mid_price'].values, linewidth=0.8)
ax1.set_title('TOMATOES Mid Price')
ax2.plot(combined['timestamp'].values, combined['cumflow'].values, linewidth=0.8, color='orange')
ax2.set_title('Cumulative Trade Flow (buy - sell)')
ax2.set_xlabel('Timestamp')
plt.tight_layout()
plt.savefig('trade_flow.png')
print('Saved trade_flow.png')

# Spread signal analysis
tomatoes_prices_d1['spread'] = tomatoes_prices_d1['ask_price_1'] - tomatoes_prices_d1['bid_price_1']
for n in [1, 5, 10, 20]:
    tomatoes_prices_d1[f'abs_change_{n}'] = (tomatoes_prices_d1['mid_price'].shift(-n) - tomatoes_prices_d1['mid_price']).abs()
    corr = tomatoes_prices_d1['spread'].corr(tomatoes_prices_d1[f'abs_change_{n}'])
    print(f'Spread vs abs_change_{n}: {corr:.4f}')

combined_flow = pd.merge_asof(
    tomatoes_prices_d1[['timestamp', 'mid_price']].sort_values('timestamp'),
    combined[['timestamp', 'cumflow']].sort_values('timestamp'),
    on='timestamp'
)
combined_flow['cumflow'] = combined_flow['cumflow'].ffill().fillna(0)

for n in [1, 5, 10, 20, 50]:
    combined_flow[f'price_change_{n}'] = combined_flow['mid_price'].shift(-n) - combined_flow['mid_price']
    corr = combined_flow['cumflow'].corr(combined_flow[f'price_change_{n}'])
    print(f'Cumflow vs price_change_{n}: {corr:.4f}')