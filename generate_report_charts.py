import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Set style for professional look
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
plt.rcParams['axes.edgecolor'] = '#cccccc'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['savefig.dpi'] = 300

# 1. Profitability: ROE and ROA comparison
data_profitability = {
    'Bank': ['JPMorgan Chase', 'Goldman Sachs', 'Morgan Stanley', 'Bank of America', 'Citigroup'],
    'ROE (%)': [15.0, 11.2, 12.5, 9.8, 4.3],
    'ROA (%)': [1.25, 0.95, 1.05, 0.85, 0.38]
}
df_profit = pd.DataFrame(data_profitability)

fig, ax1 = plt.subplots(figsize=(10, 6))
color = '#1f77b4'
ax1.set_xlabel('Bank', fontweight='bold', labelpad=10)
ax1.set_ylabel('Return on Equity (ROE) %', color=color, fontweight='bold')
bars = ax1.bar(df_profit['Bank'], df_profit['ROE (%)'], color=color, alpha=0.7, width=0.4, label='ROE')
ax1.tick_params(axis='y', labelcolor=color)
ax1.set_ylim(0, 18)

# Add values on top of bars
for bar in bars:
    height = bar.get_height()
    ax1.annotate(f'{height:.1f}%',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),  # 3 points vertical offset
                textcoords="offset points",
                ha='center', va='bottom', fontsize=9, fontweight='bold')

ax2 = ax1.twinx()  
color = '#ff7f0e'
ax2.set_ylabel('Return on Assets (ROA) %', color=color, fontweight='bold')
line = ax2.plot(df_profit['Bank'], df_profit['ROA (%)'], color=color, marker='o', linewidth=2.5, label='ROA')
ax2.tick_params(axis='y', labelcolor=color)
ax2.set_ylim(0, 1.6)

# Add values on line
for i, txt in enumerate(df_profit['ROA (%)']):
    ax2.annotate(f'{txt:.2f}%', (df_profit['Bank'][i], df_profit['ROA (%)'][i]), textcoords="offset points", xytext=(0,10), ha='center', fontweight='bold', fontsize=9, color='#d35400')

plt.title('Profitability Comparison (ROE vs. ROA) - FY 2025', fontsize=14, fontweight='bold', pad=15)
fig.tight_layout()
plt.savefig('profitability_comparison.png', dpi=300)
plt.close()

# 2. Capital Adequacy: Common Equity Tier 1 (CET1) Ratio
data_adequacy = {
    'Bank': ['JPMorgan Chase', 'Goldman Sachs', 'Morgan Stanley', 'Bank of America', 'Citigroup'],
    'CET1 Ratio (%)': [15.0, 13.9, 15.2, 11.8, 13.7],
    'Regulatory Minimum (%)': [4.5, 4.5, 4.5, 4.5, 4.5]
}
df_adequacy = pd.DataFrame(data_adequacy)

plt.figure(figsize=(10, 6))
colors = ['#2c3e50', '#18bc9c', '#3498db', '#e74c3c', '#f39c12']
bars = plt.bar(df_adequacy['Bank'], df_adequacy['CET1 Ratio (%)'], color=colors, alpha=0.85, width=0.5)
plt.axhline(y=4.5, color='red', linestyle='--', linewidth=1.5, label='Regulatory Minimum (4.5%)')
plt.axhline(y=11.5, color='green', linestyle=':', linewidth=1.5, label='Typical Basel III Target (with buffers)')

for bar in bars:
    height = bar.get_height()
    plt.annotate(f'{height:.1f}%',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha='center', va='bottom', fontsize=10, fontweight='bold')

plt.ylabel('CET1 Ratio (%)', fontweight='bold', fontsize=11)
plt.title('Capital Adequacy: Common Equity Tier 1 (CET1) Ratios', fontsize=14, fontweight='bold', pad=15)
plt.ylim(0, 18)
plt.legend(loc='lower right')
plt.tight_layout()
plt.savefig('capital_adequacy_cet1.png', dpi=300)
plt.close()

# 3. Size and Scale: Total Assets (in Trillions USD)
data_assets = {
    'Bank': ['JPMorgan Chase', 'Goldman Sachs', 'Morgan Stanley', 'Bank of America', 'Citigroup'],
    'Total Assets ($ Trillions)': [3.9, 1.7, 1.2, 3.2, 2.4]
}
df_assets = pd.DataFrame(data_assets)

plt.figure(figsize=(10, 6))
bars = plt.barh(df_assets['Bank'], df_assets['Total Assets ($ Trillions)'], color='#34495e', alpha=0.85, height=0.5)

for bar in bars:
    width = bar.get_width()
    plt.annotate(f'${width:.1f}T',
                xy=(width, bar.get_y() + bar.get_height() / 2),
                xytext=(5, 0),
                textcoords="offset points",
                ha='left', va='center', fontsize=10, fontweight='bold')

plt.xlabel('Total Assets ($ in Trillions)', fontweight='bold', fontsize=11)
plt.title('Size and Scale: Total Assets (in Trillions USD)', fontsize=14, fontweight='bold', pad=15)
plt.xlim(0, 4.5)
plt.gca().invert_yaxis()  # top-down
plt.tight_layout()
plt.savefig('total_assets_comparison.png', dpi=300)
plt.close()

print("Charts successfully generated!")
